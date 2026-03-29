from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from .workspace import DEFAULT_X_GROUP, PlotPane, PlotTrace, PlotWorkspace, default_trace_color

if TYPE_CHECKING:
    from .runtime import DashboardRuntime


DEFAULT_FOLLOW_POINT_COUNT = 250
FOLLOW_RIGHT_PADDING_FRACTION = 0.02
MAX_FOLLOW_SPAN_US = 10_000_000.0


@dataclass
class _XGroupState:
    follow_live: bool = True
    span_us: float | None = None
    span_locked: bool = False


class _PlotPaneWidget(QtWidgets.QFrame):
    activated = QtCore.Signal(str)
    title_changed = QtCore.Signal(str, str)
    x_group_changed = QtCore.Signal(str, str)
    follow_toggled = QtCore.Signal(str, bool)
    add_trace_requested = QtCore.Signal(str)
    move_up_requested = QtCore.Signal(str)
    move_down_requested = QtCore.Signal(str)
    duplicate_requested = QtCore.Signal(str)
    remove_requested = QtCore.Signal(str)
    trace_visibility_changed = QtCore.Signal(str, str, str, bool)
    trace_remove_requested = QtCore.Signal(str, str, str)
    trace_color_changed = QtCore.Signal(str, str, str, str)
    autoscale_requested = QtCore.Signal(str)
    x_range_manually_changed = QtCore.Signal(str, tuple)

    def __init__(self, pane: PlotPane, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._pane = pane
        self._pane_color = default_trace_color(0)
        self._trace_rows: dict[tuple[str, str], tuple[QtWidgets.QCheckBox, QtWidgets.QPushButton, QtWidgets.QLabel]] = {}
        self._curves: dict[tuple[str, str], pg.PlotDataItem] = {}
        self._suppress_manual_x_signal = False
        self._active = False
        self._build_ui()
        self.set_pane(pane, [pane.x_group], self._pane_color)

    @property
    def pane_id(self) -> str:
        return self._pane.id

    @property
    def plot_widget(self) -> pg.PlotWidget:
        return self._plot_widget

    def _build_ui(self) -> None:
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        self.installEventFilter(self)
        self.setStyleSheet("QFrame { border: 1px solid #3a4756; border-radius: 6px; }")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(6)
        self._active_indicator = QtWidgets.QLabel("\u25cb")
        self._active_indicator.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._active_indicator.setFixedWidth(16)
        self._active_indicator.setToolTip("Active pane indicator")
        self._active_indicator.setStatusTip("Active pane indicator")
        self._active_indicator.setStyleSheet("background: transparent; border: none;")
        header.addWidget(self._active_indicator)

        self._title_edit = QtWidgets.QLineEdit()
        self._title_edit.installEventFilter(self)
        self._title_edit.editingFinished.connect(self._emit_title_changed)
        header.addWidget(self._title_edit, 1)

        header.addWidget(QtWidgets.QLabel("Time Group"))
        self._x_group_combo = QtWidgets.QComboBox()
        self._x_group_combo.setEditable(True)
        self._x_group_combo.installEventFilter(self)
        self._x_group_combo.currentTextChanged.connect(self._emit_x_group_changed)
        header.addWidget(self._x_group_combo)

        self._follow_button = QtWidgets.QPushButton("Follow")
        self._configure_button(
            self._follow_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_MediaPlay,
            text="Follow",
            tooltip="Keep this time group following the newest samples",
        )
        self._follow_button.setCheckable(True)
        self._follow_button.setChecked(True)
        self._follow_button.installEventFilter(self)
        self._follow_button.toggled.connect(lambda checked: self.follow_toggled.emit(self._pane.id, checked))
        header.addWidget(self._follow_button)

        self._add_trace_button = QtWidgets.QPushButton("Add Trace")
        self._configure_button(
            self._add_trace_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_ArrowForward,
            text="",
            tooltip="Add the selected field to this pane",
        )
        self._add_trace_button.installEventFilter(self)
        self._add_trace_button.clicked.connect(lambda: self.add_trace_requested.emit(self._pane.id))
        header.addWidget(self._add_trace_button)

        move_up_button = QtWidgets.QPushButton("Up")
        self._configure_button(
            move_up_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_ArrowUp,
            text="",
            tooltip="Move this pane up",
        )
        move_up_button.installEventFilter(self)
        move_up_button.clicked.connect(lambda: self.move_up_requested.emit(self._pane.id))
        header.addWidget(move_up_button)

        move_down_button = QtWidgets.QPushButton("Down")
        self._configure_button(
            move_down_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_ArrowDown,
            text="",
            tooltip="Move this pane down",
        )
        move_down_button.installEventFilter(self)
        move_down_button.clicked.connect(lambda: self.move_down_requested.emit(self._pane.id))
        header.addWidget(move_down_button)

        duplicate_button = QtWidgets.QPushButton("Duplicate")
        self._configure_button(
            duplicate_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView,
            text="",
            tooltip="Duplicate this pane",
        )
        duplicate_button.installEventFilter(self)
        duplicate_button.clicked.connect(lambda: self.duplicate_requested.emit(self._pane.id))
        header.addWidget(duplicate_button)

        remove_button = QtWidgets.QPushButton("Remove")
        self._configure_button(
            remove_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_DialogDiscardButton,
            text="",
            tooltip="Remove this pane",
        )
        remove_button.installEventFilter(self)
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self._pane.id))
        header.addWidget(remove_button)

        autoscale_button = QtWidgets.QPushButton("Reset View")
        self._configure_button(
            autoscale_button,
            icon=QtWidgets.QStyle.StandardPixmap.SP_DialogResetButton,
            text="",
            tooltip="Reset this pane view and re-enable live follow",
        )
        autoscale_button.installEventFilter(self)
        autoscale_button.clicked.connect(lambda: self.autoscale_requested.emit(self._pane.id))
        header.addWidget(autoscale_button)

        layout.addLayout(header)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.installEventFilter(self)
        self._plot_widget.setBackground("#101822")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self._plot_widget.setLabel("bottom", "Device Time", units="us")
        self._plot_widget.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self._plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        self._plot_widget.getViewBox().sigRangeChangedManually.connect(self._on_manual_range_changed)
        self._plot_widget.scene().sigMouseClicked.connect(lambda *_: self.activated.emit(self._pane.id))
        layout.addWidget(self._plot_widget, 1)

        trace_container = QtWidgets.QWidget()
        trace_container.installEventFilter(self)
        self._trace_layout = QtWidgets.QVBoxLayout(trace_container)
        self._trace_layout.setContentsMargins(0, 0, 0, 0)
        self._trace_layout.setSpacing(4)
        layout.addWidget(trace_container)

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

    def _refresh_active_indicator(self) -> None:
        self._active_indicator.setText("\u25cf" if self._active else "\u25cb")
        self._active_indicator.setToolTip("Active pane" if self._active else "Inactive pane")
        self._active_indicator.setStyleSheet(
            f"color: {self._pane_color}; background: transparent; border: none; font-size: 14px;"
        )

    def set_active(self, active: bool) -> None:
        self._active = active
        self._refresh_active_indicator()

    def set_pane(self, pane: PlotPane, group_options: Iterable[str], pane_color: str) -> None:
        self._pane = pane
        self._pane_color = pane_color
        self._title_edit.blockSignals(True)
        self._title_edit.setText(pane.title)
        self._title_edit.blockSignals(False)

        current_group = pane.x_group
        self._x_group_combo.blockSignals(True)
        self._x_group_combo.clear()
        options = list(dict.fromkeys(group_options))
        if current_group not in options:
            options.append(current_group)
        if DEFAULT_X_GROUP not in options:
            options.insert(0, DEFAULT_X_GROUP)
        self._x_group_combo.addItems(options)
        self._x_group_combo.setCurrentText(current_group)
        self._x_group_combo.blockSignals(False)

        self._refresh_active_indicator()
        self._sync_trace_rows()

    def set_follow_live(self, follow_live: bool) -> None:
        self._follow_button.blockSignals(True)
        self._follow_button.setChecked(follow_live)
        self._follow_button.blockSignals(False)
        self._follow_button.setText("Following" if follow_live else "Follow")
        self._follow_button.setToolTip(
            "Live follow is enabled for this time group"
            if follow_live else
            "Resume live follow for this time group"
        )

    def current_x_range(self) -> tuple[float, float] | None:
        x_range = self._plot_widget.viewRange()[0]
        if len(x_range) != 2:
            return None
        try:
            x_min = float(x_range[0])
            x_max = float(x_range[1])
        except (TypeError, ValueError):
            return None
        if not (x_max > x_min):
            return None
        return (x_min, x_max)

    def set_x_range(self, x_min: float, x_max: float) -> None:
        if not (x_max > x_min):
            return
        self._suppress_manual_x_signal = True
        try:
            self._plot_widget.setXRange(x_min, x_max, padding=0)
        finally:
            self._suppress_manual_x_signal = False

    def _sync_trace_rows(self) -> None:
        wanted_keys = {trace.key for trace in self._pane.traces}

        for key, widgets in list(self._trace_rows.items()):
            if key in wanted_keys:
                continue
            checkbox, color_button, label = widgets
            self._trace_layout.removeWidget(checkbox.parentWidget())
            checkbox.parentWidget().deleteLater()
            self._trace_rows.pop(key, None)
            curve = self._curves.pop(key, None)
            if curve is not None:
                self._plot_widget.removeItem(curve)

        for trace in self._pane.traces:
            row = self._trace_rows.get(trace.key)
            if row is None:
                container = QtWidgets.QWidget()
                container.installEventFilter(self)
                row_layout = QtWidgets.QHBoxLayout(container)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)

                checkbox = QtWidgets.QCheckBox()
                checkbox.installEventFilter(self)
                checkbox.toggled.connect(
                    lambda checked, stream=trace.stream, field=trace.field: self.trace_visibility_changed.emit(
                        self._pane.id,
                        stream,
                        field,
                        checked,
                    )
                )
                row_layout.addWidget(checkbox)

                color_button = QtWidgets.QPushButton()
                color_button.installEventFilter(self)
                color_button.setFixedWidth(28)
                color_button.clicked.connect(
                    lambda _checked=False, stream=trace.stream, field=trace.field: self._choose_trace_color(stream, field)
                )
                row_layout.addWidget(color_button)

                label = QtWidgets.QLabel()
                label.installEventFilter(self)
                row_layout.addWidget(label, 1)

                remove_button = QtWidgets.QToolButton()
                remove_button.installEventFilter(self)
                self._configure_button(
                    remove_button,
                    icon=QtWidgets.QStyle.StandardPixmap.SP_DialogCloseButton,
                    text="",
                    tooltip="Remove this trace from the pane",
                )
                remove_button.clicked.connect(
                    lambda _checked=False, stream=trace.stream, field=trace.field: self.trace_remove_requested.emit(
                        self._pane.id,
                        stream,
                        field,
                    )
                )
                row_layout.addWidget(remove_button)

                self._trace_layout.addWidget(container)
                row = (checkbox, color_button, label)
                self._trace_rows[trace.key] = row

            checkbox, color_button, label = row
            checkbox.blockSignals(True)
            checkbox.setChecked(trace.visible)
            checkbox.blockSignals(False)
            label.setText(trace.display_label)
            label.setToolTip(trace.display_label)
            color_button.setStyleSheet(
                f"background-color: {trace.color}; border: 1px solid #2a3240; border-radius: 4px;"
            )

    def _choose_trace_color(self, stream: str, field: str) -> None:
        trace = next((item for item in self._pane.traces if item.stream == stream and item.field == field), None)
        if trace is None:
            return
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(trace.color), self, "Choose Trace Color")
        if color.isValid():
            self.trace_color_changed.emit(self._pane.id, stream, field, color.name())

    def _emit_title_changed(self) -> None:
        self.title_changed.emit(self._pane.id, self._title_edit.text().strip() or self._pane.title)

    def _emit_x_group_changed(self, group_name: str) -> None:
        normalized = group_name.strip() or DEFAULT_X_GROUP
        self.x_group_changed.emit(self._pane.id, normalized)

    def set_trace_data(self, trace: PlotTrace, x_values: list[int], y_values: list[float]) -> None:
        curve = self._curves.get(trace.key)
        if curve is None:
            curve = self._plot_widget.plot([], [], pen=pg.mkPen(trace.color, width=1), name=trace.display_label)
            if hasattr(curve, "setClipToView"):
                curve.setClipToView(True)
            if hasattr(curve, "setDownsampling"):
                curve.setDownsampling(auto=True, method="subsample")
            if hasattr(curve, "setSkipFiniteCheck"):
                curve.setSkipFiniteCheck(True)
            self._curves[trace.key] = curve
        curve.setPen(pg.mkPen(trace.color, width=1))
        curve.setData(x_values, y_values)
        curve.setVisible(trace.visible)

    def clear_trace_data(self, trace: PlotTrace) -> None:
        curve = self._curves.get(trace.key)
        if curve is None:
            return
        curve.setData([], [])
        curve.setVisible(trace.visible)

    def autoscale(self) -> None:
        self._plot_widget.autoRange()

    def _on_manual_range_changed(self, mask: object) -> None:
        if self._suppress_manual_x_signal:
            return
        x_changed = True
        if isinstance(mask, (list, tuple)) and mask:
            x_changed = bool(mask[0])
        elif mask is not None:
            try:
                x_changed = bool(mask[0])  # type: ignore[index]
            except Exception:
                x_changed = True
        if not x_changed:
            return
        x_range = self.current_x_range()
        if x_range is not None:
            self.x_range_manually_changed.emit(self._pane.id, x_range)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() in {
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.FocusIn,
        }:
            self.activated.emit(self._pane.id)
        return super().eventFilter(watched, event)


class PlotWorkspaceWidget(QtWidgets.QWidget):
    workspace_changed = QtCore.Signal(object)
    active_pane_changed = QtCore.Signal(str)
    add_trace_requested = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._workspace: PlotWorkspace | None = None
        self._pane_widgets: dict[str, _PlotPaneWidget] = {}
        self._pane_order: list[str] = []
        self._suppress_splitter_events = False
        self._group_states: dict[str, _XGroupState] = {}
        self._group_leaders: dict[str, str] = {}
        self._last_runtime: DashboardRuntime | None = None
        self._last_device: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._state_label = QtWidgets.QLabel("No plot workspace loaded")
        self._state_label.setWordWrap(True)
        layout.addWidget(self._state_label)

        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(10)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        layout.addWidget(self._splitter, 1)

    @property
    def workspace(self) -> PlotWorkspace | None:
        return self._workspace

    def current_workspace_snapshot(self) -> PlotWorkspace | None:
        if self._workspace is None:
            return None
        return self._merge_current_sizes(self._workspace)

    @property
    def active_pane_id(self) -> str | None:
        if self._workspace is None:
            return None
        pane_ids = {pane.id for pane in self._workspace.panes}
        if self._workspace.active_pane_id in pane_ids:
            return self._workspace.active_pane_id
        return self._workspace.panes[0].id if self._workspace.panes else None

    def set_workspace(self, workspace: PlotWorkspace | None) -> None:
        self._workspace = workspace
        self._sync_widgets()

    def add_pane(self) -> None:
        if self._workspace is None:
            return
        next_index = len(self._workspace.panes) + 1
        pane = PlotPane(id=f"pane-{next_index}", title=f"Pane {next_index}")
        self._replace_workspace(
            PlotWorkspace(
                device=self._workspace.device,
                panes=self._workspace.panes + (pane,),
                active_pane_id=pane.id,
            )
        )

    def duplicate_active_pane(self) -> None:
        if self._workspace is None:
            return
        active = self._active_pane()
        if active is None:
            return
        next_index = len(self._workspace.panes) + 1
        duplicate = PlotPane(
            id=f"pane-{next_index}",
            title=f"{active.title} Copy",
            x_group=active.x_group,
            traces=active.traces,
            size=active.size,
        )
        self._replace_workspace(
            PlotWorkspace(
                device=self._workspace.device,
                panes=self._workspace.panes + (duplicate,),
                active_pane_id=duplicate.id,
            )
        )

    def remove_active_pane(self) -> None:
        active = self._active_pane()
        if active is None or self._workspace is None:
            return
        remaining = tuple(pane for pane in self._workspace.panes if pane.id != active.id)
        if not remaining:
            remaining = (PlotPane(id="pane-1", title="Main"),)
        self._replace_workspace(
            PlotWorkspace(
                device=self._workspace.device,
                panes=remaining,
                active_pane_id=remaining[0].id,
            )
        )

    def move_active_pane(self, direction: int) -> None:
        active = self._active_pane()
        if active is None or self._workspace is None:
            return
        panes = list(self._workspace.panes)
        index = next((item for item, pane in enumerate(panes) if pane.id == active.id), None)
        if index is None:
            return
        target = index + direction
        if target < 0 or target >= len(panes):
            return
        panes[index], panes[target] = panes[target], panes[index]
        self._replace_workspace(
            PlotWorkspace(
                device=self._workspace.device,
                panes=tuple(panes),
                active_pane_id=active.id,
            )
        )

    def add_trace(self, stream: str, field: str, color: str) -> None:
        active = self._active_pane()
        if active is None or self._workspace is None:
            return
        if any(trace.stream == stream and trace.field == field for trace in active.traces):
            return
        updated = PlotPane(
            id=active.id,
            title=active.title,
            x_group=active.x_group,
            traces=active.traces + (PlotTrace(stream=stream, field=field, color=color),),
            size=active.size,
        )
        self._replace_pane(updated)

    def refresh_data(self, runtime: DashboardRuntime, device: str | None) -> None:
        self._last_runtime = runtime
        self._last_device = device
        if self._workspace is None or device is None or self._workspace.device != device:
            return
        for pane in self._workspace.panes:
            widget = self._pane_widgets.get(pane.id)
            if widget is None:
                continue
            for trace in pane.traces:
                x_values, y_values = runtime.series_for_field(device, trace.stream, trace.field)
                if x_values and y_values:
                    widget.set_trace_data(trace, x_values, y_values)
                else:
                    widget.clear_trace_data(trace)
        self._apply_follow_state(runtime, device)

    def active_trace_values(self, runtime: DashboardRuntime, device: str | None) -> list[tuple[str, object, str]]:
        active = self._active_pane()
        if active is None or device is None:
            return []
        items: list[tuple[str, object, str]] = []
        for trace in active.traces:
            value = runtime.latest_value_for_field(device, trace.stream, trace.field)
            unit = ""
            for field in runtime.field_specs_for_stream(device, trace.stream):
                if field.name == trace.field:
                    unit = field.unit
                    break
            items.append((trace.display_label, value, unit))
        return items

    def _replace_workspace(self, workspace: PlotWorkspace) -> None:
        self._workspace = self._merge_current_sizes(workspace)
        self._sync_widgets()
        self.workspace_changed.emit(self._workspace)
        active = self.active_pane_id
        if active is not None:
            self.active_pane_changed.emit(active)

    def _replace_pane(self, updated_pane: PlotPane) -> None:
        if self._workspace is None:
            return
        panes = tuple(updated_pane if pane.id == updated_pane.id else pane for pane in self._workspace.panes)
        self._replace_workspace(
            PlotWorkspace(
                device=self._workspace.device,
                panes=panes,
                active_pane_id=updated_pane.id,
            )
        )

    def _active_pane(self) -> PlotPane | None:
        if self._workspace is None or not self._workspace.panes:
            return None
        active_id = self.active_pane_id
        for pane in self._workspace.panes:
            if pane.id == active_id:
                return pane
        return self._workspace.panes[0]

    def _sync_widgets(self) -> None:
        workspace = self._workspace
        size_by_id = self._capture_sizes()
        self._state_label.setVisible(workspace is None or not workspace.panes)
        if workspace is None:
            self._state_label.setText("No plot workspace loaded")
            for pane_id, widget in list(self._pane_widgets.items()):
                self._remove_pane_widget(pane_id, widget)
            self._pane_order = []
            return
        if not workspace.panes:
            self._state_label.setText("No panes configured for this device")
            return
        self._state_label.setVisible(False)

        wanted_ids = {pane.id for pane in workspace.panes}
        for pane_id, widget in list(self._pane_widgets.items()):
            if pane_id not in wanted_ids:
                self._remove_pane_widget(pane_id, widget)

        group_names = self._group_names(workspace)
        self._sync_group_states(group_names)
        for index, pane in enumerate(workspace.panes):
            pane_color = default_trace_color(index)
            widget = self._pane_widgets.get(pane.id)
            if widget is None:
                widget = _PlotPaneWidget(pane)
                widget.activated.connect(self._on_pane_activated)
                widget.title_changed.connect(self._on_title_changed)
                widget.x_group_changed.connect(self._on_x_group_changed)
                widget.follow_toggled.connect(self._on_follow_toggled)
                widget.add_trace_requested.connect(self._on_add_trace_requested)
                widget.move_up_requested.connect(self._on_move_up_requested)
                widget.move_down_requested.connect(self._on_move_down_requested)
                widget.duplicate_requested.connect(self._on_duplicate_requested)
                widget.remove_requested.connect(self._on_remove_requested)
                widget.trace_visibility_changed.connect(self._on_trace_visibility_changed)
                widget.trace_remove_requested.connect(self._on_trace_removed)
                widget.trace_color_changed.connect(self._on_trace_color_changed)
                widget.autoscale_requested.connect(self._on_autoscale_requested)
                widget.x_range_manually_changed.connect(self._on_manual_x_range_changed)
                self._pane_widgets[pane.id] = widget
                self._splitter.insertWidget(index, widget)
            widget.set_pane(pane, group_names, pane_color)
            widget.set_follow_live(self._group_states.get(pane.x_group, _XGroupState()).follow_live)
            current_index = self._splitter.indexOf(widget)
            if current_index != index:
                widget.setParent(None)
                self._splitter.insertWidget(index, widget)

        active_id = self.active_pane_id
        for pane_id, widget in self._pane_widgets.items():
            widget.set_active(pane_id == active_id)
        self._pane_order = [pane.id for pane in workspace.panes]
        self._restore_sizes(size_by_id)
        self._sync_x_links()

    def _remove_pane_widget(self, pane_id: str, widget: _PlotPaneWidget) -> None:
        widget.setParent(None)
        widget.deleteLater()
        self._pane_widgets.pop(pane_id, None)

    def _capture_sizes(self) -> dict[str, int]:
        size_by_id: dict[str, int] = {}
        sizes = self._splitter.sizes()
        for index, pane_id in enumerate(self._pane_order):
            if index < len(sizes):
                size_by_id[pane_id] = sizes[index]
        return size_by_id

    def _restore_sizes(self, size_by_id: dict[str, int]) -> None:
        if self._workspace is None or not self._workspace.panes:
            return
        sizes = [size_by_id.get(pane.id, pane.size or 240) for pane in self._workspace.panes]
        if any(size > 0 for size in sizes):
            self._suppress_splitter_events = True
            try:
                self._splitter.setSizes(sizes)
            finally:
                self._suppress_splitter_events = False

    def _merge_current_sizes(self, workspace: PlotWorkspace) -> PlotWorkspace:
        if self._workspace is None or self._workspace.device != workspace.device:
            return workspace
        size_by_id = self._capture_sizes()
        if not size_by_id:
            return workspace
        panes = tuple(
            PlotPane(
                id=pane.id,
                title=pane.title,
                x_group=pane.x_group,
                traces=pane.traces,
                size=size_by_id.get(pane.id, pane.size),
            )
            for pane in workspace.panes
        )
        return PlotWorkspace(
            device=workspace.device,
            panes=panes,
            active_pane_id=workspace.active_pane_id,
            version=workspace.version,
        )

    def _sync_group_states(self, group_names: Iterable[str]) -> None:
        next_states: dict[str, _XGroupState] = {}
        for name in group_names:
            next_states[name] = self._group_states.get(name, _XGroupState())
        self._group_states = next_states

    def _group_names(self, workspace: PlotWorkspace) -> list[str]:
        groups = [DEFAULT_X_GROUP]
        for pane in workspace.panes:
            if pane.x_group not in groups:
                groups.append(pane.x_group)
        return groups

    def _sync_x_links(self) -> None:
        if self._workspace is None:
            return
        panes_by_group: dict[str, list[_PlotPaneWidget]] = {}
        self._group_leaders = {}
        for pane in self._workspace.panes:
            widget = self._pane_widgets.get(pane.id)
            if widget is None:
                continue
            widget.plot_widget.setXLink(None)
            panes_by_group.setdefault(pane.x_group, []).append(widget)

        for group_name, widgets in panes_by_group.items():
            if not widgets:
                continue
            leader = widgets[0].plot_widget.getViewBox()
            self._group_leaders[group_name] = widgets[0].pane_id
            for widget in widgets[1:]:
                widget.plot_widget.setXLink(leader)

    def _apply_follow_state(self, runtime: DashboardRuntime, device: str) -> None:
        if self._workspace is None or self._workspace.device != device:
            return

        group_latest_x: dict[str, float] = {}
        group_recent_span: dict[str, float] = {}
        for pane in self._workspace.panes:
            for trace in pane.traces:
                if not trace.visible:
                    continue
                x_values, _y_values = runtime.series_for_field(device, trace.stream, trace.field)
                if not x_values:
                    continue
                latest_x = float(x_values[-1])
                existing_latest = group_latest_x.get(pane.x_group)
                if existing_latest is None or latest_x > existing_latest:
                    group_latest_x[pane.x_group] = latest_x
                if len(x_values) >= 2:
                    start_index = max(0, len(x_values) - DEFAULT_FOLLOW_POINT_COUNT)
                    span = float(x_values[-1] - x_values[start_index])
                    if span > group_recent_span.get(pane.x_group, 0.0):
                        group_recent_span[pane.x_group] = span

        for group_name, leader_id in self._group_leaders.items():
            state = self._group_states.get(group_name)
            if state is None or not state.follow_live:
                continue
            latest_x = group_latest_x.get(group_name)
            if latest_x is None:
                continue
            leader_widget = self._pane_widgets.get(leader_id)
            if leader_widget is None:
                continue

            span_us = state.span_us
            if state.span_locked:
                if span_us is None or span_us <= 0:
                    span_us = group_recent_span.get(group_name, 0.0)
                    if span_us <= 0:
                        current_x_range = leader_widget.current_x_range()
                        if current_x_range is not None:
                            span_us = current_x_range[1] - current_x_range[0]
                    if span_us <= 0:
                        span_us = 1.0
                    span_us = self._clamp_follow_span(span_us)
                    state.span_us = span_us
            else:
                span_us = group_recent_span.get(group_name, 0.0)
                if span_us <= 0:
                    current_x_range = leader_widget.current_x_range()
                    if current_x_range is not None:
                        span_us = current_x_range[1] - current_x_range[0]
                if span_us <= 0:
                    span_us = 1.0
                span_us = self._clamp_follow_span(span_us)
                state.span_us = span_us

            padding_us = max(span_us * FOLLOW_RIGHT_PADDING_FRACTION, 1.0)
            x_max = latest_x + padding_us
            x_min = x_max - span_us
            leader_widget.set_x_range(x_min, x_max)

    @staticmethod
    def _clamp_follow_span(span_us: float) -> float:
        return max(1.0, min(float(span_us), MAX_FOLLOW_SPAN_US))

    @QtCore.Slot(str)
    def _on_pane_activated(self, pane_id: str) -> None:
        if self._workspace is None or pane_id == self.active_pane_id:
            return
        self._replace_workspace(
            PlotWorkspace(
                device=self._workspace.device,
                panes=self._workspace.panes,
                active_pane_id=pane_id,
            )
        )

    @QtCore.Slot(str, str)
    def _on_title_changed(self, pane_id: str, title: str) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        self._replace_pane(PlotPane(id=pane.id, title=title, x_group=pane.x_group, traces=pane.traces, size=pane.size))

    @QtCore.Slot(str, str)
    def _on_x_group_changed(self, pane_id: str, group_name: str) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        self._replace_pane(
            PlotPane(
                id=pane.id,
                title=pane.title,
                x_group=group_name.strip() or DEFAULT_X_GROUP,
                traces=pane.traces,
                size=pane.size,
            )
        )

    @QtCore.Slot(str, bool)
    def _on_follow_toggled(self, pane_id: str, follow_live: bool) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        state = self._group_states.setdefault(pane.x_group, _XGroupState())
        state.follow_live = follow_live
        widget = self._pane_widgets.get(pane_id)
        if widget is not None:
            current_x_range = widget.current_x_range()
            if current_x_range is not None:
                state.span_us = self._clamp_follow_span(current_x_range[1] - current_x_range[0])
        state.span_locked = True
        for group_pane in self._workspace.panes if self._workspace is not None else ():
            if group_pane.x_group == pane.x_group:
                peer = self._pane_widgets.get(group_pane.id)
                if peer is not None:
                    peer.set_follow_live(follow_live)
        if follow_live and self._last_runtime is not None and self._last_device is not None:
            self._apply_follow_state(self._last_runtime, self._last_device)

    @QtCore.Slot(str)
    def _on_add_trace_requested(self, pane_id: str) -> None:
        self._on_pane_activated(pane_id)
        self.add_trace_requested.emit(pane_id)

    @QtCore.Slot(str)
    def _on_move_up_requested(self, pane_id: str) -> None:
        self._on_pane_activated(pane_id)
        self.move_active_pane(-1)

    @QtCore.Slot(str)
    def _on_move_down_requested(self, pane_id: str) -> None:
        self._on_pane_activated(pane_id)
        self.move_active_pane(1)

    @QtCore.Slot(str)
    def _on_duplicate_requested(self, pane_id: str) -> None:
        self._on_pane_activated(pane_id)
        self.duplicate_active_pane()

    @QtCore.Slot(str)
    def _on_remove_requested(self, pane_id: str) -> None:
        self._on_pane_activated(pane_id)
        self.remove_active_pane()

    @QtCore.Slot(str, str, str, bool)
    def _on_trace_visibility_changed(self, pane_id: str, stream: str, field: str, visible: bool) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        traces = []
        for trace in pane.traces:
            if trace.stream == stream and trace.field == field:
                traces.append(
                    PlotTrace(
                        stream=trace.stream,
                        field=trace.field,
                        color=trace.color,
                        visible=visible,
                        label=trace.label,
                    )
                )
            else:
                traces.append(trace)
        self._replace_pane(PlotPane(id=pane.id, title=pane.title, x_group=pane.x_group, traces=tuple(traces), size=pane.size))

    @QtCore.Slot(str, str, str)
    def _on_trace_removed(self, pane_id: str, stream: str, field: str) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        traces = tuple(trace for trace in pane.traces if not (trace.stream == stream and trace.field == field))
        self._replace_pane(PlotPane(id=pane.id, title=pane.title, x_group=pane.x_group, traces=traces, size=pane.size))

    @QtCore.Slot(str, str, str, str)
    def _on_trace_color_changed(self, pane_id: str, stream: str, field: str, color: str) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        traces = []
        for trace in pane.traces:
            if trace.stream == stream and trace.field == field:
                traces.append(
                    PlotTrace(
                        stream=trace.stream,
                        field=trace.field,
                        color=color,
                        visible=trace.visible,
                        label=trace.label,
                    )
                )
            else:
                traces.append(trace)
        self._replace_pane(PlotPane(id=pane.id, title=pane.title, x_group=pane.x_group, traces=tuple(traces), size=pane.size))

    @QtCore.Slot(str)
    def _on_autoscale_requested(self, pane_id: str) -> None:
        widget = self._pane_widgets.get(pane_id)
        if widget is not None:
            widget.autoscale()
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        state = self._group_states.setdefault(pane.x_group, _XGroupState())
        state.follow_live = True
        state.span_us = None
        state.span_locked = False
        for group_pane in self._workspace.panes if self._workspace is not None else ():
            if group_pane.x_group == pane.x_group:
                peer = self._pane_widgets.get(group_pane.id)
                if peer is not None:
                    peer.set_follow_live(True)
        if self._last_runtime is not None and self._last_device is not None:
            self._apply_follow_state(self._last_runtime, self._last_device)

    @QtCore.Slot(str, tuple)
    def _on_manual_x_range_changed(self, pane_id: str, x_range: tuple[float, float]) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        state = self._group_states.setdefault(pane.x_group, _XGroupState())
        state.follow_live = False
        state.span_us = self._clamp_follow_span(x_range[1] - x_range[0])
        state.span_locked = True
        for group_pane in self._workspace.panes if self._workspace is not None else ():
            if group_pane.x_group == pane.x_group:
                peer = self._pane_widgets.get(group_pane.id)
                if peer is not None:
                    peer.set_follow_live(False)

    def _pane_by_id(self, pane_id: str) -> PlotPane | None:
        if self._workspace is None:
            return None
        for pane in self._workspace.panes:
            if pane.id == pane_id:
                return pane
        return None

    @QtCore.Slot(int, int)
    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        if self._suppress_splitter_events or self._workspace is None:
            return

        size_by_id = self._capture_sizes()
        panes = []
        changed = False
        for pane in self._workspace.panes:
            size = size_by_id.get(pane.id, pane.size)
            if size != pane.size:
                changed = True
            panes.append(
                PlotPane(
                    id=pane.id,
                    title=pane.title,
                    x_group=pane.x_group,
                    traces=pane.traces,
                    size=size,
                )
            )

        if not changed:
            return

        self._workspace = PlotWorkspace(
            device=self._workspace.device,
            panes=tuple(panes),
            active_pane_id=self._workspace.active_pane_id,
            version=self._workspace.version,
        )
        self.workspace_changed.emit(self._workspace)
