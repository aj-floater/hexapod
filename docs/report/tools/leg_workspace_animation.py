#!/usr/bin/env python3
"""Animate the DH leg while it sweeps the sampled workspace path."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D

from leg_kinematics import (
    C_LEAST_EXTENDED_DEG,
    C_MOST_EXTENDED_DEG,
    LegPose,
    SERVO_LIMITS_DEG,
    forward_kinematics,
    inclusive_range,
    set_fixed_workspace_axes,
)


@dataclass(frozen=True)
class WorkspaceSample:
    pose: LegPose
    layer_name: str
    colour: str


def sample_workspace_sweep(a_step: float, b_step: float) -> list[WorkspaceSample]:
    """Return the documented A/B workspace sweep for the two C boundary layers."""
    a_min, a_max = SERVO_LIMITS_DEG["A"]
    b_min, b_max = SERVO_LIMITS_DEG["B"]

    samples: list[WorkspaceSample] = []
    layers = (
        ("outer sweep, C = 20 deg", C_MOST_EXTENDED_DEG, "tab:blue"),
        ("inner sweep, C = 170 deg", C_LEAST_EXTENDED_DEG, "tab:orange"),
    )

    for layer_name, c_angle, colour in layers:
        for b_angle in inclusive_range(b_min, b_max, b_step):
            for a_angle in inclusive_range(a_min, a_max, a_step):
                samples.append(
                    WorkspaceSample(
                        pose=LegPose(
                            theta1_deg=float(a_angle),
                            theta2_deg=float(b_angle),
                            theta3_deg=float(c_angle),
                        ),
                        layer_name=layer_name,
                        colour=colour,
                    )
                )

    return samples


def compute_joint_paths(samples: list[WorkspaceSample]) -> list[np.ndarray]:
    """Precompute joint origins for all animation frames."""
    joint_paths: list[np.ndarray] = []
    for sample in samples:
        _transforms, origins = forward_kinematics(sample.pose)
        joint_paths.append(np.vstack(origins))
    return joint_paths


def draw_static_axes(ax: plt.Axes) -> None:
    ax.set_title("DH leg sweep through sampled workspace")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    set_fixed_workspace_axes(ax)
    ax.view_init(elev=24, azim=-58)
    ax.grid(True)


def make_animation(
    samples: list[WorkspaceSample],
    joint_paths: list[np.ndarray],
    interval_ms: int,
    trail_length: int,
    repeat: bool,
) -> tuple[plt.Figure, animation.FuncAnimation]:
    fig = plt.figure(figsize=(9, 8))
    ax = fig.add_subplot(111, projection="3d")
    draw_static_axes(ax)

    first_path = joint_paths[0]
    first_sample = samples[0]

    leg_line, = ax.plot(
        first_path[:, 0],
        first_path[:, 1],
        first_path[:, 2],
        "-o",
        color="black",
        linewidth=2.2,
        markersize=5,
    )
    joint_scatter = ax.scatter(
        first_path[:, 0],
        first_path[:, 1],
        first_path[:, 2],
        s=38,
        color="black",
        depthshade=False,
    )
    trail_scatter = ax.scatter(
        [first_path[-1, 0]],
        [first_path[-1, 1]],
        [first_path[-1, 2]],
        s=18,
        color=[to_rgba(first_sample.colour, 0.95)],
        depthshade=False,
    )
    foot_scatter = ax.scatter(
        [first_path[-1, 0]],
        [first_path[-1, 1]],
        [first_path[-1, 2]],
        s=75,
        color=first_sample.colour,
        edgecolor="black",
        linewidth=0.5,
        depthshade=False,
    )

    status = ax.text2D(0.02, 0.02, "", transform=ax.transAxes, fontsize=9)
    legend_handles = [
        Line2D([0], [0], color="black", marker="o", label="DH leg links"),
        Line2D(
            [0],
            [0],
            color="none",
            marker="o",
            markerfacecolor="tab:blue",
            markeredgecolor="tab:blue",
            label="outer, C = 20 deg",
        ),
        Line2D(
            [0],
            [0],
            color="none",
            marker="o",
            markerfacecolor="tab:orange",
            markeredgecolor="tab:orange",
            label="inner, C = 170 deg",
        ),
    ]
    ax.legend(handles=legend_handles, loc="upper left")

    endpoints = np.array([path[-1] for path in joint_paths])

    def update(frame_index: int):
        path = joint_paths[frame_index]
        sample = samples[frame_index]
        pose = sample.pose

        leg_line.set_data(path[:, 0], path[:, 1])
        leg_line.set_3d_properties(path[:, 2])
        joint_scatter._offsets3d = (path[:, 0], path[:, 1], path[:, 2])

        foot = path[-1]
        foot_scatter._offsets3d = ([foot[0]], [foot[1]], [foot[2]])
        foot_scatter.set_facecolor(sample.colour)

        trail_start = max(0, frame_index - trail_length + 1)
        trail_points = endpoints[trail_start : frame_index + 1]
        trail_samples = samples[trail_start : frame_index + 1]
        alphas = np.linspace(0.12, 0.95, len(trail_points))
        trail_colours = [
            to_rgba(trail_sample.colour, float(alpha))
            for trail_sample, alpha in zip(trail_samples, alphas, strict=True)
        ]
        trail_scatter._offsets3d = (trail_points[:, 0], trail_points[:, 1], trail_points[:, 2])
        trail_scatter.set_facecolors(trail_colours)
        trail_scatter.set_edgecolors(trail_colours)

        status.set_text(
            f"{sample.layer_name}; "
            f"A={pose.theta1_deg:.0f} deg, B={pose.theta2_deg:.0f} deg, C={pose.theta3_deg:.0f} deg; "
            f"sample {frame_index + 1}/{len(samples)}"
        )
        return leg_line, joint_scatter, trail_scatter, foot_scatter, status

    anim = animation.FuncAnimation(
        fig,
        update,
        frames=len(samples),
        interval=interval_ms,
        blit=False,
        repeat=repeat,
    )
    update(0)
    return fig, anim


def save_animation(anim: animation.FuncAnimation, output: Path, fps: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    suffix = output.suffix.lower()
    if suffix == ".gif":
        writer: animation.AbstractMovieWriter = animation.PillowWriter(fps=fps)
    else:
        writer = animation.FFMpegWriter(fps=fps)
    anim.save(output, writer=writer)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-step", type=float, default=5.0, help="Servo A/theta1 sampling step in degrees.")
    parser.add_argument("--b-step", type=float, default=5.0, help="Servo B/theta2 sampling step in degrees.")
    parser.add_argument("--interval-ms", type=int, default=40, help="Delay between animation frames.")
    parser.add_argument("--trail-length", type=int, default=80, help="Number of recent endpoint samples to show.")
    parser.add_argument("--no-repeat", action="store_true", help="Stop the animation after one sweep.")
    parser.add_argument("--save", type=Path, help="Optional MP4 or GIF output path.")
    parser.add_argument("--fps", type=int, default=25, help="Frames per second when saving an animation.")
    parser.add_argument(
        "--show",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Display the interactive Matplotlib window.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    samples = sample_workspace_sweep(a_step=args.a_step, b_step=args.b_step)
    if not samples:
        raise RuntimeError("no workspace samples generated")

    joint_paths = compute_joint_paths(samples)
    fig, anim = make_animation(
        samples=samples,
        joint_paths=joint_paths,
        interval_ms=args.interval_ms,
        trail_length=max(1, args.trail_length),
        repeat=not args.no_repeat,
    )

    print(f"Prepared {len(samples)} animated workspace samples")
    if args.save is not None:
        save_animation(anim, output=args.save, fps=args.fps)
        print(f"Saved {args.save}")

    if args.show:
        plt.show()
    else:
        plt.close(fig)


if __name__ == "__main__":
    main()
