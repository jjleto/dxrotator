"""
engine.py - Logica applicativa indipendente dall'interfaccia grafica.

Collega sorgenti dati (WSJT-X / N1MM), risoluzione DXCC, calcolo della rotta
e controller del rotore, applicando le regole di auto-rotazione.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

from .bands import band_for_frequency, is_enabled as is_band_enabled
from .config import AppConfig
from .dxcc import DxccEntity, DxccResolver
from .geo import (Bearing, angular_difference, great_circle, is_valid_locator,
                  locator_to_latlon, normalize_deg)
from .rotor import Dcu1Controller
from .sources import DxTarget


@dataclass
class Solution:
    """Risultato del calcolo di puntamento per una stazione DX."""
    call: str = ""
    grid: str = ""
    entity: Optional[DxccEntity] = None
    azimuth: float = 0.0            # azimut scelto (corto o lungo secondo config)
    short_path: float = 0.0
    long_path: float = 0.0
    distance_km: float = 0.0
    precision: str = ""             # "locatore" | "dxcc" | "diretto"
    source: str = ""
    kind: str = ""
    timestamp: float = 0.0

    @property
    def entity_name(self) -> str:
        return self.entity.name if self.entity else ""

    def describe(self) -> str:
        bits = []
        if self.call:
            bits.append(self.call)
        if self.entity:
            bits.append(self.entity.name)
        if self.grid:
            bits.append(self.grid)
        return "  ·  ".join(bits) if bits else "—"


class RotatorEngine:
    """Motore: da DxTarget a comando rotore."""

    def __init__(self, cfg: AppConfig, resolver: Optional[DxccResolver] = None,
                 controller: Optional[Dcu1Controller] = None) -> None:
        self.cfg = cfg
        self.resolver = resolver or DxccResolver(cfg.cty_path or None)
        self.controller = controller or Dcu1Controller()
        self.last_solution: Optional[Solution] = None
        self.last_auto_command: float = 0.0
        self.last_skip_reason: str = ""

    # ------------------------------------------------------------------
    # posizione della propria stazione
    # ------------------------------------------------------------------
    def my_position(self) -> Optional[Tuple[float, float]]:
        if self.cfg.use_latlon:
            if self.cfg.my_lat == 0.0 and self.cfg.my_lon == 0.0:
                return None
            return (self.cfg.my_lat, self.cfg.my_lon)
        if is_valid_locator(self.cfg.my_locator):
            return locator_to_latlon(self.cfg.my_locator)
        return None

    # ------------------------------------------------------------------
    # calcolo
    # ------------------------------------------------------------------
    def solve(self, target: DxTarget, remember: bool = True) -> Optional[Solution]:
        """
        Trasforma un DxTarget in una Solution con azimut.

        Priorita': azimut fornito dalla sorgente > locatore > entita' DXCC.

        `remember=False` calcola senza aggiornare `last_solution`: serve per le
        stazioni di solo ascolto (attivita' di banda), che non devono spostare
        il puntamento corrente.
        """
        sol = Solution(call=target.call, grid=target.grid, source=target.source,
                       kind=target.kind, timestamp=target.timestamp or time.time())

        # 1) azimut gia' pronto (broadcast rotore di N1MM)
        if target.azimuth is not None:
            az = normalize_deg(target.azimuth)
            sol.azimuth = az
            sol.short_path = az
            sol.long_path = normalize_deg(az + 180.0)
            sol.precision = "diretto"
            if target.call:
                sol.entity = self.resolver.lookup(target.call)
            if remember:
                self.last_solution = sol
            return sol

        me = self.my_position()
        if me is None:
            self.last_skip_reason = "posizione della propria stazione non impostata"
            return None

        entity = self.resolver.lookup(target.call) if target.call else None
        sol.entity = entity

        # 2) locatore Maidenhead (piu' preciso)
        bearing: Optional[Bearing] = None
        if target.grid and is_valid_locator(target.grid):
            lat, lon = locator_to_latlon(target.grid)
            bearing = great_circle(me[0], me[1], lat, lon)
            sol.precision = "locatore"
        # 3) centro dell'entita' DXCC
        elif entity is not None:
            bearing = great_circle(me[0], me[1], entity.lat, entity.lon)
            sol.precision = "dxcc"

        if bearing is None:
            self.last_skip_reason = f"nessun dato di posizione per {target.label()}"
            return None

        sol.short_path = bearing.short_path
        sol.long_path = bearing.long_path
        sol.distance_km = bearing.distance_km
        sol.azimuth = bearing.long_path if self.cfg.long_path else bearing.short_path
        if remember:
            self.last_solution = sol
        return sol

    def solve_manual(self, call: str = "", grid: str = "") -> Optional[Solution]:
        """Calcolo su richiesta dell'utente (campo di inserimento manuale)."""
        return self.solve(DxTarget(call=call.strip().upper(),
                                   grid=grid.strip().upper(),
                                   source="manuale", kind="manual"))

    # ------------------------------------------------------------------
    # regole di auto-rotazione
    # ------------------------------------------------------------------
    def band_allowed(self, target: DxTarget) -> Tuple[bool, Optional[str]]:
        """
        Verifica che la frequenza ricada in una banda abilitata, cioe' in una
        banda la cui antenna e' davvero sul rotatore.

        Restituisce (ammessa, nome_banda). Con frequenza sconosciuta la banda
        e' None e il target viene ammesso.
        """
        band = band_for_frequency(target.frequency_hz)
        return (is_band_enabled(band, self.cfg.enabled_bands), band)

    def source_enabled(self, target: DxTarget) -> bool:
        s = self.cfg.auto_sources
        if target.source == "WSJT-X":
            return bool(s.get(f"wsjtx_{target.kind}", False))
        if target.source == "N1MM":
            return bool(s.get("n1mm", True))
        return True

    def should_rotate(self, azimuth: float) -> Tuple[bool, str]:
        """
        Decide se inviare il comando in modalita' automatica.

        Regola principale richiesta: ruotare SOLO se la differenza angolare fra
        la posizione attuale del rotore e l'azimut della stazione DX supera la
        soglia configurata (default 30 gradi).
        """
        if not self.cfg.auto_rotate:
            return (False, "automatismo disattivato")

        now = time.time()
        if now - self.last_auto_command < max(0.0, self.cfg.auto_hold_seconds):
            return (False, "attesa fra due comandi automatici")

        current = self.controller.current_bearing
        diff = abs(angular_difference(current, azimuth))
        thr = self.cfg.auto_threshold
        if diff <= thr:
            return (False, f"differenza {diff:.0f}° ≤ soglia {thr:.0f}°")

        if self.controller.travel_to(azimuth) is None:
            return (False, f"{azimuth:.0f}° fuori dall'escursione del rotore")

        return (True, f"differenza {diff:.0f}° > soglia {thr:.0f}°")

    # ------------------------------------------------------------------
    # azioni
    # ------------------------------------------------------------------
    def rotate_to(self, azimuth: float, force: bool = True) -> bool:
        """Comando manuale: ruota subito."""
        return self.controller.goto(azimuth, force=force)

    def handle_target(self, target: DxTarget) -> Tuple[Optional[Solution], bool, str]:
        """
        Elabora un target proveniente da una sorgente esterna.

        Restituisce (solution, comando_inviato, motivo).
        """
        allowed, band = self.band_allowed(target)
        if not allowed:
            return (None, False, f"banda {band} non abilitata")

        sol = self.solve(target)
        if sol is None:
            return (None, False, self.last_skip_reason)

        if not self.source_enabled(target):
            return (sol, False, f"sorgente {target.source}/{target.kind} non abilitata")

        ok, reason = self.should_rotate(sol.azimuth)
        if not ok:
            return (sol, False, reason)

        sent = self.controller.goto(sol.azimuth, force=True)
        if sent:
            self.last_auto_command = time.time()
        return (sol, sent, reason if sent else self.controller.state.last_error)
