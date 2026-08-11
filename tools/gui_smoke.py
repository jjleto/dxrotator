#!/usr/bin/env python3
"""
gui_smoke.py - Verifica che l'interfaccia si costruisca senza errori.

Usato dall'integrazione continua e utile anche in locale dopo una modifica
alla GUI, che i test unitari non coprono:

    QT_QPA_PLATFORM=offscreen python tools/gui_smoke.py

Costruisce la finestra principale e il dialogo delle impostazioni, apre e
chiude tutte le schede, esercita i comandi principali contro il simulatore
del rotore e termina con codice 0 se non e' successo nulla di strano.
"""

from __future__ import annotations

import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QTabWidget
    except ImportError as exc:
        print("PySide6 non importabile:", exc, file=sys.stderr)
        print("Su Linux servono anche le librerie di sistema di Qt: "
              "libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1",
              file=sys.stderr)
        return 2

    from dxrotator import __version__
    from dxrotator.config import AppConfig
    from dxrotator.gui import DARK_QSS, MainWindow, SettingsDialog
    from dxrotator.sources import DxTarget

    app = QApplication([])
    app.setStyleSheet(DARK_QSS)

    cfg = AppConfig()
    cfg.my_locator = "JN53"
    cfg.wsjtx_enabled = False        # niente porte UDP nell'integrazione continua
    cfg.n1mm_enabled = False
    cfg.rotor_range_start = 335.0
    cfg.rotor_safety_margin = 20.0
    cfg.auto_rotate = True
    cfg.auto_hold_seconds = 0.0

    win = MainWindow(cfg)
    win.show()

    # comandi principali contro il simulatore
    win.connect_rotor()
    assert win.engine.controller.state.connected, "simulatore non connesso"
    win.s_calib.setValue(60)
    win._recalibrate()
    win._on_target(DxTarget(call="VK3ABC", grid="QF22", source="WSJT-X",
                            kind="status", frequency_hz=14074000))
    assert win.e_dxcall.text() == "VK3ABC", "campo Call non aggiornato"
    assert win.engine.last_solution is not None, "nessun azimut calcolato"
    win._on_compass_click(120.0)
    win._stop()
    win._tick()

    # svuotamento della stazione DX
    win._on_target(DxTarget(source="WSJT-X", kind="status", cleared=True))
    assert win.e_dxcall.text() == "", "campo Call non azzerato"

    # modalita' di visualizzazione
    for compact in (True, False):
        win._set_compact(compact)
        win._tick()
    win._set_show_log(False)
    win._set_show_compass(False)
    win._set_show_compass(True)
    win._set_show_log(True)

    # dialogo impostazioni: tutte le schede
    dlg = SettingsDialog(cfg)
    tabs = dlg.findChild(QTabWidget)
    for i in range(tabs.count()):
        tabs.setCurrentIndex(i)
    dlg.apply_to(cfg)

    win.stop_listeners()
    win.engine.controller.disconnect()
    print(f"GUI ok — DXRotator {__version__}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print("VERIFICA FALLITA:", exc, file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
