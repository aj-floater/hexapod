#!/usr/bin/env python3
"""Generate a sampled 3D end-effector workspace for the report leg."""

from __future__ import annotations

import argparse
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


def sample_workspace(a_step: float, b_step: float) -> list[dict[str, float | str]]:
    """Sample outer and inner end-effector rings from the servo soft bounds."""
    a_min, a_max = SERVO_LIMITS_DEG["A"]
    b_min, b_max = SERVO_LIMITS_DEG["B"]

    rows: list[dict[str, float | str]] = []
    layers = (
        ("outer rings, C most extended", C_MOST_EXTENDED_DEG),
        ("inner rings, C least extended", C_LEAST_EXTENDED_DEG),
    )

    for layer_name, c_angle in layers:
        for b_angle in inclusive_range(b_min, b_max, b_step):
            for a_angle in inclusive_range(a_min, a_max, a_step):
                x, y, z = end_effector_position(a_angle, b_angle, c_angle)
                rows.append(
                    {
                        "x": float(x),
                        "y": float(y),
                        "z": float(z),
                        "a_deg": float(a_angle),
                        "b_deg": float(b_angle),
                        "c_deg": float(c_angle),
                        "layer": layer_name,
                    }
                )

    return rows


def rows_to_array(rows: list[dict[str, float | str]], layer: str) -> np.ndarray:
    points = [[row["x"], row["y"], row["z"], row["b_deg"]] for row in rows if row["layer"] == layer]
    return np.array(points, dtype=float)


def draw_layer_lines(ax, data: np.ndarray, colour: str) -> None:
    """Connect each B layer so the sampled ring structure remains visible."""
    if data.size == 0:
        return
    for b_angle in np.unique(data[:, 3]):
        layer_points = data[data[:, 3] == b_angle]
        ax.plot(
            layer_points[:, 0],
            layer_points[:, 1],
            layer_points[:, 2],
            color=colour,
            linewidth=0.8,
            alpha=0.35,
        )


def plot_workspace(rows: list[dict[str, float | str]], output: Path, show: bool) -> None:
    outer_label = "outer rings, C most extended"
    inner_label = "inner rings, C least extended"
    outer = rows_to_array(rows, outer_label)
    inner = rows_to_array(rows, inner_label)

    fig = plt.figure(figsize=(9, 8))
    ax = fig.add_subplot(111, projection="3d")

    ax.scatter(outer[:, 0], outer[:, 1], outer[:, 2], s=12, color="tab:blue", alpha=0.75, label="C = 20 deg")
    ax.scatter(inner[:, 0], inner[:, 1], inner[:, 2], s=12, color="tab:orange", alpha=0.75, label="C = 170 deg")
    draw_layer_lines(ax, outer, "tab:blue")
    draw_layer_lines(ax, inner, "tab:orange")

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
        "A swept per B layer"
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output PNG path.")
    parser.add_argument("--show", action=argparse.BooleanOptionalAction, default=True, help="Display the plot window.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = sample_workspace(a_step=args.a_step, b_step=args.b_step)
    plot_workspace(rows, output=args.output, show=args.show)
    print(f"Generated {len(rows)} points")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
