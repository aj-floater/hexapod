from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

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
from .plot_workspace import PlotWorkspaceWidget
from .workspace import PlotWorkspace, WindowLayout, WindowLayoutStore, WorkspaceStore, default_trace_color

PARAM_APPLY_TIMEOUT_MS = 5000
PARAM_APPLY_MAX_ATTEMPTS = 3
LIVE_REFRESH_INTERVAL_MS = 33
RAW_VIEW_REFRESH_INTERVAL_MS = 100


class InlineIndicatorButton(QtWidgets.QPushButton):
    def __init__(self, prefix: str, suffix: str, indicator_color: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__("", parent)
        self._prefix = prefix
        self._suffix = suffix
        self._indicator_color = QtGui.QColor(indicator_color)

    def set_segments(self, prefix: str, suffix: str, indicator_color: str) -> None:
        self._prefix = prefix
        self._suffix = suffix
        self._indicator_color = QtGui.QColor(indicator_color)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QtCore.QSize:
        base = super().sizeHint()
        fm = self.fontMetrics()
        indicator = 10
        gap = 6
        width = (
            fm.horizontalAdvance(self._prefix)
            + gap
            + indicator
            + gap
            + fm.horizontalAdvance(self._suffix)
            + 24
        )
        height = max(base.height(), fm.height() + 14)
        return QtCore.QSize(width, height)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        option.icon = QtGui.QIcon()
        painter.drawControl(QtWidgets.QStyle.ControlElement.CE_PushButton, option)

        contents = self.style().subElementRect(
            QtWidgets.QStyle.SubElement.SE_PushButtonContents,
            option,
            self,
        )
        fm = painter.fontMetrics()
        indicator = 10
        gap = 6
        prefix_width = fm.horizontalAdvance(self._prefix)
        suffix_width = fm.horizontalAdvance(self._suffix)
        total_width = prefix_width + gap + indicator + gap + suffix_width
        x = contents.x() + max(0, (contents.width() - total_width) // 2)
        baseline = contents.y() + (contents.height() + fm.ascent() - fm.descent()) // 2

        if not self.isEnabled():
            painter.setOpacity(0.55)

        text_color = self.palette().buttonText().color()
        painter.setPen(text_color)
        painter.drawText(x, baseline, self._prefix)
        x += prefix_width + gap

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self._indicator_color)
        circle_y = contents.y() + (contents.height() - indicator) // 2
        painter.drawEllipse(QtCore.QRectF(x, circle_y, indicator, indicator))
        x += indicator + gap

        painter.setPen(text_color)
        painter.drawText(x, baseline, self._suffix)


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
        self._workspace: PlotWorkspace | None = None
        self._workspace_loaded_from_store = False
        self._workspace_user_modified = False
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
        self._param_apply_timers: dict[str, QtCore.QTimer] = {}
        self._param_apply_attempts: dict[str, int] = {}
        self._param_apply_values: dict[str, object] = {}
        self._live_refresh_timer = QtCore.QTimer(self)
        self._live_refresh_timer.setSingleShot(True)
        self._live_refresh_timer.setInterval(LIVE_REFRESH_INTERVAL_MS)
        self._live_refresh_timer.timeout.connect(self._flush_live_refresh)
        self._plot_refresh_pending = False
        self._raw_view_timer = QtCore.QTimer(self)
        self._raw_view_timer.setSingleShot(True)
        self._raw_view_timer.setInterval(RAW_VIEW_REFRESH_INTERVAL_MS)
        self._raw_view_timer.timeout.connect(self._flush_raw_view)
        self._pending_raw_lines: list[str] = []
        self._device_names: list[str] = []
        self._stream_names: list[str] = []
        self._field_names: list[str] = []
        self._param_schema: tuple[ParamSpec, ...] = ()
        self._workspace_store = WorkspaceStore()
        self._window_layout_store = WindowLayoutStore()

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

    def _configure_button(
        self,
        button: QtWidgets.QAbstractButton,
        *,
        icon: QtWidgets.QStyle.StandardPixmap | None = None,
        text: str | None = None,
        tooltip: str | None = None,
    ) -> None:
        if icon is not None:
            button.setIcon(self.style().standardIcon(icon))
        if text is not None:
            button.setText(text)
        if tooltip is not None:
            button.setToolTip(tooltip)
            button.setStatusTip(tooltip)

    def _active_pane_details(self) -> tuple[PlotWorkspace | None, object | None, str, str]:
        workspace = self._workspace
        active_id = self._plot_workspace.active_pane_id
        if workspace is None or active_id is None:
            return (workspace, None, "Trace", "#8b96a5")
        for index, pane in enumerate(workspace.panes):
            if pane.id == active_id:
                return (workspace, pane, pane.title, default_trace_color(index))
        return (workspace, None, "Trace", "#8b96a5")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._save_workspace_snapshot()
        self._save_window_layout()
        super().closeEvent(event)

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
        self._configure_button(
            self._refresh_ports_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload,
            text="",
            tooltip="Refresh serial ports",
        )
        toolbar.addWidget(self._refresh_ports_button)

        toolbar.addWidget(QtWidgets.QLabel("Baud"))
        self._baud_spin = QtWidgets.QSpinBox()
        self._baud_spin.setRange(1, 4_000_000)
        self._baud_spin.setValue(115200)
        toolbar.addWidget(self._baud_spin)

        self._record_checkbox = QtWidgets.QCheckBox("Record")
        toolbar.addWidget(self._record_checkbox)

        self._record_path_edit = QtWidgets.QLineEdit()
        self._record_path_edit.setPlaceholderText("recordings/")
        toolbar.addWidget(self._record_path_edit, 1)

        self._browse_button = QtWidgets.QPushButton("Browse")
        self._configure_button(
            self._browse_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_DialogOpenButton,
            text="",
            tooltip="Choose session log file",
        )
        toolbar.addWidget(self._browse_button)

        self._connect_button = QtWidgets.QPushButton("Connect")
        self._configure_button(
            self._connect_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_MediaPlay,
            text="Connect",
            tooltip="Connect to the selected serial device",
        )
        toolbar.addWidget(self._connect_button)

        self._banner = QtWidgets.QLabel()
        self._banner.setVisible(False)
        self._banner.setWordWrap(True)
        self._banner.setMargin(6)

        self._body_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self._body_splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self._body_splitter, 1)

        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(QtWidgets.QLabel("Devices"))
        self._device_list = QtWidgets.QListWidget()
        left_layout.addWidget(self._device_list, 1)

        left_layout.addWidget(QtWidgets.QLabel("Streams"))
        self._stream_list = QtWidgets.QListWidget()
        left_layout.addWidget(self._stream_list, 1)

        left_layout.addWidget(QtWidgets.QLabel("Fields"))
        self._field_list = QtWidgets.QListWidget()
        self._field_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        left_layout.addWidget(self._field_list, 1)

        self._add_trace_button = InlineIndicatorButton("Add Selected Trace to", "", "#8b96a5")
        self._add_trace_button.setToolTip("Add the selected field to the active pane")
        left_layout.addWidget(self._add_trace_button)
        self._body_splitter.addWidget(left_panel)

        plot_panel = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(8)

        workspace_toolbar = QtWidgets.QHBoxLayout()
        workspace_toolbar.setSpacing(6)
        self._workspace_label = QtWidgets.QLabel("No plot workspace loaded")
        workspace_toolbar.addWidget(self._workspace_label, 1)
        self._add_pane_button = QtWidgets.QPushButton("Add Pane")
        self._configure_button(
            self._add_pane_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_FileDialogNewFolder,
            text="Add Pane",
            tooltip="Add a new plot pane",
        )
        workspace_toolbar.addWidget(self._add_pane_button)
        self._duplicate_pane_button = QtWidgets.QPushButton("Duplicate Pane")
        self._configure_button(
            self._duplicate_pane_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView,
            text="Duplicate Pane",
            tooltip="Duplicate the active pane",
        )
        workspace_toolbar.addWidget(self._duplicate_pane_button)
        self._remove_pane_button = QtWidgets.QPushButton("Remove Pane")
        self._configure_button(
            self._remove_pane_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_DialogDiscardButton,
            text="Remove Pane",
            tooltip="Remove the active pane",
        )
        workspace_toolbar.addWidget(self._remove_pane_button)
        plot_layout.addLayout(workspace_toolbar)

        self._plot_workspace = PlotWorkspaceWidget()
        plot_layout.addWidget(self._plot_workspace, 1)
        self._body_splitter.addWidget(plot_panel)

        self._tab_widget = QtWidgets.QTabWidget()
        self._body_splitter.addWidget(self._tab_widget)

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
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        self._body_splitter.setSizes([220, 860, 360])
        root_layout.addWidget(self._banner)
        self._restore_window_layout()

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
        self._configure_button(
            self._refresh_params_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload,
            text="Refresh Params",
            tooltip="Read current parameter values from the device",
        )
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

        self._send_command_button = QtWidgets.QPushButton("Send Command")
        self._configure_button(
            self._send_command_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_ArrowForward,
            text="Send Command",
            tooltip="Send the selected command to the device",
        )
        self._send_command_button.clicked.connect(self._send_selected_command)
        layout.addWidget(self._send_command_button)
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
        self._field_list.currentTextChanged.connect(lambda _text: self._refresh_discovery_views())
        self._field_list.itemDoubleClicked.connect(lambda _item: self._add_selected_field_to_active_pane())
        self._add_trace_button.clicked.connect(self._add_selected_field_to_active_pane)
        self._add_pane_button.clicked.connect(self._plot_workspace.add_pane)
        self._duplicate_pane_button.clicked.connect(self._plot_workspace.duplicate_active_pane)
        self._remove_pane_button.clicked.connect(self._confirm_remove_active_pane)
        self._command_combo.currentIndexChanged.connect(self._rebuild_command_form)
        self._event_filter.currentTextChanged.connect(self._refresh_events_view)
        self._log_filter.currentTextChanged.connect(self._refresh_logs_view)
        self._plot_workspace.workspace_changed.connect(self._on_workspace_changed)
        self._plot_workspace.add_trace_requested.connect(lambda _pane_id: self._add_selected_field_to_active_pane())
        self._plot_workspace.active_pane_changed.connect(lambda _pane_id: self._refresh_discovery_views())

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
        self._pending_raw_lines.append(line)
        if self._tab_widget.currentWidget() is self._raw_tab and not self._raw_view_timer.isActive():
            self._raw_view_timer.start()

    def _on_parse_error(self, error: str) -> None:
        self._pending_raw_lines.append(f"[host-sync] {error}")
        if self._tab_widget.currentWidget() is self._raw_tab and not self._raw_view_timer.isActive():
            self._raw_view_timer.start()
        if self._tab_widget.currentWidget() is self._logs_tab:
            self._refresh_logs_view()

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
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Choose Recording Directory",
            self._record_path_edit.text() or str(Path.cwd()),
        )
        if path:
            self._record_checkbox.setChecked(True)
            self._record_path_edit.setText(path)

    def _build_record_output_path(self, directory_text: str, port: str) -> str:
        directory = Path(directory_text).expanduser()
        port_name = Path(port).name or "serial"
        safe_port_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in port_name)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"devlink-{safe_port_name}-{timestamp}.jsonl"
        return str(directory / filename)

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
            record_directory = self._record_path_edit.text().strip()
            if not record_directory:
                self._show_status("choose a recording directory or disable recording", error=True)
                return
            record_path = self._build_record_output_path(record_directory, port)

        self._controller.connect_to(
            ConnectionConfig(
                port=port,
                baud=self._baud_spin.value(),
                timeout=self._initial_timeout,
                record_path=record_path,
            )
        )

    def _on_session_reset(self) -> None:
        self._live_refresh_timer.stop()
        self._plot_refresh_pending = False
        self._raw_view_timer.stop()
        self._pending_raw_lines = []
        self._clear_all_param_apply_timers()
        self._selected_device = None
        self._selected_stream = None
        self._workspace = None
        self._workspace_loaded_from_store = False
        self._workspace_user_modified = False
        self._pending_param_values = {}
        self._param_apply_commands = {}
        self._apply_command_params = {}
        self._param_apply_attempts = {}
        self._param_apply_values = {}
        self._device_names = []
        self._stream_names = []
        self._field_names = []
        self._param_schema = ()
        self._device_list.clear()
        self._stream_list.clear()
        self._field_list.clear()
        self._plot_workspace.set_workspace(None)
        self._workspace_label.setText("No plot workspace loaded")
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
        if not connected:
            self._live_refresh_timer.stop()
            self._plot_refresh_pending = False
            self._raw_view_timer.stop()
            self._pending_raw_lines = []
            self._clear_all_param_apply_timers()
            self._param_apply_commands = {}
            self._apply_command_params = {}
            self._param_apply_attempts = {}
            self._param_apply_values = {}
            for param_name in list(self._param_row_indexes.keys()):
                self._update_param_row_state(param_name)
        if connected:
            self._configure_button(
                self._connect_button,
                icon=QtWidgets.QStyle.StandardPixmap.SP_BrowserStop,
                text="Disconnect",
                tooltip="Disconnect from the current serial device",
            )
        else:
            self._configure_button(
                self._connect_button,
                icon=QtWidgets.QStyle.StandardPixmap.SP_MediaPlay,
                text="Connect",
                tooltip="Connect to the selected serial device",
            )
        self._port_combo.setEnabled(not connected)
        self._baud_spin.setEnabled(not connected)
        self._refresh_ports_button.setEnabled(not connected)
        self._record_checkbox.setEnabled(not connected)
        self._record_path_edit.setEnabled(not connected)
        self._browse_button.setEnabled(not connected)
        self._add_pane_button.setEnabled(connected)
        self._duplicate_pane_button.setEnabled(connected)
        self._remove_pane_button.setEnabled(connected)
        self._add_trace_button.setEnabled(connected)
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

    def _refresh_field_list(self) -> None:
        if self._selected_device is None or self._selected_stream is None:
            self._field_names = []
            self._field_list.clear()
            return

        names = self._controller.runtime.numeric_field_names(self._selected_device, self._selected_stream)
        if names == self._field_names:
            return

        self._field_names = list(names)
        selected_name = None
        item = self._field_list.currentItem()
        if item is not None:
            selected_name = item.text()
        blocker = QtCore.QSignalBlocker(self._field_list)
        self._field_list.clear()
        for name in names:
            self._field_list.addItem(name)
        if selected_name in names:
            self._field_list.setCurrentRow(names.index(selected_name))
        elif names:
            self._field_list.setCurrentRow(0)
        del blocker

    def _load_workspace_for_selected_device(self) -> None:
        if self._selected_device is None:
            self._workspace = None
            self._plot_workspace.set_workspace(None)
            self._workspace_label.setText("No plot workspace loaded")
            return

        try:
            workspace = self._workspace_store.load(self._selected_device)
        except Exception as exc:
            self._show_status(f"failed to load saved layout: {exc}", error=True)
            workspace = None

        self._workspace_loaded_from_store = workspace is not None
        self._workspace_user_modified = False
        if workspace is None:
            workspace = self._controller.runtime.build_default_workspace(self._selected_device)

        self._workspace = workspace
        self._plot_workspace.set_workspace(workspace)
        self._workspace_label.setText(f"Workspace for {workspace.device}")
        self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)

    def _maybe_seed_default_workspace(self) -> None:
        if (
            self._selected_device is None
            or self._workspace is None
            or self._workspace_loaded_from_store
            or self._workspace_user_modified
        ):
            return

        if any(pane.traces for pane in self._workspace.panes):
            return

        seeded = self._controller.runtime.build_default_workspace(self._selected_device)
        if not any(pane.traces for pane in seeded.panes):
            return
        self._workspace = seeded
        self._plot_workspace.set_workspace(seeded)
        self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)

    def _add_selected_field_to_active_pane(self) -> None:
        if self._selected_stream is None or self._selected_device is None:
            return
        item = self._field_list.currentItem()
        if item is None:
            return

        active = self._plot_workspace.active_pane_id
        workspace = self._plot_workspace.workspace
        if active is None or workspace is None:
            self._show_status("add a pane first", error=True)
            return

        pane = next((entry for entry in workspace.panes if entry.id == active), None)
        if pane is None:
            return
        if any(trace.stream == self._selected_stream and trace.field == item.text() for trace in pane.traces):
            self._show_status(f"{self._selected_stream}.{item.text()} is already in the active pane")
            return
        color = default_trace_color(len(pane.traces))
        self._plot_workspace.add_trace(self._selected_stream, item.text(), color)
        self._show_status(f"added {self._selected_stream}.{item.text()} to {pane.title}")

    def _confirm_remove_active_pane(self) -> None:
        workspace = self._plot_workspace.workspace
        active_id = self._plot_workspace.active_pane_id
        if workspace is None or active_id is None:
            return
        pane = next((entry for entry in workspace.panes if entry.id == active_id), None)
        if pane is None:
            return
        message = f"Remove pane '{pane.title}'?"
        details = "This cannot be undone from the current session."
        result = QtWidgets.QMessageBox.warning(
            self,
            "Remove Pane",
            f"{message}\n\n{details}",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if result != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._plot_workspace.remove_active_pane()
        self._show_status(f"removed pane {pane.title}")

    def _on_device_selected(self, device: str) -> None:
        previous_device = self._selected_device
        self._selected_device = device or None
        if previous_device != self._selected_device:
            self._clear_all_param_apply_timers()
            self._param_visual_states = {}
            self._pending_param_values = {}
            self._param_apply_commands = {}
            self._apply_command_params = {}
            self._stream_names = []
            self._field_names = []
            self._param_schema = ()
            self._workspace_loaded_from_store = False
            self._workspace_user_modified = False
        self._refresh_stream_list()
        self._refresh_field_list()
        self._load_workspace_for_selected_device()
        self._refresh_params_table()
        self._refresh_command_specs()
        self._refresh_events_view()
        self._refresh_logs_view()
        self._refresh_discovery_views()

    def _on_stream_selected(self, stream_name: str) -> None:
        self._selected_stream = stream_name or None
        self._refresh_field_list()

    def _on_message_received(self, message: object) -> None:
        previous_device = self._selected_device
        self._refresh_device_list()
        if previous_device != self._selected_device and self._selected_device is not None:
            self._on_device_selected(self._selected_device)

        if isinstance(message, CapabilitiesMessage):
            if self._selected_device is None:
                self._selected_device = message.device
                self._on_device_selected(message.device)
            self._maybe_seed_default_workspace()
            self._refresh_stream_list()
            self._refresh_field_list()
            self._refresh_params_table()
            self._refresh_command_specs()
            self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)
            self._show_status(f"loaded capabilities for {message.device}")
        elif isinstance(message, SampleMessage):
            if self._selected_device == message.device:
                if self._selected_stream is None:
                    self._selected_stream = message.stream
                    self._refresh_stream_list()
                    self._refresh_field_list()
                self._maybe_seed_default_workspace()
                self._schedule_live_refresh()
        elif isinstance(message, RespMessage):
            param_name = self._apply_command_params.pop(message.id, None)
            if param_name is not None and self._param_apply_commands.get(param_name) == message.id:
                self._param_apply_commands.pop(param_name, None)
                self._clear_param_apply_timer(param_name)
                self._param_apply_attempts.pop(param_name, None)
                self._param_apply_values.pop(param_name, None)
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

    def _on_workspace_changed(self, workspace: object) -> None:
        if not isinstance(workspace, PlotWorkspace):
            return
        self._workspace = workspace
        self._workspace_user_modified = True
        self._workspace_label.setText(f"Workspace for {workspace.device}")
        self._save_workspace_snapshot()
        self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)

    def _save_workspace_snapshot(self) -> None:
        workspace = self._plot_workspace.current_workspace_snapshot()
        if workspace is None:
            return
        self._workspace = workspace
        try:
            self._workspace_store.save(workspace)
        except Exception as exc:
            self._show_status(f"failed to save layout: {exc}", error=True)

    def _restore_window_layout(self) -> None:
        try:
            layout = self._window_layout_store.load()
        except Exception as exc:
            self._show_status(f"failed to load window layout: {exc}", error=True)
            return
        if layout is None:
            return
        if layout.body_splitter_state:
            state = QtCore.QByteArray.fromBase64(layout.body_splitter_state.encode("ascii"))
            if self._body_splitter.restoreState(state):
                return
        if layout.body_splitter_sizes:
            self._body_splitter.setSizes(list(layout.body_splitter_sizes))

    def _save_window_layout(self) -> None:
        sizes = tuple(size for size in self._body_splitter.sizes() if size > 0)
        if not sizes:
            return
        try:
            splitter_state = bytes(self._body_splitter.saveState().toBase64()).decode("ascii")
            self._window_layout_store.save(
                WindowLayout(
                    body_splitter_sizes=sizes,
                    body_splitter_state=splitter_state,
                )
            )
        except Exception as exc:
            self._show_status(f"failed to save window layout: {exc}", error=True)

    def _schedule_live_refresh(self, *, plot: bool = True) -> None:
        self._plot_refresh_pending = self._plot_refresh_pending or plot
        if not self._live_refresh_timer.isActive():
            self._live_refresh_timer.start()

    def _flush_live_refresh(self) -> None:
        if self._plot_refresh_pending:
            self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)
        self._plot_refresh_pending = False

    def _flush_raw_view(self) -> None:
        if self._tab_widget.currentWidget() is not self._raw_tab:
            return
        if self._pending_raw_lines:
            self._raw_view.appendPlainText("\n".join(self._pending_raw_lines))
            self._pending_raw_lines = []

    def _reload_raw_view(self) -> None:
        self._raw_view.setPlainText("\n".join(self._controller.runtime.raw_lines))
        self._pending_raw_lines = []

    def _on_tab_changed(self, _index: int) -> None:
        current = self._tab_widget.currentWidget()
        if current is self._raw_tab:
            self._reload_raw_view()
        elif current is self._logs_tab:
            self._refresh_logs_view()
        elif current is self._events_tab:
            self._refresh_events_view()

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

            name_item = QtWidgets.QTableWidgetItem(spec.name)
            name_item.setToolTip(spec.name)
            self._param_table.setItem(row, 0, name_item)
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
            self._param_apply_attempts[param_name] = 1
            self._param_apply_values[param_name] = value
            self._start_param_apply_timer(param_name, command_id)
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
        if level_filter in {"all", "info"}:
            lines.extend(f"info [host-sync] {error}" for error in self._controller.runtime.parse_errors)
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
        _workspace, active_pane, active_title, active_color = self._active_pane_details()

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
        self._add_trace_button.set_segments("Add Selected Trace to", "", active_color)
        self._add_trace_button.setToolTip(
            f"Add the selected field to {active_title}" if active_pane is not None else "Add the selected field to the active pane"
        )
        self._add_trace_button.setEnabled(
            has_capabilities
            and self._selected_stream is not None
            and self._field_list.currentItem() is not None
            and self._plot_workspace.active_pane_id is not None
        )
        workspace_ready = self._selected_device is not None and self._controller.is_connected
        self._add_pane_button.setEnabled(workspace_ready)
        self._duplicate_pane_button.setEnabled(workspace_ready and self._plot_workspace.active_pane_id is not None)
        self._remove_pane_button.setEnabled(workspace_ready and self._plot_workspace.active_pane_id is not None)

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

    def _start_param_apply_timer(self, param_name: str, command_id: int) -> None:
        self._clear_param_apply_timer(param_name)
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(PARAM_APPLY_TIMEOUT_MS)
        timer.timeout.connect(lambda name=param_name, expected_id=command_id: self._on_param_apply_timeout(name, expected_id))
        self._param_apply_timers[param_name] = timer
        timer.start()

    def _clear_param_apply_timer(self, param_name: str) -> None:
        timer = self._param_apply_timers.pop(param_name, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def _clear_all_param_apply_timers(self) -> None:
        for param_name in list(self._param_apply_timers.keys()):
            self._clear_param_apply_timer(param_name)

    def _on_param_apply_timeout(self, param_name: str, command_id: int) -> None:
        active_command_id = self._param_apply_commands.get(param_name)
        if active_command_id != command_id:
            self._clear_param_apply_timer(param_name)
            return

        self._apply_command_params.pop(command_id, None)
        retry_value = self._param_apply_values.get(param_name)
        retry_attempt = self._param_apply_attempts.get(param_name, 1)
        self._clear_param_apply_timer(param_name)

        if (
            retry_value is not None and
            retry_attempt < PARAM_APPLY_MAX_ATTEMPTS and
            self._selected_device is not None
        ):
            next_command_id = self._controller.send_command(
                device=self._selected_device,
                name="param.set",
                args={"param": param_name, "value": retry_value},
            )
            if next_command_id is not None:
                self._param_apply_commands[param_name] = next_command_id
                self._apply_command_params[next_command_id] = param_name
                self._param_apply_attempts[param_name] = retry_attempt + 1
                self._start_param_apply_timer(param_name, next_command_id)
                self._update_param_row_state(param_name)
                self._show_status(
                    f"retrying {param_name} ({retry_attempt + 1}/{PARAM_APPLY_MAX_ATTEMPTS})"
                )
                return

        self._param_apply_commands.pop(param_name, None)
        self._param_apply_attempts.pop(param_name, None)
        self._param_apply_values.pop(param_name, None)
        self._update_param_row_state(param_name)
        self._show_status(f"timed out applying {param_name}; you can retry", error=True)
