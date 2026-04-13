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
from .workspace import (
    DEFAULT_PRESET_NAME,
    PlotWorkspace,
    WindowLayout,
    WindowLayoutStore,
    WorkspacePreset,
    WorkspacePresetCollection,
    WorkspaceStore,
    blank_workspace,
    default_trace_color,
)

PARAM_APPLY_TIMEOUT_MS = 5000
PARAM_APPLY_MAX_ATTEMPTS = 3
LIVE_REFRESH_INTERVAL_MS = 33
RAW_VIEW_REFRESH_INTERVAL_MS = 100

PRESET_TAB_ACTIVE_STYLESHEET = """
QPushButton {
    background-color: #1f2530;
    color: #eef3fb;
    border: 1px solid #466481;
    border-radius: 5px;
    padding: 5px 12px;
}
QPushButton:hover {
    background-color: #262e3b;
    border-color: #5c82a6;
}
"""

PRESET_TAB_INACTIVE_STYLESHEET = """
QPushButton {
    background-color: #343b47;
    color: #c5cfdd;
    border: 1px solid #4b5566;
    border-radius: 5px;
    padding: 5px 12px;
}
QPushButton:hover {
    background-color: #3c4553;
    color: #dce6f4;
    border-color: #607087;
}
"""

PRESET_ADD_BUTTON_STYLESHEET = """
QPushButton {
    background-color: #2d3440;
    color: #d6e0ef;
    border: 1px solid #465062;
    border-radius: 5px;
    padding: 0px;
    font-size: 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #37404d;
    border-color: #5b6e87;
}
QPushButton:disabled {
    color: #7f8997;
    border-color: #3d4450;
}
"""

PRESET_RENAME_STYLESHEET = """
QLineEdit {
    background-color: #1f2530;
    color: #eef3fb;
    border: 1px solid #466481;
    border-radius: 5px;
    padding: 5px 10px;
    selection-background-color: #0b84f3;
}
"""

HEADER_ACTION_STYLESHEET = """
QPushButton {
    background-color: #3a414d;
    color: #c6d0dd;
    border: 1px solid #4d5664;
    border-radius: 5px;
    padding: 4px 10px;
}
QPushButton:hover {
    background-color: #444c59;
    color: #eef3fb;
    border-color: #657486;
}
"""

HEADER_EXPORT_STYLESHEET = """
QPushButton {
    background-color: #414957;
    color: #d6deeb;
    border: 1px solid #556172;
    border-radius: 5px;
    padding: 4px 10px;
}
QPushButton:hover {
    background-color: #4b5564;
    color: #f0f4fb;
    border-color: #6c7d92;
}
"""

HEADER_REMOVE_STYLESHEET = """
QPushButton {
    background-color: #40363b;
    color: #d3b3bc;
    border: 1px solid #6d4b56;
    border-radius: 5px;
    padding: 4px 10px;
}
QPushButton:hover {
    background-color: #4d3a41;
    color: #f1d3da;
    border-color: #8e5d6a;
}
"""

POPUP_MENU_STYLESHEET = """
QMenu {
    background-color: #1c2128;
    color: #d7e1ef;
    border: 1px solid #4b5566;
    padding: 4px;
}
QMenu::item {
    background-color: transparent;
    border: none;
    padding: 6px 12px;
    margin: 0px;
}
QMenu::item:selected {
    background-color: #b23b50;
    color: #f7f9fc;
}
QMenu::item:disabled {
    color: #788292;
    background-color: transparent;
}
QMenu::separator {
    height: 1px;
    background-color: #475262;
    margin: 4px 8px;
}
"""

PARAM_PICKER_POPUP_STYLESHEET = """
QFrame {
    background-color: #1c2128;
    border: 1px solid #4b5566;
}
QListWidget {
    background-color: transparent;
    color: #d7e1ef;
    border: none;
    outline: none;
}
QListWidget::item {
    border: none;
    margin: 0px;
    padding: 6px 12px;
    background-color: transparent;
}
QListWidget::item:hover {
    background-color: #313946;
    color: #eef3fb;
}
QListWidget::item:selected {
    background-color: #b23b50;
    color: #f7f9fc;
}
"""


class ElidedLabel(QtWidgets.QLabel):
    def __init__(
        self,
        text: str = "",
        parent: QtWidgets.QWidget | None = None,
        *,
        elide_mode: QtCore.Qt.TextElideMode = QtCore.Qt.TextElideMode.ElideMiddle,
    ) -> None:
        super().__init__("", parent)
        self._full_text = ""
        self._elide_mode = elide_mode
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.setText(text)

    def text(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:
        self._full_text = text
        self._update_elided_text()

    def minimumSizeHint(self) -> QtCore.QSize:
        hint = super().minimumSizeHint()
        return QtCore.QSize(0, hint.height())

    def setFont(self, font: QtGui.QFont) -> None:
        super().setFont(font)
        self._update_elided_text()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_elided_text()

    def _update_elided_text(self) -> None:
        available_width = max(0, self.contentsRect().width())
        if available_width <= 0:
            display_text = self._full_text
        else:
            display_text = self.fontMetrics().elidedText(self._full_text, self._elide_mode, available_width)
        super().setText(display_text)


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


class PresetButton(QtWidgets.QPushButton):
    double_clicked = QtCore.Signal()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class ParameterPickerPopup(QtWidgets.QFrame):
    param_selected = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent, QtCore.Qt.WindowType.Popup | QtCore.Qt.WindowType.FramelessWindowHint)
        self.setObjectName("paramPickerPopup")
        self.setStyleSheet(PARAM_PICKER_POPUP_STYLESHEET)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = QtWidgets.QListWidget(self)
        self._list.setSpacing(0)
        self._list.setAlternatingRowColors(False)
        self._list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setMouseTracking(True)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemActivated.connect(self._on_item_clicked)
        layout.addWidget(self._list)

    def populate(self, param_specs: list[ParamSpec], visible_names: set[str]) -> None:
        self._list.clear()
        first_enabled_row: int | None = None
        disabled_color = QtGui.QColor("#788292")

        for index, spec in enumerate(param_specs):
            item = QtWidgets.QListWidgetItem(spec.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, spec.name)
            if spec.name in visible_names:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
                item.setForeground(disabled_color)
            elif first_enabled_row is None:
                first_enabled_row = index
            self._list.addItem(item)

        if first_enabled_row is not None:
            self._list.setCurrentRow(first_enabled_row)

    def show_below(self, anchor: QtWidgets.QWidget) -> None:
        row_height = max(28, self._list.sizeHintForRow(0) if self._list.count() else 28)
        content_width = max(
            anchor.width(),
            self._list.sizeHintForColumn(0) + 32 if self._list.count() else anchor.width(),
        )
        width = min(max(content_width, 260), 520)
        visible_rows = min(max(self._list.count(), 1), 14)
        height = visible_rows * row_height + 2
        if self._list.verticalScrollBar().isVisible():
            width += self._list.verticalScrollBar().sizeHint().width()
        self.resize(width, height)
        self.move(anchor.mapToGlobal(QtCore.QPoint(0, anchor.height())))
        self.show()
        self.raise_()
        self.activateWindow()
        self._list.setFocus()

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        if item is None or not (item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled):
            return
        param_name = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(param_name, str) and param_name:
            self.param_selected.emit(param_name)
        self.close()


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
        self._workspace_presets: WorkspacePresetCollection | None = None
        self._active_preset_name: str | None = None
        self._seedable_preset_names: set[str] = set()
        self._preset_buttons: dict[str, PresetButton] = {}
        self._preset_button_group: QtWidgets.QButtonGroup | None = None
        self._preset_rename_editor: QtWidgets.QLineEdit | None = None
        self._preset_rename_name: str | None = None
        self._add_param_popup: ParameterPickerPopup | None = None
        self._current_command_specs: list[CommandSpec] = []
        self._all_param_specs: list[ParamSpec] = []
        self._current_param_specs: list[ParamSpec] = []
        self._command_cards: dict[str, QtWidgets.QFrame] = {}
        self._command_card_widgets: dict[str, dict[str, tuple[str, QtWidgets.QWidget]]] = {}
        self._command_card_status_labels: dict[str, QtWidgets.QLabel] = {}
        self._command_id_to_name: dict[int, str] = {}
        self._param_editors: dict[str, tuple[str, QtWidgets.QWidget]] = {}
        self._param_apply_buttons: dict[str, QtWidgets.QPushButton] = {}
        self._param_cards: dict[str, QtWidgets.QFrame] = {}
        self._param_name_labels: dict[str, QtWidgets.QLabel] = {}
        self._param_current_labels: dict[str, QtWidgets.QLabel] = {}
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

        self._set_baud_selection(initial_baud)
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

    def _style_preset_button(self, button: QtWidgets.QPushButton, *, active: bool) -> None:
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(PRESET_TAB_ACTIVE_STYLESHEET if active else PRESET_TAB_INACTIVE_STYLESHEET)

    def _style_header_action_button(self, button: QtWidgets.QPushButton, *, variant: str = "neutral") -> None:
        if variant == "export":
            button.setStyleSheet(HEADER_EXPORT_STYLESHEET)
        elif variant == "danger":
            button.setStyleSheet(HEADER_REMOVE_STYLESHEET)
        else:
            button.setStyleSheet(HEADER_ACTION_STYLESHEET)
        button.setIconSize(QtCore.QSize(14, 14))

    def _workspace_for_preset(self, preset_name: str | None) -> PlotWorkspace | None:
        if self._workspace_presets is None or preset_name is None:
            return None
        for preset in self._workspace_presets.presets:
            if preset.name == preset_name:
                return preset.workspace
        return None

    def _preset_by_name(self, preset_name: str | None) -> WorkspacePreset | None:
        if self._workspace_presets is None or preset_name is None:
            return None
        for preset in self._workspace_presets.presets:
            if preset.name == preset_name:
                return preset
        return None

    def _visible_param_names(self, preset_name: str | None = None) -> tuple[str, ...]:
        preset = self._preset_by_name(preset_name or self._active_preset_name)
        if preset is None:
            return ()
        return preset.visible_param_names

    def _set_visible_param_names_for_active_preset(self, names: tuple[str, ...]) -> None:
        if self._workspace_presets is None or self._active_preset_name is None:
            return
        presets = tuple(
            WorkspacePreset(
                name=preset.name,
                workspace=preset.workspace,
                visible_param_names=names if preset.name == self._active_preset_name else preset.visible_param_names,
            )
            for preset in self._workspace_presets.presets
        )
        self._workspace_presets = WorkspacePresetCollection(
            device=self._workspace_presets.device,
            presets=presets,
            active_preset_name=self._workspace_presets.active_preset_name,
        )

    def _add_visible_param_to_active_preset(self, param_name: str) -> None:
        visible_names = self._visible_param_names()
        if param_name in visible_names:
            return
        self._set_visible_param_names_for_active_preset(visible_names + (param_name,))
        self._save_workspace_presets()
        self._refresh_params_table()

    def _remove_visible_param_from_active_preset(self, param_name: str) -> None:
        visible_names = self._visible_param_names()
        if param_name not in visible_names:
            return
        self._set_visible_param_names_for_active_preset(tuple(name for name in visible_names if name != param_name))
        self._save_workspace_presets()
        self._refresh_params_table()

    def _build_add_param_picker(self) -> ParameterPickerPopup | None:
        if not self._all_param_specs:
            return None
        if self._add_param_popup is None:
            self._add_param_popup = ParameterPickerPopup(self)
            self._add_param_popup.param_selected.connect(self._add_visible_param_to_active_preset)
        self._add_param_popup.populate(self._all_param_specs, set(self._visible_param_names()))
        return self._add_param_popup

    def _show_add_param_menu(self) -> None:
        popup = self._build_add_param_picker()
        if popup is None:
            return
        if popup.isVisible():
            popup.close()
            return
        popup.show_below(self._add_param_button)

    def _close_add_param_popup(self) -> None:
        if self._add_param_popup is not None and self._add_param_popup.isVisible():
            self._add_param_popup.close()

    def _build_param_card_context_menu(self, param_name: str) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(POPUP_MENU_STYLESHEET)
        remove_action = menu.addAction("Remove from Preset")
        remove_action.triggered.connect(lambda: self._remove_visible_param_from_active_preset(param_name))
        return menu

    def _show_param_card_context_menu(self, param_name: str, global_pos: QtCore.QPoint) -> None:
        self._build_param_card_context_menu(param_name).exec(global_pos)

    def _set_active_preset_name(self, preset_name: str) -> None:
        if self._workspace_presets is None:
            return
        self._workspace_presets = WorkspacePresetCollection(
            device=self._workspace_presets.device,
            presets=self._workspace_presets.presets,
            active_preset_name=preset_name,
        )
        self._active_preset_name = preset_name

    def _replace_preset_workspace(self, preset_name: str, workspace: PlotWorkspace) -> None:
        if self._workspace_presets is None:
            return
        presets = tuple(
            WorkspacePreset(
                name=preset.name,
                workspace=workspace if preset.name == preset_name else preset.workspace,
                visible_param_names=preset.visible_param_names,
            )
            for preset in self._workspace_presets.presets
        )
        self._workspace_presets = WorkspacePresetCollection(
            device=self._workspace_presets.device,
            presets=presets,
            active_preset_name=self._workspace_presets.active_preset_name,
        )
        if self._active_preset_name == preset_name:
            self._workspace = workspace

    def _save_workspace_presets(self) -> None:
        if self._workspace_presets is None:
            return
        try:
            self._workspace_store.save(self._workspace_presets)
        except Exception as exc:
            self._show_status(f"failed to save layout: {exc}", error=True)

    def _refresh_preset_ribbon(self, *, preserve_scroll: bool = True, reveal_active: bool = False) -> None:
        self._cancel_preset_rename()
        scroll_bar = self._preset_scroll.horizontalScrollBar()
        previous_scroll = scroll_bar.value() if preserve_scroll else 0

        while self._preset_button_layout.count():
            item = self._preset_button_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if widget is self._new_preset_button:
                    widget.setParent(None)
                else:
                    widget.deleteLater()

        self._preset_buttons = {}
        self._preset_button_group = QtWidgets.QButtonGroup(self)
        self._preset_button_group.setExclusive(True)

        if self._workspace_presets is None:
            self._new_preset_button.setEnabled(False)
            self._preset_button_layout.addWidget(self._new_preset_button)
            return

        for preset in self._workspace_presets.presets:
            button = PresetButton(preset.name)
            button.setCheckable(True)
            button.setChecked(preset.name == self._workspace_presets.active_preset_name)
            self._style_preset_button(button, active=preset.name == self._workspace_presets.active_preset_name)
            button.clicked.connect(lambda _checked=False, name=preset.name: self._select_preset(name))
            button.double_clicked.connect(lambda name=preset.name: self._begin_preset_rename(name))
            button.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, name=preset.name, source=button: self._show_preset_context_menu(
                    name,
                    source=source,
                    global_pos=source.mapToGlobal(pos),
                )
            )
            self._preset_button_group.addButton(button)
            self._preset_button_layout.addWidget(button)
            self._preset_buttons[preset.name] = button

        self._new_preset_button.setEnabled(self._selected_device is not None)
        self._preset_button_layout.addWidget(self._new_preset_button)
        self._preset_button_layout.addStretch(1)
        if reveal_active and self._active_preset_name is not None:
            active_button = self._preset_buttons.get(self._active_preset_name)
            if active_button is not None:
                QtCore.QTimer.singleShot(0, lambda: self._preset_scroll.ensureWidgetVisible(active_button, 12, 0))
                return
        if preserve_scroll:
            QtCore.QTimer.singleShot(0, lambda: scroll_bar.setValue(min(previous_scroll, scroll_bar.maximum())))

    def _next_preset_name(self) -> str:
        names = {preset.name for preset in self._workspace_presets.presets} if self._workspace_presets is not None else set()
        index = 1
        while True:
            candidate = f"Preset {index}"
            if candidate not in names:
                return candidate
            index += 1

    def _clear_preset_rename_editor(self) -> None:
        if self._preset_rename_editor is None:
            return
        self._preset_rename_editor.removeEventFilter(self)
        self._preset_button_layout.removeWidget(self._preset_rename_editor)
        self._preset_rename_editor.deleteLater()
        self._preset_rename_editor = None

    def _cancel_preset_rename(self) -> None:
        name = self._preset_rename_name
        self._clear_preset_rename_editor()
        self._preset_rename_name = None
        if name is None:
            return
        button = self._preset_buttons.get(name)
        if button is not None:
            button.show()
            button.setFocus()

    def _begin_preset_rename(self, preset_name: str) -> None:
        if preset_name != self._active_preset_name:
            return

        button = self._preset_buttons.get(preset_name)
        if button is None:
            return

        self._cancel_preset_rename()
        index = self._preset_button_layout.indexOf(button)
        if index < 0:
            return

        editor = QtWidgets.QLineEdit(preset_name)
        editor.installEventFilter(self)
        editor.setStyleSheet(PRESET_RENAME_STYLESHEET)
        editor.setMinimumWidth(max(90, editor.fontMetrics().horizontalAdvance(preset_name) + 26))
        editor.returnPressed.connect(self._finish_preset_rename)
        editor.editingFinished.connect(self._finish_preset_rename)
        self._preset_rename_editor = editor
        self._preset_rename_name = preset_name
        button.hide()
        self._preset_button_layout.insertWidget(index, editor)
        editor.selectAll()
        editor.setFocus()

    def _rename_preset(self, old_name: str, new_name: str) -> bool:
        if self._workspace_presets is None:
            return False

        cleaned_name = new_name.strip()
        if not cleaned_name:
            self._show_status("preset name cannot be empty", error=True)
            return False
        if cleaned_name != old_name and any(preset.name == cleaned_name for preset in self._workspace_presets.presets):
            self._show_status(f"preset {cleaned_name} already exists", error=True)
            return False
        if cleaned_name == old_name:
            return True

        presets = tuple(
            WorkspacePreset(
                name=cleaned_name if preset.name == old_name else preset.name,
                workspace=preset.workspace,
                visible_param_names=preset.visible_param_names,
            )
            for preset in self._workspace_presets.presets
        )
        active_name = cleaned_name if self._workspace_presets.active_preset_name == old_name else self._workspace_presets.active_preset_name
        self._workspace_presets = WorkspacePresetCollection(
            device=self._workspace_presets.device,
            presets=presets,
            active_preset_name=active_name,
        )
        if old_name in self._seedable_preset_names:
            self._seedable_preset_names.discard(old_name)
            self._seedable_preset_names.add(cleaned_name)
        if self._active_preset_name == old_name:
            self._active_preset_name = cleaned_name
        self._refresh_preset_ribbon()
        self._save_workspace_presets()
        self._show_status(f"renamed preset to {cleaned_name}")
        return True

    def _finish_preset_rename(self) -> None:
        editor = self._preset_rename_editor
        old_name = self._preset_rename_name
        if editor is None or old_name is None:
            return

        new_name = editor.text()
        self._clear_preset_rename_editor()
        self._preset_rename_name = None
        button = self._preset_buttons.get(old_name)
        if button is not None:
            button.show()

        if not self._rename_preset(old_name, new_name):
            if button is not None:
                button.setFocus()
            return

    def _build_preset_context_menu(self, preset_name: str) -> QtWidgets.QMenu | None:
        if self._workspace_presets is None:
            return None

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(POPUP_MENU_STYLESHEET)
        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._rename_preset_from_menu(preset_name))
        delete_action = menu.addAction("Delete")
        delete_action.setEnabled(len(self._workspace_presets.presets) > 1)
        delete_action.triggered.connect(lambda: self._delete_preset(preset_name))
        return menu

    def _show_preset_context_menu(
        self,
        preset_name: str,
        *,
        source: QtWidgets.QWidget | None = None,
        global_pos: QtCore.QPoint | None = None,
    ) -> None:
        menu = self._build_preset_context_menu(preset_name)
        if menu is None:
            return
        if global_pos is not None:
            anchor = global_pos
        elif source is not None:
            anchor = source.mapToGlobal(QtCore.QPoint(0, source.height()))
        else:
            anchor = self._preset_scroll.viewport().mapToGlobal(
                QtCore.QPoint(0, self._preset_scroll.viewport().height())
            )
        menu.exec(anchor)

    def _rename_preset_from_menu(self, preset_name: str) -> None:
        if preset_name != self._active_preset_name:
            self._select_preset(preset_name)
        self._begin_preset_rename(preset_name)

    def _delete_preset(self, preset_name: str) -> None:
        if self._workspace_presets is None:
            return
        if len(self._workspace_presets.presets) <= 1:
            self._show_status("cannot delete the last preset", error=True)
            return
        was_active = preset_name == self._active_preset_name

        presets = list(self._workspace_presets.presets)
        removed_index = next((index for index, preset in enumerate(presets) if preset.name == preset_name), None)
        if removed_index is None:
            return

        if was_active:
            self._save_workspace_snapshot()

        remaining = [preset for preset in presets if preset.name != preset_name]
        next_active_name = self._active_preset_name
        if preset_name == self._active_preset_name:
            next_index = max(0, min(removed_index - 1, len(remaining) - 1))
            next_active_name = remaining[next_index].name

        self._seedable_preset_names.discard(preset_name)
        self._workspace_presets = WorkspacePresetCollection(
            device=self._workspace_presets.device,
            presets=tuple(remaining),
            active_preset_name=next_active_name or remaining[0].name,
        )
        self._active_preset_name = self._workspace_presets.active_preset_name
        self._refresh_preset_ribbon()

        if was_active or self._workspace_for_preset(self._active_preset_name) != self._workspace:
            next_workspace = self._workspace_for_preset(self._active_preset_name)
            self._workspace = next_workspace
            self._plot_workspace.set_workspace(next_workspace)
            self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)

        self._save_workspace_presets()
        self._refresh_params_table()
        self._show_status(f"deleted preset {preset_name}")

    def _create_preset(self) -> None:
        if self._selected_device is None or self._workspace_presets is None:
            return

        self._close_add_param_popup()
        self._save_workspace_snapshot()
        preset_name = self._next_preset_name()
        workspace = blank_workspace(self._selected_device)
        self._workspace_presets = WorkspacePresetCollection(
            device=self._workspace_presets.device,
            presets=self._workspace_presets.presets
            + (WorkspacePreset(name=preset_name, workspace=workspace, visible_param_names=()),),
            active_preset_name=preset_name,
        )
        self._active_preset_name = preset_name
        self._workspace = workspace
        self._refresh_preset_ribbon(reveal_active=True)
        self._plot_workspace.set_workspace(workspace)
        self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)
        self._save_workspace_presets()
        self._refresh_params_table()
        self._show_status(f"created preset {preset_name}")

    def _select_preset(self, preset_name: str) -> None:
        if self._workspace_presets is None or preset_name == self._active_preset_name:
            return

        self._close_add_param_popup()
        self._save_workspace_snapshot()
        self._set_active_preset_name(preset_name)
        workspace = self._workspace_for_preset(preset_name)
        if workspace is None:
            return
        self._workspace = workspace
        self._refresh_preset_ribbon(preserve_scroll=True, reveal_active=False)
        self._plot_workspace.set_workspace(workspace)
        self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)
        self._save_workspace_presets()
        self._refresh_params_table()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._save_workspace_snapshot()
        self._save_window_layout()
        super().closeEvent(event)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if (
            watched is self._preset_rename_editor
            and event.type() == QtCore.QEvent.Type.KeyPress
            and isinstance(event, QtGui.QKeyEvent)
            and event.key() == QtCore.Qt.Key.Key_Escape
        ):
            self._cancel_preset_rename()
            return True
        return super().eventFilter(watched, event)

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
        self._baud_combo = QtWidgets.QComboBox()
        self._baud_combo.setEditable(True)
        self._baud_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self._baud_combo.setMinimumContentsLength(8)
        self._baud_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        for baud in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 1000000, 1500000, 2000000):
            self._baud_combo.addItem(str(baud), baud)
        toolbar.addWidget(self._baud_combo)

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
        plot_layout.setSpacing(6)

        workspace_toolbar = QtWidgets.QHBoxLayout()
        workspace_toolbar.setSpacing(8)

        self._preset_scroll = QtWidgets.QScrollArea()
        self._preset_scroll.setWidgetResizable(True)
        self._preset_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._preset_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._preset_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._preset_scroll.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._preset_scroll.setFixedHeight(34)
        self._preset_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._preset_strip = QtWidgets.QWidget()
        self._preset_button_layout = QtWidgets.QHBoxLayout(self._preset_strip)
        self._preset_button_layout.setContentsMargins(0, 0, 0, 0)
        self._preset_button_layout.setSpacing(4)
        self._preset_scroll.setWidget(self._preset_strip)
        workspace_toolbar.addWidget(self._preset_scroll, 1)
        workspace_toolbar.addSpacing(10)

        self._preset_toolbar_divider = QtWidgets.QFrame()
        self._preset_toolbar_divider.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        self._preset_toolbar_divider.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self._preset_toolbar_divider.setLineWidth(1)
        self._preset_toolbar_divider.setFixedHeight(24)
        self._preset_toolbar_divider.setStyleSheet("color: #4f5969; background-color: #4f5969;")
        workspace_toolbar.addWidget(self._preset_toolbar_divider)
        workspace_toolbar.addSpacing(14)

        self._new_preset_button = QtWidgets.QPushButton("+")
        self._configure_button(
            self._new_preset_button,
            tooltip="Create a new blank plot preset",
        )
        self._new_preset_button.setFixedSize(28, 28)
        self._new_preset_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._new_preset_button.setStyleSheet(PRESET_ADD_BUTTON_STYLESHEET)

        self._add_pane_button = QtWidgets.QPushButton("Add Pane")
        self._configure_button(
            self._add_pane_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_FileDialogNewFolder,
            text="Add Pane",
            tooltip="Add a new plot pane",
        )
        self._style_header_action_button(self._add_pane_button)
        self._duplicate_pane_button = QtWidgets.QPushButton("Duplicate Pane")
        self._configure_button(
            self._duplicate_pane_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView,
            text="Duplicate Pane",
            tooltip="Duplicate the active pane",
        )
        self._style_header_action_button(self._duplicate_pane_button)
        self._export_plot_button = QtWidgets.QPushButton("Export Plot")
        self._configure_button(
            self._export_plot_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton,
            text="Export Plot",
            tooltip="Export the active plot pane as a high-resolution image",
        )
        self._style_header_action_button(self._export_plot_button, variant="export")
        self._remove_pane_button = QtWidgets.QPushButton("Remove Pane")
        self._configure_button(
            self._remove_pane_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_DialogDiscardButton,
            text="Remove Pane",
            tooltip="Remove the active pane",
        )
        self._style_header_action_button(self._remove_pane_button, variant="danger")
        workspace_toolbar.addWidget(self._add_pane_button)
        workspace_toolbar.addWidget(self._duplicate_pane_button)
        workspace_toolbar.addWidget(self._export_plot_button)
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

        controls_layout = QtWidgets.QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        self._add_param_button = QtWidgets.QPushButton("Add Parameter")
        self._configure_button(
            self._add_param_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_FileDialogNewFolder,
            text="Add Parameter",
            tooltip="Add a parameter card to this preset",
        )
        controls_layout.addWidget(self._add_param_button, 1)

        self._refresh_params_button = QtWidgets.QPushButton()
        self._configure_button(
            self._refresh_params_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload,
            text="Refresh Params",
            tooltip="Read current parameter values from the device",
        )
        self._refresh_params_button.setText("")
        self._refresh_params_button.setFixedWidth(34)
        controls_layout.addWidget(self._refresh_params_button, 0)

        layout.addLayout(controls_layout)

        self._param_list_scroll = QtWidgets.QScrollArea()
        self._param_list_scroll.setWidgetResizable(True)
        self._param_list_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._param_list_container = QtWidgets.QWidget()
        self._param_list_layout = QtWidgets.QVBoxLayout(self._param_list_container)
        self._param_list_layout.setContentsMargins(0, 0, 0, 0)
        self._param_list_layout.setSpacing(8)
        self._param_list_layout.addStretch(1)
        self._param_list_scroll.setWidget(self._param_list_container)
        layout.addWidget(self._param_list_scroll, 1)
        return widget

    def _build_commands_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._commands_state_label = QtWidgets.QLabel("Waiting for device description…")
        self._commands_state_label.setWordWrap(True)
        layout.addWidget(self._commands_state_label)

        self._command_cards_scroll = QtWidgets.QScrollArea()
        self._command_cards_scroll.setWidgetResizable(True)
        self._command_cards_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._command_cards_container = QtWidgets.QWidget()
        self._command_cards_layout = QtWidgets.QVBoxLayout(self._command_cards_container)
        self._command_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._command_cards_layout.setSpacing(8)
        self._command_cards_layout.addStretch(1)
        self._command_cards_scroll.setWidget(self._command_cards_container)
        layout.addWidget(self._command_cards_scroll, 1)

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
        self._new_preset_button.clicked.connect(self._create_preset)
        self._add_param_button.clicked.connect(self._show_add_param_menu)
        self._refresh_params_button.clicked.connect(self._refresh_params_from_device)
        self._add_pane_button.clicked.connect(self._plot_workspace.add_pane)
        self._duplicate_pane_button.clicked.connect(self._plot_workspace.duplicate_active_pane)
        self._export_plot_button.clicked.connect(self._export_active_plot)
        self._remove_pane_button.clicked.connect(self._confirm_remove_active_pane)
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

    def _set_baud_selection(self, baud: int) -> None:
        for index in range(self._baud_combo.count()):
            if self._baud_combo.itemData(index) == baud:
                self._baud_combo.setCurrentIndex(index)
                return
        self._baud_combo.setEditText(str(baud))

    def _selected_baud(self) -> int | None:
        data = self._baud_combo.currentData()
        if isinstance(data, int) and data > 0:
            return data

        text = self._baud_combo.currentText().strip().replace("_", "")
        if not text:
            return None

        try:
            baud = int(text)
        except ValueError:
            return None

        if baud <= 0:
            return None
        return baud

    def _choose_record_path(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Choose Recording Directory",
            self._record_path_edit.text() or str(Path.cwd()),
        )
        if path:
            self._record_checkbox.setChecked(True)
            self._record_path_edit.setText(path)

    def _record_output_directory(self) -> Path:
        directory_text = self._record_path_edit.text().strip()
        if directory_text:
            path = Path(directory_text).expanduser()
            if path.suffix.lower() == ".jsonl":
                return path.parent if str(path.parent) else Path.cwd()
            return path
        return Path.cwd() / "firmware" / "recordings"

    def _build_record_output_path(self, directory_text: str, port: str) -> str:
        directory = Path(directory_text).expanduser()
        port_name = Path(port).name or "serial"
        safe_port_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in port_name)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"devlink-{safe_port_name}-{timestamp}.jsonl"
        return str(directory / filename)

    def _build_plot_export_path(self, directory: Path, device: str, pane_title: str) -> Path:
        safe_device = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in device) or "device"
        safe_pane_title = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in pane_title) or "pane"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return directory / f"plot-{safe_device}-{safe_pane_title}-{timestamp}.png"

    def _export_active_plot(self) -> None:
        workspace = self._plot_workspace.workspace
        active_pane_id = self._plot_workspace.active_pane_id
        if workspace is None or active_pane_id is None:
            self._show_status("choose or create a plot pane first", error=True)
            return

        active_pane = next((pane for pane in workspace.panes if pane.id == active_pane_id), None)
        if active_pane is None:
            self._show_status("active pane is unavailable", error=True)
            return

        export_directory = self._record_output_directory()
        export_directory.mkdir(parents=True, exist_ok=True)
        export_path = self._build_plot_export_path(export_directory, workspace.device, active_pane.title)

        try:
            if not self._plot_workspace.export_active_pane_image(str(export_path)):
                self._show_status("active plot pane is unavailable", error=True)
                return
        except Exception as exc:
            self._show_status(f"failed to export plot: {exc}", error=True)
            return

        self._show_status(f"exported plot to {export_path}")

    def _toggle_connection(self) -> None:
        if self._controller.is_connected:
            self._controller.disconnect()
            return

        port = self._selected_port()
        if not port:
            self._show_status("choose a serial port first", error=True)
            return

        baud = self._selected_baud()
        if baud is None:
            self._show_status("enter a valid baud rate", error=True)
            return

        record_path = None
        if self._record_checkbox.isChecked():
            record_directory = self._record_output_directory()
            record_path = self._build_record_output_path(str(record_directory), port)

        self._controller.connect_to(
            ConnectionConfig(
                port=port,
                baud=baud,
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
        self._workspace_presets = None
        self._active_preset_name = None
        self._seedable_preset_names = set()
        if self._add_param_popup is not None:
            self._add_param_popup.close()
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
        self._refresh_preset_ribbon()
        self._clear_param_records()
        self._events_view.clear()
        self._logs_view.clear()
        self._raw_view.clear()
        self._current_command_specs = []
        self._all_param_specs = []
        self._current_param_specs = []
        self._command_cards = {}
        self._command_card_widgets = {}
        self._command_card_status_labels = {}
        self._command_id_to_name = {}
        self._param_editors = {}
        self._param_apply_buttons = {}
        self._param_cards = {}
        self._param_name_labels = {}
        self._param_current_labels = {}
        self._param_row_indexes = {}
        self._param_visual_states = {}
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
        self._baud_combo.setEnabled(not connected)
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
        self._cancel_preset_rename()
        if self._selected_device is None:
            self._workspace = None
            self._workspace_presets = None
            self._active_preset_name = None
            self._seedable_preset_names = set()
            self._refresh_preset_ribbon()
            self._plot_workspace.set_workspace(None)
            return

        try:
            presets = self._workspace_store.load(self._selected_device)
        except Exception as exc:
            self._show_status(f"failed to load saved layout: {exc}", error=True)
            presets = None

        if presets is None:
            presets = WorkspacePresetCollection(
                device=self._selected_device,
                presets=(
                    WorkspacePreset(
                        name=DEFAULT_PRESET_NAME,
                        workspace=self._controller.runtime.build_default_workspace(self._selected_device),
                        visible_param_names=(),
                    ),
                ),
                active_preset_name=DEFAULT_PRESET_NAME,
            )
            self._seedable_preset_names = {DEFAULT_PRESET_NAME}
        else:
            self._seedable_preset_names = set()

        self._workspace_presets = presets
        self._active_preset_name = presets.active_preset_name
        self._workspace = self._workspace_for_preset(self._active_preset_name)
        self._refresh_preset_ribbon()
        self._plot_workspace.set_workspace(self._workspace)
        self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)

    def _maybe_seed_default_workspace(self) -> None:
        if self._selected_device is None or self._workspace is None or self._active_preset_name is None:
            return
        if self._active_preset_name not in self._seedable_preset_names:
            return

        if any(pane.traces for pane in self._workspace.panes):
            return

        seeded = self._controller.runtime.build_default_workspace(self._selected_device)
        if not any(pane.traces for pane in seeded.panes):
            return
        self._workspace = seeded
        self._replace_preset_workspace(self._active_preset_name, seeded)
        self._seedable_preset_names.discard(self._active_preset_name)
        self._plot_workspace.set_workspace(seeded)
        self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)
        self._save_workspace_presets()

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
            self._close_add_param_popup()
            self._clear_all_param_apply_timers()
            self._param_visual_states = {}
            self._pending_param_values = {}
            self._param_apply_commands = {}
            self._apply_command_params = {}
            self._stream_names = []
            self._field_names = []
            self._param_schema = ()
            self._all_param_specs = []
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
            cmd_name = self._command_id_to_name.pop(message.id, None)
            if cmd_name is not None:
                status_label = self._command_card_status_labels.get(cmd_name)
                if status_label is not None:
                    if message.ok:
                        result_str = f" {dict(message.result)}" if message.result is not None else ""
                        status_label.setText(f"ok{result_str}")
                    else:
                        err = message.error
                        status_label.setText(f"error: {err.code}: {err.message}" if err is not None else "error")
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
        if self._active_preset_name is not None:
            self._seedable_preset_names.discard(self._active_preset_name)
        self._save_workspace_snapshot()
        self._plot_workspace.refresh_data(self._controller.runtime, self._selected_device)

    def _save_workspace_snapshot(self) -> None:
        workspace = self._plot_workspace.current_workspace_snapshot()
        if workspace is None or self._workspace_presets is None or self._active_preset_name is None:
            return
        self._workspace = workspace
        self._replace_preset_workspace(self._active_preset_name, workspace)
        self._save_workspace_presets()

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
        self._all_param_specs = list(self._controller.runtime.param_specs_for_device(self._selected_device))
        visible_names = set(self._visible_param_names())
        self._current_param_specs = [spec for spec in self._all_param_specs if spec.name in visible_names]
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
        self._param_cards = {}
        self._param_name_labels = {}
        self._param_current_labels = {}
        self._param_row_indexes = {}
        self._param_visual_states = {}
        self._clear_param_records()

        for index, spec in enumerate(self._current_param_specs):
            self._param_row_indexes[spec.name] = index
            current_value = self._current_param_value(spec, device_model)
            editor_value = self._pending_param_values.get(spec.name, current_value)

            editor_kind, editor = self._create_param_editor(spec, editor_value)
            self._connect_param_editor(spec.name, editor_kind, editor)
            self._param_editors[spec.name] = (editor_kind, editor)

            card = QtWidgets.QFrame()
            card.setObjectName("paramRecord")
            card.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(
                lambda pos, name=spec.name, source=card: self._show_param_card_context_menu(name, source.mapToGlobal(pos))
            )
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            card_layout.setSpacing(4)

            name_label = ElidedLabel(spec.name)
            name_label.setProperty("role", "name")
            name_label.setToolTip(spec.name)
            name_font = name_label.font()
            name_font.setBold(True)
            name_label.setFont(name_font)
            card_layout.addWidget(name_label)

            if spec.access == "rw":
                action_widget = QtWidgets.QPushButton("Apply")
                action_widget.pressed.connect(lambda name=spec.name: self._apply_param(name))
                action_widget.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Fixed,
                    QtWidgets.QSizePolicy.Policy.Fixed,
                )
                action_widget.setMinimumWidth(max(72, action_widget.fontMetrics().horizontalAdvance("Applying...") + 22))
                self._param_apply_buttons[spec.name] = action_widget
            else:
                action_widget = self._create_param_status_badge("Read only")

            metadata_layout = QtWidgets.QHBoxLayout()
            metadata_layout.setContentsMargins(0, 0, 0, 0)
            metadata_layout.setSpacing(6)

            current_caption = QtWidgets.QLabel("Current")
            current_caption.setProperty("role", "caption")
            caption_font = current_caption.font()
            if caption_font.pointSize() > 1:
                caption_font.setPointSize(caption_font.pointSize() - 1)
            current_caption.setFont(caption_font)
            metadata_layout.addWidget(current_caption, 0)

            current_label = QtWidgets.QLabel(str(current_value))
            current_label.setProperty("role", "value")
            current_label.setToolTip(str(current_value))
            metadata_layout.addWidget(current_label, 0)

            type_caption = QtWidgets.QLabel("Type")
            type_caption.setProperty("role", "caption")
            type_caption.setFont(caption_font)
            metadata_layout.addSpacing(8)
            metadata_layout.addWidget(type_caption, 0)

            type_badge = self._create_param_type_badge(spec.type)
            metadata_layout.addWidget(type_badge, 0)
            metadata_layout.addStretch(1)
            card_layout.addLayout(metadata_layout)

            editor_layout = QtWidgets.QHBoxLayout()
            editor_layout.setContentsMargins(0, 0, 0, 0)
            editor_layout.setSpacing(8)
            editor_layout.addWidget(editor, 1)
            editor_layout.addWidget(action_widget, 0)
            card_layout.addLayout(editor_layout)
            self._param_list_layout.addWidget(card)

            self._param_cards[spec.name] = card
            self._param_name_labels[spec.name] = name_label
            self._param_current_labels[spec.name] = current_label
            self._update_param_row_state(spec.name)

        self._param_list_layout.addStretch(1)

    def _refresh_existing_param_rows(self, device_model) -> None:
        if len(self._param_row_indexes) != len(self._current_param_specs):
            self._rebuild_params_table(device_model)
            return

        for index, spec in enumerate(self._current_param_specs):
            if self._param_row_indexes.get(spec.name) != index:
                self._rebuild_params_table(device_model)
                return

            current_value = self._current_param_value(spec, device_model)
            current_label = self._param_current_labels.get(spec.name)
            if current_label is None:
                self._rebuild_params_table(device_model)
                return
            current_label.setText(str(current_value))
            current_label.setToolTip(str(current_value))

            editor_info = self._param_editors.get(spec.name)
            if editor_info is None:
                self._rebuild_params_table(device_model)
                return

            pending = spec.name in self._pending_param_values
            applying = spec.name in self._param_apply_commands
            if spec.access != "rw" or (not pending and not applying):
                self._set_param_editor_value(editor_info[0], editor_info[1], current_value)

            self._update_param_row_state(spec.name)

    def _clear_param_records(self) -> None:
        while self._param_list_layout.count():
            item = self._param_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _create_param_detail_group(self, title: str, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        caption = QtWidgets.QLabel(title)
        caption.setProperty("role", "caption")
        caption_font = caption.font()
        if caption_font.pointSize() > 1:
            caption_font.setPointSize(caption_font.pointSize() - 1)
        caption.setFont(caption_font)

        layout.addWidget(caption)
        layout.addWidget(widget)
        return container

    def _create_param_type_badge(self, label: str) -> QtWidgets.QLabel:
        badge = QtWidgets.QLabel(label)
        badge.setProperty("role", "typeBadge")
        badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        badge.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        return badge

    def _create_param_status_badge(self, label: str) -> QtWidgets.QLabel:
        badge = QtWidgets.QLabel(label)
        badge.setProperty("role", "statusBadge")
        badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        badge.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        return badge

    def _create_param_editor(self, spec: ParamSpec, current_value: object) -> tuple[str, QtWidgets.QWidget]:
        if spec.access != "rw":
            label = QtWidgets.QLabel(str(current_value))
            label.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
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
                editor.setMinimumWidth(96)
                editor.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Expanding,
                    QtWidgets.QSizePolicy.Policy.Fixed,
                )
                editor.setRange(
                    float(spec.min if spec.min is not None else -1_000_000.0),
                    float(spec.max if spec.max is not None else 1_000_000.0),
                )
                editor.setValue(float(current_value))
                return ("float_spin", editor)
            line_edit = QtWidgets.QLineEdit(str(current_value))
            line_edit.setMinimumWidth(96)
            line_edit.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            return ("text", line_edit)

        if spec.min is not None or spec.max is not None:
            min_value = int(spec.min if spec.min is not None else -2_147_483_648)
            max_value = int(spec.max if spec.max is not None else 2_147_483_647)
            if min_value >= -2_147_483_648 and max_value <= 2_147_483_647:
                editor = QtWidgets.QSpinBox()
                editor.setKeyboardTracking(False)
                editor.setMinimumWidth(96)
                editor.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Expanding,
                    QtWidgets.QSizePolicy.Policy.Fixed,
                )
                editor.setRange(min_value, max_value)
                editor.setValue(int(current_value))
                return ("int_spin", editor)

        line_edit = QtWidgets.QLineEdit(str(current_value))
        line_edit.setMinimumWidth(96)
        line_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
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
        # Remove existing cards.
        while self._command_cards_layout.count() > 1:
            item = self._command_cards_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._command_cards = {}
        self._command_card_widgets = {}
        self._command_card_status_labels = {}
        for command in self._current_command_specs:
            card = self._build_command_card(command)
            self._command_cards_layout.insertWidget(self._command_cards_layout.count() - 1, card)
            self._command_cards[command.name] = card
        self._refresh_discovery_views()

    def _build_command_card(self, command: CommandSpec) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setObjectName("paramRecord")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)

        # Header row: name + send button.
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        name_label = QtWidgets.QLabel(command.name)
        name_font = name_label.font()
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setToolTip(command.name)
        header_layout.addWidget(name_label, 1)

        send_button = QtWidgets.QPushButton("Send")
        self._configure_button(
            send_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_ArrowForward,
            tooltip=f"Send {command.name}",
        )
        send_button.setFixedWidth(72)
        header_layout.addWidget(send_button, 0)
        card_layout.addLayout(header_layout)

        # Arg editors (one row per arg).
        arg_widgets: dict[str, tuple[str, QtWidgets.QWidget]] = {}
        for arg in command.args:
            row_layout = QtWidgets.QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            arg_label = QtWidgets.QLabel(arg.name + ":")
            arg_label.setProperty("role", "caption")
            row_layout.addWidget(arg_label, 0)
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
            row_layout.addWidget(editor, 1)
            card_layout.addLayout(row_layout)
            arg_widgets[arg.name] = (kind, editor)
        self._command_card_widgets[command.name] = arg_widgets

        # Status label (hidden until a send is attempted).
        status_label = QtWidgets.QLabel()
        status_label.setProperty("role", "caption")
        status_label.setWordWrap(True)
        status_label.setVisible(False)
        card_layout.addWidget(status_label)
        self._command_card_status_labels[command.name] = status_label

        send_button.clicked.connect(lambda: self._send_command_from_card(command.name))
        return card

    def _send_command_from_card(self, command_name: str) -> None:
        if self._selected_device is None:
            self._show_status("choose a device first", error=True)
            return

        arg_widgets = self._command_card_widgets.get(command_name, {})
        args: dict[str, object] = {}
        spec_map = {c.name: c for c in self._current_command_specs}
        command = spec_map.get(command_name)
        if command is None:
            return

        try:
            for arg in command.args:
                kind, widget = arg_widgets[arg.name]
                if kind == "string":
                    value: object = widget.text()  # type: ignore[union-attr]
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
            name=command_name,
            args=args,
        )
        status_label = self._command_card_status_labels.get(command_name)
        if command_id is not None and status_label is not None:
            self._command_id_to_name[command_id] = command_name
            status_label.setText(f"sent (id={command_id})")
            status_label.setVisible(True)

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
            if not self._all_param_specs:
                params_message = "No parameters available for this device."
            elif not self._current_param_specs:
                params_message = "No parameters added to this preset."
            else:
                params_message = ""
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
        self._add_param_button.setEnabled(has_capabilities and bool(self._all_param_specs))
        self._param_list_scroll.setEnabled(has_capabilities or bool(self._all_param_specs))

        self._commands_state_label.setVisible(bool(commands_message))
        self._commands_state_label.setText(commands_message)
        self._command_cards_scroll.setEnabled(has_capabilities)
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
                line_edit.returnPressed.connect(lambda name=param_name: self._apply_param_from_editor(name))
        elif kind == "text":
            editor.textChanged.connect(lambda _text, name=param_name: self._on_param_edited(name))  # type: ignore[union-attr]
            editor.returnPressed.connect(lambda name=param_name: self._apply_param_from_editor(name))  # type: ignore[union-attr]

    def _apply_param_from_editor(self, param_name: str) -> None:
        apply_button = self._param_apply_buttons.get(param_name)
        if apply_button is None or not apply_button.isEnabled():
            return
        self._apply_param(param_name)

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
        if param_name not in self._param_row_indexes:
            return

        pending = param_name in self._pending_param_values
        applying = param_name in self._param_apply_commands
        state_key = (pending, applying)
        if self._param_visual_states.get(param_name) == state_key:
            return
        self._param_visual_states[param_name] = state_key
        palette = self._param_list_scroll.palette()
        base_color = palette.base().color()
        text_color = palette.text().color()
        caption_base_color = self._blend_color(text_color, base_color, 0.42 if base_color.lightness() < 128 else 0.48)
        orange = QtGui.QColor("#f39c12")
        blue = QtGui.QColor("#0b84f3")
        is_dark = base_color.lightness() < 128
        field_text_color = self._blend_color(text_color, QtGui.QColor("#f5f7ff"), 0.18 if is_dark else 0.0)
        name_text_color = self._blend_color(field_text_color, QtGui.QColor("#ffffff"), 0.20 if is_dark else 0.08)
        caption_color = caption_base_color
        badge_fill = self._blend_color(base_color, palette.alternateBase().color(), 0.72 if is_dark else 0.45)
        badge_border = self._blend_color(badge_fill, field_text_color, 0.30 if is_dark else 0.18)
        badge_text_color = self._blend_color(field_text_color, QtGui.QColor("#ffffff"), 0.16 if is_dark else 0.05)

        if applying:
            card_color = self._blend_color(base_color, blue, 0.20 if is_dark else 0.10)
            border_color = self._blend_color(base_color, blue, 0.58 if is_dark else 0.72)
        elif pending:
            card_color = self._blend_color(base_color, orange, 0.22 if is_dark else 0.12)
            border_color = self._blend_color(base_color, orange, 0.60 if is_dark else 0.75)
        else:
            card_color = self._blend_color(base_color, palette.alternateBase().color(), 0.55 if is_dark else 0.35)
            border_color = self._blend_color(card_color, field_text_color, 0.20 if is_dark else 0.12)

        card = self._param_cards.get(param_name)
        if card is not None:
            card.setStyleSheet(
                "QFrame#paramRecord {"
                f"background-color: {card_color.name()};"
                f"border: 1px solid {border_color.name()};"
                "border-radius: 6px;"
                "}"
                "QFrame#paramRecord QLabel {"
                f"color: {field_text_color.name()};"
                "border: none;"
                "background: transparent;"
                "}"
                "QFrame#paramRecord QLabel[role='name'] {"
                f"color: {name_text_color.name()};"
                "}"
                "QFrame#paramRecord QLabel[role='caption'] {"
                f"color: {caption_color.name()};"
                "}"
                "QFrame#paramRecord QLabel[role='typeBadge'],"
                "QFrame#paramRecord QLabel[role='statusBadge'] {"
                f"color: {badge_text_color.name()};"
                f"background-color: {badge_fill.name()};"
                f"border: 1px solid {badge_border.name()};"
                "border-radius: 4px;"
                "padding: 1px 8px;"
                "}"
            )
            if applying:
                card.setToolTip("Waiting for the board to confirm this change")
            elif pending:
                card.setToolTip("Pending local edit")
            else:
                card.setToolTip("")

        editor_info = self._param_editors.get(param_name)
        if editor_info is not None:
            editor_info[1].setStyleSheet("")
            editor_info[1].setToolTip("Pending local edit" if pending else "")

        apply_button = self._param_apply_buttons.get(param_name)
        if apply_button is not None:
            apply_button.setText("Applying..." if applying else "Apply")
            apply_button.setEnabled(pending and self._selected_device is not None and not applying)
            apply_button.setStyleSheet("")
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
