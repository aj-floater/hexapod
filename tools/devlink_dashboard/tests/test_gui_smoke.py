from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

_HAS_GUI = bool(importlib.util.find_spec("PySide6")) and bool(importlib.util.find_spec("pyqtgraph"))

if _HAS_GUI:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtTest, QtWidgets

    from devlink_dashboard.gui.controller import GuiController
    from devlink_dashboard.gui.main_window import MainWindow
    from devlink_dashboard.gui.plot_workspace import MAX_FOLLOW_SPAN_US
    from devlink_dashboard.gui.workspace import WindowLayoutStore, WorkspaceStore
    from devlink_dashboard.messages import parse_line


@unittest.skipUnless(_HAS_GUI, "GUI dependencies are not installed")
class GuiSmokeTests(unittest.TestCase):
    def test_main_window_instantiates(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        self.assertEqual(window.windowTitle(), "Devlink Dashboard")
        self.assertEqual(window._connect_button.text(), "Connect")
        window._on_connection_state_changed(True)
        self.assertEqual(window._connect_button.text(), "Disconnect")
        window.close()

        if owns_app:
            app.quit()

    def test_status_banner_is_positioned_below_main_content(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        layout = window.centralWidget().layout()

        self.assertGreater(layout.indexOf(window._banner), layout.indexOf(window._body_splitter))
        window.close()

        if owns_app:
            app.quit()

    def test_record_output_path_is_timestamped_in_selected_directory(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        record_path = window._build_record_output_path("/tmp/devlink-recordings", "/dev/ttyACM0")

        record_file = Path(record_path)
        self.assertEqual(record_file.parent, Path("/tmp/devlink-recordings"))
        self.assertEqual(record_file.suffix, ".jsonl")
        self.assertRegex(record_file.name, r"^devlink-ttyACM0-\d{8}-\d{6}\.jsonl$")
        window.close()

        if owns_app:
            app.quit()

    def test_controller_retries_device_describe_until_ready(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        sent: list[tuple[str, str, dict[str, object]]] = []

        def fake_send_command(*, device: str, name: str, args: dict[str, object] | None = None):
            sent.append((device, name, args or {}))
            return len(sent)

        controller.send_command = fake_send_command  # type: ignore[method-assign]
        controller._worker = object()  # type: ignore[assignment]

        controller._on_connected()
        controller._send_discovery_request()

        self.assertEqual(
            sent[:2],
            [
                ("*", "device.describe", {}),
                ("*", "device.describe", {}),
            ],
        )

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],"params":[]}'
        )
        controller._on_message(capabilities)
        self.assertEqual(controller.discovery_state, "ready")

        controller._on_disconnected()
        if owns_app:
            app.quit()

    def test_param_editor_survives_sample_updates(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]}],'
            '"params":[{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000}]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        sample = parse_line(
            '{"type":"sample","version":1,"device":"status_led","stream":"status_led.state","seq":1,"t_us":10,'
            '"data":{"blink_period_ms":250}}'
        )
        controller.runtime.apply_message(sample)
        window._on_message_received(sample)

        editor_before = window._param_editors["blink.period_ms"][1]
        line_edit = editor_before.lineEdit()
        self.assertIsNotNone(line_edit)
        line_edit.setText("300")
        window._on_param_text_edited("blink.period_ms", "300")

        sample2 = parse_line(
            '{"type":"sample","version":1,"device":"status_led","stream":"status_led.state","seq":2,"t_us":20,'
            '"data":{"blink_period_ms":250}}'
        )
        controller.runtime.apply_message(sample2)
        window._on_message_received(sample2)

        editor_after = window._param_editors["blink.period_ms"][1]
        self.assertIs(editor_before, editor_after)
        self.assertEqual(window._pending_param_values["blink.period_ms"], "300")
        window.close()

        if owns_app:
            app.quit()

    def test_add_selected_trace_targets_active_pane(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.state","fields":[{"name":"led_enabled","type":"bool","unit":"state"},'
            '{"name":"blink_period_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        window._selected_stream = "status_led.state"
        window._workspace = controller.runtime.build_default_workspace("status_led")
        window._plot_workspace.set_workspace(window._workspace)
        window._refresh_field_list()

        self.assertEqual([window._field_list.item(i).text() for i in range(window._field_list.count())], ["blink_period_ms"])
        window._plot_workspace.remove_active_pane()
        window._plot_workspace.add_pane()
        window._field_list.setCurrentRow(0)
        window._add_selected_field_to_active_pane()

        workspace = window._plot_workspace.workspace
        self.assertIsNotNone(workspace)
        active = workspace.active_pane_id
        pane = next(item for item in workspace.panes if item.id == active)
        self.assertEqual([(trace.stream, trace.field) for trace in pane.traces], [("status_led.state", "blink_period_ms")])
        window.close()

        if owns_app:
            app.quit()

    def test_workspace_move_active_pane_reorders_panes(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]},'
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        workspace = controller.runtime.build_default_workspace("status_led")
        window._plot_workspace.set_workspace(workspace)
        window._plot_workspace.move_active_pane(1)

        reordered = window._plot_workspace.workspace
        self.assertEqual([pane.id for pane in reordered.panes], ["pane-2", "pane-1"])
        window.close()

        if owns_app:
            app.quit()

    def test_splitter_move_updates_workspace_pane_sizes(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]},'
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        workspace = controller.runtime.build_default_workspace("status_led")
        window._plot_workspace.set_workspace(workspace)
        app.processEvents()

        window._plot_workspace._splitter.setSizes([150, 450])
        app.processEvents()
        applied_sizes = window._plot_workspace._splitter.sizes()
        window._plot_workspace._on_splitter_moved(applied_sizes[0], 0)

        updated = window._plot_workspace.workspace
        self.assertIsNotNone(updated)
        self.assertEqual(updated.panes[0].size, applied_sizes[0])
        self.assertEqual(updated.panes[1].size, applied_sizes[1])
        window.close()

        if owns_app:
            app.quit()

    def test_activating_second_pane_routes_trace_addition(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]},'
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)

        window._selected_device = "status_led"
        window._selected_stream = "status_led.timing"
        window._refresh_field_list()
        window._plot_workspace._pane_widgets["pane-2"].activated.emit("pane-2")
        window._field_list.setCurrentRow(0)
        window._add_selected_field_to_active_pane()

        updated = window._plot_workspace.workspace
        pane_1 = next(pane for pane in updated.panes if pane.id == "pane-1")
        pane_2 = next(pane for pane in updated.panes if pane.id == "pane-2")
        self.assertEqual([(trace.stream, trace.field) for trace in pane_1.traces], [("status_led.state", "blink_period_ms")])
        self.assertEqual(
            [(trace.stream, trace.field) for trace in pane_2.traces],
            [("status_led.timing", "phase_elapsed_ms")],
        )
        window.close()

        if owns_app:
            app.quit()

    def test_remove_pane_is_only_top_level_and_requires_confirmation(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]},'
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)

        pane_widget = window._plot_workspace._pane_widgets["pane-1"]
        remove_controls = [
            child for child in pane_widget.findChildren(QtWidgets.QAbstractButton)
            if child.toolTip() == "Remove this pane"
        ]
        self.assertEqual(remove_controls, [])

        calls: list[str] = []
        original_warning = QtWidgets.QMessageBox.warning

        def fake_warning(parent, title, text, buttons, default_button):  # type: ignore[no-untyped-def]
            calls.append(text)
            return QtWidgets.QMessageBox.StandardButton.Cancel

        QtWidgets.QMessageBox.warning = fake_warning
        try:
            window._confirm_remove_active_pane()
            current = window._plot_workspace.workspace
            self.assertEqual(len(current.panes), 2)
            self.assertEqual(len(calls), 1)

            QtWidgets.QMessageBox.warning = (
                lambda parent, title, text, buttons, default_button: QtWidgets.QMessageBox.StandardButton.Yes
            )
            window._confirm_remove_active_pane()
            updated = window._plot_workspace.workspace
            self.assertEqual(len(updated.panes), 1)
        finally:
            QtWidgets.QMessageBox.warning = original_warning

        window.close()

        if owns_app:
            app.quit()

    def test_plot_workspace_follows_recent_samples(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(400):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        x_range = pane_widget.current_x_range()
        self.assertIsNotNone(x_range)
        self.assertGreater(x_range[1], 399_000)
        self.assertGreater(x_range[0], 100_000)
        self.assertTrue(pane_widget._follow_button.isChecked())
        window.close()

        if owns_app:
            app.quit()

    def test_plot_workspace_follow_span_is_capped(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(12_000):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        x_range = pane_widget.current_x_range()
        self.assertIsNotNone(x_range)
        self.assertLessEqual(x_range[1] - x_range[0], MAX_FOLLOW_SPAN_US)
        window.close()

        if owns_app:
            app.quit()

    def test_window_close_persists_live_pane_sizes(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))
            window.show()
            app.processEvents()

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]},'
                '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            workspace = controller.runtime.build_default_workspace("status_led")
            window._workspace = workspace
            window._plot_workspace.set_workspace(workspace)
            app.processEvents()

            window._plot_workspace._splitter.setSizes([180, 420])
            app.processEvents()
            applied_sizes = window._plot_workspace._splitter.sizes()
            window.close()

            stored = window._workspace_store.load("status_led")
            self.assertIsNotNone(stored)
            self.assertEqual(stored.panes[0].size, applied_sizes[0])
            self.assertEqual(stored.panes[1].size, applied_sizes[1])

        if owns_app:
            app.quit()

    def test_window_close_persists_body_splitter_sizes(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._window_layout_store = WindowLayoutStore(Path(tmp_dir))
            window.show()
            app.processEvents()

            window._body_splitter.setSizes([260, 700, 440])
            app.processEvents()
            applied_sizes = window._body_splitter.sizes()
            window.close()

            restored = MainWindow(controller)
            restored._window_layout_store = WindowLayoutStore(Path(tmp_dir))
            restored._restore_window_layout()
            restored.show()
            app.processEvents()

            restored_sizes = restored._body_splitter.sizes()
            self.assertEqual(restored_sizes[:3], applied_sizes[:3])
            restored.close()

        if owns_app:
            app.quit()

    def test_manual_horizontal_range_disables_follow(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(200):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")

        pane_widget.plot_widget.setXRange(50_000, 75_000, padding=0)
        pane_widget._on_manual_range_changed([True, False])
        app.processEvents()

        for index in range(200, 300):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        x_range = pane_widget.current_x_range()
        self.assertIsNotNone(x_range)
        self.assertLess(x_range[1], 100_000)
        self.assertFalse(pane_widget._follow_button.isChecked())
        window.close()

        if owns_app:
            app.quit()

    def test_horizontal_wheel_zoom_changes_x_range_only(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(200):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        before_x = pane_widget.current_x_range()
        before_y = pane_widget.current_y_range()
        self.assertIsNotNone(before_x)
        self.assertIsNotNone(before_y)

        center = pane_widget.plot_widget.viewport().rect().center()
        handled = pane_widget._handle_plot_wheel(QtCore.QPoint(120, 0), QtCore.QPointF(center))
        app.processEvents()

        after_x = pane_widget.current_x_range()
        after_y = pane_widget.current_y_range()
        self.assertTrue(handled)
        self.assertIsNotNone(after_x)
        self.assertIsNotNone(after_y)
        self.assertLess(after_x[1] - after_x[0], before_x[1] - before_x[0])
        self.assertAlmostEqual(after_y[1] - after_y[0], before_y[1] - before_y[0], places=6)
        self.assertFalse(pane_widget._follow_button.isChecked())
        window.close()

        if owns_app:
            app.quit()

    def test_horizontal_wheel_zoom_is_anchored_to_cursor_position(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(300):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        viewport = pane_widget.plot_widget.viewport()
        target = QtCore.QPointF(viewport.rect().width() * 0.2, viewport.rect().height() * 0.35)
        before = pane_widget._map_position_to_data_point(target, viewport)
        handled = pane_widget._handle_plot_wheel(
            QtCore.QPoint(120, 0),
            target,
            source_widget=viewport,
        )
        app.processEvents()
        after = pane_widget._map_position_to_data_point(target, viewport)

        self.assertTrue(handled)
        self.assertAlmostEqual(after.x(), before.x(), places=6)
        self.assertAlmostEqual(after.y(), before.y(), places=6)
        window.close()

        if owns_app:
            app.quit()

    def test_vertical_wheel_zoom_changes_y_range_only(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(200):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        before_x = pane_widget.current_x_range()
        before_y = pane_widget.current_y_range()
        self.assertIsNotNone(before_x)
        self.assertIsNotNone(before_y)

        center = pane_widget.plot_widget.viewport().rect().center()
        handled = pane_widget._handle_plot_wheel(QtCore.QPoint(0, 120), QtCore.QPointF(center))
        app.processEvents()

        after_x = pane_widget.current_x_range()
        after_y = pane_widget.current_y_range()
        self.assertTrue(handled)
        self.assertIsNotNone(after_x)
        self.assertIsNotNone(after_y)
        self.assertAlmostEqual(after_x[1] - after_x[0], before_x[1] - before_x[0], places=6)
        self.assertLess(after_y[1] - after_y[0], before_y[1] - before_y[0])
        self.assertTrue(pane_widget._follow_button.isChecked())
        window.close()

        if owns_app:
            app.quit()

    def test_vertical_wheel_zoom_is_anchored_to_cursor_position(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(300):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        viewport = pane_widget.plot_widget.viewport()
        target = QtCore.QPointF(viewport.rect().width() * 0.7, viewport.rect().height() * 0.65)
        before = pane_widget._map_position_to_data_point(target, viewport)
        handled = pane_widget._handle_plot_wheel(
            QtCore.QPoint(0, 120),
            target,
            source_widget=viewport,
        )
        app.processEvents()
        after = pane_widget._map_position_to_data_point(target, viewport)

        self.assertTrue(handled)
        self.assertAlmostEqual(after.x(), before.x(), places=6)
        self.assertAlmostEqual(after.y(), before.y(), places=6)
        window.close()

        if owns_app:
            app.quit()

    def test_alt_vertical_wheel_performs_generic_zoom(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(200):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        before_x = pane_widget.current_x_range()
        before_y = pane_widget.current_y_range()
        self.assertIsNotNone(before_x)
        self.assertIsNotNone(before_y)

        center = pane_widget.plot_widget.viewport().rect().center()
        handled = pane_widget._handle_plot_wheel(
            QtCore.QPoint(0, 120),
            QtCore.QPointF(center),
            QtCore.Qt.KeyboardModifier.AltModifier,
        )
        app.processEvents()

        after_x = pane_widget.current_x_range()
        after_y = pane_widget.current_y_range()
        self.assertTrue(handled)
        self.assertIsNotNone(after_x)
        self.assertIsNotNone(after_y)
        self.assertLess(after_x[1] - after_x[0], before_x[1] - before_x[0])
        self.assertLess(after_y[1] - after_y[0], before_y[1] - before_y[0])
        self.assertFalse(pane_widget._follow_button.isChecked())
        window.close()

        if owns_app:
            app.quit()

    def test_generic_pinch_zoom_changes_both_axes(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(200):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        before_x = pane_widget.current_x_range()
        before_y = pane_widget.current_y_range()
        self.assertIsNotNone(before_x)
        self.assertIsNotNone(before_y)

        center = pane_widget.plot_widget.viewport().rect().center()
        handled = pane_widget._handle_plot_generic_zoom(0.8, QtCore.QPointF(center))
        app.processEvents()

        after_x = pane_widget.current_x_range()
        after_y = pane_widget.current_y_range()
        self.assertTrue(handled)
        self.assertIsNotNone(after_x)
        self.assertIsNotNone(after_y)
        self.assertLess(after_x[1] - after_x[0], before_x[1] - before_x[0])
        self.assertLess(after_y[1] - after_y[0], before_y[1] - before_y[0])
        self.assertFalse(pane_widget._follow_button.isChecked())
        window.close()

        if owns_app:
            app.quit()

    def test_generic_zoom_is_anchored_to_cursor_position(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window.show()
        app.processEvents()

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        window._selected_device = "status_led"
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)
        pane_widget = window._plot_workspace._pane_widgets["pane-1"]

        for index in range(300):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1_000},"data":{{"phase_elapsed_ms":{index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        viewport = pane_widget.plot_widget.viewport()
        target = QtCore.QPointF(viewport.rect().width() * 0.3, viewport.rect().height() * 0.4)
        before = pane_widget._map_position_to_data_point(target, viewport)
        handled = pane_widget._handle_plot_generic_zoom(0.8, target, viewport)
        app.processEvents()
        after = pane_widget._map_position_to_data_point(target, viewport)

        self.assertTrue(handled)
        self.assertAlmostEqual(after.x(), before.x(), places=6)
        self.assertAlmostEqual(after.y(), before.y(), places=6)
        window.close()

        if owns_app:
            app.quit()

    def test_param_list_response_updates_current_value(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
            '"params":[{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000}]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        window._selected_device = "status_led"
        window._refresh_params_table()

        current_item = window._param_table.item(0, 2)
        self.assertIsNotNone(current_item)
        self.assertEqual(current_item.text(), "250")

        response = parse_line(
            '{"type":"resp","version":1,"device":"status_led","id":2,"ok":true,'
            '"result":{"params":[{"name":"blink.period_ms","value":607}]}}'
        )
        controller.runtime.apply_message(response)
        window._on_message_received(response)

        current_item = window._param_table.item(0, 2)
        self.assertIsNotNone(current_item)
        self.assertEqual(current_item.text(), "607")
        window.close()

        if owns_app:
            app.quit()

    def test_trace_rows_show_latest_trace_values(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"},'
            '{"name":"time_to_toggle_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)

        for index in range(3):
            sample = parse_line(
                f'{{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":{index},'
                f'"t_us":{index * 1000},"data":{{"phase_elapsed_ms":{index + 10},"time_to_toggle_ms":{20 - index}}}}}'
            )
            controller.runtime.apply_message(sample)
            window._on_message_received(sample)
        QtTest.QTest.qWait(50)

        pane_widget = window._plot_workspace._pane_widgets["pane-1"]
        phase_row = pane_widget._trace_rows[("status_led.timing", "phase_elapsed_ms")]
        toggle_row = pane_widget._trace_rows[("status_led.timing", "time_to_toggle_ms")]
        self.assertEqual(phase_row[3].text(), "12")
        self.assertEqual(toggle_row[3].text(), "18")
        self.assertEqual(phase_row[4].text(), "ms")
        self.assertEqual(toggle_row[4].text(), "ms")
        window.close()

        if owns_app:
            app.quit()

    def test_param_name_cell_tooltip_shows_full_name(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
            '"params":[{"name":"telemetry.timing_sample_ms","type":"u32","access":"rw","default":50,"min":10,"max":1000}]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        window._selected_device = "status_led"
        window._refresh_params_table()

        name_item = window._param_table.item(0, 0)
        self.assertIsNotNone(name_item)
        self.assertEqual(name_item.toolTip(), "telemetry.timing_sample_ms")
        window.close()

        if owns_app:
            app.quit()

    def test_host_parse_noise_stays_in_logs_without_error_banner(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        controller.runtime.record_parse_error(
            "Expecting ',' delimiter: line 1 column 10 (char 9)",
            '{"type":"sample"',
        )
        window._on_parse_error(controller.runtime.parse_errors[-1])
        window._tab_widget.setCurrentWidget(window._logs_tab)

        self.assertIn("info [host-sync]", window._logs_view.toPlainText())
        self.assertFalse(window._banner.isVisible())
        window.close()

        if owns_app:
            app.quit()

    def test_param_apply_timeout_recovers_row(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window._selected_device = "status_led"

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
            '"params":[{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000}]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        window._refresh_params_table()

        editor = window._param_editors["blink.period_ms"][1]
        editor.setValue(300)
        window._on_param_edited("blink.period_ms")
        window._param_apply_commands["blink.period_ms"] = 42
        window._apply_command_params[42] = "blink.period_ms"
        window._start_param_apply_timer("blink.period_ms", 42)
        window._update_param_row_state("blink.period_ms")

        self.assertEqual(window._param_apply_buttons["blink.period_ms"].text(), "Applying...")
        window._on_param_apply_timeout("blink.period_ms", 42)

        self.assertNotIn("blink.period_ms", window._param_apply_commands)
        self.assertEqual(window._param_apply_buttons["blink.period_ms"].text(), "Apply")
        self.assertTrue(window._param_apply_buttons["blink.period_ms"].isEnabled())
        window.close()

        if owns_app:
            app.quit()

    def test_param_apply_timeout_retries_before_giving_up(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        sent: list[tuple[str, str, dict[str, object]]] = []

        def fake_send_command(*, device: str, name: str, args: dict[str, object] | None = None):
            sent.append((device, name, args or {}))
            return 100 + len(sent)

        controller.send_command = fake_send_command  # type: ignore[method-assign]
        window = MainWindow(controller)
        window._selected_device = "status_led"
        window._param_apply_commands["blink.period_ms"] = 42
        window._apply_command_params[42] = "blink.period_ms"
        window._param_apply_attempts["blink.period_ms"] = 1
        window._param_apply_values["blink.period_ms"] = 300
        window._start_param_apply_timer("blink.period_ms", 42)

        window._on_param_apply_timeout("blink.period_ms", 42)

        self.assertEqual(
            sent,
            [
                (
                    "status_led",
                    "param.set",
                    {"param": "blink.period_ms", "value": 300},
                )
            ],
        )
        self.assertEqual(window._param_apply_commands["blink.period_ms"], 101)
        self.assertEqual(window._param_apply_attempts["blink.period_ms"], 2)
        window.close()

        if owns_app:
            app.quit()


if __name__ == "__main__":
    unittest.main()
