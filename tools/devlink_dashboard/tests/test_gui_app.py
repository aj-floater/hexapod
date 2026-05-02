from __future__ import annotations

import io
import sys
import types
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from unittest import mock

from devlink_dashboard.gui.app import run_gui


class GuiAppTests(unittest.TestCase):
    def test_run_gui_imports_pyside6_before_pyqtgraph(self) -> None:
        fake_pg = types.ModuleType("pyqtgraph")
        fake_pg.setConfigOptions = lambda **kwargs: None

        class _FakeQTimer:
            @staticmethod
            def singleShot(_delay: int, callback) -> None:
                callback()

        class _FakeApplication:
            _instance = None

            def __init__(self, _argv: list[str]) -> None:
                type(self)._instance = self
                self.exec_called = False
                self.app_name = None

            @classmethod
            def instance(cls):
                return cls._instance

            def setApplicationName(self, name: str) -> None:
                self.app_name = name

            def exec(self) -> int:
                self.exec_called = True
                return 0

        fake_qtcore = types.SimpleNamespace(QTimer=_FakeQTimer)
        fake_qtwidgets = types.SimpleNamespace(QApplication=_FakeApplication)
        fake_pyside6 = types.ModuleType("PySide6")
        fake_pyside6.QtCore = fake_qtcore
        fake_pyside6.QtWidgets = fake_qtwidgets

        fake_controller_module = types.ModuleType("devlink_dashboard.gui.controller")

        class _FakeGuiController:
            pass

        fake_controller_module.GuiController = _FakeGuiController

        fake_main_window_module = types.ModuleType("devlink_dashboard.gui.main_window")

        class _FakeMainWindow:
            def __init__(
                self,
                controller,
                initial_port=None,
                initial_baud=None,
                initial_timeout=None,
                initial_record_path=None,
            ) -> None:
                self.controller = controller
                self.initial_port = initial_port
                self.initial_baud = initial_baud
                self.initial_timeout = initial_timeout
                self.initial_record_path = initial_record_path
                self.show_called = False
                self.connect_if_requested_called = False

            def show(self) -> None:
                self.show_called = True

            def connect_if_requested(self) -> None:
                self.connect_if_requested_called = True

        fake_main_window_module.MainWindow = _FakeMainWindow

        import_order: list[str] = []
        original_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "PySide6":
                import_order.append(name)
                sys.modules[name] = fake_pyside6
                return fake_pyside6
            if name == "pyqtgraph":
                import_order.append(name)
                if "PySide6" not in sys.modules:
                    raise ImportError("PySide6 must be imported first")
                sys.modules[name] = fake_pg
                return fake_pg
            return original_import(name, globals, locals, fromlist, level)

        args = Namespace(port="/dev/ttyACM0", baud=115200, timeout=0.05, record="session.jsonl")
        with mock.patch.dict(
            sys.modules,
            {
                "PySide6": None,
                "pyqtgraph": None,
                "devlink_dashboard.gui.controller": fake_controller_module,
                "devlink_dashboard.gui.main_window": fake_main_window_module,
            },
            clear=False,
        ):
            with mock.patch("builtins.__import__", side_effect=fake_import):
                with mock.patch.dict("os.environ", {}, clear=False):
                    result = run_gui(args)

        self.assertEqual(result, 0)
        self.assertEqual(import_order[:2], ["PySide6", "pyqtgraph"])

    def test_run_gui_reports_underlying_import_error(self) -> None:
        original_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "PySide6":
                raise ImportError("Qt runtime mismatch")
            return original_import(name, globals, locals, fromlist, level)

        stdout = io.StringIO()
        with mock.patch("builtins.__import__", side_effect=fake_import):
            with redirect_stdout(stdout):
                result = run_gui(Namespace(port=None, baud=115200, timeout=0.05, record=None))

        output = stdout.getvalue()
        self.assertEqual(result, 2)
        self.assertIn("PySide6 and pyqtgraph are required for the GUI", output)
        self.assertIn("Qt runtime mismatch", output)


if __name__ == "__main__":
    unittest.main()
