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
    parse_line,
)
from ..session import JsonlRecorder
from ..transport import SerialPortInfo, SerialTransport, SerialUnavailableError, list_serial_port_infos
from .runtime import DashboardRuntime

DISCOVERY_TIMEOUT_MS = 1000


@dataclass(frozen=True)
class ConnectionConfig:
    port: str
    baud: int = 115200
    timeout: float = 0.05
    record_path: str | None = None


class ConnectionWorker(QtCore.QObject):
    connected = QtCore.Signal()
    disconnected = QtCore.Signal()
    raw_line_received = QtCore.Signal(str)
    message_received = QtCore.Signal(object)
    parse_error_received = QtCore.Signal(str, str)
    connection_error = QtCore.Signal(str)

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__()
        self._config = config
        self._transport: SerialTransport | None = None
        self._recorder: JsonlRecorder | None = None
        self._timer: QtCore.QTimer | None = None
        self._stopping = False

    @QtCore.Slot()
    def start(self) -> None:
        try:
            self._transport = SerialTransport(
                self._config.port,
                baud=self._config.baud,
                timeout=self._config.timeout,
            )
            self._transport.open()
            if self._config.record_path:
                self._recorder = JsonlRecorder(self._config.record_path)
        except Exception as exc:
            self.connection_error.emit(str(exc))
            self._close()
            self.disconnected.emit()
            return

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(max(10, int(self._config.timeout * 1000)))
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self.connected.emit()

    @QtCore.Slot()
    def stop(self) -> None:
        self._stopping = True
        self._close()
        self.disconnected.emit()

    @QtCore.Slot(object)
    def send_message(self, message: object) -> None:
        if not isinstance(message, CmdMessage):
            return
        if self._transport is None:
            self.connection_error.emit("transport is not open")
            return
        try:
            if self._recorder is not None:
                self._recorder.record_message(message)
            self._transport.send_message(message)
        except Exception as exc:
            self.connection_error.emit(str(exc))
            self.stop()

    @QtCore.Slot()
    def _poll(self) -> None:
        if self._transport is None:
            return

        try:
            line = self._transport.readline()
        except Exception as exc:
            self.connection_error.emit(str(exc))
            self.stop()
            return

        if line is None or line == "":
            return

        if self._recorder is not None:
            self._recorder.record_line(line)
        self.raw_line_received.emit(line)

        try:
            message = parse_line(line)
        except ProtocolError as exc:
            self.parse_error_received.emit(str(exc), line)
            return

        self.message_received.emit(message)

    def _close(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        if self._recorder is not None:
            self._recorder.close()
            self._recorder = None
        if self._transport is not None:
            self._transport.close()
            self._transport = None


class GuiController(QtCore.QObject):
    ports_changed = QtCore.Signal()
    session_reset = QtCore.Signal()
    connection_state_changed = QtCore.Signal(bool)
    discovery_state_changed = QtCore.Signal(str)
    status_message = QtCore.Signal(str)
    raw_line_received = QtCore.Signal(str)
    parse_error_received = QtCore.Signal(str)
    message_received = QtCore.Signal(object)

    _send_message_requested = QtCore.Signal(object)
    _stop_requested = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.runtime = DashboardRuntime()
        self._ports: list[SerialPortInfo] = []
        self._thread: QtCore.QThread | None = None
        self._worker: ConnectionWorker | None = None
        self._current_config: ConnectionConfig | None = None
        self._discovery_state = "idle"
        self._discovery_command_id: int | None = None
        self._discovery_timer = QtCore.QTimer(self)
        self._discovery_timer.setSingleShot(True)
        self._discovery_timer.setInterval(DISCOVERY_TIMEOUT_MS)
        self._discovery_timer.timeout.connect(self._on_discovery_timeout)

    @property
    def is_connected(self) -> bool:
        return self._worker is not None

    @property
    def discovery_state(self) -> str:
        return self._discovery_state

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
        worker.connected.connect(self._on_connected)
        worker.disconnected.connect(self._on_disconnected)
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
        self._discovery_command_id = self.send_command(device="*", name="device.describe", args={})
        if self._current_config is not None:
            self.status_message.emit(
                f"connected to {self._current_config.port} @ {self._current_config.baud}"
            )
        self.connection_state_changed.emit(True)

    @QtCore.Slot()
    def _on_disconnected(self) -> None:
        self._discovery_timer.stop()
        self._discovery_command_id = None
        self._set_discovery_state("idle")
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
                self._discovery_timer.stop()
                self._discovery_command_id = None
                self._set_discovery_state("failed")
                self.status_message.emit("device description unavailable; try reset or update firmware")

    @QtCore.Slot()
    def _on_discovery_timeout(self) -> None:
        if self._discovery_state == "ready":
            return
        self._discovery_command_id = None
        self._set_discovery_state("failed")
        self.status_message.emit("no capabilities received; try reset or update firmware")

    def _set_discovery_state(self, state: str) -> None:
        if self._discovery_state == state:
            return
        self._discovery_state = state
        self.discovery_state_changed.emit(state)
