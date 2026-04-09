from __future__ import annotations

from argparse import Namespace


def run_gui(args: Namespace) -> int:
    try:
        import pyqtgraph as pg
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        print("PySide6 and pyqtgraph are required for the GUI; install tools/devlink_dashboard[gui]")
        return 2

    from .controller import GuiController
    from .main_window import MainWindow

    app = QtWidgets.QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QtWidgets.QApplication(["devlink-dashboard"])

    app.setApplicationName("Devlink Dashboard")
    pg.setConfigOptions(antialias=True)

    controller = GuiController()
    window = MainWindow(
        controller,
        initial_port=args.port,
        initial_baud=args.baud,
        initial_timeout=args.timeout,
        initial_record_path=args.record,
    )
    window.show()
    QtCore.QTimer.singleShot(0, window.connect_if_requested)

    if owns_app:
        return app.exec()
    return 0
