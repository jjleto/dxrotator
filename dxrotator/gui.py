"""
gui.py - Interfaccia grafica PySide6 di DXRotator.
"""

from __future__ import annotations

import time
from typing import List, Optional

from PySide6.QtCore import QByteArray, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                               QPushButton, QSpinBox, QSplitter, QTabWidget,
                               QVBoxLayout, QWidget)

from .bands import BAND_NAMES, DIRECTIVE_BANDS, band_for_frequency
from .compass import CompassWidget
from .config import AppConfig, config_path
from .dxcc import CTY_DOWNLOAD_URL, DxccResolver
from .engine import RotatorEngine, Solution
from .geo import (angular_difference, compass_point, is_valid_locator,
                  latlon_to_locator, normalize_deg)
from .rotor import (Dcu1Controller, RotorConfig, SimulatedTransport,
                    available_ports, blind_sector, HAVE_SERIAL)
from .sources import DxTarget, N1mmDecoder, UdpListener, WsjtxDecoder

from . import __version__

APP_TITLE = f"DXRotator {__version__} — controllo Hy-Gain TX2 via DCU-1"

# secondi di "tregua" dopo l'ultima digitazione dell'utente nei campi Call/Grid
# prima che le sorgenti esterne tornino ad aggiornarli
MANUAL_EDIT_GRACE = 10.0

DARK_QSS = """
QWidget { background-color: #14171c; color: #dde3ec; font-size: 13px; }
QGroupBox { border: 1px solid #2c333d; border-radius: 8px; margin-top: 10px;
            padding-top: 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px;
                   color: #93a2b6; }
QPushButton { background-color: #212832; border: 1px solid #333c48;
              border-radius: 6px; padding: 7px 12px; }
QPushButton:hover { background-color: #2b3542; }
QPushButton:pressed { background-color: #1a212a; }
QPushButton:disabled { color: #5c6675; border-color: #262c35; }
QPushButton#go { background-color: #1e6f3f; border-color: #2a8a52; font-weight: 700; }
QPushButton#go:hover { background-color: #248249; }
QPushButton#stop { background-color: #7d2626; border-color: #a13030; font-weight: 700; }
QPushButton#stop:hover { background-color: #983030; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {
    background-color: #1b212a; border: 1px solid #2f3846; border-radius: 6px;
    padding: 5px; selection-background-color: #2a6f4a; }
QLabel#big { font-size: 30px; font-weight: 700; color: #6fd39a; }
QLabel#sub { color: #93a2b6; }
QLabel#warn { color: #e0a33c; }
QCheckBox::indicator { width: 15px; height: 15px; }
QPlainTextEdit { font-family: "Menlo","DejaVu Sans Mono","Consolas",monospace;
                 font-size: 11px; }
QTabBar::tab { background: #1b212a; padding: 7px 14px; border: 1px solid #2f3846;
               border-bottom: none; border-top-left-radius: 6px;
               border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #263040; }
"""

# scostamenti applicati alla sola finestra principale in modalita' compatta
COMPACT_QSS = """
QWidget { font-size: 11px; }
QGroupBox { margin-top: 7px; padding-top: 7px; }
QPushButton { padding: 3px 7px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { padding: 2px; }
QLabel#big { font-size: 21px; }
"""


# ==========================================================================
# Ponte thread UDP -> thread GUI
# ==========================================================================

class UdpBridge(QObject):
    """
    Ponte fra i thread di servizio (listener UDP, polling e sequenza di stop
    del rotore) e il thread dell'interfaccia. I widget Qt possono essere
    toccati solo dal thread della GUI: i segnali garantiscono la consegna
    nella coda giusta.
    """
    target = Signal(object)
    error = Signal(str)
    message = Signal(str)


# ==========================================================================
# Dialogo impostazioni
# ==========================================================================

class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Impostazioni")
        self.setMinimumWidth(520)

        tabs = QTabWidget()
        tabs.addTab(self._tab_station(), "Stazione")
        tabs.addTab(self._tab_rotor(), "Rotore / DCU-1")
        tabs.addTab(self._tab_udp(), "WSJT-X / N1MM")
        tabs.addTab(self._tab_auto(), "Automatismo")
        tabs.addTab(self._tab_bands(), "Bande")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        hint = QLabel(f"File di configurazione: {config_path()}")
        hint.setObjectName("sub")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addWidget(buttons)

    # -- schede -----------------------------------------------------------
    def _tab_station(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.e_call = QLineEdit(self.cfg.my_call)
        self.e_loc = QLineEdit(self.cfg.my_locator)
        self.e_loc.setPlaceholderText("es. JN61fu")
        self.c_latlon = QCheckBox("Usa latitudine/longitudine invece del locatore")
        self.c_latlon.setChecked(self.cfg.use_latlon)
        self.s_lat = QDoubleSpinBox(); self.s_lat.setRange(-90, 90)
        self.s_lat.setDecimals(5); self.s_lat.setValue(self.cfg.my_lat)
        self.s_lon = QDoubleSpinBox(); self.s_lon.setRange(-180, 180)
        self.s_lon.setDecimals(5); self.s_lon.setValue(self.cfg.my_lon)

        self.e_cty = QLineEdit(self.cfg.cty_path)
        self.e_cty.setPlaceholderText("(opzionale) percorso di cty.dat")
        b_cty = QPushButton("Sfoglia…")
        b_cty.clicked.connect(self._pick_cty)
        row = QHBoxLayout(); row.addWidget(self.e_cty); row.addWidget(b_cty)
        rw = QWidget(); rw.setLayout(row)

        f.addRow("Nominativo:", self.e_call)
        f.addRow("Locatore:", self.e_loc)
        f.addRow("", self.c_latlon)
        f.addRow("Latitudine (N+):", self.s_lat)
        f.addRow("Longitudine (E+):", self.s_lon)
        f.addRow("cty.dat:", rw)
        note = QLabel(f"Scarica cty.dat da {CTY_DOWNLOAD_URL} per avere tutti "
                      "i prefissi DXCC aggiornati. Senza cty.dat viene usata "
                      "la tabella interna.")
        note.setObjectName("sub"); note.setWordWrap(True)
        f.addRow("", note)
        return w

    def _pick_cty(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Seleziona cty.dat", "",
                                              "cty.dat (*.dat);;Tutti i file (*)")
        if path:
            self.e_cty.setText(path)

    def _tab_rotor(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.cb_port = QComboBox()
        self.cb_port.setEditable(True)
        ports = available_ports()
        self.cb_port.addItem("")            # vuoto = simulatore
        for p in ports:
            self.cb_port.addItem(p)
        self.cb_port.setCurrentText(self.cfg.serial_port)

        b_scan = QPushButton("Rileva")
        b_scan.clicked.connect(self._rescan)
        row = QHBoxLayout(); row.addWidget(self.cb_port); row.addWidget(b_scan)
        rw = QWidget(); rw.setLayout(row)

        self.cb_baud = QComboBox()
        for b in (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200):
            self.cb_baud.addItem(str(b))
        self.cb_baud.setCurrentText(str(self.cfg.baudrate))

        self.e_term = QLineEdit(self.cfg.terminator)
        self.e_stop = QLineEdit(self.cfg.stop_command)
        self.cb_stopmode = QComboBox()
        self._stop_modes = [
            ("command", "1 · Solo il comando di stop (protocollo)"),
            ("target_only", "2 · Sposta il set point, senza AM1 (delicato)"),
            ("goto_current", "3 · Set point + AM1 (ripiego)"),
            ("both", "4 · Comando di stop, poi set point + AM1"),
        ]
        for _k, label in self._stop_modes:
            self.cb_stopmode.addItem(label)
        keys = [k for k, _ in self._stop_modes]
        if self.cfg.stop_strategy in keys:
            self.cb_stopmode.setCurrentIndex(keys.index(self.cfg.stop_strategy))
        self.c_combined = QCheckBox("Invia \"AP1xxx;AM1;\" in un unico messaggio")
        self.c_combined.setChecked(self.cfg.send_move_with_target)
        self.s_gap = QDoubleSpinBox(); self.s_gap.setRange(0.0, 2.0)
        self.s_gap.setDecimals(2); self.s_gap.setSingleStep(0.05)
        self.s_gap.setValue(self.cfg.command_gap)
        self.s_gap.setToolTip("Pausa fra AP1 e AM1 quando sono separati. "
                              "Se il rotore parte solo al secondo comando, "
                              "aumentala.")

        self.s_start = QDoubleSpinBox(); self.s_start.setRange(0, 359)
        self.s_start.setValue(self.cfg.rotor_range_start)
        self.s_span = QDoubleSpinBox(); self.s_span.setRange(180, 540)
        self.s_span.setValue(self.cfg.rotor_range_span)
        self.s_off = QDoubleSpinBox(); self.s_off.setRange(-180, 180)
        self.s_off.setValue(self.cfg.rotor_offset)
        self.s_speed = QDoubleSpinBox(); self.s_speed.setRange(0.1, 60)
        self.s_speed.setDecimals(2); self.s_speed.setValue(self.cfg.rotor_speed)
        self.s_minmove = QDoubleSpinBox(); self.s_minmove.setRange(0, 45)
        self.s_minmove.setValue(self.cfg.rotor_min_move)
        self.s_margin = QDoubleSpinBox(); self.s_margin.setRange(0, 90)
        self.s_margin.setDecimals(0)
        self.s_margin.setValue(self.cfg.rotor_safety_margin)
        self.c_autoconn = QCheckBox("Connetti automaticamente all'avvio")
        self.c_autoconn.setChecked(self.cfg.auto_connect)

        self.c_read = QCheckBox("Leggi la posizione dal controller (AI1;) — "
                                "solo Rotor-EZ / Green Heron, NON il DCU-1")
        self.c_read.setChecked(self.cfg.rotor_read_position)
        self.s_poll = QDoubleSpinBox(); self.s_poll.setRange(0.2, 10.0)
        self.s_poll.setDecimals(1); self.s_poll.setSingleStep(0.5)
        self.s_poll.setValue(self.cfg.rotor_poll_interval)
        self.c_stopmargin = QCheckBox("Arresta il rotore se la posizione letta "
                                      "entra nel margine di sicurezza")
        self.c_stopmargin.setChecked(self.cfg.rotor_stop_on_margin)

        f.addRow("Porta seriale:", rw)
        f.addRow("Baud rate:", self.cb_baud)
        f.addRow("Terminatore:", self.e_term)
        f.addRow("Comando di stop:", self.e_stop)
        f.addRow("Modo di arresto:", self.cb_stopmode)
        self.s_streps = QSpinBox(); self.s_streps.setRange(1, 10)
        self.s_streps.setValue(self.cfg.stop_repeat)
        self.s_stgap = QDoubleSpinBox(); self.s_stgap.setRange(0.05, 3.0)
        self.s_stgap.setDecimals(2); self.s_stgap.setSingleStep(0.1)
        self.s_stgap.setValue(self.cfg.stop_repeat_gap)
        f.addRow("  tentativi di arresto:", self.s_streps)
        f.addRow("  pausa fra i tentativi (s):", self.s_stgap)
        f.addRow("", self.c_combined)
        f.addRow("Pausa fra AP1 e AM1 (s):", self.s_gap)
        f.addRow("Fermo meccanico (°):", self.s_start)
        f.addRow("Escursione (°):", self.s_span)
        f.addRow("Margine dal fermo (°):", self.s_margin)
        f.addRow("Offset di taratura (°):", self.s_off)
        f.addRow("Velocità (°/s):", self.s_speed)
        f.addRow("Movimento minimo (°):", self.s_minmove)
        f.addRow("", self.c_autoconn)
        f.addRow(QLabel(""))
        f.addRow(self.c_read)
        f.addRow("  intervallo lettura (s):", self.s_poll)
        f.addRow("", self.c_stopmargin)
        note = QLabel(
            "Porta vuota = modalità simulatore (nessun hardware).\n"
            "Fermo meccanico = azimut VERO del finecorsa, misurato con la "
            "bussola ad antenna appoggiata alla battuta (180° = rotore "
            "\"Nord centrato\" standard Hy-Gain).\n"
            "Margine dal fermo = gradi lasciati liberi a ogni estremo: i "
            "comandi che ci cadono dentro vengono limitati al bordo invece di "
            "mandare l'antenna in battuta.\n"
            "Escursione 450° per rotori con overlap."
            + ("" if HAVE_SERIAL else
               "\n\nATTENZIONE: pyserial non è installato, disponibile solo il simulatore."))
        note.setObjectName("sub"); note.setWordWrap(True)
        f.addRow("", note)
        return w

    def _rescan(self) -> None:
        cur = self.cb_port.currentText()
        self.cb_port.clear()
        self.cb_port.addItem("")
        for p in available_ports():
            self.cb_port.addItem(p)
        self.cb_port.setCurrentText(cur)

    def _tab_udp(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.c_wsjt = QCheckBox("Ascolta WSJT-X")
        self.c_wsjt.setChecked(self.cfg.wsjtx_enabled)
        self.e_wsjt_host = QLineEdit(self.cfg.wsjtx_host)
        self.s_wsjt_port = QSpinBox(); self.s_wsjt_port.setRange(1, 65535)
        self.s_wsjt_port.setValue(self.cfg.wsjtx_port)

        self.c_n1mm = QCheckBox("Ascolta N1MM+ (contatti e spot)")
        self.c_n1mm.setChecked(self.cfg.n1mm_enabled)
        self.e_n1mm_host = QLineEdit(self.cfg.n1mm_host)
        self.s_n1mm_port = QSpinBox(); self.s_n1mm_port.setRange(1, 65535)
        self.s_n1mm_port.setValue(self.cfg.n1mm_port)

        self.c_rot = QCheckBox("Ascolta il broadcast rotore di N1MM+")
        self.c_rot.setChecked(self.cfg.n1mm_rotor_enabled)
        self.e_rot_host = QLineEdit(self.cfg.n1mm_rotor_host)
        self.s_rot_port = QSpinBox(); self.s_rot_port.setRange(1, 65535)
        self.s_rot_port.setValue(self.cfg.n1mm_rotor_port)

        f.addRow(self.c_wsjt)
        f.addRow("  indirizzo:", self.e_wsjt_host)
        f.addRow("  porta:", self.s_wsjt_port)
        f.addRow(QLabel(""))
        f.addRow(self.c_n1mm)
        f.addRow("  indirizzo:", self.e_n1mm_host)
        f.addRow("  porta:", self.s_n1mm_port)
        f.addRow(QLabel(""))
        f.addRow(self.c_rot)
        f.addRow("  indirizzo:", self.e_rot_host)
        f.addRow("  porta:", self.s_rot_port)
        note = QLabel(
            "WSJT-X: File > Impostazioni > Reporting > UDP Server = questo PC, "
            "porta 2237.\n"
            "N1MM+: Config > Configure Ports > Broadcast Data: spunta Contacts "
            "e Spots verso 127.0.0.1:12060, e Rotor verso 127.0.0.1:12040.\n"
            "Per indirizzi multicast (224.x.x.x) l'app si iscrive al gruppo "
            "automaticamente.")
        note.setObjectName("sub"); note.setWordWrap(True)
        f.addRow("", note)
        return w

    def _tab_auto(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.s_thr = QDoubleSpinBox(); self.s_thr.setRange(0, 180)
        self.s_thr.setValue(self.cfg.auto_threshold)
        self.s_hold = QDoubleSpinBox(); self.s_hold.setRange(0, 120)
        self.s_hold.setValue(self.cfg.auto_hold_seconds)

        self.c_src_status = QCheckBox("WSJT-X — stazione DX selezionata (Status)")
        self.c_src_status.setChecked(self.cfg.auto_sources.get("wsjtx_status", True))
        self.c_src_decode = QCheckBox("WSJT-X — ogni decodifica (sconsigliato)")
        self.c_src_decode.setChecked(self.cfg.auto_sources.get("wsjtx_decode", False))
        self.c_src_qso = QCheckBox("WSJT-X — QSO registrato")
        self.c_src_qso.setChecked(self.cfg.auto_sources.get("wsjtx_qso", False))
        self.c_src_n1mm = QCheckBox("N1MM+ — contatti, spot e broadcast rotore")
        self.c_src_n1mm.setChecked(self.cfg.auto_sources.get("n1mm", True))

        self.c_logdec = QCheckBox("Scrivi anche le decodifiche nel registro "
                                  "(molto verboso)")
        self.c_logdec.setChecked(self.cfg.log_decodes)

        f.addRow("Soglia di rotazione (°):", self.s_thr)
        f.addRow("Attesa fra comandi (s):", self.s_hold)
        f.addRow(QLabel("Sorgenti abilitate all'automatismo:"))
        f.addRow(self.c_src_status)
        f.addRow(self.c_src_decode)
        f.addRow(self.c_src_qso)
        f.addRow(self.c_src_n1mm)
        f.addRow(QLabel(""))
        f.addRow(self.c_logdec)
        note2 = QLabel("Le sorgenti non spuntate qui sopra vengono ignorate "
                       "del tutto: non muovono il rotore e non cambiano il "
                       "puntamento mostrato.")
        note2.setObjectName("sub"); note2.setWordWrap(True)
        f.addRow("", note2)
        note = QLabel("In automatico il comando viene inviato solo se la "
                      "differenza fra la posizione del rotore e l'azimut della "
                      "stazione DX supera la soglia impostata.")
        note.setObjectName("sub"); note.setWordWrap(True)
        f.addRow("", note)
        return w

    def _tab_bands(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        intro = QLabel(
            "Spunta solo le bande la cui antenna è <b>fisicamente sul "
            "rotatore</b>. Sulle bande non spuntate DXRotator resta immobile: "
            "utile se hai una direttiva sul rotatore e una verticale o un "
            "dipolo fissi per le altre bande.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        grid = QGridLayout()
        self._band_boxes = {}
        for i, name in enumerate(BAND_NAMES):
            box = QCheckBox(name)
            box.setChecked(bool(self.cfg.enabled_bands.get(name, True)))
            self._band_boxes[name] = box
            grid.addWidget(box, i // 4, i % 4)
        lay.addLayout(grid)

        row = QHBoxLayout()
        b_all = QPushButton("Tutte")
        b_all.clicked.connect(lambda: self._set_bands(BAND_NAMES))
        b_none = QPushButton("Nessuna")
        b_none.clicked.connect(lambda: self._set_bands([]))
        b_dir = QPushButton("Solo direttiva (20-17-15-12-10-6)")
        b_dir.clicked.connect(lambda: self._set_bands(DIRECTIVE_BANDS))
        row.addWidget(b_all); row.addWidget(b_none); row.addWidget(b_dir)
        row.addStretch(1)
        lay.addLayout(row)

        note = QLabel(
            "La banda viene ricavata dalla frequenza che WSJT-X e N1MM+ "
            "trasmettono insieme ai dati della stazione. Se la frequenza "
            "manca, il target viene ammesso: il comando manuale e il click "
            "sul quadrante funzionano sempre, su qualsiasi banda.")
        note.setObjectName("sub"); note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        return w

    def _set_bands(self, names) -> None:
        wanted = set(names)
        for name, box in self._band_boxes.items():
            box.setChecked(name in wanted)

    # -- salvataggio ------------------------------------------------------
    def apply_to(self, cfg: AppConfig) -> None:
        cfg.my_call = self.e_call.text().strip().upper()
        cfg.my_locator = self.e_loc.text().strip()
        cfg.use_latlon = self.c_latlon.isChecked()
        cfg.my_lat = self.s_lat.value()
        cfg.my_lon = self.s_lon.value()
        cfg.cty_path = self.e_cty.text().strip()

        cfg.serial_port = self.cb_port.currentText().strip()
        cfg.baudrate = int(self.cb_baud.currentText())
        cfg.terminator = self.e_term.text() or ";"
        cfg.stop_command = self.e_stop.text() or ";"
        cfg.stop_strategy = self._stop_modes[self.cb_stopmode.currentIndex()][0]
        cfg.stop_repeat = self.s_streps.value()
        cfg.stop_repeat_gap = self.s_stgap.value()
        cfg.send_move_with_target = self.c_combined.isChecked()
        cfg.command_gap = self.s_gap.value()
        cfg.rotor_range_start = self.s_start.value()
        cfg.rotor_range_span = self.s_span.value()
        cfg.rotor_offset = self.s_off.value()
        cfg.rotor_speed = self.s_speed.value()
        cfg.rotor_min_move = self.s_minmove.value()
        cfg.rotor_safety_margin = self.s_margin.value()
        cfg.rotor_read_position = self.c_read.isChecked()
        cfg.rotor_poll_interval = self.s_poll.value()
        cfg.rotor_stop_on_margin = self.c_stopmargin.isChecked()
        cfg.auto_connect = self.c_autoconn.isChecked()

        cfg.wsjtx_enabled = self.c_wsjt.isChecked()
        cfg.wsjtx_host = self.e_wsjt_host.text().strip() or "0.0.0.0"
        cfg.wsjtx_port = self.s_wsjt_port.value()
        cfg.n1mm_enabled = self.c_n1mm.isChecked()
        cfg.n1mm_host = self.e_n1mm_host.text().strip() or "0.0.0.0"
        cfg.n1mm_port = self.s_n1mm_port.value()
        cfg.n1mm_rotor_enabled = self.c_rot.isChecked()
        cfg.n1mm_rotor_host = self.e_rot_host.text().strip() or "0.0.0.0"
        cfg.n1mm_rotor_port = self.s_rot_port.value()

        cfg.auto_threshold = self.s_thr.value()
        cfg.auto_hold_seconds = self.s_hold.value()
        cfg.auto_sources = {
            "wsjtx_status": self.c_src_status.isChecked(),
            "wsjtx_decode": self.c_src_decode.isChecked(),
            "wsjtx_qso": self.c_src_qso.isChecked(),
            "n1mm": self.c_src_n1mm.isChecked(),
        }
        cfg.log_decodes = self.c_logdec.isChecked()
        cfg.enabled_bands = {name: box.isChecked()
                             for name, box in self._band_boxes.items()}


# ==========================================================================
# Finestra principale
# ==========================================================================

class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle(APP_TITLE)

        self._warned_disconnected = 0.0
        self._last_manual_edit = 0.0
        self._last_rx_key = ""
        self._last_band_block: object = None
        self._pending_log: List[str] = []

        # il ponte va creato prima del motore: _apply_rotor_config lo usa
        self.bridge = UdpBridge()
        self.bridge.target.connect(self._on_target)
        self.bridge.error.connect(lambda m: self._log(m, "!"))
        self.bridge.message.connect(lambda m: self._log(m))
        self.listeners: List[UdpListener] = []

        self.engine = RotatorEngine(cfg)
        self._apply_rotor_config()

        self._build_ui()
        self._build_menu()
        self._apply_view()
        self._restore_geometry()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(120)

        self._log(f"DXRotator {__version__} avviato — DXCC: "
                  f"{self.engine.resolver.source} — fermo meccanico "
                  f"{self.cfg.rotor_range_start:.0f}°")
        self.start_listeners()
        if cfg.auto_connect:
            self.connect_rotor()

    # ------------------------------------------------------------------
    # costruzione interfaccia
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        # --- colonna sinistra: bussola -------------------------------
        left = QVBoxLayout()
        self.compass = CompassWidget()
        self.compass.bearingClicked.connect(self._on_compass_click)
        left.addWidget(self.compass, 1)

        cal = QHBoxLayout()
        self.lbl_calib = QLabel("Posizione reale del rotore:")
        cal.addWidget(self.lbl_calib)
        self.s_calib = QDoubleSpinBox()
        self.s_calib.setRange(0, 359.9); self.s_calib.setSuffix(" °")
        self.s_calib.setDecimals(0); self.s_calib.setSingleStep(1)
        cal.addWidget(self.s_calib)
        b_cal = QPushButton("Ricalibra")
        b_cal.setToolTip("Allinea la posizione stimata a quella indicata dal "
                         "quadrante del controller (non muove il rotore)")
        b_cal.clicked.connect(self._recalibrate)
        cal.addWidget(b_cal)
        self.b_test = QPushButton("Prova lettura posizione")
        self.b_test.setToolTip("Invia AI1; e mostra cosa risponde il controller")
        self.b_test.clicked.connect(self._test_readback)
        cal.addWidget(self.b_test)
        cal.addStretch(1)
        left.addLayout(cal)

        self.compass_panel = QWidget()
        self.compass_panel.setLayout(left)

        # --- colonna destra: comandi ---------------------------------
        right = QVBoxLayout()
        right.setSpacing(10)
        self.right_layout = right

        right.addWidget(self._grp_dx())
        right.addWidget(self._grp_manual())
        right.addWidget(self._grp_auto())

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(800)
        self.log.setMinimumHeight(60)
        self.log_panel = QGroupBox("Registro")
        glv = QVBoxLayout(self.log_panel); glv.addWidget(self.log)
        right.addWidget(self.log_panel, 1)

        rw = QWidget(); rw.setLayout(right)

        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(self.compass_panel)
        self.split.addWidget(rw)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 4)
        self.split.setChildrenCollapsible(True)
        root.addWidget(self.split)

        self.status = self.statusBar()
        self.lbl_conn = QLabel("rotore: non connesso")
        self.lbl_udp = QLabel("UDP: —")
        self.status.addPermanentWidget(self.lbl_udp)
        self.status.addPermanentWidget(self.lbl_conn)

    def _grp_dx(self) -> QGroupBox:
        g = QGroupBox("Stazione DX")
        lay = QGridLayout(g)

        self.e_dxcall = QLineEdit()
        self.e_dxcall.setPlaceholderText("nominativo (es. VK3ABC)")
        self.e_dxcall.returnPressed.connect(self._compute_manual)
        self.e_dxgrid = QLineEdit()
        self.e_dxgrid.setPlaceholderText("locatore (es. QF22)")
        self.e_dxgrid.returnPressed.connect(self._compute_manual)
        # minimi bassi: i campi devono poter stringere con la finestra
        for w in (self.e_dxcall, self.e_dxgrid):
            w.setMinimumWidth(72)
        # textEdited scatta solo per le modifiche fatte a mano, non per setText
        for w in (self.e_dxcall, self.e_dxgrid):
            w.textEdited.connect(self._note_manual_edit)

        b_calc = QPushButton("Calcola")
        b_calc.clicked.connect(self._compute_manual)
        self.b_go = QPushButton("RUOTA")
        self.b_go.setObjectName("go")
        self.b_go.setToolTip("Invia AP1xxx; + AM1; verso l'azimut calcolato")
        self.b_go.clicked.connect(self._go_to_solution)

        lay.addWidget(QLabel("Call:"), 0, 0)
        lay.addWidget(self.e_dxcall, 0, 1)
        lay.addWidget(QLabel("Grid:"), 0, 2)
        lay.addWidget(self.e_dxgrid, 0, 3)
        lay.addWidget(b_calc, 0, 4)

        self.lbl_az = QLabel("---°")
        self.lbl_az.setObjectName("big")
        self.lbl_info = QLabel("nessuna stazione")
        self.lbl_info.setObjectName("sub")
        self.lbl_info.setWordWrap(True)
        self.lbl_delta = QLabel("")
        self.lbl_delta.setObjectName("sub")
        self.lbl_delta.setWordWrap(True)

        lay.addWidget(self.lbl_az, 1, 0, 1, 2)
        lay.addWidget(self.lbl_delta, 1, 2, 1, 3)
        lay.addWidget(self.lbl_info, 2, 0, 1, 4)
        lay.addWidget(self.b_go, 2, 4)

        self.c_lp = QCheckBox("Percorso lungo (long path)")
        self.c_lp.setChecked(self.cfg.long_path)
        self.c_lp.toggled.connect(self._toggle_lp)
        lay.addWidget(self.c_lp, 3, 0, 1, 5)
        return g

    def _grp_manual(self) -> QGroupBox:
        g = QGroupBox("Comando manuale")
        lay = QGridLayout(g)

        self.s_manual = QDoubleSpinBox()
        self.s_manual.setRange(0, 359.9)
        self.s_manual.setSuffix(" °")
        self.s_manual.setDecimals(0)
        self.s_manual.setSingleStep(1)
        b_send = QPushButton("Vai")
        b_send.clicked.connect(lambda: self._rotate(self.s_manual.value(), "manuale"))
        self.b_stop = QPushButton("STOP")
        self.b_stop.setObjectName("stop")
        self.b_stop.setToolTip("Arresto immediato (Esc)")
        self.b_stop.clicked.connect(self._stop)

        lay.addWidget(QLabel("Azimut:"), 0, 0)
        lay.addWidget(self.s_manual, 0, 1)
        lay.addWidget(b_send, 0, 2)
        lay.addWidget(self.b_stop, 0, 3)

        prow = QHBoxLayout()
        prow.setContentsMargins(0, 0, 0, 0)
        for name, az in self.cfg.presets.items():
            b = QPushButton(f"{name}\n{az:.0f}°")
            b.setMinimumHeight(38)
            b.setMinimumWidth(40)
            b.clicked.connect(lambda _=False, a=az, n=name: self._rotate(a, f"preset {n}"))
            prow.addWidget(b)
        self.presets_widget = QWidget()
        self.presets_widget.setLayout(prow)
        lay.addWidget(self.presets_widget, 1, 0, 1, 4)
        return g

    def _grp_auto(self) -> QGroupBox:
        g = QGroupBox("Rotazione automatica")
        lay = QGridLayout(g)

        self.c_auto = QCheckBox("Attiva auto-rotazione")
        self.c_auto.setChecked(self.cfg.auto_rotate)
        self.c_auto.toggled.connect(self._toggle_auto)

        self.s_thr = QDoubleSpinBox()
        self.s_thr.setRange(0, 180)
        self.s_thr.setSuffix(" °")
        self.s_thr.setDecimals(0)
        self.s_thr.setSingleStep(5)
        self.s_thr.setValue(self.cfg.auto_threshold)
        self.s_thr.valueChanged.connect(self._change_threshold)

        self.lbl_auto = QLabel("in attesa di dati")
        self.lbl_auto.setObjectName("sub")
        self.lbl_auto.setWordWrap(True)

        self.lbl_thr = QLabel("Ruota solo se la differenza supera:")
        self.lbl_thr.setWordWrap(True)
        lay.addWidget(self.c_auto, 0, 0, 1, 2)
        lay.addWidget(self.lbl_thr, 1, 0)
        lay.addWidget(self.s_thr, 1, 1)
        lay.addWidget(self.lbl_auto, 2, 0, 1, 2)
        return g

    def _build_menu(self) -> None:
        m = self.menuBar()

        mf = m.addMenu("&File")
        a_set = QAction("Impostazioni…", self)
        a_set.setShortcut(QKeySequence("Ctrl+,"))
        a_set.triggered.connect(self.open_settings)
        mf.addAction(a_set)
        a_save = QAction("Salva configurazione", self)
        a_save.triggered.connect(self.save_config)
        mf.addAction(a_save)
        mf.addSeparator()
        a_quit = QAction("Esci", self)
        a_quit.setShortcut(QKeySequence.Quit)
        a_quit.triggered.connect(self.close)
        mf.addAction(a_quit)

        mr = m.addMenu("&Rotore")
        self.a_conn = QAction("Connetti", self)
        self.a_conn.triggered.connect(self.toggle_connection)
        mr.addAction(self.a_conn)
        a_stop = QAction("STOP", self)
        a_stop.setShortcut(QKeySequence(Qt.Key_Escape))
        a_stop.triggered.connect(self._stop)
        mr.addAction(a_stop)

        a_raw = QAction("Invia comando grezzo…", self)
        a_raw.triggered.connect(self._raw_console)
        mr.addAction(a_raw)

        mv = m.addMenu("&Visualizza")
        self.a_compact = QAction("Finestra compatta", self, checkable=True)
        self.a_compact.setShortcut(QKeySequence("Ctrl+K"))
        self.a_compact.setChecked(self.cfg.compact_mode)
        self.a_compact.toggled.connect(self._set_compact)
        mv.addAction(self.a_compact)

        self.a_showcompass = QAction("Mostra quadrante", self, checkable=True)
        self.a_showcompass.setChecked(self.cfg.show_compass)
        self.a_showcompass.toggled.connect(self._set_show_compass)
        mv.addAction(self.a_showcompass)

        self.a_showlog = QAction("Mostra registro", self, checkable=True)
        self.a_showlog.setChecked(self.cfg.show_log)
        self.a_showlog.toggled.connect(self._set_show_log)
        mv.addAction(self.a_showlog)

        mv.addSeparator()
        self.a_ontop = QAction("Sempre in primo piano", self, checkable=True)
        self.a_ontop.setChecked(self.cfg.always_on_top)
        self.a_ontop.toggled.connect(self._set_on_top)
        mv.addAction(self.a_ontop)

        mv.addSeparator()
        a_shrink = QAction("Riduci al minimo", self)
        a_shrink.setShortcut(QKeySequence("Ctrl+M"))
        a_shrink.triggered.connect(self._shrink_to_minimum)
        mv.addAction(a_shrink)

        mu = m.addMenu("&Sorgenti")
        a_restart = QAction("Riavvia ascolto UDP", self)
        a_restart.triggered.connect(self.start_listeners)
        mu.addAction(a_restart)

        mh = m.addMenu("&?")
        a_about = QAction("Informazioni", self)
        a_about.triggered.connect(self._about)
        mh.addAction(a_about)

    # ------------------------------------------------------------------
    # aspetto della finestra
    # ------------------------------------------------------------------
    def _set_compact(self, on: bool) -> None:
        self.cfg.compact_mode = on
        self._apply_view()

    def _set_show_log(self, on: bool) -> None:
        self.cfg.show_log = on
        self._apply_view()

    def _set_show_compass(self, on: bool) -> None:
        self.cfg.show_compass = on
        self._apply_view()

    def _set_on_top(self, on: bool) -> None:
        self.cfg.always_on_top = on
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()          # su alcuni sistemi il flag richiede un re-show

    def _apply_view(self) -> None:
        """Applica modalità compatta e visibilità dei pannelli."""
        compact = self.cfg.compact_mode

        self.log_panel.setVisible(self.cfg.show_log and not compact)
        self.compass_panel.setVisible(self.cfg.show_compass)

        # in compatto spariscono le cose che si usano di rado e che allargano
        self.presets_widget.setVisible(not compact)
        self.b_test.setVisible(not compact)
        self.lbl_calib.setText("Posizione:" if compact
                               else "Posizione reale del rotore:")
        self.lbl_thr.setText("Soglia:" if compact
                             else "Ruota solo se la differenza supera:")
        self.lbl_info.setVisible(not compact)
        self.c_lp.setVisible(not compact)
        for w in (self.e_dxcall, self.e_dxgrid):
            w.setMinimumWidth(56 if compact else 72)

        self.setStyleSheet(COMPACT_QSS if compact else "")
        margin = 4 if compact else 10
        lay = self.centralWidget().layout()
        if lay is not None:
            lay.setContentsMargins(margin, margin, margin, margin)
            lay.setSpacing(4 if compact else 12)
        self.right_layout.setSpacing(4 if compact else 10)
        self.statusBar().setVisible(not compact)

        self.a_compact.setChecked(compact)
        self.a_showlog.setChecked(self.cfg.show_log)
        self.a_showcompass.setChecked(self.cfg.show_compass)

    def _shrink_to_minimum(self) -> None:
        """Rimpicciolisce la finestra fino al minimo consentito dal contenuto."""
        self.centralWidget().layout().activate()
        self.resize(self.minimumSizeHint())

    # ------------------------------------------------------------------
    # configurazione
    # ------------------------------------------------------------------
    def _apply_rotor_config(self) -> None:
        c = self.cfg
        self.engine.controller.cfg = RotorConfig(
            port=c.serial_port,
            baudrate=c.baudrate,
            terminator=c.terminator,
            stop_command=c.stop_command,
            stop_strategy=c.stop_strategy,
            stop_repeat=c.stop_repeat,
            stop_repeat_gap=c.stop_repeat_gap,
            send_move_with_target=c.send_move_with_target,
            command_gap=c.command_gap,
            settle_delay=c.settle_delay,
            range_start=c.rotor_range_start,
            range_span=c.rotor_range_span,
            offset=c.rotor_offset,
            speed_deg_s=c.rotor_speed,
            min_move=c.rotor_min_move,
            safety_margin=c.rotor_safety_margin,
            read_position=c.rotor_read_position,
            poll_interval=c.rotor_poll_interval,
            stop_on_margin=c.rotor_stop_on_margin,
        )
        # gli eventi del rotore arrivano anche da thread di servizio: passano
        # per un segnale, mai direttamente sul widget del registro
        self.engine.controller._on_event = self.bridge.message.emit

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() != QDialog.Accepted:
            return
        was_connected = self.engine.controller.state.connected
        old_cty = self.cfg.cty_path
        dlg.apply_to(self.cfg)
        self.save_config()

        self.engine.controller.disconnect()
        self._apply_rotor_config()
        if self.cfg.cty_path != old_cty:
            self._reload_dxcc()
        self.s_thr.setValue(self.cfg.auto_threshold)
        self.start_listeners()
        if was_connected or self.cfg.auto_connect:
            self.connect_rotor()

    def _reload_dxcc(self) -> None:
        try:
            if self.cfg.cty_path:
                self.engine.resolver = DxccResolver(self.cfg.cty_path)
            else:
                self.engine.resolver = DxccResolver()
            self._log(f"Database DXCC: {self.engine.resolver.source}")
        except Exception as exc:
            self._log(f"ERRORE caricamento cty.dat: {exc}", "!")

    def save_config(self) -> None:
        try:
            path = self.cfg.save()
            self._log(f"Configurazione salvata in {path}")
        except Exception as exc:
            self._log(f"ERRORE salvataggio configurazione: {exc}", "!")

    # ------------------------------------------------------------------
    # rotore
    # ------------------------------------------------------------------
    def connect_rotor(self) -> None:
        ok = self.engine.controller.connect()
        if not ok:
            QMessageBox.warning(self, "Rotore",
                                "Connessione non riuscita:\n"
                                f"{self.engine.controller.state.last_error}")
        self._update_conn_label()

    def toggle_connection(self) -> None:
        if self.engine.controller.state.connected:
            self.engine.controller.disconnect()
            self._log("Disconnesso dal rotore")
        else:
            self.connect_rotor()
        self._update_conn_label()

    def _update_conn_label(self) -> None:
        st = self.engine.controller.state
        if st.connected:
            where = self.cfg.serial_port or "simulatore"
            how = "posizione letta" if st.reading else "posizione stimata"
            self.lbl_conn.setText(f"rotore: {where} · {how}")
            self.lbl_conn.setStyleSheet("color: #6fd39a;")
            self.a_conn.setText("Disconnetti")
        else:
            self.lbl_conn.setText("rotore: NON CONNESSO")
            self.lbl_conn.setStyleSheet("color: #ff6961; font-weight: 600;")
            self.a_conn.setText("Connetti")

    def _rotate(self, azimuth: float, why: str) -> None:
        if not self.engine.controller.state.connected:
            self.connect_rotor()
            if not self.engine.controller.state.connected:
                return
        eta = self.engine.controller.eta_seconds(azimuth)
        ok = self.engine.rotate_to(azimuth, force=True)
        if ok:
            extra = f", ~{eta:.0f} s" if eta else ""
            self._log(f"→ {azimuth:03.0f}° ({compass_point(azimuth)}) [{why}{extra}]")
        else:
            self._log(f"comando non inviato: {self.engine.controller.state.last_error}", "!")

    def _stop(self) -> None:
        if self.engine.controller.state.connected:
            self.engine.controller.stop()
            self._log("STOP inviato")

    def _recalibrate(self) -> None:
        self.engine.controller.set_current_bearing(self.s_calib.value())

    def _raw_console(self) -> None:
        """Console per provare comandi arbitrari sul controller."""
        if not self.engine.controller.state.connected:
            self.connect_rotor()
            if not self.engine.controller.state.connected:
                return

        dlg = QDialog(self)
        dlg.setWindowTitle("Comando grezzo al controller")
        dlg.resize(560, 380)
        lay = QVBoxLayout(dlg)

        info = QLabel(
            "Scrive esattamente quello che digiti sulla porta seriale e mostra "
            "l'eventuale risposta. Usa <code>\\r</code> per il ritorno a capo.<br>"
            "Da provare per l'arresto, con il rotore in movimento: "
            "<code>;</code> &nbsp; <code>AS1;</code> &nbsp; <code>;\\r</code> "
            "&nbsp; <code>\\r</code>. Il pulsante <code>AP1…</code> sposta il "
            "set point sulla posizione attuale senza <code>AM1</code>: se "
            "ferma il rotore senza sbloccare il freno, è il modo migliore.")
        info.setObjectName("sub")
        info.setWordWrap(True)
        lay.addWidget(info)

        out = QPlainTextEdit()
        out.setReadOnly(True)
        lay.addWidget(out, 1)

        row = QHBoxLayout()
        entry = QLineEdit()
        entry.setPlaceholderText("es.  AS1;")
        row.addWidget(entry, 1)
        btn = QPushButton("Invia")
        row.addWidget(btn)
        lay.addLayout(row)

        here = int(round(self.engine.controller.current_bearing)) % 360
        quick = QHBoxLayout()
        for cmd in (";", "AS1;", ";\\r", "\\r", f"AP1{here:03d};", "AI1;"):
            b = QPushButton(cmd)
            b.clicked.connect(lambda _=False, c=cmd: entry.setText(c) or send())
            quick.addWidget(b)
        lay.addLayout(quick)

        def send() -> None:
            text = entry.text()
            if not text:
                return
            reply = self.engine.controller.send_raw(text)
            out.appendPlainText(f"→ {text!r}")
            out.appendPlainText(f"←  {reply!r}" if reply else "←  (nessuna risposta)")

        btn.clicked.connect(send)
        entry.returnPressed.connect(send)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(dlg.reject)
        lay.addWidget(close)
        dlg.exec()

    def _test_readback(self) -> None:
        """Interroga il controller con AI1; e riferisce cosa e' tornato."""
        ctrl = self.engine.controller
        if not ctrl.state.connected:
            self.connect_rotor()
            if not ctrl.state.connected:
                return

        self._log("Prova lettura: invio AI1;")
        results = [ctrl.query_position(timeout=1.0) for _ in range(3)]
        raw = ctrl.state.last_raw_response
        good = [r for r in results if r is not None]

        if not good:
            self._log("Prova lettura: nessuna risposta dal controller", "!")
            QMessageBox.warning(
                self, "Prova lettura posizione",
                "<b>Il controller non ha risposto.</b><br><br>"
                "Su 3 tentativi non è arrivato nulla"
                + (f" (byte ricevuti: <code>{raw!r}</code>)" if raw else "")
                + ".<br><br>Cause tipiche:<br>"
                "• <b>è un Hy-Gain DCU-1 originale</b>: il manuale documenta "
                "solo <code>AP1xxx;</code> e <code>AM1;</code> e dichiara che "
                "non è previsto alcun invio della posizione al computer. "
                "<code>AI1;</code> esiste solo sui controller che lo emulano "
                "(Rotor-EZ, Green Heron RT-21);<br>"
                "• il cavo seriale ha solo TX e massa;<br>"
                "• terminatore diverso: prova a mettere <code>\\r</code> al "
                "posto di <code>;</code>.<br><br>"
                "Il programma continua a funzionare con la posizione stimata.")
            return

        letture = ", ".join(f"{v:.0f}°" for v in good)
        self._log(f"Prova lettura: risposta {raw!r} → {letture}")
        stima = ctrl.current_bearing
        QMessageBox.information(
            self, "Prova lettura posizione",
            f"<b>Il controller risponde.</b><br><br>"
            f"Risposta grezza: <code>{raw!r}</code><br>"
            f"Letture: {letture}<br>"
            f"Posizione stimata dal programma: {stima:.0f}°<br>"
            f"Scarto: {abs(good[-1] - stima):.0f}°<br><br>"
            "Puoi attivare <i>Leggi la posizione dal controller</i> in "
            "Impostazioni → Rotore / DCU-1: la lancetta verde diventerà la "
            "posizione vera e non servirà più ricalibrare.")

    def _on_compass_click(self, bearing: float) -> None:
        self.s_manual.setValue(bearing)
        self._rotate(bearing, "click sulla bussola")

    # ------------------------------------------------------------------
    # calcolo e target
    # ------------------------------------------------------------------
    def _note_manual_edit(self, _text: str = "") -> None:
        self._last_manual_edit = time.time()

    def _go_to_solution(self) -> None:
        """Pulsante RUOTA: invia il comando verso l'azimut calcolato."""
        sol = self.engine.last_solution
        if sol is None:
            self._compute_manual()
            sol = self.engine.last_solution
        if sol is None:
            self._log("nessun azimut calcolato", "!")
            return
        who = sol.call or sol.entity_name or "DX"
        self._rotate(sol.azimuth, who)

    def _compute_manual(self) -> None:
        call = self.e_dxcall.text().strip()
        grid = self.e_dxgrid.text().strip()
        if not call and not grid:
            return
        sol = self.engine.solve_manual(call, grid)
        if sol is None:
            self.lbl_info.setText(f"Impossibile calcolare: {self.engine.last_skip_reason}")
            self.lbl_az.setText("---°")
            return
        self._show_solution(sol)

    def _toggle_lp(self, on: bool) -> None:
        self.cfg.long_path = on
        sol = self.engine.last_solution
        if sol:
            sol.azimuth = sol.long_path if on else sol.short_path
            self._show_solution(sol)

    def _toggle_auto(self, on: bool) -> None:
        self.cfg.auto_rotate = on
        self._log(f"Auto-rotazione {'ATTIVA' if on else 'disattivata'} "
                  f"(soglia {self.cfg.auto_threshold:.0f}°)")

    def _change_threshold(self, v: float) -> None:
        self.cfg.auto_threshold = v

    def _show_solution(self, sol: Solution, update_fields: bool = False) -> None:
        self.lbl_az.setText(f"{sol.azimuth:03.0f}°")
        parts = [sol.describe()]
        if sol.precision:
            parts.append(f"fonte: {sol.precision}")
        if sol.distance_km:
            parts.append(f"{sol.distance_km:,.0f} km".replace(",", "."))
        if sol.short_path or sol.long_path:
            parts.append(f"SP {sol.short_path:.0f}° / LP {sol.long_path:.0f}°")
        self.lbl_info.setText("   ·   ".join(parts))

        cur = self.engine.controller.current_bearing
        d = angular_difference(cur, sol.azimuth)
        verso = "destra" if d > 0 else "sinistra"
        self.lbl_delta.setText(f"Δ {abs(d):.0f}° a {verso}  "
                               f"({compass_point(sol.azimuth)})")
        # I campi Call/Grid seguono la stazione ricevuta dalle sorgenti esterne.
        # Non si usa hasFocus(): Qt assegna il focus iniziale al primo campo
        # della finestra, che resterebbe percio' bloccato per sempre. Si guarda
        # invece quando l'utente ha digitato davvero (segnale textEdited).
        if update_fields and (time.time() - self._last_manual_edit) > MANUAL_EDIT_GRACE:
            self.e_dxcall.setText(sol.call)
            self.e_dxgrid.setText(sol.grid)
        self.s_manual.setValue(sol.azimuth)

    def _clear_dx(self) -> None:
        """
        Azzera il riquadro Stazione DX: campi, azimut, bersaglio sul quadrante.

        Non tocca la posizione del rotore, che resta dove si trova, e rispetta
        la tregua di digitazione manuale.
        """
        if (time.time() - self._last_manual_edit) <= MANUAL_EDIT_GRACE:
            return
        if self.engine.last_solution is None and not self.e_dxcall.text():
            return                        # gia' pulito: niente da fare
        self.engine.last_solution = None
        self._last_rx_key = ""
        self.e_dxcall.clear()
        self.e_dxgrid.clear()
        self.lbl_az.setText("---°")
        self.lbl_info.setText("nessuna stazione")
        self.lbl_delta.setText("")
        self.lbl_auto.setText("in attesa di dati")
        self._log("stazione DX azzerata (campo svuotato in WSJT-X)")

    def _on_target(self, target: DxTarget) -> None:
        # avviso (non ripetuto all'infinito) se l'automatismo e' acceso ma il
        # rotore non e' connesso: altrimenti i comandi verrebbero scartati
        # senza che si veda il perche'
        if self.cfg.auto_rotate and not self.engine.controller.state.connected:
            now = time.time()
            if now - self._warned_disconnected > 30.0:
                self._warned_disconnected = now
                self._log("auto-rotazione attiva ma il rotore non è connesso "
                          "— usa Rotore → Connetti", "!")

        tag = f"{target.source}/{target.kind}"

        # La sorgente ha svuotato la stazione DX (campo DX Call cancellato in
        # WSJT-X, cambio banda o configurazione): si azzera anche qui.
        if target.cleared:
            self._clear_dx()
            return

        # Banda non abilitata: l'antenna di quella banda non e' sul rotatore.
        allowed, band = self.engine.band_allowed(target)
        if not allowed:
            if self._last_band_block != band:
                self._last_band_block = band
                self._log(f"banda {band} non abilitata: DXRotator resta fermo")
            self.lbl_auto.setText(f"banda {band}: non abilitata in Impostazioni "
                                  f"→ Bande")
            return
        self._last_band_block = None

        # Sorgente non abilitata (tipicamente le decodifiche di WSJT-X in
        # multicast): ignorata del tutto.
        if not self.engine.source_enabled(target):
            if self.cfg.log_decodes:
                sol = self.engine.solve(target, remember=False)
                if sol is not None:
                    self._log(f"rx [{tag}] {sol.describe()} → {sol.azimuth:03.0f}°")
            return

        sol, sent, reason = self.engine.handle_target(target)
        if sol is None:
            self.lbl_auto.setText(f"{target.label()}: {reason}")
            return
        self._show_solution(sol, update_fields=True)

        # traccia nel registro ogni cambio di stazione, anche quando
        # l'automatismo non invia nulla: serve a capire cosa sta arrivando
        key = f"{sol.call}|{sol.grid}|{sol.azimuth:.0f}"
        if key != self._last_rx_key:
            self._last_rx_key = key
            self._log(f"RX [{tag}] {sol.describe()} → {sol.azimuth:03.0f}°")

        if sent:
            self.lbl_auto.setText(f"AUTO → {sol.azimuth:.0f}° per {sol.describe()} ({reason})")
            self._log(f"AUTO [{tag}] {sol.describe()} → {sol.azimuth:03.0f}°  ({reason})")
        else:
            self.lbl_auto.setText(f"{tag}: {sol.describe()} → {sol.azimuth:.0f}°  "
                                  f"— nessun comando ({reason})")

    # ------------------------------------------------------------------
    # sorgenti UDP
    # ------------------------------------------------------------------
    def stop_listeners(self) -> None:
        for l in self.listeners:
            l.stop()
        self.listeners = []

    def start_listeners(self) -> None:
        self.stop_listeners()
        cb = self.bridge.target.emit
        err = self.bridge.error.emit
        c = self.cfg
        if c.wsjtx_enabled:
            self.listeners.append(UdpListener("WSJT-X", c.wsjtx_host, c.wsjtx_port,
                                              WsjtxDecoder(), cb, err))
        if c.n1mm_enabled:
            self.listeners.append(UdpListener("N1MM", c.n1mm_host, c.n1mm_port,
                                              N1mmDecoder(), cb, err))
        if c.n1mm_rotor_enabled:
            self.listeners.append(UdpListener("N1MM-rotore", c.n1mm_rotor_host,
                                              c.n1mm_rotor_port,
                                              N1mmDecoder(), cb, err))
        for l in self.listeners:
            l.start()
            self._log(f"Ascolto {l.label} su UDP {l.host}:{l.port}")
        if not self.listeners:
            self._log("Nessuna sorgente UDP attiva", "!")

    # ------------------------------------------------------------------
    # ciclo periodico
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        ctrl = self.engine.controller
        ctrl.tick()
        sol = self.engine.last_solution
        target_az = sol.azimuth if sol else None
        label = ""
        if sol:
            label = sol.call or sol.entity_name or ""
        self.compass.set_state(
            current=ctrl.current_bearing,
            target=target_az,
            threshold=self.cfg.auto_threshold if self.cfg.auto_rotate else 0.0,
            moving=ctrl.state.moving,
            label=label,
            stop_bearing=self.cfg.rotor_range_start,
            span=self.cfg.rotor_range_span,
            blind=blind_sector(ctrl.cfg),
        )
        if sol:
            d = angular_difference(ctrl.current_bearing, sol.azimuth)
            verso = "destra" if d > 0 else "sinistra"
            self.lbl_delta.setText(f"Δ {abs(d):.0f}° a {verso}  "
                                   f"({compass_point(sol.azimuth)})")

        bits = []
        for l in self.listeners:
            age = time.time() - l.last_packet_at if l.last_packet_at else None
            mark = "●" if (age is not None and age < 15) else "○"
            bits.append(f"{mark} {l.label} {l.packets}")
        self.lbl_udp.setText("UDP: " + ("  ".join(bits) if bits else "—"))
        self._update_conn_label()

    # ------------------------------------------------------------------
    def _log(self, msg: str, level: str = " ") -> None:
        line = f"{time.strftime('%H:%M:%S')} {level} {msg}"
        widget = getattr(self, "log", None)
        if widget is None:
            # messaggio arrivato prima che il registro esistesse
            self._pending_log.append(line)
            return
        if self._pending_log:
            for pending in self._pending_log:
                widget.appendPlainText(pending)
            self._pending_log.clear()
        widget.appendPlainText(line)

    def _about(self) -> None:
        QMessageBox.information(
            self, "DXRotator",
            "<b>DXRotator</b><br>"
            "Controllo rotore Hy-Gain TX2 con protocollo DCU-1.<br><br>"
            "Sorgenti: WSJT-X (UDP binario) e N1MM+ (UDP XML).<br>"
            "Puntamento da locatore Maidenhead o entità DXCC.<br><br>"
            "Licenza MIT — 73!")

    # ------------------------------------------------------------------
    def _restore_geometry(self) -> None:
        """Ripristina posizione e dimensioni dell'ultima sessione."""
        data = self.cfg.window_geometry
        if data:
            try:
                if self.restoreGeometry(QByteArray.fromBase64(data.encode())):
                    return
            except Exception:
                pass
        self.resize(560, 460) if self.cfg.compact_mode else self.resize(1020, 680)

    def _save_geometry(self) -> None:
        try:
            self.cfg.window_geometry = bytes(
                self.saveGeometry().toBase64()).decode("ascii")
        except Exception:
            self.cfg.window_geometry = ""

    def closeEvent(self, event) -> None:
        self.stop_listeners()
        self.engine.controller.disconnect()
        self._save_geometry()
        try:
            self.cfg.save()
        except Exception:
            pass
        super().closeEvent(event)


def run() -> int:
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("DXRotator")
    cfg = AppConfig.load()
    if cfg.dark_theme:
        app.setStyleSheet(DARK_QSS)
    win = MainWindow(cfg)
    win.show()
    return app.exec()
