"""Shared DH kinematics for the report leg workspace tools."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


LINK_LENGTHS_MM = (36.0, 62.0, 87.0)
MAX_REACH_MM = sum(LINK_LENGTHS_MM)

# Standard DH table from the frame sketch:
#   d = 0 for all joints
#   theta = theta_i
#   a/r = l_i
#   alpha = [90, 0, -90] degrees
ALPHA_DEG = (90.0, 0.0, -90.0)

SERVO_LIMITS_DEG = {
    "A": (40.0, 140.0),
    "B": (30.0, 130.0),
    "C": (20.0, 170.0),
}

C_MOST_EXTENDED_DEG = 20.0
C_LEAST_EXTENDED_DEG = 170.0


@dataclass(frozen=True)
class LegPose:
    theta1_deg: float = 90.0
    theta2_deg: float = 80.0
    theta3_deg: float = 95.0


DEFAULT_POSE = LegPose()


def standard_dh_transform(theta_deg: float, d: float, a: float, alpha_deg: float) -> np.ndarray:
    """Return the standard DH transform Rz(theta) Tz(d) Tx(a) Rx(alpha)."""
    theta = math.radians(theta_deg)
    alpha = math.radians(alpha_deg)
    ct, st = math.cos(theta), math.sin(theta)
    ca, sa = math.cos(alpha), math.sin(alpha)

    return np.array(
        [
            [ct, -st * ca, st * sa, a * ct],
            [st, ct * ca, -ct * sa, a * st],
            [0.0, sa, ca, d],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def forward_kinematics(pose: LegPose) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Return frame transforms and joint origins for the current pose."""
    angles = (pose.theta1_deg, pose.theta2_deg, pose.theta3_deg)

    transforms = [np.eye(4)]
    transform = np.eye(4)
    for theta_deg, length, alpha_deg in zip(angles, LINK_LENGTHS_MM, ALPHA_DEG, strict=True):
        transform = transform @ standard_dh_transform(theta_deg, d=0.0, a=length, alpha_deg=alpha_deg)
        transforms.append(transform)

    origins = [transform[:3, 3].copy() for transform in transforms]
    return transforms, origins


def end_effector_position(theta1_deg: float, theta2_deg: float, theta3_deg: float) -> np.ndarray:
    """Return the final frame origin for a given set of joint angles."""
    _, origins = forward_kinematics(LegPose(theta1_deg, theta2_deg, theta3_deg))
    return origins[-1]


def inclusive_range(start: float, stop: float, step: float) -> np.ndarray:
    """Return a floating-point range that includes the upper bound when step divides it."""
    if step <= 0:
        raise ValueError("step must be positive")
    return np.arange(start, stop + step * 0.5, step, dtype=float)


def set_fixed_workspace_axes(ax) -> None:
    """Use fixed equal axes so changing pose or layer data does not rescale the plot."""
    reach = MAX_REACH_MM
    ax.set_xlim(-reach, reach)
    ax.set_ylim(-reach, reach)
    ax.set_zlim(-reach, reach)
    ax.set_box_aspect((1, 1, 1))
