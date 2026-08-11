"""
geo.py - Calcoli geografici per DXRotator.

Contiene:
  * conversione locatore Maidenhead <-> latitudine/longitudine
  * azimut ortodromico (great circle) percorso corto e lungo
  * distanza ortodromica in km e miglia
  * utilita' per differenze angolari e normalizzazione

Nessuna dipendenza esterna: solo la libreria standard.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional, Tuple

# Raggio medio terrestre (IUGG mean radius) in km
EARTH_RADIUS_KM = 6371.0088
KM_PER_MILE = 1.609344

_LOC_RE = re.compile(r"^[A-Ra-r]{2}[0-9]{2}([A-Xa-x]{2}([0-9]{2}([A-Xa-x]{2})?)?)?$")


class GeoError(ValueError):
    """Errore di validazione dei dati geografici."""


# --------------------------------------------------------------------------
# Maidenhead
# --------------------------------------------------------------------------

def is_valid_locator(loc: str) -> bool:
    """True se la stringa e' un locatore Maidenhead valido (4, 6, 8 o 10 caratteri)."""
    if not loc:
        return False
    loc = loc.strip()
    if len(loc) not in (4, 6, 8, 10):
        return False
    return bool(_LOC_RE.match(loc))


def locator_to_latlon(loc: str) -> Tuple[float, float]:
    """
    Converte un locatore Maidenhead nel centro del quadrato corrispondente.

    Supporta 4 (campo+quadrato), 6 (+sotto-quadrato), 8 e 10 caratteri.
    Restituisce (lat, lon) in gradi decimali, lon positiva a Est.
    """
    if not is_valid_locator(loc):
        raise GeoError(f"Locatore non valido: {loc!r}")

    loc = loc.strip()
    lon = -180.0
    lat = -90.0
    # dimensione della cella corrente
    lon_step = 360.0
    lat_step = 180.0

    # Coppia 1: campo A..R  (20 x 10 gradi)
    lon_step /= 18.0
    lat_step /= 18.0
    lon += (ord(loc[0].upper()) - ord("A")) * lon_step
    lat += (ord(loc[1].upper()) - ord("A")) * lat_step

    # Coppia 2: quadrato 0..9 (2 x 1 gradi)
    lon_step /= 10.0
    lat_step /= 10.0
    lon += int(loc[2]) * lon_step
    lat += int(loc[3]) * lat_step

    # Coppia 3: sotto-quadrato a..x (5' x 2.5')
    if len(loc) >= 6:
        lon_step /= 24.0
        lat_step /= 24.0
        lon += (ord(loc[4].upper()) - ord("A")) * lon_step
        lat += (ord(loc[5].upper()) - ord("A")) * lat_step

    # Coppia 4: extended square 0..9
    if len(loc) >= 8:
        lon_step /= 10.0
        lat_step /= 10.0
        lon += int(loc[6]) * lon_step
        lat += int(loc[7]) * lat_step

    # Coppia 5: a..x
    if len(loc) >= 10:
        lon_step /= 24.0
        lat_step /= 24.0
        lon += (ord(loc[8].upper()) - ord("A")) * lon_step
        lat += (ord(loc[9].upper()) - ord("A")) * lat_step

    # centro della cella
    return (lat + lat_step / 2.0, lon + lon_step / 2.0)


def latlon_to_locator(lat: float, lon: float, precision: int = 6) -> str:
    """
    Converte lat/lon nel locatore Maidenhead.

    precision: numero di caratteri (4, 6, 8 o 10).
    """
    if precision not in (4, 6, 8, 10):
        raise GeoError("precision deve essere 4, 6, 8 o 10")
    if not (-90.0 <= lat <= 90.0):
        raise GeoError(f"Latitudine fuori range: {lat}")

    lon = ((lon + 180.0) % 360.0)      # 0..360
    lat = min(max(lat, -90.0), 90.0) + 90.0   # 0..180

    out = []

    lon_v = lon / 20.0
    lat_v = lat / 10.0
    out.append(chr(ord("A") + int(lon_v)))
    out.append(chr(ord("A") + int(lat_v)))

    lon_v = (lon_v - int(lon_v)) * 10.0
    lat_v = (lat_v - int(lat_v)) * 10.0
    out.append(str(int(lon_v)))
    out.append(str(int(lat_v)))

    if precision >= 6:
        lon_v = (lon_v - int(lon_v)) * 24.0
        lat_v = (lat_v - int(lat_v)) * 24.0
        out.append(chr(ord("a") + int(lon_v)))
        out.append(chr(ord("a") + int(lat_v)))

    if precision >= 8:
        lon_v = (lon_v - int(lon_v)) * 10.0
        lat_v = (lat_v - int(lat_v)) * 10.0
        out.append(str(int(lon_v)))
        out.append(str(int(lat_v)))

    if precision >= 10:
        lon_v = (lon_v - int(lon_v)) * 24.0
        lat_v = (lat_v - int(lat_v)) * 24.0
        out.append(chr(ord("a") + int(lon_v)))
        out.append(chr(ord("a") + int(lat_v)))

    return "".join(out)


# --------------------------------------------------------------------------
# Rotta ortodromica
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Bearing:
    """Risultato di un calcolo di rotta."""
    short_path: float      # azimut percorso corto, 0..360
    long_path: float       # azimut percorso lungo, 0..360
    distance_km: float     # distanza percorso corto in km

    @property
    def distance_miles(self) -> float:
        return self.distance_km / KM_PER_MILE

    @property
    def long_path_km(self) -> float:
        return 2.0 * math.pi * EARTH_RADIUS_KM - self.distance_km


def great_circle(lat1: float, lon1: float, lat2: float, lon2: float) -> Bearing:
    """
    Calcola azimut (percorso corto e lungo) e distanza fra due punti.

    Angoli in gradi decimali, longitudine positiva a Est.
    Azimut riferito al Nord geografico, senso orario.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    # azimut iniziale
    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    az = math.degrees(math.atan2(y, x))
    az = normalize_deg(az)

    # distanza con haversine (stabile per distanze piccole)
    dphi = phi2 - phi1
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon / 2.0) ** 2
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.asin(math.sqrt(a))
    dist = EARTH_RADIUS_KM * c

    return Bearing(short_path=az, long_path=normalize_deg(az + 180.0), distance_km=dist)


def bearing_between_locators(my_loc: str, dx_loc: str) -> Bearing:
    """Rotta fra due locatori Maidenhead."""
    lat1, lon1 = locator_to_latlon(my_loc)
    lat2, lon2 = locator_to_latlon(dx_loc)
    return great_circle(lat1, lon1, lat2, lon2)


# --------------------------------------------------------------------------
# Utilita' angolari
# --------------------------------------------------------------------------

def normalize_deg(a: float) -> float:
    """Riporta un angolo nell'intervallo [0, 360)."""
    a = math.fmod(a, 360.0)
    if a < 0:
        a += 360.0
    return a


def angular_difference(a: float, b: float) -> float:
    """
    Differenza angolare con segno da `a` verso `b`, in [-180, +180].

    Positiva = senso orario (verso destra).
    """
    d = normalize_deg(b - a)
    if d > 180.0:
        d -= 360.0
    return d


def angular_distance(a: float, b: float) -> float:
    """Differenza angolare assoluta piu' breve fra due azimut, in [0, 180]."""
    return abs(angular_difference(a, b))


def compass_point(deg: float, letters: str = "N NE E SE S SO O NO") -> str:
    """Restituisce il punto cardinale (8 settori) per un azimut."""
    names = letters.split()
    idx = int((normalize_deg(deg) + 22.5) // 45.0) % 8
    return names[idx]


def parse_coordinate(text: str) -> Optional[float]:
    """
    Interpreta una coordinata scritta in vari formati:
      "41.9", "41.9N", "41 54 N", "41°54'00\"N", "-9.15", "9.15W"
    Restituisce gradi decimali (positivi N/E) oppure None.
    """
    if text is None:
        return None
    t = text.strip().upper().replace(",", ".")
    if not t:
        return None

    sign = 1.0
    hemi = None
    for h in ("N", "S", "E", "W", "O"):
        if t.endswith(h):
            hemi = h
            t = t[:-1].strip()
            break
        if t.startswith(h) and len(t) > 1 and not t[1].isalpha():
            hemi = h
            t = t[1:].strip()
            break
    if hemi in ("S", "W", "O"):
        sign = -1.0

    t = t.replace("°", " ").replace("'", " ").replace('"', " ").replace("º", " ")
    parts = [p for p in re.split(r"[\s:]+", t) if p]
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return None
    if not vals:
        return None

    neg = vals[0] < 0
    deg = abs(vals[0])
    if len(vals) > 1:
        deg += vals[1] / 60.0
    if len(vals) > 2:
        deg += vals[2] / 3600.0
    if neg:
        deg = -deg
    return sign * deg
