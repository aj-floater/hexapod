#!/usr/bin/env python3
"""Plot commanded vs measured end-effector position and tracking error from a telemetry capture."""

from __future__ import annotations

import argparse
import csv
import math
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
REPORT_TOOLS_DIR = THIS_DIR.parent.parent / "docs" / "report" / "tools" / "leg_figures"
AXES = ("x", "y", "z")
DEFAULT_ELEVATION_DEG = 24.0
DEFAULT_AZIMUTH_DEG = -58.0

sys.path.insert(0, str(REPORT_TOOLS_DIR))

from leg_kinematics import end_effector_position  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        help="Telemetry CSV or Devlink JSONL recording to plot. Defaults to the newest local capture.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="PNG output path. Defaults to <input_stem>_end_effector_tracking_3d.png.",
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


def default_output_path(input_path: Path) -> Path:
    filename = f"{input_path.stem}_end_effector_tracking_3d.png"
    if input_path.parent == THIS_DIR:
        return input_path.with_name(filename)
    return THIS_DIR / filename


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
) -> tuple[str, list[float], dict[str, dict[str, list[float]]], list[float]]:
    required_columns = ["time_us"]
    for axis_name in AXES:
        required_columns.append(f"cmd_{axis_name}_mm")
        required_columns.append(f"meas_{axis_name}_mm")

    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        require_columns(reader.fieldnames, required_columns, csv_path)
        rows = list(reader)

    if not rows:
        raise ValueError(f"{csv_path} has no telemetry rows.")

    elapsed_s: list[float] = []
    positions = {
        "commanded": {axis_name: [] for axis_name in AXES},
        "measured": {axis_name: [] for axis_name in AXES},
    }
    error_mm: list[float] = []

    start_time_us: float | None = None
    for row_index, row in enumerate(rows, start=2):
        try:
            time_us = float(row["time_us"])
        except ValueError as exc:
            raise ValueError(f"{csv_path}:{row_index} has a non-numeric time_us value.") from exc

        if start_time_us is None:
            start_time_us = time_us
        elapsed_s.append((time_us - start_time_us) / 1_000_000.0)

        squared_error = 0.0
        for axis_name in AXES:
            cmd_column = f"cmd_{axis_name}_mm"
            meas_column = f"meas_{axis_name}_mm"
            try:
                commanded = float(row[cmd_column])
                measured = float(row[meas_column])
            except ValueError as exc:
                raise ValueError(
                    f"{csv_path}:{row_index} has a non-numeric value in {cmd_column} or {meas_column}."
                ) from exc

            positions["commanded"][axis_name].append(commanded)
            positions["measured"][axis_name].append(measured)
            squared_error += (measured - commanded) ** 2

        error_mm.append(math.sqrt(squared_error))

    return "Basic Leg", elapsed_s, positions, error_mm


def load_jsonl_tracking_data(
    jsonl_path: Path,
) -> tuple[str, list[float], dict[str, dict[str, list[float]]], list[float]]:
    samples = load_designed_arm_hold_samples(jsonl_path)
    start_time_us = samples[0].time_us
    elapsed_s = [(sample.time_us - start_time_us) / 1_000_000.0 for sample in samples]
    positions = {
        "commanded": {axis_name: [] for axis_name in AXES},
        "measured": {axis_name: [] for axis_name in AXES},
    }
    error_mm: list[float] = []

    for sample in samples:
        commanded_position = end_effector_position(
            sample.target_deg["A"],
            sample.target_deg["B"],
            sample.target_deg["C"],
        )
        measured_position = end_effector_position(
            sample.actual_deg["A"],
            sample.actual_deg["B"],
            sample.actual_deg["C"],
        )

        squared_error = 0.0
        for axis_index, axis_name in enumerate(AXES):
            commanded = float(commanded_position[axis_index])
            measured = float(measured_position[axis_index])
            positions["commanded"][axis_name].append(commanded)
            positions["measured"][axis_name].append(measured)
            squared_error += (measured - commanded) ** 2

        error_mm.append(math.sqrt(squared_error))

    return "Designed Arm", elapsed_s, positions, error_mm


def load_tracking_data(
    input_path: Path,
) -> tuple[str, list[float], dict[str, dict[str, list[float]]], list[float]]:
    input_format = detect_input_format(input_path)
    if input_format == INPUT_FORMAT_JSONL:
        return load_jsonl_tracking_data(input_path)
    if input_format == INPUT_FORMAT_CSV:
        return load_csv_tracking_data(input_path)
    raise ValueError(f"Unsupported input format for {input_path}.")


def equal_axis_limits(positions: dict[str, dict[str, np.ndarray]]) -> dict[str, tuple[float, float]]:
    bounds: dict[str, tuple[float, float]] = {}
    minima = []
    maxima = []

    for axis_name in AXES:
        values = np.concatenate((positions["commanded"][axis_name], positions["measured"][axis_name]))
        axis_min = min(values)
        axis_max = max(values)
        bounds[axis_name] = (axis_min, axis_max)
        minima.append(axis_min)
        maxima.append(axis_max)

    max_span = max(maximum - minimum for minimum, maximum in zip(minima, maxima, strict=True))
    half_span = max(max_span * 0.5, 1.0) * 1.08

    equalized: dict[str, tuple[float, float]] = {}
    for axis_name in AXES:
        axis_min, axis_max = bounds[axis_name]
        center = 0.5 * (axis_min + axis_max)
        equalized[axis_name] = (center - half_span, center + half_span)

    return equalized


def plot_tracking(
    input_path: Path,
    source_label: str,
    elapsed_s: list[float],
    positions: dict[str, dict[str, list[float]]],
    error_mm: list[float],
    output: Path,
    t_min: float | None,
    t_max: float | None,
    show: bool,
) -> None:
    elapsed = np.asarray(elapsed_s, dtype=float)
    positions_arrays = {
        position_name: {
            axis_name: np.asarray(values, dtype=float)
            for axis_name, values in axes_values.items()
        }
        for position_name, axes_values in positions.items()
    }
    error_values = np.asarray(error_mm, dtype=float)
    initial_t_min, initial_t_max = resolve_time_window(elapsed_s, t_min, t_max)

    figure = plt.figure(figsize=(11.5, 9.0), constrained_layout=False)
    figure.subplots_adjust(left=0.07, right=0.985, top=0.90, bottom=0.18, hspace=0.25)
    grid = figure.add_gridspec(2, 1, height_ratios=(2.3, 1.0))
    trajectory_axis = figure.add_subplot(grid[0], projection="3d")
    error_axis = figure.add_subplot(grid[1])

    figure.suptitle(f"{source_label} End-Effector Tracking\n{input_path.name}", fontsize=14)

    commanded_line = trajectory_axis.plot(
        positions_arrays["commanded"]["x"],
        positions_arrays["commanded"]["y"],
        positions_arrays["commanded"]["z"],
        color="tab:blue",
        linewidth=2.0,
        label="Commanded",
    )[0]
    measured_line = trajectory_axis.plot(
        positions_arrays["measured"]["x"],
        positions_arrays["measured"]["y"],
        positions_arrays["measured"]["z"],
        color="tab:orange",
        linewidth=1.8,
        label="Measured",
    )[0]
    trajectory_axis.set_xlabel("X (mm)")
    trajectory_axis.set_ylabel("Y (mm)")
    trajectory_axis.set_zlabel("Z (mm)")
    trajectory_axis.view_init(elev=DEFAULT_ELEVATION_DEG, azim=DEFAULT_AZIMUTH_DEG)
    trajectory_axis.legend(loc="best")

    error_axis.plot(elapsed_s, error_mm, color="tab:red", linewidth=1.8)
    error_axis.set_title("Position Error Magnitude")
    error_axis.set_xlabel("Elapsed time (s)")
    error_axis.set_ylabel("Position error (mm)")
    error_axis.grid(True, alpha=0.35)

    current_limits = {"t_min": initial_t_min, "t_max": initial_t_max}

    def apply_time_window(requested_t_min: float, requested_t_max: float) -> bool:
        clamped_t_min = float(np.clip(requested_t_min, elapsed[0], elapsed[-1]))
        clamped_t_max = float(np.clip(requested_t_max, elapsed[0], elapsed[-1]))
        if clamped_t_max <= clamped_t_min:
            return False

        window = slice_for_time_window(elapsed, clamped_t_min, clamped_t_max)
        current_limits["t_min"] = clamped_t_min
        current_limits["t_max"] = clamped_t_max

        visible_positions = {
            position_name: {
                axis_name: values[window]
                for axis_name, values in axes_values.items()
            }
            for position_name, axes_values in positions_arrays.items()
        }

        commanded_line.set_data_3d(
            visible_positions["commanded"]["x"],
            visible_positions["commanded"]["y"],
            visible_positions["commanded"]["z"],
        )
        measured_line.set_data_3d(
            visible_positions["measured"]["x"],
            visible_positions["measured"]["y"],
            visible_positions["measured"]["z"],
        )

        trajectory_axis.set_title(f"3D End-Effector Trajectory ({clamped_t_min:.3f}s to {clamped_t_max:.3f}s)")
        axis_limits = equal_axis_limits(visible_positions)
        trajectory_axis.set_xlim(*axis_limits["x"])
        trajectory_axis.set_ylim(*axis_limits["y"])
        trajectory_axis.set_zlim(*axis_limits["z"])
        trajectory_axis.set_box_aspect(
            (
                axis_limits["x"][1] - axis_limits["x"][0],
                axis_limits["y"][1] - axis_limits["y"][0],
                axis_limits["z"][1] - axis_limits["z"][0],
            )
        )

        error_axis.set_xlim(clamped_t_min, clamped_t_max)
        error_axis.set_ylim(*padded_limits(error_values[window], include_zero=True))
        figure.canvas.draw_idle()
        return True

    apply_time_window(initial_t_min, initial_t_max)
    output.parent.mkdir(parents=True, exist_ok=True)

    if not show:
        figure.savefig(output, dpi=220, bbox_inches="tight")
        plt.close(figure)
        return

    min_axis = figure.add_axes([0.22, 0.06, 0.18, 0.05])
    max_axis = figure.add_axes([0.50, 0.06, 0.18, 0.05])
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
    output = args.output.resolve() if args.output is not None else default_output_path(input_path)

    try:
        source_label, elapsed_s, positions, error_mm = load_tracking_data(input_path)
        plot_tracking(
            input_path,
            source_label,
            elapsed_s,
            positions,
            error_mm,
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
