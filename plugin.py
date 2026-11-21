# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

try:                                   # Qt6 (QGIS 4)
    from qgis.PyQt.QtGui import QAction
except ImportError:                    # Qt5 (QGIS 3)
    from qgis.PyQt.QtWidgets import QAction

NAME = "Aufschluss Suite"


def _icon(text="AS"):
    pm = QPixmap(32, 32)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setPen(QColor("#1F4E9C"))
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    f = QFont()
    f.setBold(True)
    f.setPixelSize(22)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return QIcon(pm)


class SuitePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.win = None

    def initGui(self):
        self.action = QAction(_icon(), NAME, self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&" + NAME, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.win is not None:
            self.win.shutdown()
            self.win = None
        if self.action is not None:
            self.iface.removePluginMenu("&" + NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def run(self):
        from .main_window import SuiteWindow
        if self.win is None:
            self.win = SuiteWindow(self.iface, self.iface.mainWindow())
        self.win.present()
