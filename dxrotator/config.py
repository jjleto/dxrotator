"""
config.py - Persistenza delle impostazioni in JSON.

Il file viene salvato nella cartella di configurazione dell'utente:
  Windows : %APPDATA%\\DXRotator\\config.json
  macOS   : ~/Library/Application Support/DXRotator/config.json
  Linux   : ~/.config/dxrotator/config.json
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict

from .bands import BAND_NAMES, default_enabled_bands

APP_NAME = "DXRotator"


def config_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", APP_NAME)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME.lower())


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


@dataclass
class AppConfig:
    # --- stazione ---
    my_call: str = ""
    my_locator: str = "JN61"
    my_lat: float = 0.0
    my_lon: float = 0.0
    use_latlon: bool = False          # True: usa lat/lon invece del locatore

    # --- rotore / DCU-1 ---
    serial_port: str = ""
    baudrate: int = 4800
    terminator: str = ";"
    stop_command: str = ";"
    # command | target_only | goto_current | both
    stop_strategy: str = "both"
    stop_repeat: int = 3
    stop_repeat_gap: float = 0.6
    send_move_with_target: bool = False   # AP1 e AM1 separati, con pausa
    command_gap: float = 0.15
    settle_delay: float = 0.20
    rotor_range_start: float = 180.0  # azimut vero del fermo meccanico
    rotor_range_span: float = 360.0
    rotor_offset: float = 0.0
    rotor_speed: float = 6.0          # gradi/secondo
    rotor_min_move: float = 2.0
    rotor_safety_margin: float = 10.0  # gradi da tenere liberi dal fermo
    rotor_read_position: bool = False  # usa AI1; invece della stima
    rotor_poll_interval: float = 1.0
    rotor_stop_on_margin: bool = True
    auto_connect: bool = False

    # --- automatismo ---
    auto_rotate: bool = False
    auto_threshold: float = 30.0      # ruota solo se |differenza| > soglia
    auto_sources: Dict[str, bool] = field(default_factory=lambda: {
        "wsjtx_status": True,
        "wsjtx_decode": False,
        "wsjtx_qso": False,
        "n1mm": True,
    })
    long_path: bool = False
    log_decodes: bool = False         # scrive anche le decodifiche nel registro

    # bande su cui DXRotator puo' agire: quelle la cui antenna sta davvero
    # sul rotatore. Le altre (verticale fissa, dipoli) vanno tolte.
    enabled_bands: Dict[str, bool] = field(default_factory=default_enabled_bands)
    auto_hold_seconds: float = 3.0    # attesa minima fra due comandi automatici

    # --- UDP ---
    wsjtx_enabled: bool = True
    wsjtx_host: str = "0.0.0.0"
    wsjtx_port: int = 2237
    n1mm_enabled: bool = True
    n1mm_host: str = "0.0.0.0"
    n1mm_port: int = 12060
    n1mm_rotor_enabled: bool = False
    n1mm_rotor_host: str = "0.0.0.0"
    n1mm_rotor_port: int = 12040

    # --- dati ---
    cty_path: str = ""

    # --- interfaccia ---
    window_geometry: str = ""         # posizione e dimensioni, base64 di saveGeometry
    dark_theme: bool = True
    compact_mode: bool = False        # finestra ridotta al minimo indispensabile
    show_log: bool = True
    show_compass: bool = True
    always_on_top: bool = False
    presets: Dict[str, float] = field(default_factory=lambda: {
        "NA": 300.0, "SA": 240.0, "EU": 0.0,
        "AF": 180.0, "AS": 60.0, "OC": 100.0,
    })

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (data or {}).items() if k in known}
        cfg = cls(**clean)
        # merge dei dizionari annidati con i default
        base = cls()
        merged = dict(base.auto_sources)
        merged.update(cfg.auto_sources or {})
        cfg.auto_sources = merged

        # le bande aggiunte in versioni successive partono abilitate
        merged_bands = default_enabled_bands()
        for name, on in (cfg.enabled_bands or {}).items():
            if name in merged_bands:
                merged_bands[name] = bool(on)
        cfg.enabled_bands = merged_bands

        if not cfg.presets:
            cfg.presets = dict(base.presets)
        return cfg

    # ------------------------------------------------------------------
    def save(self, path: str = "") -> str:
        path = path or config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return path

    @classmethod
    def load(cls, path: str = "") -> "AppConfig":
        path = path or config_path()
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return cls.from_dict(json.load(fh))
        except Exception:
            return cls()
