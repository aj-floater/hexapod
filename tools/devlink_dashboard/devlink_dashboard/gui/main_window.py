from __future__ import annotations

import json

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..messages import (
    CapabilitiesMessage,
    CommandSpec,
    EventMessage,
    LogMessage,
    ParamSpec,
    RespMessage,
    SampleMessage,
)
from .controller import ConnectionConfig, GuiController

_PLOT_COLORS = (
    "#0b84f3",
    "#f39c12",
    "#19b36b",
    "#d64550",
    "#8a5cf6",
    "#00a4a6",
)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        controller: GuiController,
        *,
        initial_port: str | None = None,
        initial_baud: int = 115200,
        initial_timeout: float = 0.05,
        initial_record_path: str | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._initial_timeout = initial_timeout
        self._selected_device: str | None = None
        self._selected_stream: str | None = None
        self._current_command_specs: list[CommandSpec] = []
        self._current_param_specs: list[ParamSpec] = []
        self._command_widgets: dict[str, tuple[str, QtWidgets.QWidget]] = {}
        self._param_editors: dict[str, tuple[str, QtWidgets.QWidget]] = {}
        self._param_apply_buttons: dict[str, QtWidgets.QPushButton] = {}
        self._param_row_indexes: dict[str, int] = {}
        self._param_visual_states: dict[str, tuple[bool, bool]] = {}
        self._pending_param_values: dict[str, object] = {}
        self._param_apply_commands: dict[str, int] = {}
        self._apply_command_params: dict[int, str] = {}
        self._device_names: list[str] = []
        self._stream_names: list[str] = []
        self._param_schema: tuple[ParamSpec, ...] = ()
        self._stream_units: dict[str, str] = {}

        self.setWindowTitle("Devlink Dashboard")
        self.resize(1400, 900)

        self._build_ui()
        self._connect_signals()
        self._refresh_discovery_views()

        self._baud_spin.setValue(initial_baud)
        if initial_record_path is not None:
            self._record_checkbox.setChecked(True)
            self._record_path_edit.setText(initial_record_path)

        self._controller.refresh_ports()
        if initial_port is not None:
            self._pending_port = initial_port
        else:
            self._pending_port = None

    def connect_if_requested(self) -> None:
        if self._pending_port is None:
            return
        self._set_port_selection(self._pending_port)
        self._toggle_connection()
        self._pending_port = None

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        root_layout = QtWidgets.QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)
        self.setCentralWidget(central)

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(8)
        root_layout.addLayout(toolbar)

        toolbar.addWidget(QtWidgets.QLabel("Port"))
        self._port_combo = QtWidgets.QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.setMinimumWidth(280)
        toolbar.addWidget(self._port_combo)

        self._refresh_ports_button = QtWidgets.QPushButton("Refresh")
        toolbar.addWidget(self._refresh_ports_button)

        toolbar.addWidget(QtWidgets.QLabel("Baud"))
        self._baud_spin = QtWidgets.QSpinBox()
        self._baud_spin.setRange(1, 4_000_000)
        self._baud_spin.setValue(115200)
        toolbar.addWidget(self._baud_spin)

        self._record_checkbox = QtWidgets.QCheckBox("Record")
        toolbar.addWidget(self._record_checkbox)

        self._record_path_edit = QtWidgets.QLineEdit()
        self._record_path_edit.setPlaceholderText("session.jsonl")
        toolbar.addWidget(self._record_path_edit, 1)

        self._browse_button = QtWidgets.QPushButton("Browse")
        toolbar.addWidget(self._browse_button)

        self._connect_button = QtWidgets.QPushButton("Connect")
        toolbar.addWidget(self._connect_button)

        self._banner = QtWidgets.QLabel()
        self._banner.setVisible(False)
        self._banner.setWordWrap(True)
        self._banner.setMargin(6)
        root_layout.addWidget(self._banner)

        body_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        body_splitter.setChildrenCollapsible(False)
        root_layout.addWidget(body_splitter, 1)

        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(QtWidgets.QLabel("Devices"))
        self._device_list = QtWidgets.QListWidget()
        left_layout.addWidget(self._device_list, 1)

        left_layout.addWidget(QtWidgets.QLabel("Streams"))
        self._stream_list = QtWidgets.QListWidget()
        left_layout.addWidget(self._stream_list, 2)
        body_splitter.addWidget(left_panel)

        center_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        center_splitter.setChildrenCollapsible(False)

        plot_panel = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(8)
        self._plot_caption = QtWidgets.QLabel("No stream selected")
        plot_layout.addWidget(self._plot_caption)
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("#101822")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self._plot_widget.setLabel("bottom", "Device Time", units="us")
        plot_layout.addWidget(self._plot_widget, 1)
        center_splitter.addWidget(plot_panel)

        value_panel = QtWidgets.QWidget()
        value_layout = QtWidgets.QVBoxLayout(value_panel)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.setSpacing(8)
        value_layout.addWidget(QtWidgets.QLabel("Current Values"))
        self._value_table = QtWidgets.QTableWidget(0, 3)
        self._value_table.setHorizontalHeaderLabels(["Field", "Value", "Unit"])
        self._value_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._value_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._value_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._value_table.verticalHeader().setVisible(False)
        self._value_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._value_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        value_layout.addWidget(self._value_table, 1)
        center_splitter.addWidget(value_panel)

        body_splitter.addWidget(center_splitter)

        self._tab_widget = QtWidgets.QTabWidget()
        body_splitter.addWidget(self._tab_widget)

        self._params_tab = self._build_params_tab()
        self._commands_tab = self._build_commands_tab()
        self._events_tab = self._build_events_tab()
        self._logs_tab = self._build_logs_tab()
        self._raw_tab = self._build_raw_tab()

        self._tab_widget.addTab(self._params_tab, "Params")
        self._tab_widget.addTab(self._commands_tab, "Commands")
        self._tab_widget.addTab(self._events_tab, "Events")
        self._tab_widget.addTab(self._logs_tab, "Logs")
        self._tab_widget.addTab(self._raw_tab, "Raw NDJSON")

        body_splitter.setSizes([220, 720, 460])
        center_splitter.setSizes([560, 240])

        self.statusBar().showMessage("Ready")

    def _build_params_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._params_state_label = QtWidgets.QLabel("Waiting for device description…")
        self._params_state_label.setWordWrap(True)
        layout.addWidget(self._params_state_label)

        self._refresh_params_button = QtWidgets.QPushButton("Refresh Params")
        self._refresh_params_button.clicked.connect(self._refresh_params_from_device)
        layout.addWidget(self._refresh_params_button)

        self._param_table = QtWidgets.QTableWidget(0, 5)
        self._param_table.setHorizontalHeaderLabels(["Name", "Type", "Current", "Edit", "Action"])
        self._param_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._param_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._param_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._param_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._param_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._param_table.verticalHeader().setVisible(False)
        layout.addWidget(self._param_table, 1)
        return widget

    def _build_commands_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._command_combo = QtWidgets.QComboBox()
        layout.addWidget(self._command_combo)

        self._commands_state_label = QtWidgets.QLabel("Waiting for device description…")
        self._commands_state_label.setWordWrap(True)
        layout.addWidget(self._commands_state_label)

        self._command_form_container = QtWidgets.QWidget()
        self._command_form_layout = QtWidgets.QFormLayout(self._command_form_container)
        self._command_form_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._command_form_container)

        self._command_response_label = QtWidgets.QLabel("No command sent yet")
        self._command_response_label.setWordWrap(True)
        layout.addWidget(self._command_response_label)

        send_button = QtWidgets.QPushButton("Send Command")
        send_button.clicked.connect(self._send_selected_command)
        layout.addWidget(send_button)
        layout.addStretch(1)
        return widget

    def _build_events_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self._event_filter = QtWidgets.QComboBox()
        self._event_filter.addItems(["all", "debug", "info", "warn", "error"])
        layout.addWidget(self._event_filter)
        self._events_view = QtWidgets.QPlainTextEdit()
        self._events_view.setReadOnly(True)
        layout.addWidget(self._events_view, 1)
        return widget

    def _build_logs_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self._log_filter = QtWidgets.QComboBox()
        self._log_filter.addItems(["all", "debug", "info", "warn", "error"])
        layout.addWidget(self._log_filter)
        self._logs_view = QtWidgets.QPlainTextEdit()
        self._logs_view.setReadOnly(True)
        layout.addWidget(self._logs_view, 1)
        return widget

    def _build_raw_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self._raw_view = QtWidgets.QPlainTextEdit()
        self._raw_view.setReadOnly(True)
        self._raw_view.setMaximumBlockCount(2000)
        layout.addWidget(self._raw_view, 1)
        return widget

    def _connect_signals(self) -> None:
        self._refresh_ports_button.clicked.connect(self._controller.refresh_ports)
        self._browse_button.clicked.connect(self._choose_record_path)
        self._connect_button.clicked.connect(self._toggle_connection)
        self._device_list.currentTextChanged.connect(self._on_device_selected)
        self._stream_list.currentTextChanged.connect(self._on_stream_selected)
        self._command_combo.currentIndexChanged.connect(self._rebuild_command_form)
        self._event_filter.currentTextChanged.connect(self._refresh_events_view)
        self._log_filter.currentTextChanged.connect(self._refresh_logs_view)

        self._controller.ports_changed.connect(self._refresh_port_combo)
        self._controller.session_reset.connect(self._on_session_reset)
        self._controller.connection_state_changed.connect(self._on_connection_state_changed)
        self._controller.discovery_state_changed.connect(self._on_discovery_state_changed)
        self._controller.status_message.connect(self._show_status)
        self._controller.raw_line_received.connect(self._append_raw_line)
        self._controller.parse_error_received.connect(self._on_parse_error)
        self._controller.message_received.connect(self._on_message_received)

    def _show_status(self, message: str, *, error: bool = False) -> None:
        self.statusBar().showMessage(message, 5000)
        color = "#5c1f24" if error else "#1f3f5c"
        border = "#d64550" if error else "#0b84f3"
        self._banner.setStyleSheet(
            f"background-color: {color}; color: #f7f7f7; border: 1px solid {border}; border-radius: 4px;"
        )
        self._banner.setText(message)
        self._banner.setVisible(True)
        QtCore.QTimer.singleShot(5000, lambda: self._banner.setVisible(False))

    def _append_raw_line(self, line: str) -> None:
        self._raw_view.appendPlainText(line)

    def _on_parse_error(self, error: str) -> None:
        self._raw_view.appendPlainText(f"[parse-error] {error}")
        self._show_status(error, error=True)

    def _refresh_port_combo(self) -> None:
        current = self._selected_port()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        for port in self._controller.port_infos():
            label = port.device if not port.description else f"{port.device} - {port.description}"
            self._port_combo.addItem(label, port.device)
        self._port_combo.blockSignals(False)

        if current is not None:
            self._set_port_selection(current)
        elif self._port_combo.count() > 0:
            self._port_combo.setCurrentIndex(0)

    def _selected_port(self) -> str | None:
        data = self._port_combo.currentData()
        if isinstance(data, str):
            return data
        text = self._port_combo.currentText().strip()
        if text:
            return text.split(" - ", 1)[0]
        return None

    def _set_port_selection(self, port: str) -> None:
        for index in range(self._port_combo.count()):
            if self._port_combo.itemData(index) == port:
                self._port_combo.setCurrentIndex(index)
                return
        self._port_combo.setEditText(port)

    def _choose_record_path(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Choose Session Log",
            self._record_path_edit.text() or "session.jsonl",
            "JSON Lines (*.jsonl);;All Files (*)",
        )
        if path:
            self._record_checkbox.setChecked(True)
            self._record_path_edit.setText(path)

    def _toggle_connection(self) -> None:
        if self._controller.is_connected:
            self._controller.disconnect()
            return

        port = self._selected_port()
        if not port:
            self._show_status("choose a serial port first", error=True)
            return

        record_path = None
        if self._record_checkbox.isChecked():
            record_path = self._record_path_edit.text().strip()
            if not record_path:
                self._show_status("choose a record path or disable recording", error=True)
                return

        self._controller.connect_to(
            ConnectionConfig(
                port=port,
                baud=self._baud_spin.value(),
                timeout=self._initial_timeout,
                record_path=record_path,
            )
        )

    def _on_session_reset(self) -> None:
        self._selected_device = None
        self._selected_stream = None
        self._pending_param_values = {}
        self._param_apply_commands = {}
        self._apply_command_params = {}
        self._device_names = []
        self._stream_names = []
        self._param_schema = ()
        self._device_list.clear()
        self._stream_list.clear()
        self._plot_widget.clear()
        self._plot_caption.setText("No stream selected")
        self._value_table.setRowCount(0)
        self._param_table.setRowCount(0)
        self._events_view.clear()
        self._logs_view.clear()
        self._raw_view.clear()
        self._command_response_label.setText("No command sent yet")
        self._current_command_specs = []
        self._current_param_specs = []
        self._command_widgets = {}
        self._param_editors = {}
        self._param_apply_buttons = {}
        self._param_row_indexes = {}
        self._param_visual_states = {}
        self._command_combo.clear()
        self._refresh_discovery_views()

    def _on_connection_state_changed(self, connected: bool) -> None:
        self._connect_button.setText("Disconnect" if connected else "Connect")
        self._port_combo.setEnabled(not connected)
        self._baud_spin.setEnabled(not connected)
        self._refresh_ports_button.setEnabled(not connected)
        self._record_checkbox.setEnabled(not connected)
        self._record_path_edit.setEnabled(not connected)
        self._browse_button.setEnabled(not connected)
        self._refresh_discovery_views()

    def _on_discovery_state_changed(self, _state: str) -> None:
        self._refresh_discovery_views()

    def _refresh_device_list(self) -> None:
        selected = self._selected_device
        names = self._controller.runtime.device_names()
        if names == self._device_names:
            if selected not in names:
                self._selected_device = names[0] if names else None
            return

        self._device_names = list(names)
        blocker = QtCore.QSignalBlocker(self._device_list)
        self._device_list.clear()
        for name in names:
            self._device_list.addItem(name)

        if selected in names:
            self._device_list.setCurrentRow(names.index(selected))
            self._selected_device = selected
            return
        if names:
            self._device_list.setCurrentRow(0)
            self._selected_device = names[0]
        else:
            self._selected_device = None
        del blocker

    def _refresh_stream_list(self) -> None:
        selected = self._selected_stream
        names = self._controller.runtime.stream_names_for_device(self._selected_device)
        if names == self._stream_names:
            if selected not in names:
                self._selected_stream = names[0] if names else None
            return

        self._stream_names = list(names)
        blocker = QtCore.QSignalBlocker(self._stream_list)
        self._stream_list.clear()
        for name in names:
            self._stream_list.addItem(name)

        if selected in names:
            self._stream_list.setCurrentRow(names.index(selected))
            self._selected_stream = selected
            return
        if names:
            self._stream_list.setCurrentRow(0)
            self._selected_stream = names[0]
        else:
            self._selected_stream = None
        del blocker

    def _on_device_selected(self, device: str) -> None:
        previous_device = self._selected_device
        self._selected_device = device or None
        if previous_device != self._selected_device:
            self._param_visual_states = {}
            self._pending_param_values = {}
            self._param_apply_commands = {}
            self._apply_command_params = {}
            self._stream_names = []
            self._param_schema = ()
        self._refresh_stream_list()
        self._refresh_params_table()
        self._refresh_command_specs()
        self._refresh_events_view()
        self._refresh_logs_view()
        self._refresh_plot_and_values()
        self._refresh_discovery_views()

    def _on_stream_selected(self, stream_name: str) -> None:
        self._selected_stream = stream_name or None
        self._refresh_plot_and_values()

    def _on_message_received(self, message: object) -> None:
        self._refresh_device_list()

        if isinstance(message, CapabilitiesMessage):
            if self._selected_device is None:
                self._selected_device = message.device
            self._refresh_stream_list()
            self._refresh_params_table()
            self._refresh_command_specs()
            self._show_status(f"loaded capabilities for {message.device}")
        elif isinstance(message, SampleMessage):
            if self._selected_device == message.device and (
                self._selected_stream is None or self._selected_stream == message.stream
            ):
                if self._selected_stream is None:
                    self._selected_stream = message.stream
                    self._refresh_stream_list()
                self._refresh_plot_and_values()
        elif isinstance(message, RespMessage):
            param_name = self._apply_command_params.pop(message.id, None)
            if param_name is not None and self._param_apply_commands.get(param_name) == message.id:
                self._param_apply_commands.pop(param_name, None)
            suffix = ""
            if message.ok and message.result is not None:
                suffix = f" result={dict(message.result)}"
            elif not message.ok and message.error is not None:
                suffix = f" error={message.error.code}: {message.error.message}"
            self._command_response_label.setText(f"resp id={message.id} ok={message.ok}{suffix}")
            self._refresh_params_table()
        elif isinstance(message, EventMessage):
            self._refresh_events_view()
        elif isinstance(message, LogMessage):
            self._refresh_logs_view()
        self._refresh_discovery_views()

    def _stream_units_for_selected(self) -> dict[str, str]:
        units: dict[str, str] = {}
        stream_spec = self._controller.runtime.get_stream_spec(self._selected_device, self._selected_stream)
        if stream_spec is None:
            return units
        for field in stream_spec.fields:
            units[field.name] = field.unit
        return units

    def _refresh_plot_and_values(self) -> None:
        self._plot_widget.clear()
        self._stream_units = self._stream_units_for_selected()

        if self._selected_device is None or self._selected_stream is None:
            self._plot_caption.setText("No stream selected")
            self._value_table.setRowCount(0)
            return

        field_names = self._controller.runtime.numeric_field_names(self._selected_device, self._selected_stream)
        if field_names:
            self._plot_caption.setText(
                f"{self._selected_device} / {self._selected_stream} ({', '.join(field_names)})"
            )
        else:
            self._plot_caption.setText(f"{self._selected_device} / {self._selected_stream} (no numeric fields)")

        for index, field_name in enumerate(field_names):
            x_values, y_values = self._controller.runtime.series_for_field(
                self._selected_device,
                self._selected_stream,
                field_name,
            )
            if not x_values:
                continue
            pen = pg.mkPen(_PLOT_COLORS[index % len(_PLOT_COLORS)], width=2)
            self._plot_widget.plot(x_values, y_values, pen=pen)

        values = self._controller.runtime.latest_stream_values(self._selected_device, self._selected_stream)
        items = list(values.items())
        self._value_table.setRowCount(len(items))
        for row, (field_name, value) in enumerate(items):
            self._value_table.setItem(row, 0, QtWidgets.QTableWidgetItem(field_name))
            self._value_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(value)))
            self._value_table.setItem(row, 2, QtWidgets.QTableWidgetItem(self._stream_units.get(field_name, "")))

    def _refresh_params_from_device(self) -> None:
        if self._selected_device is None:
            return
        self._controller.send_command(device=self._selected_device, name="param.list", args={})

    def _refresh_params_table(self) -> None:
        device_model = self._controller.runtime.get_device(self._selected_device)
        self._current_param_specs = list(self._controller.runtime.param_specs_for_device(self._selected_device))
        self._drop_satisfied_pending_params(device_model)
        next_schema = tuple(self._current_param_specs)
        if next_schema != self._param_schema:
            self._rebuild_params_table(device_model)
        else:
            self._refresh_existing_param_rows(device_model)
        self._refresh_discovery_views()

    def _rebuild_params_table(self, device_model) -> None:
        self._param_schema = tuple(self._current_param_specs)
        self._param_editors = {}
        self._param_apply_buttons = {}
        self._param_row_indexes = {}
        self._param_visual_states = {}
        self._param_table.setRowCount(len(self._current_param_specs))

        for row, spec in enumerate(self._current_param_specs):
            self._param_row_indexes[spec.name] = row
            current_value = self._current_param_value(spec, device_model)
            editor_value = self._pending_param_values.get(spec.name, current_value)

            self._param_table.setItem(row, 0, QtWidgets.QTableWidgetItem(spec.name))
            self._param_table.setItem(row, 1, QtWidgets.QTableWidgetItem(spec.type))
            self._param_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(current_value)))

            editor_kind, editor = self._create_param_editor(spec, editor_value)
            self._connect_param_editor(spec.name, editor_kind, editor)
            self._param_editors[spec.name] = (editor_kind, editor)
            self._param_table.setCellWidget(row, 3, editor)

            if spec.access == "rw":
                button = QtWidgets.QPushButton("Apply")
                button.pressed.connect(lambda name=spec.name: self._apply_param(name))
                self._param_apply_buttons[spec.name] = button
                self._param_table.setCellWidget(row, 4, button)
            else:
                self._param_table.setItem(row, 4, QtWidgets.QTableWidgetItem("read-only"))
            self._update_param_row_state(spec.name)

    def _refresh_existing_param_rows(self, device_model) -> None:
        if self._param_table.rowCount() != len(self._current_param_specs):
            self._rebuild_params_table(device_model)
            return

        for row, spec in enumerate(self._current_param_specs):
            if self._param_row_indexes.get(spec.name) != row:
                self._rebuild_params_table(device_model)
                return

            current_value = self._current_param_value(spec, device_model)
            current_item = self._param_table.item(row, 2)
            if current_item is None:
                current_item = QtWidgets.QTableWidgetItem()
                self._param_table.setItem(row, 2, current_item)
            current_item.setText(str(current_value))

            editor_info = self._param_editors.get(spec.name)
            if editor_info is None:
                self._rebuild_params_table(device_model)
                return

            pending = spec.name in self._pending_param_values
            applying = spec.name in self._param_apply_commands
            if spec.access != "rw" or (not pending and not applying):
                self._set_param_editor_value(editor_info[0], editor_info[1], current_value)

            self._update_param_row_state(spec.name)

    def _create_param_editor(self, spec: ParamSpec, current_value: object) -> tuple[str, QtWidgets.QWidget]:
        if spec.access != "rw":
            label = QtWidgets.QLabel(str(current_value))
            return ("readonly", label)

        if spec.type == "bool":
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(bool(current_value))
            return ("bool", checkbox)

        if spec.type.startswith("f") or spec.type == "float":
            if spec.min is not None or spec.max is not None:
                editor = QtWidgets.QDoubleSpinBox()
                editor.setKeyboardTracking(False)
                editor.setDecimals(3)
                editor.setRange(
                    float(spec.min if spec.min is not None else -1_000_000.0),
                    float(spec.max if spec.max is not None else 1_000_000.0),
                )
                editor.setValue(float(current_value))
                return ("float_spin", editor)
            line_edit = QtWidgets.QLineEdit(str(current_value))
            return ("text", line_edit)

        if spec.min is not None or spec.max is not None:
            min_value = int(spec.min if spec.min is not None else -2_147_483_648)
            max_value = int(spec.max if spec.max is not None else 2_147_483_647)
            if min_value >= -2_147_483_648 and max_value <= 2_147_483_647:
                editor = QtWidgets.QSpinBox()
                editor.setKeyboardTracking(False)
                editor.setRange(min_value, max_value)
                editor.setValue(int(current_value))
                return ("int_spin", editor)

        line_edit = QtWidgets.QLineEdit(str(current_value))
        return ("text", line_edit)

    def _apply_param(self, param_name: str) -> None:
        editor_info = self._param_editors.get(param_name)
        if editor_info is None or self._selected_device is None:
            return
        if param_name in self._param_apply_commands:
            return

        kind, widget = editor_info
        try:
            if kind in {"int_spin", "float_spin"}:
                widget.interpretText()  # type: ignore[union-attr]
            raw_value = self._read_param_editor_value(kind, widget)
            if kind == "text":
                value = self._parse_text_scalar(str(raw_value))
            else:
                value = raw_value
        except ValueError as exc:
            self._show_status(f"invalid value for {param_name}: {exc}", error=True)
            return

        command_id = self._controller.send_command(
            device=self._selected_device,
            name="param.set",
            args={"param": param_name, "value": value},
        )
        if command_id is not None:
            self._param_apply_commands[param_name] = command_id
            self._apply_command_params[command_id] = param_name
            self._update_param_row_state(param_name)

    def _refresh_command_specs(self) -> None:
        self._current_command_specs = list(
            self._controller.runtime.command_specs_for_device(self._selected_device, include_reserved=False)
        )
        self._command_combo.blockSignals(True)
        self._command_combo.clear()
        for command in self._current_command_specs:
            self._command_combo.addItem(command.name)
        self._command_combo.blockSignals(False)
        self._rebuild_command_form()
        self._refresh_discovery_views()

    def _rebuild_command_form(self) -> None:
        while self._command_form_layout.count():
            item = self._command_form_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._command_widgets = {}
        index = self._command_combo.currentIndex()
        if index < 0 or index >= len(self._current_command_specs):
            self._command_response_label.setText("No command available for this device")
            return

        command = self._current_command_specs[index]
        for arg in command.args:
            if arg.type == "string":
                editor: QtWidgets.QWidget = QtWidgets.QLineEdit()
                kind = "string"
            elif arg.type == "integer":
                spin = QtWidgets.QSpinBox()
                spin.setRange(-2_147_483_648, 2_147_483_647)
                editor = spin
                kind = "integer"
            elif arg.type == "boolean":
                editor = QtWidgets.QCheckBox()
                kind = "boolean"
            else:
                line = QtWidgets.QLineEdit()
                line.setPlaceholderText("JSON value")
                editor = line
                kind = "json"
            self._command_form_layout.addRow(arg.name, editor)
            self._command_widgets[arg.name] = (kind, editor)
        self._command_response_label.setText(f"Ready to send {command.name}")
        self._refresh_discovery_views()

    def _send_selected_command(self) -> None:
        index = self._command_combo.currentIndex()
        if index < 0 or index >= len(self._current_command_specs) or self._selected_device is None:
            self._show_status("choose a device and command first", error=True)
            return

        command = self._current_command_specs[index]
        args: dict[str, object] = {}

        try:
            for arg in command.args:
                kind, widget = self._command_widgets[arg.name]
                if kind == "string":
                    value = widget.text()  # type: ignore[union-attr]
                    if arg.required and value == "":
                        raise ValueError(f"{arg.name} is required")
                elif kind == "integer":
                    value = widget.value()  # type: ignore[union-attr]
                elif kind == "boolean":
                    value = widget.isChecked()  # type: ignore[union-attr]
                else:
                    raw = widget.text().strip()  # type: ignore[union-attr]
                    if raw == "":
                        if arg.required:
                            raise ValueError(f"{arg.name} is required")
                        continue
                    value = json.loads(raw)
                args[arg.name] = value
        except (ValueError, json.JSONDecodeError) as exc:
            self._show_status(f"invalid command args: {exc}", error=True)
            return

        command_id = self._controller.send_command(
            device=self._selected_device,
            name=command.name,
            args=args,
        )
        if command_id is not None:
            self._command_response_label.setText(f"sent {command.name} id={command_id}")

    def _refresh_events_view(self) -> None:
        device_model = self._controller.runtime.get_device(self._selected_device)
        severity_filter = self._event_filter.currentText()
        lines: list[str] = []
        if device_model is not None:
            for event in device_model.events:
                if severity_filter != "all" and event.severity != severity_filter:
                    continue
                suffix = ""
                if event.data is not None:
                    suffix = f" data={dict(event.data)}"
                lines.append(f"{event.severity} {event.name}{suffix}")
        self._events_view.setPlainText("\n".join(lines))

    def _refresh_logs_view(self) -> None:
        device_model = self._controller.runtime.get_device(self._selected_device)
        level_filter = self._log_filter.currentText()
        lines: list[str] = []
        if device_model is not None:
            for log in device_model.logs:
                if level_filter != "all" and log.level != level_filter:
                    continue
                lines.append(f"{log.level} {log.msg}")
        self._logs_view.setPlainText("\n".join(lines))

    def _parse_text_scalar(self, raw: str) -> object:
        text = raw.strip()
        if text == "":
            raise ValueError("empty value")
        if text.lower() == "true":
            return True
        if text.lower() == "false":
            return False
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    def _blend_color(self, base: QtGui.QColor, accent: QtGui.QColor, mix: float) -> QtGui.QColor:
        mix = max(0.0, min(1.0, mix))
        return QtGui.QColor(
            round(base.red() + (accent.red() - base.red()) * mix),
            round(base.green() + (accent.green() - base.green()) * mix),
            round(base.blue() + (accent.blue() - base.blue()) * mix),
        )

    def _refresh_discovery_views(self) -> None:
        device_model = self._controller.runtime.get_device(self._selected_device)
        has_capabilities = device_model is not None and device_model.capabilities is not None

        if has_capabilities:
            params_message = "" if self._current_param_specs else "No parameters available for this device."
            commands_message = "" if self._current_command_specs else "No device-specific commands available."
        elif self._controller.discovery_state == "pending":
            params_message = "Waiting for device description…"
            commands_message = "Waiting for device description…"
        elif self._controller.discovery_state == "failed":
            params_message = "No capabilities received for this session. Try reset or update firmware."
            commands_message = "No capabilities received for this session. Try reset or update firmware."
        elif self._controller.is_connected:
            params_message = "Waiting for device traffic…"
            commands_message = "Waiting for device traffic…"
        else:
            params_message = "Connect to a device to load parameters."
            commands_message = "Connect to a device to load commands."

        self._params_state_label.setVisible(bool(params_message))
        self._params_state_label.setText(params_message)
        self._refresh_params_button.setEnabled(has_capabilities and self._controller.is_connected)
        self._param_table.setEnabled(has_capabilities)

        self._commands_state_label.setVisible(bool(commands_message))
        self._commands_state_label.setText(commands_message)
        self._command_combo.setEnabled(has_capabilities and bool(self._current_command_specs))
        self._command_form_container.setEnabled(has_capabilities and bool(self._current_command_specs))

    def _current_param_value(self, spec: ParamSpec, device_model) -> object:
        if device_model is None:
            return spec.default
        return device_model.params.get(spec.name, spec.default)

    def _connect_param_editor(self, param_name: str, kind: str, editor: QtWidgets.QWidget) -> None:
        if kind == "bool":
            editor.toggled.connect(lambda _checked, name=param_name: self._on_param_edited(name))  # type: ignore[union-attr]
        elif kind in {"int_spin", "float_spin"}:
            editor.valueChanged.connect(lambda _value, name=param_name: self._on_param_edited(name))  # type: ignore[union-attr]
            line_edit = editor.lineEdit()  # type: ignore[union-attr]
            if line_edit is not None:
                line_edit.textEdited.connect(
                    lambda text, name=param_name: self._on_param_text_edited(name, text)
                )
        elif kind == "text":
            editor.textChanged.connect(lambda _text, name=param_name: self._on_param_edited(name))  # type: ignore[union-attr]

    def _read_param_editor_value(self, kind: str, widget: QtWidgets.QWidget) -> object:
        if kind == "bool":
            return widget.isChecked()  # type: ignore[union-attr]
        if kind in {"int_spin", "float_spin"}:
            return widget.value()  # type: ignore[union-attr]
        if kind == "text":
            return widget.text()  # type: ignore[union-attr]
        raise ValueError(f"unsupported param editor kind {kind}")

    def _set_param_editor_value(self, kind: str, widget: QtWidgets.QWidget, value: object) -> None:
        if kind == "readonly":
            widget.setText(str(value))  # type: ignore[union-attr]
            return
        if kind == "bool":
            blocker = QtCore.QSignalBlocker(widget)
            widget.setChecked(bool(value))  # type: ignore[union-attr]
            del blocker
            return
        if kind == "int_spin":
            blocker = QtCore.QSignalBlocker(widget)
            widget.setValue(int(value))  # type: ignore[union-attr]
            del blocker
            return
        if kind == "float_spin":
            blocker = QtCore.QSignalBlocker(widget)
            widget.setValue(float(value))  # type: ignore[union-attr]
            del blocker
            return
        if kind == "text":
            blocker = QtCore.QSignalBlocker(widget)
            widget.setText(str(value))  # type: ignore[union-attr]
            del blocker
            return
        raise ValueError(f"unsupported param editor kind {kind}")

    def _normalize_pending_value(self, kind: str, value: object) -> object:
        if kind == "int_spin" and isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return value.strip()
        if kind == "float_spin" and isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return value.strip()
        if kind != "text":
            return value
        try:
            return self._parse_text_scalar(str(value))
        except ValueError:
            return str(value).strip()

    def _pending_matches_current(self, kind: str, pending_value: object, current_value: object) -> bool:
        normalized = self._normalize_pending_value(kind, pending_value)
        return normalized == current_value or str(normalized) == str(current_value)

    def _drop_satisfied_pending_params(self, device_model) -> None:
        active_names = {spec.name for spec in self._current_param_specs}
        for param_name in list(self._pending_param_values.keys()):
            spec = next((item for item in self._current_param_specs if item.name == param_name), None)
            if spec is None or param_name not in active_names:
                self._pending_param_values.pop(param_name, None)
                continue
            kind = self._editor_kind_for_spec(spec)
            current_value = self._current_param_value(spec, device_model)
            if self._pending_matches_current(kind, self._pending_param_values[param_name], current_value):
                self._pending_param_values.pop(param_name, None)

    def _editor_kind_for_spec(self, spec: ParamSpec) -> str:
        if spec.access != "rw":
            return "readonly"
        if spec.type == "bool":
            return "bool"
        if spec.type.startswith("f") or spec.type == "float":
            return "float_spin" if spec.min is not None or spec.max is not None else "text"
        if spec.min is not None or spec.max is not None:
            min_value = int(spec.min if spec.min is not None else -2_147_483_648)
            max_value = int(spec.max if spec.max is not None else 2_147_483_647)
            if min_value >= -2_147_483_648 and max_value <= 2_147_483_647:
                return "int_spin"
        return "text"

    def _on_param_edited(self, param_name: str) -> None:
        editor_info = self._param_editors.get(param_name)
        spec = next((item for item in self._current_param_specs if item.name == param_name), None)
        device_model = self._controller.runtime.get_device(self._selected_device)
        if editor_info is None or spec is None:
            return

        kind, widget = editor_info
        raw_value = self._read_param_editor_value(kind, widget)
        current_value = self._current_param_value(spec, device_model)
        if self._pending_matches_current(kind, raw_value, current_value):
            self._pending_param_values.pop(param_name, None)
        else:
            self._pending_param_values[param_name] = raw_value
        self._update_param_row_state(param_name)

    def _on_param_text_edited(self, param_name: str, raw_text: str) -> None:
        spec = next((item for item in self._current_param_specs if item.name == param_name), None)
        device_model = self._controller.runtime.get_device(self._selected_device)
        if spec is None:
            return

        kind = self._editor_kind_for_spec(spec)
        current_value = self._current_param_value(spec, device_model)
        if self._pending_matches_current(kind, raw_text, current_value):
            self._pending_param_values.pop(param_name, None)
        else:
            self._pending_param_values[param_name] = raw_text
        self._update_param_row_state(param_name)

    def _update_param_row_state(self, param_name: str) -> None:
        row = self._param_row_indexes.get(param_name)
        if row is None:
            return

        pending = param_name in self._pending_param_values
        applying = param_name in self._param_apply_commands
        state_key = (pending, applying)
        if self._param_visual_states.get(param_name) == state_key:
            return
        self._param_visual_states[param_name] = state_key
        palette = self._param_table.palette()
        base_color = palette.base().color()
        text_color = palette.text().color()
        orange = QtGui.QColor("#f39c12")
        cream = QtGui.QColor("#ffd7a0")
        blue = QtGui.QColor("#0b84f3")
        sky = QtGui.QColor("#a8d5ff")
        is_dark = base_color.lightness() < 128

        if applying:
            row_color = self._blend_color(base_color, blue, 0.20 if is_dark else 0.10)
            field_text_color = self._blend_color(text_color, sky if is_dark else blue, 0.28)
            border_color = self._blend_color(base_color, blue, 0.58 if is_dark else 0.72)
            editor_style = (
                f"background-color: {row_color.name()};"
                f"color: {field_text_color.name()};"
                f"border: 1px solid {border_color.name()};"
                "border-radius: 3px;"
            )
            button_style = (
                f"background-color: {row_color.name()};"
                f"color: {field_text_color.name()};"
                f"border: 1px solid {border_color.name()};"
                "border-radius: 4px;"
                "padding: 2px 8px;"
            )
        elif pending:
            row_color = self._blend_color(base_color, orange, 0.22 if is_dark else 0.12)
            field_text_color = self._blend_color(text_color, cream if is_dark else orange, 0.30)
            border_color = self._blend_color(base_color, orange, 0.60 if is_dark else 0.75)
            editor_style = (
                f"background-color: {row_color.name()};"
                f"color: {field_text_color.name()};"
                f"border: 1px solid {border_color.name()};"
                "border-radius: 3px;"
            )
            button_style = (
                f"background-color: {row_color.name()};"
                f"color: {field_text_color.name()};"
                f"border: 1px solid {border_color.name()};"
                "border-radius: 4px;"
                "padding: 2px 8px;"
            )
        else:
            row_color = base_color
            field_text_color = text_color
            editor_style = ""
            button_style = ""

        for column in range(3):
            item = self._param_table.item(row, column)
            if item is not None:
                item.setBackground(row_color)
                item.setForeground(field_text_color)

        editor_info = self._param_editors.get(param_name)
        if editor_info is not None:
            editor_info[1].setStyleSheet(editor_style)
            editor_info[1].setToolTip("Pending local edit" if pending else "")

        apply_button = self._param_apply_buttons.get(param_name)
        if apply_button is not None:
            apply_button.setText("Applying..." if applying else "Apply")
            apply_button.setEnabled(pending and self._selected_device is not None and not applying)
            apply_button.setStyleSheet(button_style)
            if applying:
                apply_button.setToolTip("Waiting for the board to confirm this change")
            elif pending:
                apply_button.setToolTip("Apply this pending edit to the board")
            else:
                apply_button.setToolTip("")
