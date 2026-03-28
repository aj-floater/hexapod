from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from .workspace import DEFAULT_X_GROUP, PlotPane, PlotTrace, PlotWorkspace

if TYPE_CHECKING:
    from .runtime import DashboardRuntime


class _PlotPaneWidget(QtWidgets.QFrame):
    activated = QtCore.Signal(str)
    title_changed = QtCore.Signal(str, str)
    x_group_changed = QtCore.Signal(str, str)
    add_trace_requested = QtCore.Signal(str)
    duplicate_requested = QtCore.Signal(str)
    remove_requested = QtCore.Signal(str)
    trace_visibility_changed = QtCore.Signal(str, str, str, bool)
    trace_remove_requested = QtCore.Signal(str, str, str)
    trace_color_changed = QtCore.Signal(str, str, str, str)
    autoscale_requested = QtCore.Signal(str)

    def __init__(self, pane: PlotPane, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._pane = pane
        self._trace_rows: dict[tuple[str, str], tuple[QtWidgets.QCheckBox, QtWidgets.QPushButton, QtWidgets.QLabel]] = {}
        self._curves: dict[tuple[str, str], pg.PlotDataItem] = {}
        self._build_ui()
        self.set_pane(pane, [pane.x_group])

    @property
    def pane_id(self) -> str:
        return self._pane.id

    @property
    def plot_widget(self) -> pg.PlotWidget:
        return self._plot_widget

    def _build_ui(self) -> None:
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setLineWidth(1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(6)
        self._title_edit = QtWidgets.QLineEdit()
        self._title_edit.editingFinished.connect(self._emit_title_changed)
        header.addWidget(self._title_edit, 1)

        header.addWidget(QtWidgets.QLabel("Time Group"))
        self._x_group_combo = QtWidgets.QComboBox()
        self._x_group_combo.setEditable(True)
        self._x_group_combo.currentTextChanged.connect(self._emit_x_group_changed)
        header.addWidget(self._x_group_combo)

        self._add_trace_button = QtWidgets.QPushButton("Add Trace")
        self._add_trace_button.clicked.connect(lambda: self.add_trace_requested.emit(self._pane.id))
        header.addWidget(self._add_trace_button)

        duplicate_button = QtWidgets.QPushButton("Duplicate")
        duplicate_button.clicked.connect(lambda: self.duplicate_requested.emit(self._pane.id))
        header.addWidget(duplicate_button)

        remove_button = QtWidgets.QPushButton("Remove")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self._pane.id))
        header.addWidget(remove_button)

        autoscale_button = QtWidgets.QPushButton("Reset View")
        autoscale_button.clicked.connect(lambda: self.autoscale_requested.emit(self._pane.id))
        header.addWidget(autoscale_button)

        layout.addLayout(header)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("#101822")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self._plot_widget.setLabel("bottom", "Device Time", units="us")
        self._plot_widget.scene().sigMouseClicked.connect(lambda *_: self.activated.emit(self._pane.id))
        layout.addWidget(self._plot_widget, 1)

        trace_container = QtWidgets.QWidget()
        self._trace_layout = QtWidgets.QVBoxLayout(trace_container)
        self._trace_layout.setContentsMargins(0, 0, 0, 0)
        self._trace_layout.setSpacing(4)
        layout.addWidget(trace_container)

    def set_active(self, active: bool) -> None:
        if active:
            self.setStyleSheet("QFrame { border: 2px solid #0b84f3; border-radius: 6px; }")
        else:
            self.setStyleSheet("QFrame { border: 1px solid #3a4756; border-radius: 6px; }")

    def set_pane(self, pane: PlotPane, group_options: Iterable[str]) -> None:
        self._pane = pane
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

        self._sync_trace_rows()

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
                row_layout = QtWidgets.QHBoxLayout(container)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)

                checkbox = QtWidgets.QCheckBox()
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
                color_button.setFixedWidth(28)
                color_button.clicked.connect(
                    lambda _checked=False, stream=trace.stream, field=trace.field: self._choose_trace_color(stream, field)
                )
                row_layout.addWidget(color_button)

                label = QtWidgets.QLabel()
                row_layout.addWidget(label, 1)

                remove_button = QtWidgets.QToolButton()
                remove_button.setText("x")
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
            curve = self._plot_widget.plot([], [], pen=pg.mkPen(trace.color, width=2), name=trace.display_label)
            self._curves[trace.key] = curve
        curve.setPen(pg.mkPen(trace.color, width=2))
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


class PlotWorkspaceWidget(QtWidgets.QWidget):
    workspace_changed = QtCore.Signal(object)
    active_pane_changed = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._workspace: PlotWorkspace | None = None
        self._pane_widgets: dict[str, _PlotPaneWidget] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._state_label = QtWidgets.QLabel("No plot workspace loaded")
        self._state_label.setWordWrap(True)
        layout.addWidget(self._state_label)

        self._scroll_area = QtWidgets.QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self._pane_container = QtWidgets.QWidget()
        self._pane_layout = QtWidgets.QVBoxLayout(self._pane_container)
        self._pane_layout.setContentsMargins(0, 0, 0, 0)
        self._pane_layout.setSpacing(10)
        self._pane_layout.addStretch(1)

        self._scroll_area.setWidget(self._pane_container)
        layout.addWidget(self._scroll_area, 1)

    @property
    def workspace(self) -> PlotWorkspace | None:
        return self._workspace

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
        )
        self._replace_pane(updated)

    def refresh_data(self, runtime: DashboardRuntime, device: str | None) -> None:
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
        self._workspace = workspace
        self._sync_widgets()
        self.workspace_changed.emit(workspace)
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
        self._state_label.setVisible(workspace is None or not workspace.panes)
        if workspace is None:
            self._state_label.setText("No plot workspace loaded")
            for pane_id, widget in list(self._pane_widgets.items()):
                self._remove_pane_widget(pane_id, widget)
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
        for index, pane in enumerate(workspace.panes):
            widget = self._pane_widgets.get(pane.id)
            if widget is None:
                widget = _PlotPaneWidget(pane)
                widget.activated.connect(self._on_pane_activated)
                widget.title_changed.connect(self._on_title_changed)
                widget.x_group_changed.connect(self._on_x_group_changed)
                widget.add_trace_requested.connect(self._on_add_trace_requested)
                widget.duplicate_requested.connect(self._on_duplicate_requested)
                widget.remove_requested.connect(self._on_remove_requested)
                widget.trace_visibility_changed.connect(self._on_trace_visibility_changed)
                widget.trace_remove_requested.connect(self._on_trace_removed)
                widget.trace_color_changed.connect(self._on_trace_color_changed)
                widget.autoscale_requested.connect(self._on_autoscale_requested)
                self._pane_widgets[pane.id] = widget
                self._pane_layout.insertWidget(index, widget)
            widget.set_pane(pane, group_names)
            current_index = self._pane_layout.indexOf(widget)
            if current_index != index:
                self._pane_layout.removeWidget(widget)
                self._pane_layout.insertWidget(index, widget)

        active_id = self.active_pane_id
        for pane_id, widget in self._pane_widgets.items():
            widget.set_active(pane_id == active_id)
        self._sync_x_links()

    def _remove_pane_widget(self, pane_id: str, widget: _PlotPaneWidget) -> None:
        self._pane_layout.removeWidget(widget)
        widget.deleteLater()
        self._pane_widgets.pop(pane_id, None)

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
        for pane in self._workspace.panes:
            widget = self._pane_widgets.get(pane.id)
            if widget is None:
                continue
            panes_by_group.setdefault(pane.x_group, []).append(widget)

        for widgets in panes_by_group.values():
            if not widgets:
                continue
            leader = widgets[0].plot_widget
            leader.setXLink(None)
            for widget in widgets[1:]:
                widget.plot_widget.setXLink(leader)

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
        self._replace_pane(PlotPane(id=pane.id, title=title, x_group=pane.x_group, traces=pane.traces))

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
            )
        )

    @QtCore.Slot(str)
    def _on_add_trace_requested(self, pane_id: str) -> None:
        self._on_pane_activated(pane_id)

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
        self._replace_pane(PlotPane(id=pane.id, title=pane.title, x_group=pane.x_group, traces=tuple(traces)))

    @QtCore.Slot(str, str, str)
    def _on_trace_removed(self, pane_id: str, stream: str, field: str) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        traces = tuple(trace for trace in pane.traces if not (trace.stream == stream and trace.field == field))
        self._replace_pane(PlotPane(id=pane.id, title=pane.title, x_group=pane.x_group, traces=traces))

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
        self._replace_pane(PlotPane(id=pane.id, title=pane.title, x_group=pane.x_group, traces=tuple(traces)))

    @QtCore.Slot(str)
    def _on_autoscale_requested(self, pane_id: str) -> None:
        widget = self._pane_widgets.get(pane_id)
        if widget is not None:
            widget.autoscale()

    def _pane_by_id(self, pane_id: str) -> PlotPane | None:
        if self._workspace is None:
            return None
        for pane in self._workspace.panes:
            if pane.id == pane_id:
                return pane
        return None
