#!/usr/bin/env python3
"""Interactive 3D DH viewer for the three-joint hexapod leg."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.widgets import Button, Slider

from leg_kinematics import DEFAULT_POSE, LegPose, forward_kinematics, set_fixed_workspace_axes


def draw_frame(ax: plt.Axes, transform: np.ndarray, scale: float, label: str) -> None:
    """Draw a small coordinate frame at a DH frame origin."""
    origin = transform[:3, 3]
    axes = transform[:3, :3]
    colours = ("tab:red", "tab:green", "tab:blue")
    suffixes = ("x", "y", "z")

    for axis_index, colour, suffix in zip(range(3), colours, suffixes, strict=True):
        direction = axes[:, axis_index]
        end = origin + direction * scale
        ax.quiver(
            origin[0],
            origin[1],
            origin[2],
            direction[0],
            direction[1],
            direction[2],
            length=scale,
            normalize=True,
            color=colour,
            linewidth=0.8,
            alpha=0.75,
        )
        ax.text(end[0], end[1], end[2], f"{label}{suffix}", color=colour, fontsize=8)


def make_pose_from_sliders(sliders: dict[str, Slider]) -> LegPose:
    return LegPose(
        theta1_deg=sliders["theta1"].val,
        theta2_deg=sliders["theta2"].val,
        theta3_deg=sliders["theta3"].val,
    )


def main() -> None:
    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")
    fig.subplots_adjust(left=0.08, right=0.97, top=0.92, bottom=0.22)

    slider_axes = {
        "theta1": fig.add_axes((0.16, 0.14, 0.70, 0.025)),
        "theta2": fig.add_axes((0.16, 0.10, 0.70, 0.025)),
        "theta3": fig.add_axes((0.16, 0.06, 0.70, 0.025)),
    }

    sliders = {
        "theta1": Slider(slider_axes["theta1"], "theta1 / A (deg)", 40.0, 140.0, valinit=DEFAULT_POSE.theta1_deg),
        "theta2": Slider(slider_axes["theta2"], "theta2 / B (deg)", 30.0, 130.0, valinit=DEFAULT_POSE.theta2_deg),
        "theta3": Slider(slider_axes["theta3"], "theta3 / C (deg)", 20.0, 170.0, valinit=DEFAULT_POSE.theta3_deg),
    }

    reset_ax = fig.add_axes((0.88, 0.055, 0.08, 0.05))
    reset_button = Button(reset_ax, "Reset")

    def redraw(_event: object | None = None) -> None:
        pose = make_pose_from_sliders(sliders)
        transforms, origins = forward_kinematics(pose)
        points = np.vstack(origins)

        ax.clear()
        ax.plot(points[:, 0], points[:, 1], points[:, 2], "-o", color="black", linewidth=2.0, markersize=6)
        ax.scatter(points[-1, 0], points[-1, 1], points[-1, 2], s=90, color="tab:orange", label="End effector")

        frame_scale = 14.0
        for frame_index, transform in enumerate(transforms):
            draw_frame(ax, transform, scale=frame_scale, label=f"{frame_index}")

        end = points[-1]
        ax.text(
            end[0],
            end[1],
            end[2],
            f"  foot ({end[0]:.1f}, {end[1]:.1f}, {end[2]:.1f}) mm",
            color="tab:orange",
            fontsize=9,
        )

        ax.set_title("Three-joint leg DH visualiser")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_zlabel("Z (mm)")
        ax.legend(loc="upper left")
        ax.grid(True)
        set_fixed_workspace_axes(ax)
        fig.canvas.draw_idle()

    def reset(_event: object) -> None:
        for slider in sliders.values():
            slider.reset()

    for slider in sliders.values():
        slider.on_changed(redraw)
    reset_button.on_clicked(reset)

    redraw()
    plt.show()


if __name__ == "__main__":
    main()
