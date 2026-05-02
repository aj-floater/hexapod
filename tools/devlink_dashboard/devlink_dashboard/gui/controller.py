from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore

from ..messages import (
    CapabilitiesMessage,
    CmdMessage,
    EventMessage,
    HelloMessage,
    LogMessage,
    ProtocolError,
    RespMessage,
    SampleMessage,
    build_cmd_message,
    parse_line_resilient,
)
from ..session import JsonlRecorder
from ..transport import SerialPortInfo, SerialTransport, SerialUnavailableError, list_serial_port_infos
from .runtime import DashboardRuntime

DISCOVERY_TIMEOUT_MS = 3000
DISCOVERY_RETRY_INTERVAL_MS = 250
MAX_LINES_PER_POLL = 200
OUTBOX_FLUSH_INTERVAL_MS = 5
MAX_MESSAGES_PER_FLUSH = 1


@dataclass(frozen=True)
class ConnectionConfig:
    port: str
    baud: int = 115200
    timeout: float = 0.05
    record_path: str | None = None


class ConnectionWorker(QtCore.QObject):
    connected = QtCore.Signal()
    disconnected = QtCore.Signal()
    recording_state_changed = QtCore.Signal(bool, str)
    raw_line_received = QtCore.Signal(str)
    message_received = QtCore.Signal(object)
    parse_error_received = QtCore.Signal(str, str)
    connection_error = QtCore.Signal(str)

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__()
        self._config = config
        self._transport: SerialTransport | None = None
        self._recorder: JsonlRecorder | None = None
        self._record_path: str | None = None
        self._timer: QtCore.QTimer | None = None
        self._outbox_timer: QtCore.QTimer | None = None
        self._outbox: list[CmdMessage] = []
        self._stopping = False

    @staticmethod
    def _format_line_for_display(line: bytes | str) -> str:
        if isinstance(line, str):
            return line

        if not line:
            return ""

        if line[0] == 0xA5:
            return f"<binary telemetry {line.hex()}>"

        return line.decode("utf-8", errors="replace")

    @QtCore.Slot()
    def start(self) -> None:
        try:
            self._transport = SerialTransport(
                self._config.port,
                baud=self._config.baud,
                timeout=self._config.timeout,
            )
            self._transport.open()
        except Exception as exc:
            self.connection_error.emit(str(exc))
            self._close()
            self.disconnected.emit()
            return

        if self._config.record_path:
            self._start_recording(self._config.record_path)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(max(10, int(self._config.timeout * 1000)))
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._outbox_timer = QtCore.QTimer(self)
        self._outbox_timer.setInterval(OUTBOX_FLUSH_INTERVAL_MS)
        self._outbox_timer.timeout.connect(self._flush_outbox)
        self.connected.emit()

    @QtCore.Slot()
    def stop(self) -> None:
        self._stopping = True
        self._close()
        self.disconnected.emit()

    @QtCore.Slot(str)
    def start_recording(self, record_path: str) -> None:
        if self._transport is None:
            self.connection_error.emit("transport is not open")
            return
        self._start_recording(record_path)

    @QtCore.Slot()
    def stop_recording(self) -> None:
        self._stop_recording()

    @QtCore.Slot(object)
    def send_message(self, message: object) -> None:
        if not isinstance(message, CmdMessage):
            return
        if self._transport is None:
            self.connection_error.emit("transport is not open")
            return
        self._outbox.append(message)
        if self._outbox_timer is not None and not self._outbox_timer.isActive():
            self._outbox_timer.start()
        self._flush_outbox()

    @QtCore.Slot()
    def _poll(self) -> None:
        if self._transport is None:
            return

        if self._outbox:
            self._flush_outbox()
            if self._outbox:
                return

        lines_read = 0
        while lines_read < MAX_LINES_PER_POLL:
            try:
                line = self._transport.readline()
            except Exception as exc:
                self.connection_error.emit(str(exc))
                self.stop()
                return

            if line is None:
                if self._outbox:
                    self._flush_outbox()
                return

            lines_read += 1
            self._handle_line(line)

            if self._outbox:
                self._flush_outbox()
                return

            try:
                if self._transport.pending_input_bytes() <= 0:
                    return
            except Exception as exc:
                self.connection_error.emit(str(exc))
                self.stop()
                return

        if self._outbox:
            self._flush_outbox()

    def _handle_line(self, line: bytes | str) -> None:
        display_line = self._format_line_for_display(line)

        if display_line == "":
            return

        self.raw_line_received.emit(display_line)

        try:
            message = parse_line_resilient(line)
        except ProtocolError as exc:
            cleaned = display_line.replace("\x00", "").strip()
            if cleaned == "" or not cleaned.startswith("{") or not cleaned.endswith("}"):
                return
            self.parse_error_received.emit(str(exc), display_line)
            return

        if self._recorder is not None:
            self._recorder.record_message(message)
        self.message_received.emit(message)

    def _close(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        if self._outbox_timer is not None:
            self._outbox_timer.stop()
            self._outbox_timer.deleteLater()
            self._outbox_timer = None
        self._outbox = []
        self._stop_recording()
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    @QtCore.Slot()
    def _flush_outbox(self) -> None:
        if self._transport is None or not self._outbox:
            if self._outbox_timer is not None:
                self._outbox_timer.stop()
            return

        sent = 0
        while self._outbox and sent < MAX_MESSAGES_PER_FLUSH:
            message = self._outbox.pop(0)
            try:
                if self._recorder is not None:
                    self._recorder.record_message(message)
                self._transport.send_message(message)
            except Exception as exc:
                self.connection_error.emit(str(exc))
                self.stop()
                return
            sent += 1

        if self._outbox:
            if self._outbox_timer is not None and not self._outbox_timer.isActive():
                self._outbox_timer.start()
        elif self._outbox_timer is not None:
            self._outbox_timer.stop()

    def _start_recording(self, record_path: str) -> None:
        if self._recorder is not None:
            return
        try:
            self._recorder = JsonlRecorder(record_path)
        except Exception as exc:
            self.connection_error.emit(str(exc))
            return
        self._record_path = record_path
        self.recording_state_changed.emit(True, record_path)

    def _stop_recording(self) -> None:
        if self._recorder is None:
            return
        self._recorder.close()
        self._recorder = None
        self._record_path = None
        self.recording_state_changed.emit(False, "")


class GuiController(QtCore.QObject):
    ports_changed = QtCore.Signal()
    session_reset = QtCore.Signal()
    connection_state_changed = QtCore.Signal(bool)
    recording_state_changed = QtCore.Signal(bool, str)
    discovery_state_changed = QtCore.Signal(str)
    status_message = QtCore.Signal(str)
    raw_line_received = QtCore.Signal(str)
    parse_error_received = QtCore.Signal(str)
    message_received = QtCore.Signal(object)

    _send_message_requested = QtCore.Signal(object)
    _stop_requested = QtCore.Signal()
    _start_recording_requested = QtCore.Signal(str)
    _stop_recording_requested = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.runtime = DashboardRuntime()
        self._ports: list[SerialPortInfo] = []
        self._thread: QtCore.QThread | None = None
        self._worker: ConnectionWorker | None = None
        self._current_config: ConnectionConfig | None = None
        self._recording_active = False
        self._recording_path: str | None = None
        self._discovery_state = "idle"
        self._discovery_command_id: int | None = None
        self._discovery_timer = QtCore.QTimer(self)
        self._discovery_timer.setSingleShot(True)
        self._discovery_timer.setInterval(DISCOVERY_TIMEOUT_MS)
        self._discovery_timer.timeout.connect(self._on_discovery_timeout)
        self._discovery_retry_timer = QtCore.QTimer(self)
        self._discovery_retry_timer.setInterval(DISCOVERY_RETRY_INTERVAL_MS)
        self._discovery_retry_timer.timeout.connect(self._send_discovery_request)

    @property
    def is_connected(self) -> bool:
        return self._worker is not None

    @property
    def discovery_state(self) -> str:
        return self._discovery_state

    @property
    def is_recording(self) -> bool:
        return self._recording_active

    @property
    def recording_path(self) -> str | None:
        return self._recording_path

    def port_infos(self) -> list[SerialPortInfo]:
        return list(self._ports)

    def refresh_ports(self) -> None:
        try:
            self._ports = list_serial_port_infos()
        except SerialUnavailableError as exc:
            self._ports = []
            self.status_message.emit(str(exc))
        self.ports_changed.emit()

    def connect_to(self, config: ConnectionConfig) -> None:
        if self.is_connected:
            self.disconnect()

        self._current_config = config
        thread = QtCore.QThread(self)
        worker = ConnectionWorker(config)
        worker.moveToThread(thread)

        thread.started.connect(worker.start)
        self._send_message_requested.connect(worker.send_message)
        self._stop_requested.connect(worker.stop)
        self._start_recording_requested.connect(worker.start_recording)
        self._stop_recording_requested.connect(worker.stop_recording)
        worker.connected.connect(self._on_connected)
        worker.disconnected.connect(self._on_disconnected)
        worker.recording_state_changed.connect(self._on_recording_state_changed)
        worker.raw_line_received.connect(self._on_raw_line)
        worker.parse_error_received.connect(self._on_parse_error)
        worker.message_received.connect(self._on_message)
        worker.connection_error.connect(self.status_message.emit)
        worker.disconnected.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()

    def disconnect(self) -> None:
        if self._worker is None:
            return
        self._stop_requested.emit()

    def start_recording(self, record_path: str) -> None:
        if self._worker is None:
            self.status_message.emit("not connected")
            return
        self._start_recording_requested.emit(record_path)

    def stop_recording(self) -> None:
        if self._worker is None:
            self.status_message.emit("not connected")
            return
        self._stop_recording_requested.emit()

    def send_command(self, *, device: str, name: str, args: dict[str, object] | None = None) -> int | None:
        if self._worker is None:
            self.status_message.emit("not connected")
            return None
        command_id = self.runtime.allocate_command_id()
        command = build_cmd_message(device=device, command_id=command_id, name=name, args=args or {})
        self._send_message_requested.emit(command)
        return command_id

    @QtCore.Slot()
    def _on_connected(self) -> None:
        self.runtime.reset_session()
        self.session_reset.emit()
        self._set_discovery_state("pending")
        self._discovery_timer.start()
        self._discovery_retry_timer.start()
        self._send_discovery_request()
        if self._current_config is not None:
            self.status_message.emit(
                f"connected to {self._current_config.port} @ {self._current_config.baud}"
            )
        self.connection_state_changed.emit(True)

    @QtCore.Slot()
    def _on_disconnected(self) -> None:
        self._discovery_timer.stop()
        self._discovery_retry_timer.stop()
        self._discovery_command_id = None
        self._set_discovery_state("idle")
        self._recording_active = False
        self._recording_path = None
        self.recording_state_changed.emit(False, "")
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(250)
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self.connection_state_changed.emit(False)
        self.status_message.emit("disconnected")

    @QtCore.Slot(str)
    def _on_raw_line(self, line: str) -> None:
        self.runtime.record_raw_line(line)
        self.raw_line_received.emit(line)

    @QtCore.Slot(str, str)
    def _on_parse_error(self, error: str, line: str) -> None:
        self.runtime.record_parse_error(error, line)
        self.parse_error_received.emit(error)

    @QtCore.Slot(object)
    def _on_message(self, message: object) -> None:
        if not isinstance(
            message,
            (HelloMessage, CapabilitiesMessage, RespMessage, EventMessage, SampleMessage, LogMessage),
        ):
            return

        self.runtime.apply_message(message)
        self.message_received.emit(message)

        if isinstance(message, CapabilitiesMessage):
            self._discovery_timer.stop()
            self._discovery_retry_timer.stop()
            self._discovery_command_id = None
            self._set_discovery_state("ready")
            self.send_command(device=message.device, name="param.list", args={})
        elif isinstance(message, RespMessage):
            if (
                self._discovery_command_id is not None and
                message.id == self._discovery_command_id and
                not message.ok and
                self._discovery_state != "ready"
            ):
                self.status_message.emit("device describe not accepted yet; retrying")

    @QtCore.Slot(bool, str)
    def _on_recording_state_changed(self, active: bool, record_path: str) -> None:
        was_active = self._recording_active
        previous_path = self._recording_path
        self._recording_active = active
        self._recording_path = record_path or None
        self.recording_state_changed.emit(active, record_path)
        if active and record_path:
            self.status_message.emit(f"recording to {record_path}")
        elif was_active and not active:
            if previous_path:
                self.status_message.emit(f"recording stopped: saved to {previous_path}")
            else:
                self.status_message.emit("recording stopped")

    @QtCore.Slot()
    def _on_discovery_timeout(self) -> None:
        if self._discovery_state == "ready":
            return
        self._discovery_retry_timer.stop()
        self._discovery_command_id = None
        self._set_discovery_state("failed")
        self.status_message.emit("no capabilities received; try reset or update firmware")

    @QtCore.Slot()
    def _send_discovery_request(self) -> None:
        if self._worker is None or self._discovery_state == "ready":
            return
        self._discovery_command_id = self.send_command(device="*", name="device.describe", args={})

    def _set_discovery_state(self, state: str) -> None:
        if self._discovery_state == state:
            return
        self._discovery_state = state
        self.discovery_state_changed.emit(state)
