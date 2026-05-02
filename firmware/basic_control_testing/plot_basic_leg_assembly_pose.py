#!/usr/bin/env python3
"""Generate a side-on assembly diagram for the basic leg pose."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-basic-control-testing")

import matplotlib.pyplot as plt
import numpy as np


THIS_DIR = Path(__file__).resolve().parent
REPORT_TOOLS_DIR = THIS_DIR.parent.parent / "docs" / "report" / "tools"
DEFAULT_OUTPUT = THIS_DIR / "basic_leg_assembly_pose_side_on.png"

sys.path.insert(0, str(REPORT_TOOLS_DIR))

from leg_kinematics import LINK_LENGTHS_MM, LegPose, forward_kinematics  # noqa: E402


BASIC_Q_DEG = {"A": 25.0, "B": 20.0, "C": 40.0}
BASIC_OFFSETS_DEG = {"A": 65.0, "B": 62.0, "C": 51.0}
POINT_LABELS = ("Base", "Joint 1", "Joint 2", "Foot")


def basic_pose_to_absolute_pose() -> LegPose:
    return LegPose(
        theta1_deg=BASIC_OFFSETS_DEG["A"] + BASIC_Q_DEG["A"],
        theta2_deg=BASIC_OFFSETS_DEG["B"] + BASIC_Q_DEG["B"],
        theta3_deg=BASIC_OFFSETS_DEG["C"] + BASIC_Q_DEG["C"],
    )


def section_path_yz(pose: LegPose) -> np.ndarray:
    _transforms, origins = forward_kinematics(pose)
    points_xyz = np.vstack(origins)
    return points_xyz[:, 1:3]


def square_axis_limits(points_yz: np.ndarray, padding_frac: float = 0.16) -> tuple[float, float, float, float]:
    min_y, min_z = np.min(points_yz, axis=0)
    max_y, max_z = np.max(points_yz, axis=0)
    center_y = 0.5 * (min_y + max_y)
    center_z = 0.5 * (min_z + max_z)
    span = max(max_y - min_y, max_z - min_z)
    half_span = max(20.0, 0.5 * span) * (1.0 + padding_frac)
    return (
        center_y - half_span,
        center_y + half_span,
        center_z - half_span,
        center_z + half_span,
    )


def annotate_link_lengths(ax: plt.Axes, points_yz: np.ndarray) -> None:
    for index, length_mm in enumerate(LINK_LENGTHS_MM):
        start = points_yz[index]
        end = points_yz[index + 1]
        midpoint = 0.5 * (start + end)
        offset = np.array((4.0, 6.0 if index % 2 == 0 else -6.0))
        ax.text(
            midpoint[0] + offset[0],
            midpoint[1] + offset[1],
            f"{length_mm:.0f} mm",
            fontsize=9,
            color="tab:blue",
            bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "tab:blue", "alpha": 0.9},
        )


def annotate_points(ax: plt.Axes, points_yz: np.ndarray) -> None:
    offsets = ((-8.0, 6.0), (4.0, 6.0), (4.0, 6.0), (4.0, -10.0))
    for label, point, (dy, dz) in zip(POINT_LABELS, points_yz, offsets, strict=True):
        ax.text(point[0] + dy, point[1] + dz, label, fontsize=9, color="black")


def make_info_text(pose: LegPose) -> str:
    return "\n".join(
        (
            "Basic command pose",
            f"qA={BASIC_Q_DEG['A']:.0f}°, qB={BASIC_Q_DEG['B']:.0f}°, qC={BASIC_Q_DEG['C']:.0f}°",
            "",
            "Absolute DH pose",
            f"A={pose.theta1_deg:.0f}°, B={pose.theta2_deg:.0f}°, C={pose.theta3_deg:.0f}°",
            "",
            "Offset mapping",
            "A = 65 + qA",
            "B = 62 + qB",
            "C = 51 + qC",
        )
    )


def plot_assembly_pose(output: Path, show: bool) -> None:
    pose = basic_pose_to_absolute_pose()
    points_yz = section_path_yz(pose)

    fig, ax = plt.subplots(figsize=(8.5, 8.0))
    ax.plot(points_yz[:, 0], points_yz[:, 1], "-o", color="black", linewidth=2.2, markersize=6, label="Linkage")
    ax.scatter(points_yz[-1, 0], points_yz[-1, 1], s=95, color="tab:orange", edgecolor="black", linewidth=0.5, zorder=4)

    annotate_link_lengths(ax, points_yz)
    annotate_points(ax, points_yz)

    foot_y, foot_z = points_yz[-1]
    ax.text(foot_y + 4.0, foot_z - 18.0, f"Foot ({foot_y:.1f}, {foot_z:.1f}) mm", fontsize=9, color="tab:orange")

    y_min, y_max, z_min, z_max = square_axis_limits(points_yz)
    ax.set_xlim(y_min, y_max)
    ax.set_ylim(z_min, z_max)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True)
    ax.set_xlabel("Y (mm)")
    ax.set_ylabel("Z (mm)")
    ax.set_title("Basic Leg Assembly Pose, Side-On")

    ax.text(
        0.02,
        0.98,
        make_info_text(pose),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "0.5", "alpha": 0.95},
    )

    ax.text(
        0.02,
        0.02,
        "Shared DH linkage from report tools; A fixed to the side-on section plane.",
        transform=ax.transAxes,
        fontsize=9,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output PNG path.")
    parser.add_argument(
        "--show",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Display the plot window after saving.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plot_assembly_pose(output=args.output, show=args.show)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
