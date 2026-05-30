"""应用入口：创建 QApplication、主题与主窗口。"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from .constants import USE_WEBENGINE, ensure_markdown
from .markdown_render import markdown_ready
from .ui.main_window import MainWindow


def run() -> int:
    ensure_markdown()
    markdown_ready()

    if USE_WEBENGINE:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = app.palette()
    pal.setColor(pal.ColorRole.Window, QColor("#0f1117"))
    pal.setColor(pal.ColorRole.WindowText, QColor("#e2e8f0"))
    pal.setColor(pal.ColorRole.Base, QColor("#1a202c"))
    pal.setColor(pal.ColorRole.AlternateBase, QColor("#111827"))
    pal.setColor(pal.ColorRole.Text, QColor("#e2e8f0"))
    pal.setColor(pal.ColorRole.Button, QColor("#1a202c"))
    pal.setColor(pal.ColorRole.ButtonText, QColor("#e2e8f0"))
    pal.setColor(pal.ColorRole.Highlight, QColor("#2c5282"))
    pal.setColor(pal.ColorRole.HighlightedText, QColor("#e2e8f0"))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
