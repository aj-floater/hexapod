#!/usr/bin/env python3
"""Live Matplotlib digital twin for the three-joint leg over DevLink."""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from dataclasses import dataclass

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np

from devlink_dashboard.messages import (
    CapabilitiesMessage,
    EventMessage,
    LogMessage,
    Message,
    ProtocolError,
    SampleMessage,
    build_cmd_message,
    parse_line_resilient,
)
from devlink_dashboard.transport import SerialTransport, SerialUnavailableError, list_serial_ports
from leg_kinematics import (
    DEFAULT_POSE,
    LegPose,
    SERVO_LIMITS_DEG,
    dh_theta_angles_deg,
    forward_kinematics,
    set_fixed_workspace_axes,
)
from leg_workspace_plot import WORKSPACE_LAYER_SPECS, sample_workspace


DEFAULT_DEVICE = "control_testing"
DEFAULT_STREAM = "control_testing.angle_lp"
DEFAULT_FIELDS = ("adc_a_lp_deg", "adc_b_lp_deg", "adc_c_lp_deg")
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT_S = 0.05
FRAME_AXIS_SCALE_MM = 40.0
WORKSPACE_POINT_ALPHA = 0.12
WORKSPACE_POINT_SIZE = 9.0


@dataclass(frozen=True)
class MeasuredAngleSample:
    raw_pose: LegPose
    seq: int
    t_us: int
    received_at: float


def resolve_serial_port(requested_port: str | None) -> str:
    if requested_port:
        return requested_port

    ports = list_serial_ports()
    if len(ports) == 1:
        return ports[0]
    if not ports:
        raise RuntimeError("no serial ports found; pass --port /dev/ttyACM0")
    joined = ", ".join(ports)
    raise RuntimeError(f"multiple serial ports found ({joined}); pass --port explicitly")


def extract_measured_angle_sample(
    message: Message,
    *,
    device: str,
    stream: str,
    fields: tuple[str, str, str] = DEFAULT_FIELDS,
    received_at: float | None = None,
) -> MeasuredAngleSample | None:
    """Return a measured leg pose from the configured angle telemetry sample."""
    if not isinstance(message, SampleMessage):
        return None
    if message.device != device or message.stream != stream:
        return None

    missing = [field for field in fields if field not in message.data]
    if missing:
        raise ValueError(f"{stream} sample missing field(s): {', '.join(missing)}")

    try:
        a_deg, b_deg, c_deg = (float(message.data[field]) for field in fields)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{stream} angle fields must be numeric") from exc

    raw_pose = LegPose(theta1_deg=a_deg, theta2_deg=b_deg, theta3_deg=c_deg)
    return MeasuredAngleSample(
        raw_pose=raw_pose,
        seq=message.seq,
        t_us=message.t_us,
        received_at=time.monotonic() if received_at is None else received_at,
    )


def servo_limit_warnings(raw_pose: LegPose) -> list[str]:
    values = {
        "A": raw_pose.theta1_deg,
        "B": raw_pose.theta2_deg,
        "C": raw_pose.theta3_deg,
    }
    warnings: list[str] = []
    for name, value in values.items():
        lower, upper = SERVO_LIMITS_DEG[name]
        if value < lower or value > upper:
            warnings.append(f"{name}={value:.1f} outside {lower:.0f}-{upper:.0f} deg")
    return warnings


def workspace_point_cloud_layers() -> list[tuple[str, str, np.ndarray]]:
    """Return the sampled workspace point clouds as per-layer XYZ arrays."""
    rows = sample_workspace(a_step=5.0, b_step=5.0, c_step=5.0)
    layers: list[tuple[str, str, np.ndarray]] = []
    for spec in WORKSPACE_LAYER_SPECS:
        points = np.array(
            [[row["x"], row["y"], row["z"]] for row in rows if row["layer"] == spec.key],
            dtype=float,
        ).reshape(-1, 3)
        layers.append((spec.label, spec.colour, points))
    return layers


class DevlinkReader:
    def __init__(
        self,
        *,
        port: str,
        baud: int,
        timeout: float,
        messages: "queue.Queue[Message]",
        statuses: "queue.Queue[str]",
    ) -> None:
        self._port = port
        self._baud = baud
        self._timeout = timeout
        self._messages = messages
        self._statuses = statuses
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._transport: SerialTransport | None = None
        self._parse_error_count = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="leg-devlink-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._transport is not None:
            self._transport.close()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _status(self, text: str) -> None:
        self._statuses.put(text)

    def _run(self) -> None:
        try:
            with SerialTransport(self._port, baud=self._baud, timeout=self._timeout) as transport:
                self._transport = transport
                self._status(f"connected to {self._port} @ {self._baud}")
                describe = build_cmd_message(device="*", command_id=1, name="device.describe", args={})
                transport.send_message(describe)

                while not self._stop.is_set():
                    try:
                        line = transport.readline()
                    except Exception as exc:
                        if not self._stop.is_set():
                            self._status(f"serial read error: {exc}")
                        break
                    if line is None or line == b"":
                        continue

                    try:
                        message = parse_line_resilient(line)
                    except ProtocolError as exc:
                        self._parse_error_count += 1
                        if self._parse_error_count <= 3 or self._parse_error_count % 50 == 0:
                            self._status(f"parse error {self._parse_error_count}: {exc}")
                        continue

                    self._messages.put(message)
        except SerialUnavailableError as exc:
            self._status(str(exc))
        except Exception as exc:
            if not self._stop.is_set():
                self._status(f"connection error: {exc}")
        finally:
            self._transport = None
            self._status("disconnected")


class DigitalTwinPlot:
    def __init__(
        self,
        *,
        device: str,
        stream: str,
        messages: "queue.Queue[Message]",
        statuses: "queue.Queue[str]",
        trail_length: int,
        show_trail: bool,
    ) -> None:
        self._device = device
        self._stream = stream
        self._messages = messages
        self._statuses = statuses
        self._trail_length = max(1, trail_length)
        self._show_trail = show_trail
        self._latest_sample: MeasuredAngleSample | None = None
        self._latest_status = "waiting for telemetry"
        self._latest_warning = ""
        self._trail_points: list[np.ndarray] = []
        self._workspace_scatters: list[object] = []
        self._frame_artists: list[object] = []

        self.fig = plt.figure(figsize=(9, 8))
        self.ax = self.fig.add_subplot(111, projection="3d")
        self._build_axes()

        for label, colour, points in workspace_point_cloud_layers():
            scatter = self.ax.scatter(
                points[:, 0],
                points[:, 1],
                points[:, 2],
                s=WORKSPACE_POINT_SIZE,
                color=colour,
                alpha=WORKSPACE_POINT_ALPHA,
                depthshade=False,
                label=label,
            )
            self._workspace_scatters.append(scatter)

        _initial_transforms, initial_path = self._leg_geometry(DEFAULT_POSE)
        (self._leg_line,) = self.ax.plot(
            initial_path[:, 0],
            initial_path[:, 1],
            initial_path[:, 2],
            "-o",
            color="black",
            linewidth=2.2,
            markersize=6,
            label="measured DH pose",
        )
        self._joint_scatter = self.ax.scatter(
            initial_path[:, 0],
            initial_path[:, 1],
            initial_path[:, 2],
            s=42,
            color="black",
            depthshade=False,
        )
        self._foot_scatter = self.ax.scatter(
            [initial_path[-1, 0]],
            [initial_path[-1, 1]],
            [initial_path[-1, 2]],
            s=90,
            color="tab:green",
            edgecolor="black",
            linewidth=0.5,
            depthshade=False,
            label="measured end effector",
        )
        self._trail_scatter = self.ax.scatter([], [], [], s=14, color="tab:green", alpha=0.35, depthshade=False)
        self._status_text = self.ax.text2D(0.02, 0.02, "", transform=self.ax.transAxes, fontsize=9)
        self.ax.legend(loc="upper left")
        self._refresh_artists(DEFAULT_POSE)

    def _build_axes(self) -> None:
        self.ax.set_title("Live measured leg digital twin")
        self.ax.set_xlabel("X (mm)")
        self.ax.set_ylabel("Y (mm)")
        self.ax.set_zlabel("Z (mm)")
        set_fixed_workspace_axes(self.ax)
        self.ax.view_init(elev=24, azim=-58)
        self.ax.grid(True)

    @staticmethod
    def _leg_geometry(pose: LegPose) -> tuple[list[np.ndarray], np.ndarray]:
        transforms, origins = forward_kinematics(pose)
        return transforms, np.vstack(origins)

    def _redraw_coordinate_frames(self, transforms: list[np.ndarray]) -> None:
        for artist in self._frame_artists:
            artist.remove()
        self._frame_artists = []

        colours = ("tab:red", "tab:green", "tab:blue")
        for transform in transforms:
            origin = transform[:3, 3]
            axes = transform[:3, :3]
            for axis_index, colour in zip(range(3), colours, strict=True):
                direction = axes[:, axis_index]
                artist = self.ax.quiver(
                    origin[0],
                    origin[1],
                    origin[2],
                    direction[0],
                    direction[1],
                    direction[2],
                    length=FRAME_AXIS_SCALE_MM,
                    normalize=True,
                    color=colour,
                    linewidth=0.9,
                    alpha=0.8,
                )
                self._frame_artists.append(artist)

    def update(self, _frame_index: int) -> tuple[object, ...]:
        self._drain_statuses()
        self._drain_messages()

        pose = DEFAULT_POSE if self._latest_sample is None else self._latest_sample.raw_pose
        self._refresh_artists(pose)
        return (
            *self._workspace_scatters,
            self._leg_line,
            self._joint_scatter,
            self._foot_scatter,
            self._trail_scatter,
            self._status_text,
            *self._frame_artists,
        )

    def _drain_statuses(self) -> None:
        while True:
            try:
                self._latest_status = self._statuses.get_nowait()
            except queue.Empty:
                return

    def _drain_messages(self) -> None:
        processed = 0
        while processed < 500:
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                return
            processed += 1
            self._handle_message(message)

    def _handle_message(self, message: Message) -> None:
        if isinstance(message, CapabilitiesMessage):
            if message.device == self._device:
                self._latest_status = f"loaded capabilities for {message.device}"
            return

        if isinstance(message, EventMessage):
            if message.device == self._device:
                self._latest_status = f"event {message.severity}: {message.name}"
            return

        if isinstance(message, LogMessage):
            if message.device == self._device:
                self._latest_status = f"log {message.level}: {message.msg}"
            return

        try:
            sample = extract_measured_angle_sample(message, device=self._device, stream=self._stream)
        except ValueError as exc:
            self._latest_status = str(exc)
            return

        if sample is None:
            return

        self._latest_sample = sample
        _transforms, path = self._leg_geometry(sample.raw_pose)
        self._trail_points.append(path[-1])
        while len(self._trail_points) > self._trail_length:
            self._trail_points.pop(0)

    def _refresh_artists(self, pose: LegPose) -> None:
        transforms, path = self._leg_geometry(pose)
        sample = self._latest_sample
        warnings = [] if sample is None else servo_limit_warnings(sample.raw_pose)
        self._latest_warning = "; ".join(warnings)
        has_warning = bool(warnings)
        foot_colour = "tab:red" if has_warning else "tab:green"

        self._leg_line.set_data(path[:, 0], path[:, 1])
        self._leg_line.set_3d_properties(path[:, 2])
        self._joint_scatter._offsets3d = (path[:, 0], path[:, 1], path[:, 2])
        self._foot_scatter._offsets3d = ([path[-1, 0]], [path[-1, 1]], [path[-1, 2]])
        self._foot_scatter.set_facecolor(foot_colour)

        if self._show_trail and self._trail_points:
            trail = np.vstack(self._trail_points)
            self._trail_scatter._offsets3d = (trail[:, 0], trail[:, 1], trail[:, 2])
            self._trail_scatter.set_facecolor(foot_colour)
            self._trail_scatter.set_alpha(0.35)
        else:
            self._trail_scatter._offsets3d = ([], [], [])

        self._redraw_coordinate_frames(transforms)

        if sample is None:
            raw_angle_line = "servo raw: A=-- deg, B=-- deg, C=-- deg"
            model_angle_line = "DH model: theta1=-- deg, theta2=-- deg, theta3=-- deg"
            age_line = "no measured sample received"
        else:
            age_s = max(0.0, time.monotonic() - sample.received_at)
            dh_theta1_deg, dh_theta2_deg, dh_theta3_deg = dh_theta_angles_deg(sample.raw_pose)
            raw_angle_line = (
                f"servo raw: A={sample.raw_pose.theta1_deg:.1f} deg, "
                f"B={sample.raw_pose.theta2_deg:.1f} deg, "
                f"C={sample.raw_pose.theta3_deg:.1f} deg"
            )
            model_angle_line = (
                f"DH model: theta1={dh_theta1_deg:.1f} deg, "
                f"theta2={dh_theta2_deg:.1f} deg, "
                f"theta3={dh_theta3_deg:.1f} deg"
            )
            age_line = f"seq={sample.seq}, device t={sample.t_us / 1_000_000.0:.3f} s, age={age_s:.2f} s"

        foot = path[-1]
        foot_line = f"foot=({foot[0]:.1f}, {foot[1]:.1f}, {foot[2]:.1f}) mm"
        warning_line = f"\nWARNING: {self._latest_warning}" if self._latest_warning else ""
        self._status_text.set_text(
            f"{raw_angle_line}\n{model_angle_line}\n{foot_line}\n{age_line}\n{self._latest_status}{warning_line}"
        )
        self._status_text.set_color("firebrick" if has_warning else "black")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial port, for example /dev/ttyACM0. Auto-detected only if exactly one exists.")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="Serial baud rate.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="Serial read timeout in seconds.")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="DevLink device name.")
    parser.add_argument("--stream", default=DEFAULT_STREAM, help="DevLink angle telemetry stream.")
    parser.add_argument("--trail-length", type=int, default=200, help="Number of measured foot positions to keep.")
    parser.add_argument("--interval-ms", type=int, default=33, help="Matplotlib refresh interval.")
    parser.add_argument("--no-trail", action="store_true", help="Disable the fading foot trail.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        port = resolve_serial_port(args.port)
    except (RuntimeError, SerialUnavailableError) as exc:
        print(exc, file=sys.stderr)
        return 2

    messages: queue.Queue[Message] = queue.Queue()
    statuses: queue.Queue[str] = queue.Queue()
    reader = DevlinkReader(
        port=port,
        baud=args.baud,
        timeout=args.timeout,
        messages=messages,
        statuses=statuses,
    )
    plot = DigitalTwinPlot(
        device=args.device,
        stream=args.stream,
        messages=messages,
        statuses=statuses,
        trail_length=args.trail_length,
        show_trail=not args.no_trail,
    )

    reader.start()

    def stop_reader(_event: object | None = None) -> None:
        reader.stop()

    plot.fig.canvas.mpl_connect("close_event", stop_reader)
    live_animation = animation.FuncAnimation(
        plot.fig,
        plot.update,
        interval=max(1, args.interval_ms),
        blit=False,
        cache_frame_data=False,
    )

    try:
        plt.show()
    finally:
        # Keep a reference until after show() returns so Matplotlib does not
        # discard the animation timer.
        _ = live_animation
        reader.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
