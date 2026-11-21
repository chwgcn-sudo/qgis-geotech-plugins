# -*- coding: utf-8 -*-
"""Hauptfenster: links Projekt-Layerbaum, daneben schmale Buttonspalte. Ohne gewähltes Modul ist das Fenster
schmal (nur Baum + Buttons); ein Klick auf einen Button öffnet das Modul als dritte Spalte rechts und das
Fenster wird 1200 x 794. Die drei Spalten sind per Splitter (Lücke ziehen) verschiebbar. Es ist immer nur
ein Modul offen; beim Wechsel wird das vorige geschlossen (Erzeugtes bleibt gespeichert). Module bleiben
eigenständig und werden erst beim Klick geladen – schlägt eines fehl, bleiben die anderen benutzbar."""

import traceback

from qgis.PyQt.QtCore import QEvent, QRectF, QSize, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter,
                                 QVBoxLayout)

from . import VERSION
from .core import screens, selection, ui
from .core.layertree import ProjectPanel

# Reihenfolge der Buttons: Aufschluss, Mappe, Lageplan
MODULES = (("aufschluss", "Aufschluss"), ("mappe", "Mappe"), ("lageplan", "Lageplan"))

W_FULL, H_FULL = 1200, 794       # Fenster mit geöffnetem Modul
W_TREE, W_BTN = 380, 190         # Spaltenbreiten (Baum, Buttons = halbe Breite); Rest geht ans Modul
MARGIN, HANDLE = 12, 10


def collapse_icon():
    """Kleines Symbol 'Seitenleiste zu': graues Kästchen, rechts ein dunklerer Streifen."""
    r = 2
    pm = QPixmap(26 * r, 20 * r)
    pm.setDevicePixelRatio(r)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    box = QRectF(1.5, 1.5, 23, 17)
    p.setPen(QPen(QColor("#8a948f"), 1.4))
    p.setBrush(QColor("#e3e7e5"))
    p.drawRoundedRect(box, 3, 3)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#6b7570"))
    p.drawRoundedRect(QRectF(16.5, 3.5, 6, 13), 1.8, 1.8)
    p.end()
    return QIcon(pm)


class SuiteWindow(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setObjectName("suiteWin")
        self.setWindowTitle("Aufschluss Suite")
        self.setStyleSheet(ui.SUITE_QSS)
        self._resize_to(W_TREE + W_BTN + 2 * MARGIN + HANDLE)
        self._mods = {}          # key -> eingebettetes Modul-Widget
        self._active = None
        self._narrow = False
        self._maxed = False
        self._map_loaded = False
        self._maxer = ui.MaximizeOnDoubleClick(self, self._on_maximize)   # Doppelklick = Vollbild
        self._mapping = screens.HideWhileMapping(self)
        # einheitliche Höhe aller Felder/Buttons (Maß: Auswahlfeld „Projektart“), auch in Vorschaufenstern
        self.field_h = ui.field_height(self)
        self._windows = [self]
        self._hfilter = ui.install_heights(self._windows, self.field_h)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 8)
        outer.setSpacing(6)
        cols = QSplitter(Qt.Orientation.Horizontal)
        cols.setHandleWidth(HANDLE)
        cols.setChildrenCollapsible(False)
        self.cols = cols
        outer.addWidget(cols, 1)

        # links: Projekt
        self.card_tree = QFrame()
        self.card_tree.setObjectName("card")
        lt = QVBoxLayout(self.card_tree)
        lt.setContentsMargins(14, 12, 14, 12)
        self.panel = ProjectPanel(iface, self.card_tree)
        lt.addWidget(self.panel)
        self.card_tree.setMinimumWidth(200)
        cols.addWidget(self.card_tree)

        # Mitte: drei Buttons
        self.card_btn = QFrame()
        self.card_btn.setObjectName("card")
        lb = QVBoxLayout(self.card_btn)
        lb.setContentsMargins(12, 14, 12, 14)
        lb.setSpacing(12)
        self.card_btn.setMinimumWidth(130)
        self.btns = {}
        for key, label in MODULES:
            b = QPushButton(label)
            b.setObjectName("modBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.toggle_module(k))
            b.setMinimumHeight(64)
            lb.addWidget(b)
            self.btns[key] = b
        lb.addStretch(1)
        cols.addWidget(self.card_btn)

        # rechts: Modulspalte (zunächst zu)
        self.card_mod = QFrame()
        self.card_mod.setObjectName("card")
        lm = QVBoxLayout(self.card_mod)
        lm.setContentsMargins(10, 12, 6, 12)
        head = QHBoxLayout()
        self.lbl_mod = QLabel("")
        self.lbl_mod.setObjectName("cardTitle")
        head.addWidget(self.lbl_mod, 1)
        self.btn_collapse = QPushButton()
        self.btn_collapse.setObjectName("collapseBtn")
        self.btn_collapse.setIcon(collapse_icon())
        self.btn_collapse.setIconSize(QSize(26, 20))
        self.btn_collapse.setFixedSize(40, 30)
        self.btn_collapse.setToolTip("Einklappen")
        self.btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse.clicked.connect(self.collapse)
        head.addWidget(self.btn_collapse)
        lm.addLayout(head)
        self.body = QVBoxLayout()
        lm.addLayout(self.body, 1)
        self.card_mod.hide()
        cols.addWidget(self.card_mod)
        self._set_sizes(False)

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.lbl_ver = QLabel("v%s WANG" % VERSION)
        self.lbl_ver.setObjectName("footer")
        foot.addWidget(self.lbl_ver)
        outer.addLayout(foot)

    # ------------------------------------------------------------------ Spalte auf-/zuklappen
    def _on_maximize(self, maxi):
        """Doppelklick auf den Fensterhintergrund: maximiert (Spalten wachsen mit) / zurück zur festen Größe."""
        self._maxed = maxi
        if maxi:
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            QTimer.singleShot(0, lambda: self._set_sizes(self._active is not None and not self._narrow))
        else:
            QTimer.singleShot(0, self._restore_size)

    def _restore_size(self):
        full = self._active is not None and not self._narrow
        if full:
            self._resize_to(W_FULL, H_FULL)
        else:
            self._resize_to(W_TREE + W_BTN + 2 * MARGIN + HANDLE)
        self._set_sizes(full)

    def register_window(self, win):
        """Eigene Fenster der Module (Vorschau): gleiche Feldhöhe und Schriftstufen."""
        if not any(w is win for w in self._windows):
            self._windows.append(win)
            win.setStyleSheet(ui.WINDOW_QSS + "\n" + (win.styleSheet() or ""))
            if getattr(win, "_maxer", None) is None:
                win._maxer = ui.MaximizeOnDoubleClick(win)        # Vorschau: Doppelklick = maximieren

    def narrow_view(self, on):
        """Schmale Ansicht (nur Baum + Buttons), z. B. während auf der Karte gewählt wird.
        Das Modul bleibt offen und erscheint danach unverändert wieder."""
        self._narrow = bool(on)
        if on:
            self.card_mod.hide()
            self._resize_to(W_TREE + W_BTN + 2 * MARGIN + HANDLE)
            self._set_sizes(False)
        elif self._active is not None:
            self.card_mod.show()
            self._resize_to(W_FULL, H_FULL)
            self._set_sizes(True)

    def toggle_module(self, key):
        if self._active == key:
            self.collapse()
        else:
            self.open_module(key)

    def open_module(self, key):
        try:
            for k in list(self._mods):          # immer nur ein Modul: vorige schließen
                if k != key:
                    self._dispose(k)
            w = self._mods.get(key)
            if w is None:
                w = self._create(key)
                self._mods[key] = w
                self.body.addWidget(w)
            w.setVisible(True)
            self._active = key
            self.lbl_mod.setText(dict(MODULES)[key])
            self.card_mod.show()
            self._resize_to(W_FULL, H_FULL)
            self._set_sizes(True)
            for k, b in self.btns.items():
                b.setChecked(k == key)
            if hasattr(w, "on_expand"):
                w.on_expand()
        except Exception:  # noqa: BLE001
            err = traceback.format_exc()
            self._dispose(key)
            self.collapse()
            self._fail(dict(MODULES)[key], err)

    def collapse(self):
        """Modul zuklappen (Eingaben bleiben, bis ein anderes Modul geöffnet wird)."""
        self._active = None
        self.card_mod.hide()
        self._resize_to(W_TREE + W_BTN + 2 * MARGIN + HANDLE)
        self._set_sizes(False)
        for b in self.btns.values():
            b.setChecked(False)

    def _dispose(self, key):
        """Modul schließen und verwerfen. Schon Erzeugtes (Layer, Dateien) bleibt gespeichert."""
        w = self._mods.pop(key, None)
        if w is None:
            return
        d = getattr(w, "dialog", None)
        try:
            if key == "aufschluss" and d is not None:
                d.clear_canvas(all_items=True)
                if getattr(d, "imp", None) is not None:
                    d.imp.close()
            if d is not None:
                d.close()
        except Exception:  # noqa: BLE001
            pass
        self.body.removeWidget(w)
        w.hide()
        w.deleteLater()

    # ------------------------------------------------------------------ Größen
    def _resize_to(self, w, h=H_FULL):
        """Feste Fenstergröße (bei kleinem Bildschirm verkleinert); Position bleibt, nichts ragt hinaus."""
        if getattr(self, "_maxed", False):          # maximiert: Größe bleibt, nur die Spalten ändern sich
            return
        screens.fit_to_screen(self, w, h)
        if self.isVisible():
            g = (self.screen() or self.window().screen()).availableGeometry()
            x = min(self.x(), g.right() - self.width())
            self.move(max(g.left(), x), self.y())

    def _set_sizes(self, with_module):
        total = self.width() - 2 * MARGIN - (2 if with_module else 1) * HANDLE
        if with_module:
            rest = max(300, total - W_TREE - W_BTN)
            self.cols.setSizes([W_TREE, W_BTN, rest])
        else:
            self.cols.setSizes([max(200, total - W_BTN), W_BTN, 0])

    def _create(self, key):
        """Modul laden und als Widget einbetten (Rahmen/Scroll gehört zum Wirt)."""
        if key == "aufschluss":
            from .modules.aufschluss.dialog import MainDialog
            dlg = MainDialog(self.iface, None)
        elif key == "lageplan":
            from .modules.lageplan.dialog import LageplanDialog
            dlg = LageplanDialog(self.iface, None)
        else:
            from .modules.blaue_mappe.dialog import DeckblattDialog
            dlg = DeckblattDialog(self.iface, None)
        dlg.suite = self
        ui.embed(dlg)
        sa = ui.wrap_scroll(dlg)
        sa.setParent(self.card_mod)          # erst im Fenster: Schriftstufen gelten beim Anpassen
        ui.tune(dlg, height=self.field_h)
        for win in getattr(dlg, "own_windows", lambda: [])():
            self.register_window(win)
        sa.dialog = dlg
        sa.on_expand = getattr(dlg, "on_expand", None)
        return sa

    # ------------------------------------------------------------------ Karte wählen (Fenster ausblenden)
    def hide_for_map(self):
        self._mapping.hide()

    def show_after_map(self):
        self._mapping.show()

    # ------------------------------------------------------------------ Öffnen
    def present(self):
        """Beim Öffnen: mit zweitem Bildschirm dort platzieren, sonst unverändert."""
        if not self.isVisible():
            screens.place_on_second_screen(self, self.iface.mainWindow())
        self.show()
        self.raise_()
        self.activateWindow()
        if not self._map_loaded:             # Projekt ohne Karte: zuletzt gewählte Karte laden
            self._map_loaded = True
            QTimer.singleShot(0, self.panel.auto_load_map)

    def _fail(self, name, err=None):
        QMessageBox.critical(self, name, "%s konnte nicht geöffnet werden:\n\n%s" % (
            name, (err or traceback.format_exc())[-1500:]))

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            QTimer.singleShot(0, selection.notify)

    def module_dialog(self, key):
        w = self._mods.get(key)
        return getattr(w, "dialog", None)

    # ------------------------------------------------------------------ Aufräumen
    def shutdown(self):
        for key in list(self._mods):
            d = self.module_dialog(key)
            try:
                if key == "aufschluss" and d is not None:
                    d.clear_canvas(all_items=True)
                    if getattr(d, "imp", None) is not None:
                        d.imp.close()
                if d is not None:
                    d.close()
            except Exception:  # noqa: BLE001
                pass
        self._mods.clear()
        try:
            self.panel.disconnect_all()
        except Exception:  # noqa: BLE001
            pass
        ui.remove_heights(self._hfilter)
        self._hfilter = None
        self.close()
