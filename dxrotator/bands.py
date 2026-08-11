"""
bands.py - Riconoscimento della banda radioamatoriale dalla frequenza.

Serve a limitare l'azione di DXRotator alle sole bande la cui antenna e'
effettivamente installata sul rotatore. Chi ha una direttiva sul rotatore e
una verticale fissa per le bande basse non vuole che il rotore si muova
mentre opera sulla verticale.

I limiti sono volutamente un po' larghi: servono a classificare, non a
verificare la licenza.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# (nome, frequenza minima Hz, frequenza massima Hz)
BAND_LIMITS: List[Tuple[str, int, int]] = [
    ("2200m", 135_700, 137_800),
    ("630m", 472_000, 479_000),
    ("160m", 1_800_000, 2_000_000),
    ("80m", 3_500_000, 4_000_000),
    ("60m", 5_250_000, 5_450_000),
    ("40m", 7_000_000, 7_300_000),
    ("30m", 10_100_000, 10_150_000),
    ("20m", 14_000_000, 14_350_000),
    ("17m", 18_068_000, 18_168_000),
    ("15m", 21_000_000, 21_450_000),
    ("12m", 24_890_000, 24_990_000),
    ("10m", 28_000_000, 29_700_000),
    ("6m", 50_000_000, 54_000_000),
    ("4m", 70_000_000, 70_500_000),
    ("2m", 144_000_000, 148_000_000),
    ("70cm", 430_000_000, 450_000_000),
]

BAND_NAMES: List[str] = [name for name, _lo, _hi in BAND_LIMITS]

# bande tipiche di una direttiva HF (es. hexbeam 6 bande)
DIRECTIVE_BANDS = {"20m", "17m", "15m", "12m", "10m", "6m"}


def band_for_frequency(hz) -> Optional[str]:
    """
    Restituisce il nome della banda per una frequenza in Hz.

    None se la frequenza e' nulla, non numerica o fuori da ogni banda.
    """
    try:
        f = float(hz)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    for name, lo, hi in BAND_LIMITS:
        if lo <= f <= hi:
            return name
    return None


def default_enabled_bands(only: Optional[set] = None) -> Dict[str, bool]:
    """Dizionario banda -> abilitata. Senza argomenti sono tutte abilitate."""
    if only is None:
        return {name: True for name in BAND_NAMES}
    return {name: (name in only) for name in BAND_NAMES}


def is_enabled(band: Optional[str], enabled: Dict[str, bool]) -> bool:
    """
    True se la banda e' abilitata.

    Una banda sconosciuta (frequenza assente o fuori banda) viene considerata
    ammessa: meglio lasciar lavorare il programma che bloccarlo per un dato
    mancante. Le sorgenti che contano (Status di WSJT-X, contatti di N1MM)
    la frequenza la portano sempre.
    """
    if not band:
        return True
    return bool(enabled.get(band, True))
