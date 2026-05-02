#!/usr/bin/env python3
"""Plot commanded vs measured servo angles and tracking error from a telemetry capture."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-basic-control-testing")

import matplotlib.pyplot as plt
from matplotlib.widgets import TextBox
import numpy as np

from telemetry_plot_utils import (
    INPUT_FORMAT_CSV,
    INPUT_FORMAT_JSONL,
    detect_input_format,
    find_latest_capture,
    load_designed_arm_hold_samples,
    require_columns,
)


THIS_DIR = Path(__file__).resolve().parent
SERVO_NAMES = ("A", "B", "C")
ANGLE_SPACES = ("relative", "absolute")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        help="Telemetry CSV or Devlink JSONL recording to plot. Defaults to the newest local capture.",
    )
    parser.add_argument(
        "--angle-space",
        choices=ANGLE_SPACES,
        default="relative",
        help="Plot relative servo q angles or absolute linkage angles.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="PNG output path. Defaults to <input_stem>_servo_tracking_<angle-space>.png.",
    )
    parser.add_argument(
        "--t-min",
        type=float,
        help="Initial minimum elapsed time in seconds.",
    )
    parser.add_argument(
        "--t-max",
        type=float,
        help="Initial maximum elapsed time in seconds.",
    )
    parser.add_argument(
        "--show",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Display the plot window after saving.",
    )
    return parser.parse_args()


def default_output_path(input_path: Path, angle_space: str) -> Path:
    filename = f"{input_path.stem}_servo_tracking_{angle_space}.png"
    if input_path.parent == THIS_DIR:
        return input_path.with_name(filename)
    return THIS_DIR / filename


def commanded_column(servo_name: str, angle_space: str) -> str:
    servo_id = servo_name.lower()
    if angle_space == "relative":
        return f"cmd_q_{servo_id}_deg"
    return f"cmd_{servo_id}_abs_deg"


def measured_column(servo_name: str, angle_space: str) -> str:
    servo_id = servo_name.lower()
    if angle_space == "relative":
        return f"meas_q_{servo_id}_deg"
    return f"meas_{servo_id}_abs_deg"


def format_time_value(value: float) -> str:
    return f"{value:.3f}"


def resolve_time_window(
    elapsed_s: list[float],
    t_min: float | None,
    t_max: float | None,
) -> tuple[float, float]:
    if not elapsed_s:
        raise ValueError("Telemetry capture has no elapsed time samples.")

    full_min = float(elapsed_s[0])
    full_max = float(elapsed_s[-1])
    resolved_min = full_min if t_min is None else float(t_min)
    resolved_max = full_max if t_max is None else float(t_max)

    if resolved_max <= resolved_min:
        raise ValueError("--t-max must be greater than --t-min.")

    return resolved_min, resolved_max


def slice_for_time_window(elapsed_s: np.ndarray, t_min: float, t_max: float) -> slice:
    left = int(np.searchsorted(elapsed_s, t_min, side="left"))
    right = int(np.searchsorted(elapsed_s, t_max, side="right"))

    if left == right:
        nearest = int(np.clip(left, 0, len(elapsed_s) - 1))
        left = max(0, nearest - 1)
        right = min(len(elapsed_s), left + 1)

    left = max(0, min(left, len(elapsed_s) - 1))
    right = max(left + 1, min(right, len(elapsed_s)))
    return slice(left, right)


def padded_limits(values: np.ndarray, *, include_zero: bool = False) -> tuple[float, float]:
    data = np.asarray(values, dtype=float)
    if include_zero:
        data = np.concatenate((data, np.array([0.0], dtype=float)))

    minimum = float(np.min(data))
    maximum = float(np.max(data))
    if np.isclose(minimum, maximum):
        padding = max(abs(minimum) * 0.05, 0.5)
    else:
        padding = (maximum - minimum) * 0.08
    return minimum - padding, maximum + padding


def load_csv_tracking_data(
    csv_path: Path,
    angle_space: str,
) -> tuple[str, str, list[float], dict[str, dict[str, list[float]]]]:
    required_columns = ["time_us"]
    for servo_name in SERVO_NAMES:
        required_columns.append(commanded_column(servo_name, angle_space))
        required_columns.append(measured_column(servo_name, angle_space))

    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        require_columns(reader.fieldnames, required_columns, csv_path)

        rows = list(reader)

    if not rows:
        raise ValueError(f"{csv_path} has no telemetry rows.")

    elapsed_s: list[float] = []
    series = {
        servo_name: {"commanded": [], "measured": [], "error": []}
        for servo_name in SERVO_NAMES
    }

    start_time_us: float | None = None
    for row_index, row in enumerate(rows, start=2):
        try:
            time_us = float(row["time_us"])
        except ValueError as exc:
            raise ValueError(f"{csv_path}:{row_index} has a non-numeric time_us value.") from exc

        if start_time_us is None:
            start_time_us = time_us
        elapsed_s.append((time_us - start_time_us) / 1_000_000.0)

        for servo_name in SERVO_NAMES:
            cmd_column = commanded_column(servo_name, angle_space)
            meas_column = measured_column(servo_name, angle_space)
            try:
                commanded = float(row[cmd_column])
                measured = float(row[meas_column])
            except ValueError as exc:
                raise ValueError(
                    f"{csv_path}:{row_index} has a non-numeric value in {cmd_column} or {meas_column}."
                ) from exc

            series[servo_name]["commanded"].append(commanded)
            series[servo_name]["measured"].append(measured)
            series[servo_name]["error"].append(measured - commanded)

    return "Basic Leg", f"{angle_space.title()} Angles", elapsed_s, series


def load_jsonl_tracking_data(
    jsonl_path: Path,
    angle_space: str,
) -> tuple[str, str, list[float], dict[str, dict[str, list[float]]]]:
    if angle_space != "relative":
        raise ValueError(
            f"{jsonl_path} only contains raw hold angles for servo tracking. Use --angle-space relative."
        )

    samples = load_designed_arm_hold_samples(jsonl_path)
    start_time_us = samples[0].time_us
    elapsed_s = [(sample.time_us - start_time_us) / 1_000_000.0 for sample in samples]
    series = {
        servo_name: {"commanded": [], "measured": [], "error": []}
        for servo_name in SERVO_NAMES
    }

    for sample in samples:
        for servo_name in SERVO_NAMES:
            commanded = sample.target_deg[servo_name]
            measured = sample.actual_deg[servo_name]
            series[servo_name]["commanded"].append(commanded)
            series[servo_name]["measured"].append(measured)
            series[servo_name]["error"].append(measured - commanded)

    return "Designed Arm", "Hold Angles", elapsed_s, series


def load_tracking_data(
    input_path: Path,
    angle_space: str,
) -> tuple[str, str, list[float], dict[str, dict[str, list[float]]]]:
    input_format = detect_input_format(input_path)
    if input_format == INPUT_FORMAT_JSONL:
        return load_jsonl_tracking_data(input_path, angle_space)
    if input_format == INPUT_FORMAT_CSV:
        return load_csv_tracking_data(input_path, angle_space)
    raise ValueError(f"Unsupported input format for {input_path}.")


def plot_tracking(
    input_path: Path,
    source_label: str,
    angle_label: str,
    elapsed_s: list[float],
    series: dict[str, dict[str, list[float]]],
    output: Path,
    t_min: float | None,
    t_max: float | None,
    show: bool,
) -> None:
    elapsed = np.asarray(elapsed_s, dtype=float)
    series_arrays = {
        servo_name: {
            metric: np.asarray(values, dtype=float)
            for metric, values in servo_series.items()
        }
        for servo_name, servo_series in series.items()
    }
    initial_t_min, initial_t_max = resolve_time_window(elapsed_s, t_min, t_max)

    figure, axes = plt.subplots(
        2,
        len(SERVO_NAMES),
        figsize=(15.5, 8.5),
        sharex="col",
        gridspec_kw={"height_ratios": (2.3, 1.0)},
        constrained_layout=False,
    )
    figure.subplots_adjust(left=0.06, right=0.985, top=0.90, bottom=0.18, wspace=0.18, hspace=0.18)
    figure.suptitle(
        f"{source_label} Servo Tracking ({angle_label})\n{input_path.name}",
        fontsize=14,
    )

    for axis_index, servo_name in enumerate(SERVO_NAMES):
        top_axis = axes[0, axis_index]
        bottom_axis = axes[1, axis_index]
        commanded = series_arrays[servo_name]["commanded"]
        measured = series_arrays[servo_name]["measured"]
        error = series_arrays[servo_name]["error"]

        top_axis.plot(elapsed_s, commanded, color="tab:blue", linewidth=1.8, label="Commanded")
        top_axis.plot(elapsed_s, measured, color="tab:orange", linewidth=1.6, label="Measured")
        top_axis.set_title(f"Servo {servo_name}")
        top_axis.grid(True, alpha=0.35)
        top_axis.legend(loc="best")
        if axis_index == 0:
            top_axis.set_ylabel("Angle (deg)")

        bottom_axis.plot(elapsed_s, error, color="tab:red", linewidth=1.5)
        bottom_axis.axhline(0.0, color="0.35", linestyle="--", linewidth=1.0)
        bottom_axis.grid(True, alpha=0.35)
        bottom_axis.set_xlabel("Elapsed time (s)")
        if axis_index == 0:
            bottom_axis.set_ylabel("Meas - Cmd (deg)")

    current_limits = {"t_min": initial_t_min, "t_max": initial_t_max}

    def apply_time_window(requested_t_min: float, requested_t_max: float) -> bool:
        clamped_t_min = float(np.clip(requested_t_min, elapsed[0], elapsed[-1]))
        clamped_t_max = float(np.clip(requested_t_max, elapsed[0], elapsed[-1]))
        if clamped_t_max <= clamped_t_min:
            return False

        window = slice_for_time_window(elapsed, clamped_t_min, clamped_t_max)
        current_limits["t_min"] = clamped_t_min
        current_limits["t_max"] = clamped_t_max

        for axis_index, servo_name in enumerate(SERVO_NAMES):
            top_axis = axes[0, axis_index]
            bottom_axis = axes[1, axis_index]
            top_axis.set_xlim(clamped_t_min, clamped_t_max)
            bottom_axis.set_xlim(clamped_t_min, clamped_t_max)

            visible_commanded = series_arrays[servo_name]["commanded"][window]
            visible_measured = series_arrays[servo_name]["measured"][window]
            visible_error = series_arrays[servo_name]["error"][window]

            top_axis.set_ylim(*padded_limits(np.concatenate((visible_commanded, visible_measured))))
            bottom_axis.set_ylim(*padded_limits(visible_error, include_zero=True))

        figure.canvas.draw_idle()
        return True

    apply_time_window(initial_t_min, initial_t_max)
    output.parent.mkdir(parents=True, exist_ok=True)

    if not show:
        figure.savefig(output, dpi=220, bbox_inches="tight")
        plt.close(figure)
        return

    min_axis = figure.add_axes([0.18, 0.06, 0.18, 0.05])
    max_axis = figure.add_axes([0.46, 0.06, 0.18, 0.05])
    min_box = TextBox(min_axis, "t min", initial=format_time_value(current_limits["t_min"]))
    max_box = TextBox(max_axis, "t max", initial=format_time_value(current_limits["t_max"]))
    figure._time_window_widgets = (min_box, max_box)  # type: ignore[attr-defined]

    widget_state = {"syncing": False}

    def sync_boxes() -> None:
        widget_state["syncing"] = True
        min_box.set_val(format_time_value(current_limits["t_min"]))
        max_box.set_val(format_time_value(current_limits["t_max"]))
        widget_state["syncing"] = False

    def submit_min(text: str) -> None:
        if widget_state["syncing"]:
            return
        try:
            requested = float(text)
        except ValueError:
            sync_boxes()
            return
        if not apply_time_window(requested, current_limits["t_max"]):
            sync_boxes()
            return
        sync_boxes()

    def submit_max(text: str) -> None:
        if widget_state["syncing"]:
            return
        try:
            requested = float(text)
        except ValueError:
            sync_boxes()
            return
        if not apply_time_window(current_limits["t_min"], requested):
            sync_boxes()
            return
        sync_boxes()

    min_box.on_submit(submit_min)
    max_box.on_submit(submit_max)

    plt.show()

    min_axis.remove()
    max_axis.remove()
    figure.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(figure)


def main() -> int:
    args = parse_args()
    input_path = args.input_path.resolve() if args.input_path is not None else find_latest_capture(THIS_DIR)
    output = args.output.resolve() if args.output is not None else default_output_path(input_path, args.angle_space)

    try:
        source_label, angle_label, elapsed_s, series = load_tracking_data(input_path, args.angle_space)
        plot_tracking(
            input_path,
            source_label,
            angle_label,
            elapsed_s,
            series,
            output,
            args.t_min,
            args.t_max,
            args.show,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2

    print(f"Saved {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
