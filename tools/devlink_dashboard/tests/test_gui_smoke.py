from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

_HAS_GUI = bool(importlib.util.find_spec("PySide6")) and bool(importlib.util.find_spec("pyqtgraph"))

if _HAS_GUI:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtTest, QtWidgets

    from devlink_dashboard.gui.controller import GuiController
    from devlink_dashboard.gui.main_window import MainWindow, PRESET_TAB_ACTIVE_STYLESHEET, PRESET_TAB_INACTIVE_STYLESHEET
    from devlink_dashboard.gui.plot_workspace import MAX_FOLLOW_SPAN_US
    from devlink_dashboard.gui.workspace import DEFAULT_PRESET_NAME, WindowLayoutStore, WorkspaceStore
    from devlink_dashboard.messages import parse_line


@unittest.skipUnless(_HAS_GUI, "GUI dependencies are not installed")
class GuiSmokeTests(unittest.TestCase):
    def _show_param_in_active_preset(self, window: MainWindow, param_name: str) -> None:
        window._add_visible_param_to_active_preset(param_name)

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

    def test_plot_export_path_uses_recordings_directory_and_png_name(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window._record_path_edit.setText("/tmp/devlink-recordings")
        workspace = controller.runtime.build_default_workspace("status_led")
        window._workspace = workspace
        window._plot_workspace.set_workspace(workspace)

        exported_paths: list[str] = []

        def fake_export(path: str) -> bool:
            exported_paths.append(path)
            return True

        window._plot_workspace.export_active_pane_image = fake_export  # type: ignore[method-assign]
        window._export_active_plot()

        self.assertEqual(len(exported_paths), 1)
        export_path = Path(exported_paths[0])
        self.assertEqual(export_path.parent, Path("/tmp/devlink-recordings"))
        self.assertEqual(export_path.suffix, ".png")
        self.assertRegex(export_path.name, r"^plot-status_led-Main-\d{8}-\d{6}\.png$")
        window.close()

        if owns_app:
            app.quit()

    def test_record_output_directory_uses_parent_for_jsonl_input(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)
        window._record_path_edit.setText("/tmp/devlink-recordings/session.jsonl")

        self.assertEqual(window._record_output_directory(), Path("/tmp/devlink-recordings"))
        window.close()

        if owns_app:
            app.quit()

    def test_record_path_edit_defaults_to_resolved_directory(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        self.assertEqual(window._record_path_edit.text(), str(Path.cwd() / "firmware" / "recordings"))
        window.close()

        if owns_app:
            app.quit()

    def test_record_controls_stay_available_when_connected_but_idle(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        controller._worker = object()  # type: ignore[assignment]
        window = MainWindow(controller)
        window._on_connection_state_changed(True)

        self.assertFalse(window._record_checkbox.isEnabled())
        self.assertTrue(window._record_path_edit.isEnabled())
        self.assertTrue(window._browse_button.isEnabled())
        self.assertTrue(window._record_toggle_button.isEnabled())
        self.assertEqual(window._record_toggle_button.text(), "Start Recording")
        window.close()

        if owns_app:
            app.quit()

    def test_record_controls_remember_last_output_path_after_stop(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        controller._worker = object()  # type: ignore[assignment]
        window = MainWindow(controller)
        window._on_connection_state_changed(True)
        controller._on_recording_state_changed(True, "/tmp/devlink/session.jsonl")
        controller._on_recording_state_changed(False, "")

        self.assertEqual(window._record_path_edit.text(), "/tmp/devlink")
        self.assertEqual(window._record_toggle_button.text(), "Start Recording")
        self.assertIn("/tmp/devlink/session.jsonl", window._record_toggle_button.toolTip())
        window.close()

        if owns_app:
            app.quit()
    def test_record_controls_lock_while_recording(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        controller._worker = object()  # type: ignore[assignment]
        window = MainWindow(controller)
        window._on_connection_state_changed(True)
        controller._on_recording_state_changed(True, "/tmp/devlink/session.jsonl")

        self.assertFalse(window._record_path_edit.isEnabled())
        self.assertFalse(window._browse_button.isEnabled())
        self.assertTrue(window._record_toggle_button.isEnabled())
        self.assertEqual(window._record_toggle_button.text(), "Stop Recording")
        self.assertIn("/tmp/devlink/session.jsonl", window._record_toggle_button.toolTip())
        window.close()

        if owns_app:
            app.quit()

    def test_toggle_recording_builds_a_new_output_path(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        controller._worker = object()  # type: ignore[assignment]
        window = MainWindow(controller)
        window._on_connection_state_changed(True)
        window._port_combo.setEditText("/dev/ttyACM0")
        window._record_path_edit.setText("/tmp/devlink-recordings")

        started_paths: list[str] = []
        controller.start_recording = started_paths.append  # type: ignore[method-assign]
        window._toggle_recording()

        self.assertEqual(len(started_paths), 1)
        record_path = Path(started_paths[0])
        self.assertEqual(record_path.parent, Path("/tmp/devlink-recordings"))
        self.assertRegex(record_path.name, r"^devlink-ttyACM0-\d{8}-\d{6}\.jsonl$")
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
        self._show_param_in_active_preset(window, "blink.period_ms")

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
            window.resize(960, 720)
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
            self.assertEqual(stored.active_preset_name, DEFAULT_PRESET_NAME)
            self.assertEqual(stored.presets[0].workspace.panes[0].size, applied_sizes[0])
            self.assertEqual(stored.presets[0].workspace.panes[1].size, applied_sizes[1])

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

    def test_reenabling_follow_restores_y_auto_range_after_horizontal_zoom(self) -> None:
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

        center = pane_widget.plot_widget.viewport().rect().center()
        handled = pane_widget._handle_plot_wheel(QtCore.QPoint(120, 0), QtCore.QPointF(center))
        self.assertTrue(handled)
        app.processEvents()
        self.assertFalse(pane_widget._follow_button.isChecked())

        outlier = parse_line(
            '{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":300,'
            '"t_us":300000,"data":{"phase_elapsed_ms":1000}}'
        )
        controller.runtime.apply_message(outlier)
        window._plot_workspace.refresh_data(controller.runtime, "status_led")
        app.processEvents()

        before_follow_y = pane_widget.current_y_range()
        self.assertIsNotNone(before_follow_y)
        self.assertLess(before_follow_y[1], 1000)

        pane_widget._follow_button.click()
        app.processEvents()

        after_follow_y = pane_widget.current_y_range()
        self.assertIsNotNone(after_follow_y)
        self.assertGreater(after_follow_y[1], 1000)
        self.assertTrue(pane_widget._follow_button.isChecked())
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

    def test_alt_horizontal_wheel_performs_generic_zoom(self) -> None:
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
            QtCore.QPoint(120, 0),
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
        self._show_param_in_active_preset(window, "blink.period_ms")
        window._refresh_params_table()

        current_label = window._param_current_labels.get("blink.period_ms")
        self.assertIsNotNone(current_label)
        self.assertEqual(current_label.text(), "250")

        response = parse_line(
            '{"type":"resp","version":1,"device":"status_led","id":2,"ok":true,'
            '"result":{"params":[{"name":"blink.period_ms","value":607}]}}'
        )
        controller.runtime.apply_message(response)
        window._on_message_received(response)

        current_label = window._param_current_labels.get("blink.period_ms")
        self.assertIsNotNone(current_label)
        self.assertEqual(current_label.text(), "607")
        window.close()

        if owns_app:
            app.quit()

    def test_trace_rows_show_latest_trace_values(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))
            window.resize(960, 720)
            window.show()
            app.processEvents()

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

    def test_trace_overlay_is_collapsed_by_default(self) -> None:
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
                '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            QtTest.QTest.qWait(50)

            pane_widget = window._plot_workspace._pane_widgets["pane-1"]
            self.assertEqual(pane_widget.layout().count(), 2)
            self.assertTrue(pane_widget._show_trace_panel_button.isVisible())
            self.assertFalse(pane_widget._trace_overlay.isVisible())
            window.close()

        if owns_app:
            app.quit()

    def test_trace_overlay_repositions_when_plot_view_rect_changes(self) -> None:
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
                '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            QtTest.QTest.qWait(50)

            pane_widget = window._plot_workspace._pane_widgets["pane-1"]
            initial_button_x = pane_widget._show_trace_panel_button.x()
            initial_rect = pane_widget._plot_view_rect()
            shifted_rect = QtCore.QRect(
                initial_rect.x() + 32,
                initial_rect.y(),
                max(1, initial_rect.width() - 32),
                initial_rect.height(),
            )
            pane_widget._plot_view_rect = lambda: shifted_rect  # type: ignore[method-assign]
            pane_widget.plot_widget.getViewBox().sigResized.emit(pane_widget.plot_widget.getViewBox())
            app.processEvents()

            self.assertGreater(pane_widget._show_trace_panel_button.x(), initial_button_x)
            self.assertEqual(pane_widget._show_trace_panel_button.x(), shifted_rect.x() + 10)
            window.close()

        if owns_app:
            app.quit()

    def test_trace_overlay_show_hide_and_latest_values_update(self) -> None:
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
                '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"},'
                '{"name":"time_to_toggle_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            sample = parse_line(
                '{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":1,"t_us":1000,'
                '"data":{"phase_elapsed_ms":10,"time_to_toggle_ms":20}}'
            )
            controller.runtime.apply_message(sample)
            window._on_message_received(sample)
            QtTest.QTest.qWait(50)

            pane_widget = window._plot_workspace._pane_widgets["pane-1"]
            pane_widget._show_trace_panel_button.click()
            app.processEvents()

            phase_row = pane_widget._trace_rows[("status_led.timing", "phase_elapsed_ms")]
            plot_view_rect = pane_widget._plot_view_rect()
            self.assertTrue(pane_widget._trace_overlay.isVisible())
            self.assertFalse(pane_widget._show_trace_panel_button.isVisible())
            self.assertGreaterEqual(pane_widget._trace_overlay.x(), plot_view_rect.x())
            self.assertGreaterEqual(pane_widget._trace_overlay.y(), plot_view_rect.y())
            self.assertEqual(phase_row[2].text(), "phase_elapsed_ms")
            self.assertEqual(phase_row[2].toolTip(), "phase_elapsed_ms")

            sample = parse_line(
                '{"type":"sample","version":1,"device":"status_led","stream":"status_led.timing","seq":2,"t_us":2000,'
                '"data":{"phase_elapsed_ms":11,"time_to_toggle_ms":19}}'
            )
            controller.runtime.apply_message(sample)
            window._on_message_received(sample)
            QtTest.QTest.qWait(50)

            self.assertEqual(phase_row[3].text(), "11")
            pane_widget._hide_trace_panel_button.click()
            app.processEvents()
            self.assertFalse(pane_widget._trace_overlay.isVisible())
            self.assertTrue(pane_widget._show_trace_panel_button.isVisible())
            window.close()

        if owns_app:
            app.quit()

    def test_trace_overlay_controls_update_workspace(self) -> None:
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
                '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"},'
                '{"name":"time_to_toggle_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            QtTest.QTest.qWait(50)

            pane_widget = window._plot_workspace._pane_widgets["pane-1"]
            pane_widget._show_trace_panel_button.click()
            app.processEvents()

            phase_row = pane_widget._trace_rows[("status_led.timing", "phase_elapsed_ms")]
            toggle_row = pane_widget._trace_rows[("status_led.timing", "time_to_toggle_ms")]
            phase_row[0].click()
            app.processEvents()

            workspace = window._plot_workspace.workspace
            self.assertIsNotNone(workspace)
            pane = workspace.panes[0]
            self.assertFalse(pane.traces[0].visible)

            original_get_color = QtWidgets.QColorDialog.getColor
            QtWidgets.QColorDialog.getColor = lambda *args, **kwargs: QtGui.QColor("#123456")  # type: ignore[assignment]
            try:
                phase_row[1].click()
            finally:
                QtWidgets.QColorDialog.getColor = original_get_color
            app.processEvents()

            workspace = window._plot_workspace.workspace
            self.assertIsNotNone(workspace)
            pane = workspace.panes[0]
            self.assertEqual(pane.traces[0].color, "#123456")

            remove_button = toggle_row[0].parentWidget().findChild(QtWidgets.QToolButton)
            self.assertIsNotNone(remove_button)
            assert remove_button is not None
            remove_button.click()
            app.processEvents()

            workspace = window._plot_workspace.workspace
            self.assertIsNotNone(workspace)
            pane = workspace.panes[0]
            self.assertEqual([trace.field for trace in pane.traces], ["phase_elapsed_ms"])
            self.assertTrue(pane.trace_panel_visible)
            self.assertTrue(pane_widget._trace_overlay.isVisible())
            window.close()

        if owns_app:
            app.quit()

    def test_trace_overlay_height_is_capped_and_scrollable(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))
            window.resize(960, 720)
            window.show()
            app.processEvents()

            fields = ",".join(
                f'{{"name":"field_{index}_value","type":"u32","unit":"ms"}}'
                for index in range(18)
            )
            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                f'{{"name":"status_led.timing","fields":[{fields}]}}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            QtTest.QTest.qWait(50)

            pane_widget = window._plot_workspace._pane_widgets["pane-1"]
            pane_widget._show_trace_panel_button.click()
            QtTest.QTest.qWait(50)

            first_row = pane_widget._trace_rows[("status_led.timing", "field_0_value")]
            remove_button = first_row[0].parentWidget().findChild(QtWidgets.QToolButton)
            self.assertIsNotNone(remove_button)
            assert remove_button is not None
            scrollbar = pane_widget._trace_scroll.verticalScrollBar()
            self.assertIsNone(window._plot_workspace.workspace.panes[0].trace_panel_height)
            self.assertTrue(pane_widget._trace_overlay.height() <= pane_widget._plot_view_rect().height() // 2)
            self.assertGreater(scrollbar.maximum(), 0)
            self.assertLess(
                remove_button.mapToGlobal(remove_button.rect().topRight()).x(),
                scrollbar.mapToGlobal(scrollbar.rect().topLeft()).x(),
            )
            window.close()

        if owns_app:
            app.quit()

    def test_trace_overlay_custom_height_respects_bounds(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))
            window._window_layout_store = WindowLayoutStore(Path(tmp_dir))
            window.resize(960, 720)
            window.show()
            app.processEvents()

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            QtTest.QTest.qWait(50)

            pane_widget = window._plot_workspace._pane_widgets["pane-1"]
            pane_widget._show_trace_panel_button.click()
            QtTest.QTest.qWait(50)

            default_height = pane_widget._trace_overlay.height()
            pane_widget._start_trace_panel_resize(100.0)
            pane_widget._update_trace_panel_resize(500.0)
            pane_widget._finish_trace_panel_resize()
            app.processEvents()

            workspace = window._plot_workspace.workspace
            self.assertIsNotNone(workspace)
            assert workspace is not None
            custom_height = pane_widget._trace_overlay.height()
            self.assertGreater(custom_height, default_height)
            self.assertEqual(workspace.panes[0].trace_panel_height, custom_height)
            self.assertLessEqual(custom_height, pane_widget._trace_panel_custom_height_bounds()[1])
            self.assertLessEqual(
                pane_widget._trace_overlay.geometry().bottom(),
                pane_widget._plot_view_rect().bottom(),
            )

            pane_widget._start_trace_panel_resize(500.0)
            pane_widget._update_trace_panel_resize(-1000.0)
            pane_widget._finish_trace_panel_resize()
            app.processEvents()

            min_height = pane_widget._trace_panel_minimum_height()
            row_widget = next(iter(pane_widget._trace_rows.values()))[0].parentWidget()
            self.assertIsNotNone(row_widget)
            assert row_widget is not None
            self.assertEqual(pane_widget._trace_overlay.height(), min_height)
            self.assertLessEqual(row_widget.height(), pane_widget._trace_scroll.viewport().height())
            window.close()

        if owns_app:
            app.quit()

    def test_trace_overlay_visibility_persists_after_restore_and_preset_switch(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
            '"params":[]}'
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))
            window._window_layout_store = WindowLayoutStore(Path(tmp_dir))
            window.resize(960, 720)
            window.show()
            app.processEvents()

            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            QtTest.QTest.qWait(50)

            pane_widget = window._plot_workspace._pane_widgets["pane-1"]
            pane_widget._show_trace_panel_button.click()
            app.processEvents()
            self.assertTrue(window._plot_workspace.workspace.panes[0].trace_panel_visible)
            pane_widget._start_trace_panel_resize(100.0)
            pane_widget._update_trace_panel_resize(280.0)
            pane_widget._finish_trace_panel_resize()
            app.processEvents()

            resized_height = pane_widget._trace_overlay.height()
            self.assertEqual(window._plot_workspace.workspace.panes[0].trace_panel_height, resized_height)

            window._plot_workspace.duplicate_active_pane()
            app.processEvents()
            duplicated_workspace = window._plot_workspace.workspace
            self.assertIsNotNone(duplicated_workspace)
            self.assertTrue(duplicated_workspace.panes[-1].trace_panel_visible)
            self.assertEqual(duplicated_workspace.panes[-1].trace_panel_height, resized_height)

            window.close()

            restored_controller = GuiController()
            restored = MainWindow(restored_controller)
            restored._workspace_store = WorkspaceStore(Path(tmp_dir))
            restored._window_layout_store = WindowLayoutStore(Path(tmp_dir))
            restored.resize(960, 720)
            restored.show()
            app.processEvents()

            restored_controller.runtime.apply_message(capabilities)
            restored._on_message_received(capabilities)
            QtTest.QTest.qWait(50)

            restored_pane = restored._plot_workspace._pane_widgets["pane-1"]
            self.assertTrue(restored_pane._trace_overlay.isVisible())
            self.assertFalse(restored_pane._show_trace_panel_button.isVisible())
            self.assertEqual(restored._plot_workspace.workspace.panes[0].trace_panel_height, resized_height)
            restored_min_height, restored_max_height = restored_pane._trace_panel_custom_height_bounds()
            expected_restored_height = min(max(resized_height, restored_min_height), restored_max_height)
            self.assertEqual(restored_pane._trace_overlay.height(), expected_restored_height)

            restored._create_preset()
            app.processEvents()
            self.assertEqual(restored._workspace.panes, ())

            restored._select_preset(DEFAULT_PRESET_NAME)
            QtTest.QTest.qWait(50)
            restored_pane = restored._plot_workspace._pane_widgets["pane-1"]
            self.assertTrue(restored_pane._trace_overlay.isVisible())
            restored_min_height, restored_max_height = restored_pane._trace_panel_custom_height_bounds()
            expected_restored_height = min(max(resized_height, restored_min_height), restored_max_height)
            self.assertEqual(restored_pane._trace_overlay.height(), expected_restored_height)
            restored.close()

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
        self._show_param_in_active_preset(window, "telemetry.timing_sample_ms")
        window._refresh_params_table()

        name_label = window._param_name_labels.get("telemetry.timing_sample_ms")
        self.assertIsNotNone(name_label)
        self.assertEqual(name_label.toolTip(), "telemetry.timing_sample_ms")
        window.close()

        if owns_app:
            app.quit()

    def test_param_card_uses_stacked_layout_without_horizontal_overflow(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
            '"params":[{"name":"servo.a.hold.deadband_deg","type":"f32","access":"rw","default":0.0,"min":0.0,"max":15.0}]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        window._selected_device = "status_led"
        self._show_param_in_active_preset(window, "servo.a.hold.deadband_deg")
        window._refresh_params_table()

        window.resize(1200, 800)
        window.show()
        window._body_splitter.setSizes([220, 760, 240])
        QtTest.QTest.qWait(50)

        viewport = window._param_list_scroll.viewport()
        card = window._param_cards["servo.a.hold.deadband_deg"]
        button = window._param_apply_buttons["servo.a.hold.deadband_deg"]
        name_label = window._param_name_labels["servo.a.hold.deadband_deg"]
        current_label = window._param_current_labels["servo.a.hold.deadband_deg"]
        type_badge = next(
            child
            for child in card.findChildren(QtWidgets.QLabel)
            if child.property("role") == "typeBadge"
        )

        button_rect = QtCore.QRect(button.mapTo(viewport, QtCore.QPoint(0, 0)), button.size())
        name_rect = QtCore.QRect(name_label.mapTo(card, QtCore.QPoint(0, 0)), name_label.size())
        current_rect = QtCore.QRect(current_label.mapTo(card, QtCore.QPoint(0, 0)), current_label.size())
        type_rect = QtCore.QRect(type_badge.mapTo(card, QtCore.QPoint(0, 0)), type_badge.size())
        button_card_rect = QtCore.QRect(button.mapTo(card, QtCore.QPoint(0, 0)), button.size())

        self.assertFalse(name_label.wordWrap())
        self.assertTrue(viewport.rect().contains(button_rect))
        self.assertEqual(window._param_list_scroll.horizontalScrollBar().maximum(), 0)
        self.assertLessEqual(card.width(), viewport.width())
        self.assertLess(name_rect.top(), current_rect.top())
        self.assertLess(name_rect.top(), type_rect.top())
        self.assertLess(current_rect.top(), button_card_rect.top())
        self.assertLess(type_rect.top(), button_card_rect.top())
        window.close()

        if owns_app:
            app.quit()

    def test_pressing_enter_in_param_editor_applies_pending_value(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        sent: list[tuple[str, str, dict[str, object]]] = []

        def fake_send_command(*, device: str, name: str, args: dict[str, object] | None = None):
            sent.append((device, name, args or {}))
            return 17

        controller.send_command = fake_send_command  # type: ignore[method-assign]
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
            '"params":[{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000}]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        window._selected_device = "status_led"
        self._show_param_in_active_preset(window, "blink.period_ms")
        window._refresh_params_table()

        editor = window._param_editors["blink.period_ms"][1]
        editor.setValue(300)
        line_edit = editor.lineEdit()
        self.assertIsNotNone(line_edit)
        assert line_edit is not None
        self.assertTrue(window._param_apply_buttons["blink.period_ms"].isEnabled())

        line_edit.setFocus()
        QtTest.QTest.keyClick(line_edit, QtCore.Qt.Key.Key_Return)

        self.assertEqual(sent, [("status_led", "param.set", {"param": "blink.period_ms", "value": 300})])
        self.assertEqual(window._param_apply_buttons["blink.period_ms"].text(), "Applying...")
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

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
                '"params":[{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000}]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            self._show_param_in_active_preset(window, "blink.period_ms")
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

    def test_params_tab_starts_empty_and_add_menu_tracks_visible_params(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
                '"params":['
                '{"name":"blink.enabled","type":"bool","access":"rw","default":false},'
                '{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000},'
                '{"name":"telemetry.rate_hz","type":"u32","access":"rw","default":20,"min":1,"max":100}'
                ']}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            self.assertEqual(window._params_state_label.text(), "No parameters added to this preset.")
            self.assertEqual(window._refresh_params_button.text(), "")
            self.assertEqual(window._add_param_button.text(), "Add Parameter")
            self.assertEqual(window._param_cards, {})

            popup = window._build_add_param_picker()
            self.assertIsNotNone(popup)
            assert popup is not None
            self.assertIn("QListWidget::item", popup.styleSheet())
            self.assertEqual(
                [popup._list.item(index).text() for index in range(popup._list.count())],
                ["blink.enabled", "blink.period_ms", "telemetry.rate_hz"],
            )
            self.assertTrue(all(bool(popup._list.item(index).flags() & QtCore.Qt.ItemFlag.ItemIsEnabled) for index in range(popup._list.count())))

            popup._on_item_clicked(popup._list.item(1))
            self.assertEqual(list(window._param_cards.keys()), ["blink.period_ms"])
            self.assertFalse(window._params_state_label.isVisible())

            popup = window._build_add_param_picker()
            assert popup is not None
            self.assertFalse(bool(popup._list.item(1).flags() & QtCore.Qt.ItemFlag.ItemIsEnabled))
            self.assertTrue(bool(popup._list.item(0).flags() & QtCore.Qt.ItemFlag.ItemIsEnabled))
            self.assertTrue(bool(popup._list.item(2).flags() & QtCore.Qt.ItemFlag.ItemIsEnabled))
            window.close()

        if owns_app:
            app.quit()

    def test_gait_speed_mode_param_can_be_added_and_applied(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            sent: list[tuple[str, str, dict[str, object]]] = []

            def fake_send_command(*, device: str, name: str, args: dict[str, object] | None = None):
                sent.append((device, name, args or {}))
                return 41

            controller.send_command = fake_send_command  # type: ignore[method-assign]
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"control_testing",'
                '"commands":[{"name":"gait.play","args":[]},{"name":"gait.pause","args":[]},{"name":"gait.status","args":[]}],'
                '"streams":[],'
                '"params":['
                '{"name":"gait.speed_mode","type":"u8","access":"rw","default":0,"min":0,"max":3}'
                ']}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            popup = window._build_add_param_picker()
            self.assertIsNotNone(popup)
            assert popup is not None
            self.assertEqual([popup._list.item(index).text() for index in range(popup._list.count())], ["gait.speed_mode"])

            popup._on_item_clicked(popup._list.item(0))
            self.assertEqual(list(window._param_cards.keys()), ["gait.speed_mode"])
            self.assertEqual([command.name for command in window._current_command_specs], ["gait.play", "gait.pause", "gait.status"])

            editor_kind, editor = window._param_editors["gait.speed_mode"]
            self.assertEqual(editor_kind, "int_spin")
            self.assertEqual(editor.minimum(), 0)
            self.assertEqual(editor.maximum(), 3)

            editor.setValue(3)
            window._on_param_edited("gait.speed_mode")
            self.assertTrue(window._param_apply_buttons["gait.speed_mode"].isEnabled())

            window._apply_param("gait.speed_mode")

            self.assertEqual(
                sent,
                [("control_testing", "param.set", {"param": "gait.speed_mode", "value": 3})],
            )
            self.assertEqual(window._param_apply_buttons["gait.speed_mode"].text(), "Applying...")
            window.close()

        if owns_app:
            app.quit()

    def test_visible_params_are_scoped_per_preset(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
                '"params":['
                '{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000},'
                '{"name":"telemetry.rate_hz","type":"u32","access":"rw","default":20,"min":1,"max":100}'
                ']}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            self._show_param_in_active_preset(window, "blink.period_ms")
            self.assertEqual(list(window._param_cards.keys()), ["blink.period_ms"])

            window._create_preset()
            self.assertEqual(window._active_preset_name, "Preset 1")
            self.assertEqual(window._params_state_label.text(), "No parameters added to this preset.")
            self.assertEqual(window._param_cards, {})

            self._show_param_in_active_preset(window, "telemetry.rate_hz")
            self.assertEqual(list(window._param_cards.keys()), ["telemetry.rate_hz"])

            window._select_preset(DEFAULT_PRESET_NAME)
            self.assertEqual(list(window._param_cards.keys()), ["blink.period_ms"])

            window._select_preset("Preset 1")
            self.assertEqual(list(window._param_cards.keys()), ["telemetry.rate_hz"])
            window.close()

        if owns_app:
            app.quit()

    def test_param_card_context_menu_removes_param_from_active_preset_only(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
                '"params":[{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000}]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            self._show_param_in_active_preset(window, "blink.period_ms")
            window._create_preset()
            self._show_param_in_active_preset(window, "blink.period_ms")

            menu = window._build_param_card_context_menu("blink.period_ms")
            menu.actions()[0].trigger()
            self.assertEqual(window._params_state_label.text(), "No parameters added to this preset.")
            self.assertEqual(window._param_cards, {})

            window._select_preset(DEFAULT_PRESET_NAME)
            self.assertEqual(list(window._param_cards.keys()), ["blink.period_ms"])
            window.close()

        if owns_app:
            app.quit()

    def test_refresh_params_button_still_requests_param_list(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        controller = GuiController()
        sent: list[tuple[str, str, dict[str, object]]] = []

        def fake_send_command(*, device: str, name: str, args: dict[str, object] | None = None):
            sent.append((device, name, args or {}))
            return 7

        controller.send_command = fake_send_command  # type: ignore[method-assign]
        window = MainWindow(controller)

        capabilities = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":[],'
            '"params":[{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000}]}'
        )
        controller.runtime.apply_message(capabilities)
        window._on_message_received(capabilities)
        controller._worker = object()  # type: ignore[assignment]
        window._on_connection_state_changed(True)

        window._refresh_params_button.click()

        self.assertEqual(sent, [("status_led", "param.list", {})])
        window.close()

        if owns_app:
            app.quit()

    def test_preset_ribbon_loads_default_preset_for_device(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]},'
                '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            label_texts = {label.text() for label in window.findChildren(QtWidgets.QLabel)}
            self.assertEqual(window._workspace_presets.active_preset_name, DEFAULT_PRESET_NAME)
            self.assertEqual(list(window._preset_buttons.keys()), [DEFAULT_PRESET_NAME])
            self.assertTrue(window._preset_buttons[DEFAULT_PRESET_NAME].isChecked())
            self.assertEqual(window._new_preset_button.text(), "+")
            self.assertEqual(
                window._preset_scroll.horizontalScrollBarPolicy(),
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self.assertNotIn("Presets", label_texts)
            self.assertFalse(any(text.startswith("Workspace for ") for text in label_texts))
            self.assertEqual(window._add_pane_button.text(), "Add Pane")
            self.assertEqual(window._duplicate_pane_button.text(), "Duplicate Pane")
            self.assertEqual(window._export_plot_button.text(), "Export Plot")
            self.assertEqual(window._remove_pane_button.text(), "Remove Pane")
            window.close()

        if owns_app:
            app.quit()

    def test_new_preset_stays_blank_after_samples_arrive(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]},'
                '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            window._new_preset_button.click()

            self.assertEqual(window._active_preset_name, "Preset 1")
            self.assertEqual(window._workspace.panes, ())
            self.assertEqual(window._plot_workspace._pane_widgets, {})
            self.assertEqual(window._plot_workspace._state_label.text(), "No panes configured for this device")

            sample = parse_line(
                '{"type":"sample","version":1,"device":"status_led","stream":"status_led.state","seq":1,"t_us":1000,'
                '"data":{"blink_period_ms":250}}'
            )
            controller.runtime.apply_message(sample)
            window._on_message_received(sample)

            self.assertEqual(window._workspace.panes, ())
            window.close()

        if owns_app:
            app.quit()

    def test_switching_presets_restores_each_preset_sizes(self) -> None:
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

            window._plot_workspace._splitter.setSizes([180, 420])
            app.processEvents()
            default_sizes = window._plot_workspace._splitter.sizes()

            window._create_preset()
            window._plot_workspace.add_pane()
            window._plot_workspace.add_pane()
            app.processEvents()
            window._plot_workspace._splitter.setSizes([320, 220])
            app.processEvents()
            preset_sizes = window._plot_workspace._splitter.sizes()

            window._select_preset(DEFAULT_PRESET_NAME)
            app.processEvents()
            self.assertEqual(window._plot_workspace._splitter.sizes()[:2], default_sizes[:2])

            window._select_preset("Preset 1")
            app.processEvents()
            self.assertEqual(window._plot_workspace._splitter.sizes()[:2], preset_sizes[:2])
            window.close()

        if owns_app:
            app.quit()

    def test_selecting_preset_preserves_header_scroll(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))
            window.resize(720, 700)
            window.show()
            app.processEvents()

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            for _ in range(8):
                window._create_preset()
            app.processEvents()
            QtTest.QTest.qWait(50)

            scroll_bar = window._preset_scroll.horizontalScrollBar()
            self.assertGreater(scroll_bar.maximum(), 0)
            scroll_bar.setValue(scroll_bar.maximum())
            app.processEvents()
            before = scroll_bar.value()

            window._select_preset(DEFAULT_PRESET_NAME)
            app.processEvents()
            QtTest.QTest.qWait(50)

            self.assertEqual(window._active_preset_name, DEFAULT_PRESET_NAME)
            self.assertEqual(scroll_bar.value(), before)
            window.close()

        if owns_app:
            app.quit()

    def test_switching_presets_restores_each_workspace(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]},'
                '{"name":"status_led.timing","fields":[{"name":"phase_elapsed_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            self.assertEqual(len(window._workspace.panes), 2)

            window._create_preset()
            self.assertEqual(window._preset_buttons["Preset 1"].styleSheet(), PRESET_TAB_ACTIVE_STYLESHEET)
            self.assertEqual(window._preset_buttons[DEFAULT_PRESET_NAME].styleSheet(), PRESET_TAB_INACTIVE_STYLESHEET)
            window._plot_workspace.add_pane()
            window._selected_stream = "status_led.state"
            window._refresh_field_list()
            window._field_list.setCurrentRow(0)
            window._add_selected_field_to_active_pane()

            custom_workspace = window._plot_workspace.workspace
            self.assertIsNotNone(custom_workspace)
            self.assertEqual(len(custom_workspace.panes), 1)
            self.assertEqual(custom_workspace.panes[0].traces[0].field, "blink_period_ms")

            window._select_preset(DEFAULT_PRESET_NAME)
            self.assertEqual(len(window._workspace.panes), 2)
            self.assertEqual(window._preset_buttons[DEFAULT_PRESET_NAME].styleSheet(), PRESET_TAB_ACTIVE_STYLESHEET)
            self.assertEqual(window._preset_buttons["Preset 1"].styleSheet(), PRESET_TAB_INACTIVE_STYLESHEET)

            window._select_preset("Preset 1")
            self.assertEqual(len(window._workspace.panes), 1)
            self.assertEqual(window._workspace.panes[0].traces[0].field, "blink_period_ms")
            self.assertEqual(window._preset_buttons["Preset 1"].styleSheet(), PRESET_TAB_ACTIVE_STYLESHEET)
            self.assertEqual(window._preset_buttons[DEFAULT_PRESET_NAME].styleSheet(), PRESET_TAB_INACTIVE_STYLESHEET)
            window.close()

        if owns_app:
            app.quit()

    def test_preset_context_menu_supports_rename_and_delete(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            default_button = window._preset_buttons[DEFAULT_PRESET_NAME]
            self.assertEqual(default_button.contextMenuPolicy(), QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            menu = window._build_preset_context_menu(DEFAULT_PRESET_NAME)
            self.assertIsNotNone(menu)
            assert menu is not None
            self.assertIn("QMenu::item", menu.styleSheet())
            self.assertEqual([action.text() for action in menu.actions()], ["Rename", "Delete"])
            self.assertFalse(menu.actions()[1].isEnabled())

            window._create_preset()
            preset_button = window._preset_buttons["Preset 1"]
            self.assertEqual(preset_button.contextMenuPolicy(), QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            menu = window._build_preset_context_menu("Preset 1")
            self.assertIsNotNone(menu)
            assert menu is not None
            menu.actions()[0].trigger()
            self.assertEqual(window._active_preset_name, "Preset 1")
            self.assertIsNotNone(window._preset_rename_editor)
            window._cancel_preset_rename()

            menu = window._build_preset_context_menu("Preset 1")
            assert menu is not None
            self.assertTrue(menu.actions()[1].isEnabled())
            menu.actions()[1].trigger()
            self.assertNotIn("Preset 1", window._preset_buttons)
            self.assertEqual(window._active_preset_name, DEFAULT_PRESET_NAME)
            window.close()

        if owns_app:
            app.quit()

    def test_preset_context_menu_signal_passes_button_global_click_pos(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))
            window.resize(720, 700)
            window.show()
            app.processEvents()

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            for _ in range(3):
                window._create_preset()
            app.processEvents()

            target_button = window._preset_buttons["Preset 2"]
            viewport_origin = window._preset_scroll.viewport().mapToGlobal(QtCore.QPoint(0, 0))
            self.assertGreater(target_button.mapToGlobal(QtCore.QPoint(0, 0)).x(), viewport_origin.x())

            captured: list[tuple[str, QtWidgets.QWidget | None, QtCore.QPoint | None]] = []

            def fake_show_preset_context_menu(
                preset_name: str,
                *,
                source: QtWidgets.QWidget | None = None,
                global_pos: QtCore.QPoint | None = None,
            ) -> None:
                captured.append((preset_name, source, QtCore.QPoint(global_pos) if global_pos is not None else None))

            window._show_preset_context_menu = fake_show_preset_context_menu  # type: ignore[method-assign]

            local_pos = QtCore.QPoint(target_button.width() - 4, target_button.height() // 2)
            expected_global_pos = target_button.mapToGlobal(local_pos)
            target_button.customContextMenuRequested.emit(local_pos)

            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0][0], "Preset 2")
            self.assertIs(captured[0][1], target_button)
            self.assertEqual(captured[0][2], expected_global_pos)
            window.close()

        if owns_app:
            app.quit()

    def test_show_preset_context_menu_prefers_click_pos_and_falls_back_to_source_bottom(self) -> None:
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
                '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)

            source = window._preset_buttons[DEFAULT_PRESET_NAME]
            anchors: list[QtCore.QPoint] = []

            class MenuStub:
                def exec(self, anchor: QtCore.QPoint) -> None:
                    anchors.append(QtCore.QPoint(anchor))

            window._build_preset_context_menu = lambda _preset_name: MenuStub()  # type: ignore[method-assign]

            explicit_anchor = QtCore.QPoint(321, 654)
            window._show_preset_context_menu(DEFAULT_PRESET_NAME, source=source, global_pos=explicit_anchor)
            self.assertEqual(anchors, [explicit_anchor])

            anchors.clear()
            expected_fallback_anchor = source.mapToGlobal(QtCore.QPoint(0, source.height()))
            window._show_preset_context_menu(DEFAULT_PRESET_NAME, source=source)
            self.assertEqual(anchors, [expected_fallback_anchor])
            window.close()

        if owns_app:
            app.quit()

    def test_inline_preset_rename_persists_and_rejects_invalid_names(self) -> None:
        app = QtWidgets.QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QtWidgets.QApplication(["devlink-dashboard-test"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            controller = GuiController()
            window = MainWindow(controller)
            window._workspace_store = WorkspaceStore(Path(tmp_dir))

            capabilities = parse_line(
                '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
                '{"name":"status_led.state","fields":[{"name":"blink_period_ms","type":"u32","unit":"ms"}]}],'
                '"params":[]}'
            )
            controller.runtime.apply_message(capabilities)
            window._on_message_received(capabilities)
            window._create_preset()

            window._begin_preset_rename("Preset 1")
            self.assertIsNotNone(window._preset_rename_editor)
            window._preset_rename_editor.setText("Analysis")
            window._finish_preset_rename()

            self.assertEqual(window._active_preset_name, "Analysis")
            self.assertIn("Analysis", window._preset_buttons)

            window._begin_preset_rename("Analysis")
            self.assertIsNotNone(window._preset_rename_editor)
            window._preset_rename_editor.setText(DEFAULT_PRESET_NAME)
            window._finish_preset_rename()
            self.assertEqual(window._active_preset_name, "Analysis")
            self.assertIn("Analysis", window._preset_buttons)

            window._begin_preset_rename("Analysis")
            self.assertIsNotNone(window._preset_rename_editor)
            window._preset_rename_editor.setText("   ")
            window._finish_preset_rename()
            self.assertEqual(window._active_preset_name, "Analysis")
            window.close()

            restored_controller = GuiController()
            restored = MainWindow(restored_controller)
            restored._workspace_store = WorkspaceStore(Path(tmp_dir))
            restored_controller.runtime.apply_message(capabilities)
            restored._on_message_received(capabilities)

            self.assertEqual(restored._active_preset_name, "Analysis")
            self.assertIn(DEFAULT_PRESET_NAME, restored._preset_buttons)
            self.assertIn("Analysis", restored._preset_buttons)
            restored.close()

        if owns_app:
            app.quit()


if __name__ == "__main__":
    unittest.main()
