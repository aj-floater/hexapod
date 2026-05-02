from __future__ import annotations

import math
import os
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter

from .workspace import DEFAULT_X_GROUP, PlotPane, PlotTrace, PlotWorkspace, default_trace_color

if TYPE_CHECKING:
    from .runtime import DashboardRuntime


DEFAULT_FOLLOW_POINT_COUNT = 250
FOLLOW_RIGHT_PADDING_FRACTION = 0.02
MAX_FOLLOW_SPAN_US = 10_000_000.0
WHEEL_ZOOM_BASE = 0.85
MIN_Y_SPAN = 1e-6
MIN_EXPORT_WIDTH_PX = 2400
EXPORT_SCALE_FACTOR = 3
TRACE_PANEL_MARGIN_PX = 10
TRACE_PANEL_MAX_HEIGHT_FRACTION = 0.5
TRACE_PANEL_MIN_WIDTH_PX = 320
TRACE_PANEL_MIN_HEIGHT_PX = 96
TRACE_PANEL_SCROLLBAR_GUTTER_PX = 6
TRACE_PANEL_RESIZE_GRIP_HEIGHT_PX = 20


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
    trace_panel_visibility_changed = QtCore.Signal(str, bool)
    trace_panel_height_changed = QtCore.Signal(str, int)
    trace_visibility_changed = QtCore.Signal(str, str, str, bool)
    trace_remove_requested = QtCore.Signal(str, str, str)
    trace_color_changed = QtCore.Signal(str, str, str, str)
    autoscale_requested = QtCore.Signal(str)
    x_range_manually_changed = QtCore.Signal(str, tuple)

    def __init__(self, pane: PlotPane, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._pane = pane
        self._pane_color = default_trace_color(0)
        self._trace_rows: dict[
            tuple[str, str],
            tuple[QtWidgets.QCheckBox, QtWidgets.QPushButton, QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel],
        ] = {}
        self._curves: dict[tuple[str, str], pg.PlotDataItem] = {}
        self._suppress_manual_x_signal = False
        self._active = False
        self._trace_panel_drag_origin_y: float | None = None
        self._trace_panel_drag_start_height: int | None = None
        self._trace_panel_drag_height: int | None = None
        self._trace_panel_drag_moved = False
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
        self.setObjectName("plotPane")
        self.installEventFilter(self)
        self.setStyleSheet("#plotPane { border: 1px solid #3a4756; border-radius: 6px; }")

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

        self._plot_host = QtWidgets.QWidget()
        self._plot_host.installEventFilter(self)
        plot_layout = QtWidgets.QVBoxLayout(self._plot_host)
        plot_layout.setContentsMargins(0, 0, 0, 0)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.grabGesture(QtCore.Qt.GestureType.PinchGesture)
        self._plot_widget.installEventFilter(self)
        self._plot_widget.viewport().grabGesture(QtCore.Qt.GestureType.PinchGesture)
        self._plot_widget.viewport().installEventFilter(self)
        self._plot_widget.setBackground("#101822")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self._plot_widget.setLabel("bottom", "Device Time", units="us")
        self._plot_widget.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self._plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        self._plot_widget.getViewBox().sigRangeChangedManually.connect(self._on_manual_range_changed)
        self._plot_widget.getViewBox().sigResized.connect(self._on_plot_view_resized)
        self._plot_widget.scene().sigMouseClicked.connect(lambda *_: self.activated.emit(self._pane.id))
        plot_layout.addWidget(self._plot_widget, 1)
        layout.addWidget(self._plot_host, 1)

        self._show_trace_panel_button = QtWidgets.QPushButton("Show Traces", self._plot_host)
        self._show_trace_panel_button.installEventFilter(self)
        self._show_trace_panel_button.setToolTip("Show trace controls for this pane")
        self._show_trace_panel_button.setStatusTip("Show trace controls for this pane")
        self._show_trace_panel_button.setStyleSheet(
            "QPushButton {"
            " background-color: rgba(42, 50, 64, 235);"
            " color: #d7e1ef;"
            " border: 1px solid #4f5d70;"
            " border-radius: 5px;"
            " padding: 4px 10px;"
            "}"
            "QPushButton:hover {"
            " background-color: rgba(51, 60, 76, 245);"
            " border-color: #62748b;"
            "}"
        )
        self._show_trace_panel_button.clicked.connect(lambda: self.trace_panel_visibility_changed.emit(self._pane.id, True))

        self._trace_overlay = QtWidgets.QFrame(self._plot_host)
        self._trace_overlay.setObjectName("traceOverlay")
        self._trace_overlay.installEventFilter(self)
        self._trace_overlay.setStyleSheet(
            "QFrame#traceOverlay {"
            " background-color: rgba(20, 28, 39, 240);"
            " border: 1px solid #465566;"
            " border-radius: 6px;"
            "}"
        )
        overlay_layout = QtWidgets.QVBoxLayout(self._trace_overlay)
        overlay_layout.setContentsMargins(8, 8, 8, 8)
        overlay_layout.setSpacing(6)


        self._trace_scroll = QtWidgets.QScrollArea()
        self._trace_scroll.installEventFilter(self)
        self._trace_scroll.viewport().installEventFilter(self)
        self._trace_scroll.setWidgetResizable(True)
        self._trace_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._trace_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._trace_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._trace_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        overlay_layout.addWidget(self._trace_scroll, 1)

        trace_container = QtWidgets.QWidget()
        trace_container.installEventFilter(self)
        self._trace_layout = QtWidgets.QVBoxLayout(trace_container)
        scrollbar_extent = self.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent)
        self._trace_layout.setContentsMargins(0, 0, scrollbar_extent + TRACE_PANEL_SCROLLBAR_GUTTER_PX, 0)
        self._trace_layout.setSpacing(4)
        self._trace_scroll.setWidget(trace_container)

        self._trace_resize_grip = QtWidgets.QWidget()
        self._trace_resize_grip.installEventFilter(self)
        self._trace_resize_grip.setCursor(QtCore.Qt.CursorShape.SizeVerCursor)
        self._trace_resize_grip.setFixedHeight(TRACE_PANEL_RESIZE_GRIP_HEIGHT_PX)
        self._trace_resize_grip.setToolTip("Drag to resize the trace panel")
        self._trace_resize_grip.setStatusTip("Drag to resize the trace panel")
        self._trace_resize_grip.setStyleSheet("background: transparent; border: none;")
        grip_layout = QtWidgets.QHBoxLayout(self._trace_resize_grip)
        grip_layout.setContentsMargins(2, 0, 2, 0)
        grip_layout.setSpacing(0)

        self._hide_trace_panel_button = QtWidgets.QToolButton()
        hide_button = self._hide_trace_panel_button
        hide_button.installEventFilter(self)
        _pm = QtGui.QPixmap(12, 12)
        _pm.fill(QtCore.Qt.GlobalColor.transparent)
        _p = QtGui.QPainter(_pm)
        _p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        _p.setPen(QtGui.QPen(
            QtGui.QColor(95, 110, 130, 180), 1.5,
            QtCore.Qt.PenStyle.SolidLine,
            QtCore.Qt.PenCapStyle.RoundCap,
            QtCore.Qt.PenJoinStyle.RoundJoin,
        ))
        _p.drawPolyline([QtCore.QPointF(2, 8), QtCore.QPointF(6, 4), QtCore.QPointF(10, 8)])
        _p.end()
        hide_button.setIcon(QtGui.QIcon(_pm))
        hide_button.setIconSize(QtCore.QSize(12, 12))
        hide_button.setFixedSize(18, 16)
        hide_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        hide_button.setToolTip("Hide trace panel")
        hide_button.setStatusTip("Hide trace panel")
        hide_button.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 0px; }"
            "QToolButton:hover { background: rgba(90, 105, 125, 140); border-radius: 3px; }"
        )
        hide_button.clicked.connect(lambda: self.trace_panel_visibility_changed.emit(self._pane.id, False))
        grip_layout.addWidget(hide_button, 0)

        grip_layout.addStretch(1)
        grip_handle = QtWidgets.QFrame()
        grip_handle.setFixedSize(36, 3)
        grip_handle.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        grip_handle.setStyleSheet("background-color: rgba(95, 110, 130, 180); border: none; border-radius: 1px;")
        grip_layout.addWidget(grip_handle)
        grip_layout.addStretch(1)
        overlay_layout.addWidget(self._trace_resize_grip, 0)

        self._trace_overlay.hide()
        self._show_trace_panel_button.hide()

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

    def _update_trace_panel_visibility(self) -> None:
        has_traces = bool(self._pane.traces)
        panel_visible = has_traces and self._pane.trace_panel_visible
        self._trace_overlay.setVisible(panel_visible)
        self._show_trace_panel_button.setVisible(has_traces and not panel_visible)
        self._update_trace_panel_geometry()
        if panel_visible:
            self._trace_overlay.raise_()
        elif has_traces:
            self._show_trace_panel_button.raise_()

    def _plot_view_rect(self) -> QtCore.QRect:
        host_rect = self._plot_host.contentsRect()
        plot_item = self._plot_widget.plotItem
        view_box = plot_item.getViewBox()
        scene_rect = view_box.sceneBoundingRect()
        if not scene_rect.isValid() or scene_rect.isEmpty():
            return host_rect

        top_left = self._plot_widget.mapTo(
            self._plot_host,
            self._plot_widget.mapFromScene(scene_rect.topLeft()),
        )
        bottom_right = self._plot_widget.mapTo(
            self._plot_host,
            self._plot_widget.mapFromScene(scene_rect.bottomRight()),
        )
        view_rect = QtCore.QRect(top_left, bottom_right).normalized()
        if not view_rect.isValid() or view_rect.isEmpty():
            return host_rect
        clipped = view_rect.intersected(host_rect)
        return clipped if clipped.isValid() and not clipped.isEmpty() else host_rect

    def _trace_panel_minimum_height(self) -> int:
        overlay_layout = self._trace_overlay.layout()
        if overlay_layout is None:
            return TRACE_PANEL_MIN_HEIGHT_PX
        overlay_layout.activate()

        first_row_widget: QtWidgets.QWidget | None = None
        if self._trace_rows:
            first_row = next(iter(self._trace_rows.values()))
            first_row_widget = first_row[0].parentWidget()
        if first_row_widget is None:
            return TRACE_PANEL_MIN_HEIGHT_PX

        row_height = first_row_widget.sizeHint().height()
        margins = overlay_layout.contentsMargins()
        spacing = overlay_layout.spacing()
        grip_height = max(self._trace_resize_grip.sizeHint().height(), self._trace_resize_grip.height())
        scroll_viewport_overhead = 2  # QScrollArea internal border/margin overhead
        return (
            margins.top()
            + row_height + scroll_viewport_overhead
            + spacing
            + grip_height
            + margins.bottom()
        )

    def _trace_panel_custom_height_bounds(self, anchor_rect: QtCore.QRect | None = None) -> tuple[int, int]:
        target_rect = anchor_rect if anchor_rect is not None else self._plot_view_rect()
        available_height = max(0, target_rect.height() - (TRACE_PANEL_MARGIN_PX * 2))
        if available_height <= 0:
            return (1, 1)
        max_panel_height = max(1, available_height)
        min_panel_height = min(self._trace_panel_minimum_height(), max_panel_height)
        return (min_panel_height, max_panel_height)

    def _clamp_trace_panel_custom_height(self, height: int, anchor_rect: QtCore.QRect | None = None) -> int:
        min_panel_height, max_panel_height = self._trace_panel_custom_height_bounds(anchor_rect)
        return min(max(int(height), min_panel_height), max_panel_height)

    def _start_trace_panel_resize(self, global_y: float) -> bool:
        if not self._trace_overlay.isVisible():
            return False
        self._trace_panel_drag_origin_y = float(global_y)
        self._trace_panel_drag_start_height = max(1, self._trace_overlay.height())
        self._trace_panel_drag_height = self._trace_panel_drag_start_height
        self._trace_panel_drag_moved = False
        self._trace_resize_grip.grabMouse()
        return True

    def _update_trace_panel_resize(self, global_y: float) -> bool:
        if self._trace_panel_drag_origin_y is None or self._trace_panel_drag_start_height is None:
            return False
        desired_height = self._trace_panel_drag_start_height + round(float(global_y) - self._trace_panel_drag_origin_y)
        clamped_height = self._clamp_trace_panel_custom_height(desired_height)
        if clamped_height == self._trace_panel_drag_height:
            return False
        self._trace_panel_drag_height = clamped_height
        self._trace_panel_drag_moved = True
        self._update_trace_panel_geometry()
        return True

    def _finish_trace_panel_resize(self, *, commit: bool = True) -> None:
        if self._trace_panel_drag_origin_y is None:
            return
        final_height = self._trace_panel_drag_height or self._trace_overlay.height()
        self._trace_panel_drag_origin_y = None
        self._trace_panel_drag_start_height = None
        self._trace_resize_grip.releaseMouse()
        if commit and self._trace_panel_drag_moved and final_height != self._pane.trace_panel_height:
            self.trace_panel_height_changed.emit(self._pane.id, final_height)
        self._trace_panel_drag_height = None
        self._trace_panel_drag_moved = False
        self._update_trace_panel_geometry()

    def _update_trace_panel_geometry(self) -> None:
        anchor_rect = self._plot_view_rect()
        available_width = max(0, anchor_rect.width() - (TRACE_PANEL_MARGIN_PX * 2))
        available_height = max(0, anchor_rect.height() - (TRACE_PANEL_MARGIN_PX * 2))
        if available_width <= 0 or available_height <= 0:
            return

        button_size = self._show_trace_panel_button.sizeHint()
        button_width = min(max(button_size.width(), 120), available_width)
        button_height = min(button_size.height(), available_height)
        self._show_trace_panel_button.setGeometry(
            anchor_rect.left() + TRACE_PANEL_MARGIN_PX,
            anchor_rect.top() + TRACE_PANEL_MARGIN_PX,
            button_width,
            button_height,
        )

        if not self._trace_overlay.isVisible():
            return

        overlay_layout = self._trace_overlay.layout()
        if overlay_layout is not None:
            overlay_layout.activate()
        overlay_hint = self._trace_overlay.sizeHint()
        panel_width = min(max(TRACE_PANEL_MIN_WIDTH_PX, overlay_hint.width()), available_width)
        desired_custom_height = self._trace_panel_drag_height if self._trace_panel_drag_height is not None else self._pane.trace_panel_height
        if desired_custom_height is None:
            max_panel_height = max(1, int(available_height * TRACE_PANEL_MAX_HEIGHT_FRACTION))
            min_panel_height = min(TRACE_PANEL_MIN_HEIGHT_PX, max_panel_height)
            panel_height = min(max(min_panel_height, overlay_hint.height()), max_panel_height)
        else:
            panel_height = self._clamp_trace_panel_custom_height(desired_custom_height, anchor_rect)
        self._trace_overlay.setGeometry(
            anchor_rect.left() + TRACE_PANEL_MARGIN_PX,
            anchor_rect.top() + TRACE_PANEL_MARGIN_PX,
            panel_width,
            panel_height,
        )
        self._trace_overlay.raise_()

    @QtCore.Slot(object)
    def _on_plot_view_resized(self, _view_box: object) -> None:
        self._update_trace_panel_geometry()

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
        self._update_trace_panel_visibility()

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

    def current_y_range(self) -> tuple[float, float] | None:
        y_range = self._plot_widget.viewRange()[1]
        if len(y_range) != 2:
            return None
        try:
            y_min = float(y_range[0])
            y_max = float(y_range[1])
        except (TypeError, ValueError):
            return None
        if not (y_max > y_min):
            return None
        return (y_min, y_max)

    def set_x_range(self, x_min: float, x_max: float) -> None:
        if not (x_max > x_min):
            return
        self._suppress_manual_x_signal = True
        try:
            self._plot_widget.setXRange(x_min, x_max, padding=0)
        finally:
            self._suppress_manual_x_signal = False

    def set_y_range(self, y_min: float, y_max: float) -> None:
        if not (y_max > y_min):
            return
        self._plot_widget.setYRange(y_min, y_max, padding=0)

    def set_y_auto_range(self, enabled: bool) -> None:
        self._plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis, enable=enabled)

    def resume_y_auto_range(self) -> None:
        self.set_y_auto_range(True)
        self._plot_widget.getViewBox().updateAutoRange()

    def _sync_trace_rows(self) -> None:
        wanted_keys = {trace.key for trace in self._pane.traces}

        for key, widgets in list(self._trace_rows.items()):
            if key in wanted_keys:
                continue
            checkbox, color_button, label, value_label, unit_label = widgets
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

                value_label = QtWidgets.QLabel("\u2014")
                value_label.installEventFilter(self)
                value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                value_label.setMinimumWidth(64)
                value_font = value_label.font()
                value_font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
                value_label.setFont(value_font)
                row_layout.addWidget(value_label)

                unit_label = QtWidgets.QLabel("")
                unit_label.installEventFilter(self)
                unit_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                unit_label.setMinimumWidth(28)
                row_layout.addWidget(unit_label)

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
                row = (checkbox, color_button, label, value_label, unit_label)
                self._trace_rows[trace.key] = row

            checkbox, color_button, label, value_label, unit_label = row
            checkbox.blockSignals(True)
            checkbox.setChecked(trace.visible)
            checkbox.blockSignals(False)
            label.setText(trace.field)
            label.setToolTip(trace.field)
            color_button.setStyleSheet(
                f"background-color: {trace.color}; border: 1px solid #2a3240; border-radius: 4px;"
            )

        self._update_trace_panel_visibility()

    def set_trace_status(self, trace: PlotTrace, value: object | None, unit: str) -> None:
        row = self._trace_rows.get(trace.key)
        if row is None:
            return
        _checkbox, _color_button, _label, value_label, unit_label = row
        value_label.setText("\u2014" if value is None else str(value))
        unit_label.setText(unit)

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
        self.set_y_auto_range(True)
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

    def _zoom_range(
        self,
        minimum: float,
        maximum: float,
        focus: float,
        steps: float,
        minimum_span: float,
    ) -> tuple[float, float] | None:
        if not (maximum > minimum):
            return None
        span = maximum - minimum
        factor = WHEEL_ZOOM_BASE ** steps
        new_span = max(minimum_span, span * factor)
        if not (new_span > 0):
            return None
        focus_ratio = (focus - minimum) / span if span > 0 else 0.5
        focus_ratio = max(0.0, min(1.0, focus_ratio))
        new_minimum = focus - (new_span * focus_ratio)
        new_maximum = new_minimum + new_span
        return (new_minimum, new_maximum)

    def _map_position_to_data_point(
        self,
        position: QtCore.QPointF,
        source_widget: QtWidgets.QWidget | None = None,
    ) -> QtCore.QPointF:
        if source_widget is not None and source_widget is not self._plot_widget:
            mapped_position = source_widget.mapTo(self._plot_widget, position.toPoint())
        else:
            mapped_position = position.toPoint()
        scene_point = self._plot_widget.mapToScene(mapped_position)
        return self._plot_widget.getViewBox().mapSceneToView(scene_point)

    def _handle_plot_generic_zoom(
        self,
        scale_factor: float,
        position: QtCore.QPointF,
        source_widget: QtWidgets.QWidget | None = None,
    ) -> bool:
        if not math.isfinite(scale_factor) or scale_factor <= 0 or math.isclose(scale_factor, 1.0, rel_tol=1e-3):
            return False

        self.activated.emit(self._pane.id)
        data_point = self._map_position_to_data_point(position, source_widget)
        current_x_range = self.current_x_range()
        current_y_range = self.current_y_range()
        if current_x_range is None or current_y_range is None:
            return False

        new_x_range = self._zoom_range(
            current_x_range[0],
            current_x_range[1],
            float(data_point.x()),
            math.log(scale_factor) / math.log(WHEEL_ZOOM_BASE),
            1.0,
        )
        new_y_range = self._zoom_range(
            current_y_range[0],
            current_y_range[1],
            float(data_point.y()),
            math.log(scale_factor) / math.log(WHEEL_ZOOM_BASE),
            max(MIN_Y_SPAN, abs(float(data_point.y())) * 1e-6),
        )
        if new_x_range is None or new_y_range is None:
            return False

        self.set_y_auto_range(False)
        self.set_x_range(*new_x_range)
        self.set_y_range(*new_y_range)
        self.x_range_manually_changed.emit(self._pane.id, new_x_range)
        return True

    def _handle_plot_wheel(
        self,
        angle_delta: QtCore.QPoint,
        position: QtCore.QPointF,
        modifiers: QtCore.Qt.KeyboardModifier | QtCore.Qt.KeyboardModifiers = QtCore.Qt.KeyboardModifier.NoModifier,
        source_widget: QtWidgets.QWidget | None = None,
    ) -> bool:
        if angle_delta.isNull():
            return False

        self.activated.emit(self._pane.id)
        data_point = self._map_position_to_data_point(position, source_widget)
        handled = False
        preserved_y_range = self.current_y_range()

        if modifiers & QtCore.Qt.KeyboardModifier.AltModifier:
            dominant_delta = angle_delta.y()
            if abs(angle_delta.x()) > abs(dominant_delta):
                dominant_delta = angle_delta.x()
            generic_steps = dominant_delta / 120.0
            if generic_steps:
                return self._handle_plot_generic_zoom(
                    WHEEL_ZOOM_BASE ** generic_steps,
                    position,
                    source_widget,
                )
            return False

        horizontal_steps = angle_delta.x() / 120.0
        if horizontal_steps:
            current_x_range = self.current_x_range()
            if current_x_range is not None:
                new_x_range = self._zoom_range(
                    current_x_range[0],
                    current_x_range[1],
                    float(data_point.x()),
                    horizontal_steps,
                    1.0,
                )
                if new_x_range is not None:
                    self.set_x_range(*new_x_range)
                    if preserved_y_range is not None and not angle_delta.y():
                        self.set_y_range(*preserved_y_range)
                    self.x_range_manually_changed.emit(self._pane.id, new_x_range)
                    handled = True

        vertical_steps = angle_delta.y() / 120.0
        if vertical_steps:
            current_y_range = self.current_y_range()
            if current_y_range is not None:
                new_y_range = self._zoom_range(
                    current_y_range[0],
                    current_y_range[1],
                    float(data_point.y()),
                    vertical_steps,
                    max(MIN_Y_SPAN, abs(float(data_point.y())) * 1e-6),
                )
                if new_y_range is not None:
                    self.set_y_auto_range(False)
                    self.set_y_range(*new_y_range)
                    handled = True

        return handled

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        plot_widget = getattr(self, "_plot_widget", None)
        viewport = plot_widget.viewport() if plot_widget is not None else None
        source_widget = watched if isinstance(watched, QtWidgets.QWidget) else None
        plot_host = getattr(self, "_plot_host", None)
        trace_resize_grip = getattr(self, "_trace_resize_grip", None)
        if (
            plot_host is not None
            and watched is plot_host
            and event.type() in {QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show}
        ):
            self._update_trace_panel_geometry()
        if (
            plot_widget is not None
            and watched in {plot_widget, viewport}
            and event.type() == QtCore.QEvent.Type.Wheel
            and isinstance(event, QtGui.QWheelEvent)
        ):
            if self._handle_plot_wheel(event.angleDelta(), event.position(), event.modifiers(), source_widget):
                event.accept()
                return True
        if (
            plot_widget is not None
            and watched in {plot_widget, viewport}
            and event.type() == QtCore.QEvent.Type.NativeGesture
            and isinstance(event, QtGui.QNativeGestureEvent)
            and event.gestureType() == QtCore.Qt.NativeGestureType.ZoomNativeGesture
        ):
            if self._handle_plot_generic_zoom(math.exp(-event.value()), event.position(), source_widget):
                event.accept()
                return True
        if (
            plot_widget is not None
            and watched in {plot_widget, viewport}
            and event.type() == QtCore.QEvent.Type.Gesture
            and isinstance(event, QtWidgets.QGestureEvent)
        ):
            gesture = event.gesture(QtCore.Qt.GestureType.PinchGesture)
            if isinstance(gesture, QtWidgets.QPinchGesture):
                last_scale = gesture.lastScaleFactor() or 1.0
                scale_delta = gesture.scaleFactor() / last_scale if last_scale else gesture.scaleFactor()
                if self._handle_plot_generic_zoom(1.0 / max(scale_delta, 1e-6), gesture.centerPoint(), source_widget):
                    event.accept(gesture)
                    return True
        if event.type() in {
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.FocusIn,
        }:
            self.activated.emit(self._pane.id)
        if watched is trace_resize_grip and isinstance(event, QtGui.QMouseEvent):
            if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
                if self._start_trace_panel_resize(event.globalPosition().y()):
                    event.accept()
                    return True
            if event.type() == QtCore.QEvent.Type.MouseMove:
                if self._update_trace_panel_resize(event.globalPosition().y()):
                    event.accept()
                    return True
            if event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._finish_trace_panel_resize(commit=True)
                event.accept()
                return True
        if watched is trace_resize_grip and event.type() == QtCore.QEvent.Type.UngrabMouse:
            self._finish_trace_panel_resize(commit=False)
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
        self._sync_widgets(preserve_current_sizes=False)

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
        duplicate = replace(active, id=f"pane-{next_index}", title=f"{active.title} Copy")
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

    def export_active_pane_image(self, path: str) -> bool:
        active_id = self.active_pane_id
        if active_id is None:
            return False
        widget = self._pane_widgets.get(active_id)
        if widget is None:
            return False

        plot_item = widget.plot_widget.plotItem
        exporter = ImageExporter(plot_item)
        width = max(
            MIN_EXPORT_WIDTH_PX,
            int(max(1, widget.plot_widget.viewport().width()) * EXPORT_SCALE_FACTOR),
        )
        try:
            exporter.parameters()["width"] = width
        except Exception:
            pass
        exporter.export(path)
        return True

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
        updated = replace(active, traces=active.traces + (PlotTrace(stream=stream, field=field, color=color),))
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
                unit = ""
                for field in runtime.field_specs_for_stream(device, trace.stream):
                    if field.name == trace.field:
                        unit = field.unit
                        break
                widget.set_trace_status(
                    trace,
                    runtime.latest_value_for_field(device, trace.stream, trace.field),
                    unit,
                )
        self._apply_follow_state(runtime, device)

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

    def _sync_widgets(self, *, preserve_current_sizes: bool = True) -> None:
        workspace = self._workspace
        size_by_id = self._capture_sizes() if preserve_current_sizes else {}
        self._state_label.setVisible(workspace is None or not workspace.panes)
        if workspace is None:
            self._state_label.setText("No plot workspace loaded")
            for pane_id, widget in list(self._pane_widgets.items()):
                self._remove_pane_widget(pane_id, widget)
            self._pane_order = []
            self._group_leaders = {}
            return
        if not workspace.panes:
            self._state_label.setText("No panes configured for this device")
            for pane_id, widget in list(self._pane_widgets.items()):
                self._remove_pane_widget(pane_id, widget)
            self._pane_order = []
            self._group_leaders = {}
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
                widget.trace_panel_visibility_changed.connect(self._on_trace_panel_visibility_changed)
                widget.trace_panel_height_changed.connect(self._on_trace_panel_height_changed)
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
            replace(
                pane,
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
        self._replace_pane(replace(pane, title=title))

    @QtCore.Slot(str, str)
    def _on_x_group_changed(self, pane_id: str, group_name: str) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        self._replace_pane(replace(pane, x_group=group_name.strip() or DEFAULT_X_GROUP))

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
            if follow_live:
                widget.resume_y_auto_range()
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

    @QtCore.Slot(str, bool)
    def _on_trace_panel_visibility_changed(self, pane_id: str, visible: bool) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None or pane.trace_panel_visible == visible:
            return
        self._replace_pane(replace(pane, trace_panel_visible=visible))

    @QtCore.Slot(str, int)
    def _on_trace_panel_height_changed(self, pane_id: str, height: int) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None or pane.trace_panel_height == height:
            return
        self._replace_pane(replace(pane, trace_panel_height=height))

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
        self._replace_pane(replace(pane, traces=tuple(traces)))

    @QtCore.Slot(str, str, str)
    def _on_trace_removed(self, pane_id: str, stream: str, field: str) -> None:
        pane = self._pane_by_id(pane_id)
        if pane is None:
            return
        traces = tuple(trace for trace in pane.traces if not (trace.stream == stream and trace.field == field))
        self._replace_pane(replace(pane, traces=traces))

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
        self._replace_pane(replace(pane, traces=tuple(traces)))

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
        leader_id = self._group_leaders.get(pane.x_group)
        if leader_id is not None and leader_id != pane_id:
            leader = self._pane_widgets.get(leader_id)
            if leader is not None:
                leader.set_x_range(*x_range)
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
                replace(
                    pane,
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
