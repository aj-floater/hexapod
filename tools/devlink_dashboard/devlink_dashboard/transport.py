from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .bus import MessageBus
from .messages import CmdMessage, Message, parse_line_resilient, serialize_message
from .session import JsonlRecorder


class SerialUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class SerialPortInfo:
    device: str
    description: str


class SerialTransport:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.1) -> None:
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._serial = None

    @staticmethod
    def _require_serial():
        try:
            import serial  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SerialUnavailableError(
                "pyserial is required for live serial transport; install tools/devlink_dashboard[serial]"
            ) from exc
        return serial

    def open(self) -> None:
        serial = self._require_serial()
        self._serial = serial.Serial(self.port, self.baud, timeout=self.timeout)
        self._resynchronize_input()

    def _resynchronize_input(self) -> None:
        if self._serial is None:
            return

        reset_input = getattr(self._serial, "reset_input_buffer", None)
        if callable(reset_input):
            reset_input()

        reset_output = getattr(self._serial, "reset_output_buffer", None)
        if callable(reset_output):
            reset_output()

        read_until = getattr(self._serial, "read_until", None)
        if callable(read_until):
            try:
                read_until(b"\n")
            except Exception:
                pass

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def readline(self) -> str | None:
        if self._serial is None:
            raise RuntimeError("transport is not open")
        raw = self._serial.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="replace").rstrip("\r\n")

    def pending_input_bytes(self) -> int:
        if self._serial is None:
            raise RuntimeError("transport is not open")
        waiting = getattr(self._serial, "in_waiting", 0)
        try:
            return int(waiting)
        except (TypeError, ValueError):
            return 0

    def send_line(self, line: str) -> None:
        if self._serial is None:
            raise RuntimeError("transport is not open")
        self._serial.write(line.rstrip("\r\n").encode("utf-8") + b"\n")
        self._serial.flush()

    def send_message(self, message: CmdMessage) -> None:
        self.send_line(serialize_message(message))

    def __enter__(self) -> "SerialTransport":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def list_serial_port_infos() -> list[SerialPortInfo]:
    SerialTransport._require_serial()
    try:
        from serial.tools import list_ports  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SerialUnavailableError(
            "pyserial is required for live serial transport; install tools/devlink_dashboard[serial]"
        ) from exc
    return [
        SerialPortInfo(
            device=port.device,
            description=getattr(port, "description", "") or "",
        )
        for port in list_ports.comports()
    ]


def list_serial_ports() -> list[str]:
    return [port.device for port in list_serial_port_infos()]


@dataclass
class SerialPump:
    transport: SerialTransport
    bus: MessageBus | None = None
    recorder: JsonlRecorder | None = None

    def pump_once(self) -> Message | None:
        line = self.transport.readline()
        if line is None or line == "":
            return None
        if self.recorder is not None:
            self.recorder.record_line(line)
        message = parse_line_resilient(line)
        if self.bus is not None:
            self.bus.publish(message)
        return message

    def drain(self, limit: int | None = None) -> Iterable[Message]:
        seen = 0
        while limit is None or seen < limit:
            message = self.pump_once()
            if message is None:
                break
            seen += 1
            yield message
