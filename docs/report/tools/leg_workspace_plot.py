#!/usr/bin/env python3
"""Generate a sampled 3D end-effector workspace for the report leg."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leg_kinematics import (
    C_LEAST_EXTENDED_DEG,
    C_MOST_EXTENDED_DEG,
    LINK_LENGTHS_MM,
    SERVO_LIMITS_DEG,
    end_effector_position,
    inclusive_range,
    set_fixed_workspace_axes,
)


DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "figures" / "leg_workspace_point_cloud.png"


@dataclass(frozen=True)
class WorkspaceLayerSpec:
    key: str
    label: str
    colour: str


_B_MIN_DEG, _B_MAX_DEG = SERVO_LIMITS_DEG["B"]
WORKSPACE_LAYER_SPECS = (
    WorkspaceLayerSpec(
        key="outer_c_min",
        label=f"outer rings, C = {C_MOST_EXTENDED_DEG:.0f} deg",
        colour="tab:blue",
    ),
    WorkspaceLayerSpec(
        key="inner_c_max",
        label=f"inner rings, C = {C_LEAST_EXTENDED_DEG:.0f} deg",
        colour="tab:orange",
    ),
    WorkspaceLayerSpec(
        key="b_max_c_sweep",
        label=f"B = {_B_MAX_DEG:.0f} deg, C sweep",
        colour="tab:green",
    ),
    WorkspaceLayerSpec(
        key="b_min_c_sweep",
        label=f"B = {_B_MIN_DEG:.0f} deg, C sweep",
        colour="tab:red",
    ),
)
WORKSPACE_LAYER_SPECS_BY_KEY = {spec.key: spec for spec in WORKSPACE_LAYER_SPECS}


def sample_workspace(a_step: float, b_step: float, c_step: float) -> list[dict[str, float | str]]:
    """Sample the documented C-fixed and B-fixed workspace sweeps."""
    a_min, a_max = SERVO_LIMITS_DEG["A"]
    b_min, b_max = SERVO_LIMITS_DEG["B"]
    c_min, c_max = SERVO_LIMITS_DEG["C"]

    rows: list[dict[str, float | str]] = []

    def append_row(layer_key: str, a_angle: float, b_angle: float, c_angle: float, line_group_deg: float) -> None:
        x, y, z = end_effector_position(a_angle, b_angle, c_angle)
        rows.append(
            {
                "x": float(x),
                "y": float(y),
                "z": float(z),
                "a_deg": float(a_angle),
                "b_deg": float(b_angle),
                "c_deg": float(c_angle),
                "line_group_deg": float(line_group_deg),
                "layer": layer_key,
            }
        )

    for b_angle in inclusive_range(b_min, b_max, b_step):
        for a_angle in inclusive_range(a_min, a_max, a_step):
            append_row("outer_c_min", a_angle, b_angle, C_MOST_EXTENDED_DEG, line_group_deg=b_angle)

    for b_angle in inclusive_range(b_min, b_max, b_step):
        for a_angle in inclusive_range(a_min, a_max, a_step):
            append_row("inner_c_max", a_angle, b_angle, C_LEAST_EXTENDED_DEG, line_group_deg=b_angle)

    for c_angle in inclusive_range(c_min, c_max, c_step):
        for a_angle in inclusive_range(a_min, a_max, a_step):
            append_row("b_max_c_sweep", a_angle, b_max, c_angle, line_group_deg=c_angle)

    for c_angle in inclusive_range(c_min, c_max, c_step):
        for a_angle in inclusive_range(a_min, a_max, a_step):
            append_row("b_min_c_sweep", a_angle, b_min, c_angle, line_group_deg=c_angle)

    return rows


def rows_to_array(rows: list[dict[str, float | str]], layer: str) -> np.ndarray:
    points = [[row["x"], row["y"], row["z"], row["line_group_deg"]] for row in rows if row["layer"] == layer]
    return np.array(points, dtype=float)


def draw_layer_lines(ax, data: np.ndarray, colour: str) -> None:
    """Connect each sampled strip so the sweep structure remains visible."""
    if data.size == 0:
        return
    for group_value in np.unique(data[:, 3]):
        layer_points = data[data[:, 3] == group_value]
        ax.plot(
            layer_points[:, 0],
            layer_points[:, 1],
            layer_points[:, 2],
            color=colour,
            linewidth=0.8,
            alpha=0.35,
        )


def plot_workspace(rows: list[dict[str, float | str]], output: Path, show: bool) -> None:
    fig = plt.figure(figsize=(9, 8))
    ax = fig.add_subplot(111, projection="3d")

    for spec in WORKSPACE_LAYER_SPECS:
        data = rows_to_array(rows, spec.key)
        if data.size == 0:
            continue
        ax.scatter(data[:, 0], data[:, 1], data[:, 2], s=12, color=spec.colour, alpha=0.75, label=spec.label)
        draw_layer_lines(ax, data, spec.colour)

    ax.scatter(0.0, 0.0, 0.0, s=45, color="black", label="base frame")
    ax.set_title("Sampled end-effector workspace from servo soft bounds")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    set_fixed_workspace_axes(ax)
    ax.view_init(elev=24, azim=-58)
    ax.grid(True)
    ax.legend(loc="upper left")

    note = (
        f"l1={LINK_LENGTHS_MM[0]:.0f} mm, l2={LINK_LENGTHS_MM[1]:.0f} mm, l3={LINK_LENGTHS_MM[2]:.0f} mm; "
        "A swept per B layer at C bounds and per C layer at B bounds"
    )
    ax.text2D(0.02, 0.02, note, transform=ax.transAxes, fontsize=9)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-step", type=float, default=5.0, help="Servo A/theta1 sampling step in degrees.")
    parser.add_argument("--b-step", type=float, default=5.0, help="Servo B/theta2 sampling step in degrees.")
    parser.add_argument("--c-step", type=float, default=5.0, help="Servo C/theta3 sampling step in degrees.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output PNG path.")
    parser.add_argument("--show", action=argparse.BooleanOptionalAction, default=True, help="Display the plot window.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = sample_workspace(a_step=args.a_step, b_step=args.b_step, c_step=args.c_step)
    plot_workspace(rows, output=args.output, show=args.show)
    print(f"Generated {len(rows)} points")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
