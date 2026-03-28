from __future__ import annotations

import importlib.util
import os
import unittest

_HAS_GUI = bool(importlib.util.find_spec("PySide6")) and bool(importlib.util.find_spec("pyqtgraph"))

if _HAS_GUI:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets

    from devlink_dashboard.gui.controller import GuiController
    from devlink_dashboard.gui.main_window import MainWindow
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


if __name__ == "__main__":
    unittest.main()
