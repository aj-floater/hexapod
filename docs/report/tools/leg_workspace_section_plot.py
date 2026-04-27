#!/usr/bin/env python3
"""Generate side-on Y-Z workspace section figures for a fixed servo A angle."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Polygon

from leg_kinematics import LINK_LENGTHS_MM, LegPose, forward_kinematics
from leg_workspace_plot import WORKSPACE_LAYER_SPECS, WORKSPACE_LAYER_SPECS_BY_KEY, sample_workspace_section


DEFAULT_A_ANGLE_DEG = 90.0
DEFAULT_B_ANGLE_DEG = 60.0
DEFAULT_C_ANGLE_DEG = 130.0
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "figures"
FILLED_PATCH_COLOUR = "tab:blue"
FILLED_PATCH_ALPHA = 0.18
SECTION_FRAME_PADDING = 0.08


def default_output_paths(a_angle_deg: float) -> tuple[Path, Path]:
    angle_suffix = f"{a_angle_deg:.1f}".rstrip("0").rstrip(".").replace("-", "m").replace(".", "p")
    return (
        DEFAULT_OUTPUT_DIR / f"leg_workspace_section_a{angle_suffix}_point_cloud.png",
        DEFAULT_OUTPUT_DIR / f"leg_workspace_section_a{angle_suffix}_filled.png",
    )


def section_rows_to_yz_array(rows: list[dict[str, float | str]], layer_key: str) -> np.ndarray:
    points = [[row["y"], row["z"]] for row in rows if row["layer"] == layer_key]
    return np.array(points, dtype=float).reshape(-1, 2)


def section_rows_x_values(rows: list[dict[str, float | str]]) -> np.ndarray:
    return np.array([float(row["x"]) for row in rows], dtype=float)


def leg_yz_path(pose: LegPose) -> np.ndarray:
    _transforms, origins = forward_kinematics(pose)
    points = np.vstack(origins)
    return points[:, 1:3]


def build_section_polygon_vertices(rows: list[dict[str, float | str]]) -> np.ndarray:
    outer = section_rows_to_yz_array(rows, "outer_c_min")
    b_max = section_rows_to_yz_array(rows, "b_max_c_sweep")
    inner = section_rows_to_yz_array(rows, "inner_c_max")
    b_min = section_rows_to_yz_array(rows, "b_min_c_sweep")
    return np.vstack((outer, b_max[1:], inner[-2::-1], b_min[-2:0:-1]))


def section_axis_limits(rows: list[dict[str, float | str]], pose: LegPose) -> tuple[float, float, float, float]:
    section_points = np.array([[float(row["y"]), float(row["z"])] for row in rows], dtype=float)
    leg_points = leg_yz_path(pose)
    combined = np.vstack((section_points, leg_points))

    min_y, min_z = np.min(combined, axis=0)
    max_y, max_z = np.max(combined, axis=0)
    centre_y = 0.5 * (min_y + max_y)
    centre_z = 0.5 * (min_z + max_z)

    span = max(max_y - min_y, max_z - min_z)
    half_span = max(1.0, 0.5 * span) * (1.0 + SECTION_FRAME_PADDING)
    return (
        centre_y - half_span,
        centre_y + half_span,
        centre_z - half_span,
        centre_z + half_span,
    )


def setup_section_axes(
    ax: plt.Axes,
    a_angle_deg: float,
    title: str,
    limits: tuple[float, float, float, float],
) -> None:
    y_min, y_max, z_min, z_max = limits
    ax.set_title(title)
    ax.set_xlabel("Y (mm)")
    ax.set_ylabel("Z (mm)")
    ax.set_xlim(y_min, y_max)
    ax.set_ylim(z_min, z_max)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True)
    ax.text(
        0.02,
        0.02,
        f"l1={LINK_LENGTHS_MM[0]:.0f} mm, l2={LINK_LENGTHS_MM[1]:.0f} mm, l3={LINK_LENGTHS_MM[2]:.0f} mm; A={a_angle_deg:.0f} deg",
        transform=ax.transAxes,
        fontsize=9,
    )


def point_cloud_legend_handles() -> list[Line2D]:
    handles = [
        Line2D([0], [0], color="black", marker="o", linewidth=2.0, markersize=5, label="leg pose"),
        Line2D(
            [0],
            [0],
            color="none",
            marker="o",
            markerfacecolor="tab:orange",
            markeredgecolor="tab:orange",
            markersize=8,
            label="end effector",
        ),
        Patch(
            facecolor=FILLED_PATCH_COLOUR,
            edgecolor=FILLED_PATCH_COLOUR,
            alpha=FILLED_PATCH_ALPHA,
            label="filled workspace section",
        ),
    ]
    for spec in WORKSPACE_LAYER_SPECS:
        handles.append(
            Line2D(
                [0],
                [0],
                color=spec.colour,
                marker="o",
                linewidth=1.0,
                markersize=4,
                label=spec.label,
            )
        )
    return handles


def filled_legend_handles() -> list[object]:
    return [
        Line2D([0], [0], color="black", marker="o", linewidth=2.0, markersize=5, label="leg pose"),
        Line2D(
            [0],
            [0],
            color="none",
            marker="o",
            markerfacecolor="tab:orange",
            markeredgecolor="tab:orange",
            markersize=8,
            label="end effector",
        ),
        Patch(
            facecolor=FILLED_PATCH_COLOUR,
            edgecolor=FILLED_PATCH_COLOUR,
            alpha=FILLED_PATCH_ALPHA,
            label="filled workspace section",
        ),
    ]


def draw_leg_overlay(ax: plt.Axes, pose: LegPose) -> None:
    path = leg_yz_path(pose)
    ax.plot(path[:, 0], path[:, 1], "-o", color="black", linewidth=2.0, markersize=5)
    ax.scatter(path[-1, 0], path[-1, 1], s=80, color="tab:orange", edgecolor="black", linewidth=0.4, zorder=4)


def make_section_patch(rows: list[dict[str, float | str]]) -> Polygon:
    return Polygon(
        build_section_polygon_vertices(rows),
        closed=True,
        facecolor=FILLED_PATCH_COLOUR,
        edgecolor=FILLED_PATCH_COLOUR,
        linewidth=1.3,
        alpha=FILLED_PATCH_ALPHA,
        zorder=1,
    )


def plot_section_point_cloud(
    rows: list[dict[str, float | str]],
    pose: LegPose,
    a_angle_deg: float,
    output: Path,
    show: bool,
) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 8.0))
    setup_section_axes(
        ax,
        a_angle_deg,
        title=f"Side-on workspace section at A = {a_angle_deg:.0f} deg",
        limits=section_axis_limits(rows, pose),
    )
    ax.add_patch(make_section_patch(rows))

    for spec in WORKSPACE_LAYER_SPECS:
        data = section_rows_to_yz_array(rows, spec.key)
        if data.size == 0:
            continue
        ax.scatter(data[:, 0], data[:, 1], s=18, color=spec.colour, alpha=0.8, zorder=2)
        ax.plot(data[:, 0], data[:, 1], color=spec.colour, linewidth=0.9, alpha=0.45, zorder=1)

    draw_leg_overlay(ax, pose)
    ax.legend(handles=point_cloud_legend_handles(), loc="upper left")

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight")
    if not show:
        plt.close(fig)


def plot_section_filled(
    rows: list[dict[str, float | str]],
    pose: LegPose,
    a_angle_deg: float,
    output: Path,
    show: bool,
) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 8.0))
    setup_section_axes(
        ax,
        a_angle_deg,
        title=f"Filled side-on workspace section at A = {a_angle_deg:.0f} deg",
        limits=section_axis_limits(rows, pose),
    )

    ax.add_patch(make_section_patch(rows))

    for spec in WORKSPACE_LAYER_SPECS:
        data = section_rows_to_yz_array(rows, spec.key)
        if data.size == 0:
            continue
        ax.plot(data[:, 0], data[:, 1], color=spec.colour, linewidth=0.9, alpha=0.4, zorder=2)

    draw_leg_overlay(ax, pose)
    ax.legend(handles=filled_legend_handles(), loc="upper left")

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight")
    if not show:
        plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-angle", type=float, default=DEFAULT_A_ANGLE_DEG, help="Fixed servo A angle in degrees.")
    parser.add_argument("--b-angle", type=float, default=DEFAULT_B_ANGLE_DEG, help="Overlay servo B angle in degrees.")
    parser.add_argument("--c-angle", type=float, default=DEFAULT_C_ANGLE_DEG, help="Overlay servo C angle in degrees.")
    parser.add_argument("--b-step", type=float, default=5.0, help="Servo B/theta2 sampling step in degrees.")
    parser.add_argument("--c-step", type=float, default=5.0, help="Servo C/theta3 sampling step in degrees.")
    parser.add_argument("--output-point-cloud", type=Path, help="Output PNG path for the section point cloud figure.")
    parser.add_argument("--output-filled", type=Path, help="Output PNG path for the filled section figure.")
    parser.add_argument("--show", action=argparse.BooleanOptionalAction, default=True, help="Display the figures.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    point_cloud_output, filled_output = default_output_paths(args.a_angle)
    if args.output_point_cloud is not None:
        point_cloud_output = args.output_point_cloud
    if args.output_filled is not None:
        filled_output = args.output_filled

    pose = LegPose(theta1_deg=args.a_angle, theta2_deg=args.b_angle, theta3_deg=args.c_angle)
    rows = sample_workspace_section(a_angle=args.a_angle, b_step=args.b_step, c_step=args.c_step)

    x_values = section_rows_x_values(rows)
    print(f"Generated {len(rows)} section points")
    print(f"Section max |X| = {np.max(np.abs(x_values)):.6f} mm")

    plot_section_point_cloud(rows, pose=pose, a_angle_deg=args.a_angle, output=point_cloud_output, show=args.show)
    plot_section_filled(rows, pose=pose, a_angle_deg=args.a_angle, output=filled_output, show=args.show)

    print(f"Saved {point_cloud_output}")
    print(f"Saved {filled_output}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
