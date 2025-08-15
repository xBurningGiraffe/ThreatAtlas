# cyber_risk/gui/app.py
from __future__ import annotations
import sys
from PyQt6 import QtWidgets

from .view import MainWindow
from .controller import Controller


def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    # IMPORTANT: keep a strong reference so signals/slots stay connected
    win.controller = Controller(win)  # <-- instead of just Controller(win)
    win.show()
    sys.exit(app.exec())
