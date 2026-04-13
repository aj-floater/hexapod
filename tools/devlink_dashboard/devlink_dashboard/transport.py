from __future__ import annotations

import time
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
        self._rx_buffer = bytearray()

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
        self._rx_buffer.clear()
        self._resynchronize_input()

    def _resynchronize_input(self) -> None:
        if self._serial is None:
            return

        reset_output = getattr(self._serial, "reset_output_buffer", None)
        if callable(reset_output):
            reset_output()

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None
        self._rx_buffer.clear()

    def _serial_pending_input_bytes(self) -> int:
        if self._serial is None:
            raise RuntimeError("transport is not open")
        waiting = getattr(self._serial, "in_waiting", 0)
        try:
            return int(waiting)
        except (TypeError, ValueError):
            return 0

    def _pop_buffered_line(self) -> bytes | None:
        terminator_index = self._rx_buffer.find(b"\r\n")
        if terminator_index < 0:
            return None

        line = bytes(self._rx_buffer[:terminator_index])
        del self._rx_buffer[:terminator_index + 2]
        return line

    def readline(self) -> bytes | None:
        if self._serial is None:
            raise RuntimeError("transport is not open")

        line = self._pop_buffered_line()
        if line is not None:
            return line

        last_activity_at = time.monotonic()
        while True:
            read_size = self._serial_pending_input_bytes()
            if read_size <= 0:
                read_size = 1

            raw = self._serial.read(read_size)
            if raw:
                self._rx_buffer.extend(raw)
                last_activity_at = time.monotonic()
                line = self._pop_buffered_line()
                if line is not None:
                    return line
                continue

            if time.monotonic() - last_activity_at >= self.timeout:
                return None

    def pending_input_bytes(self) -> int:
        return len(self._rx_buffer) + self._serial_pending_input_bytes()

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
        if line is None or line == b"":
            return None
        message = parse_line_resilient(line)
        if self.recorder is not None:
            self.recorder.record_message(message)
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
