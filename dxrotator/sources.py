"""
sources.py - Sorgenti dati UDP: WSJT-X e N1MM+.

Espone:
  * DxTarget          -> informazione normalizzata sulla stazione DX
  * WsjtxDecoder      -> decodifica i pacchetti binari (QDataStream) di WSJT-X
  * N1mmDecoder       -> decodifica i pacchetti XML di N1MM+
  * UdpListener       -> thread che riceve su una porta UDP (anche multicast)

Porte tipiche
  WSJT-X ........ 2237  (UDP Server in File > Settings > Reporting)
  N1MM+ dati .... 12060 (Config > Ports > Broadcast Data: Contacts, Spots)
  N1MM+ rotore .. 12040 (Config > Ports > Broadcast Data: Rotor)
"""

from __future__ import annotations

import logging
import re
import socket
import struct
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

log = logging.getLogger(__name__)

WSJTX_MAGIC = 0xADBCCBDA

_GRID_RE = re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2})?$", re.I)
_NOT_GRID = {"RR73", "RRR", "73", "TU", "DE", "CQ", "QRZ", "NA", "SA",
             "EU", "AS", "AF", "OC", "DX", "TEST"}


def looks_like_grid(token: str) -> bool:
    """True se il token e' un locatore Maidenhead a 4 o 6 caratteri."""
    if not token:
        return False
    t = token.strip().upper()
    if t in _NOT_GRID:
        return False
    return bool(_GRID_RE.match(t))


# --------------------------------------------------------------------------
# Target normalizzato
# --------------------------------------------------------------------------

@dataclass
class DxTarget:
    """Informazione su una stazione DX proveniente da una sorgente esterna."""
    call: str = ""
    grid: str = ""
    azimuth: Optional[float] = None    # se la sorgente fornisce gia' l'azimut
    source: str = ""                   # "WSJT-X", "N1MM", ...
    kind: str = ""                     # "status", "decode", "qso", "spot", "rotor"
    mode: str = ""
    frequency_hz: int = 0
    text: str = ""
    cleared: bool = False               # la sorgente ha svuotato la stazione DX
    timestamp: float = field(default_factory=time.time)

    @property
    def is_empty(self) -> bool:
        if self.cleared:
            return False               # e' un evento significativo, non un vuoto
        return not (self.call or self.grid or self.azimuth is not None)

    def label(self) -> str:
        bits = [b for b in (self.call, self.grid) if b]
        return " ".join(bits) if bits else "?"


# --------------------------------------------------------------------------
# Lettore binario stile QDataStream (big endian)
# --------------------------------------------------------------------------

class _Reader:
    def __init__(self, data: bytes) -> None:
        self.d = data
        self.i = 0

    def _take(self, n: int) -> bytes:
        if self.i + n > len(self.d):
            raise EOFError("pacchetto troncato")
        b = self.d[self.i:self.i + n]
        self.i += n
        return b

    def u8(self) -> int:
        return struct.unpack(">B", self._take(1))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self._take(4))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self._take(4))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self._take(8))[0]

    def i64(self) -> int:
        return struct.unpack(">q", self._take(8))[0]

    def f64(self) -> float:
        return struct.unpack(">d", self._take(8))[0]

    def boolean(self) -> bool:
        return self.u8() != 0

    def utf8(self) -> str:
        n = self.u32()
        if n == 0xFFFFFFFF:      # QString/QByteArray nullo
            return ""
        return self._take(n).decode("utf-8", "replace")

    def qtime(self) -> int:
        """QTime = ms dalla mezzanotte."""
        return self.u32()

    def qdatetime(self) -> float:
        """QDateTime -> timestamp unix approssimato."""
        jd = self.i64()
        ms = self.u32()
        spec = self.u8()
        if spec == 2:            # OffsetFromUTC
            self.i32()
        elif spec == 3:          # TimeZone
            self.utf8()
        # giorno giuliano 2440588 = 1970-01-01
        return (jd - 2440588) * 86400.0 + ms / 1000.0

    @property
    def remaining(self) -> int:
        return len(self.d) - self.i


# --------------------------------------------------------------------------
# WSJT-X
# --------------------------------------------------------------------------

class WsjtxDecoder:
    """Decodifica i pacchetti UDP di WSJT-X in DxTarget."""

    HEARTBEAT = 0
    STATUS = 1
    DECODE = 2
    QSO_LOGGED = 5
    LOGGED_ADIF = 12

    def __init__(self) -> None:
        self.last_status: Dict[str, str] = {}
        self.my_grid: str = ""
        self.my_call: str = ""
        # ultima frequenza vista in un messaggio Status: i messaggi Decode non
        # la contengono, ma servono per capire su che banda si sta operando
        self.last_frequency_hz: int = 0

    def decode(self, data: bytes) -> Optional[DxTarget]:
        try:
            r = _Reader(data)
            magic = r.u32()
            if magic != WSJTX_MAGIC:
                return None
            r.u32()                       # schema
            mtype = r.u32()
            r.utf8()                      # id (nome programma)
        except Exception:
            return None

        try:
            if mtype == self.STATUS:
                return self._status(r)
            if mtype == self.DECODE:
                return self._decode_msg(r)
            if mtype == self.QSO_LOGGED:
                return self._qso(r)
            if mtype == self.LOGGED_ADIF:
                return self._adif(r)
        except Exception as exc:
            log.debug("WSJT-X: pacchetto tipo %s non decodificabile: %s", mtype, exc)
        return None

    # -- singoli messaggi -------------------------------------------------
    def _status(self, r: _Reader) -> Optional[DxTarget]:
        freq = r.u64()
        mode = r.utf8()
        dx_call = r.utf8()
        r.utf8()                 # report
        r.utf8()                 # tx mode
        r.boolean()              # tx enabled
        r.boolean()              # transmitting
        r.boolean()              # decoding
        r.u32()                  # rx df
        r.u32()                  # tx df
        de_call = r.utf8()
        de_grid = r.utf8()
        dx_grid = r.utf8()

        if de_call:
            self.my_call = de_call
        if de_grid:
            self.my_grid = de_grid
        if freq:
            self.last_frequency_hz = freq

        if not dx_call and not dx_grid:
            # l'operatore ha svuotato il campo DX Call in WSJT-X (o ha
            # cambiato banda/configurazione): la stazione DX non c'e' piu'
            return DxTarget(source="WSJT-X", kind="status", cleared=True,
                            mode=mode, frequency_hz=freq)
        return DxTarget(
            call=dx_call.upper(),
            grid=dx_grid.upper() if looks_like_grid(dx_grid) else "",
            source="WSJT-X",
            kind="status",
            mode=mode,
            frequency_hz=freq,
        )

    def _decode_msg(self, r: _Reader) -> Optional[DxTarget]:
        r.boolean()              # new
        r.qtime()
        r.i32()                  # snr
        r.f64()                  # delta time
        r.u32()                  # delta frequency
        mode = r.utf8()
        message = r.utf8()

        call, grid = parse_ft8_message(message, my_call=self.my_call)
        if not call and not grid:
            return None
        return DxTarget(call=call, grid=grid, source="WSJT-X",
                        kind="decode", mode=mode, text=message,
                        frequency_hz=self.last_frequency_hz)

    def _qso(self, r: _Reader) -> Optional[DxTarget]:
        r.qdatetime()            # date/time off
        dx_call = r.utf8()
        dx_grid = r.utf8()
        freq = r.u64()
        mode = r.utf8()
        if not dx_call:
            return None
        return DxTarget(call=dx_call.upper(),
                        grid=dx_grid.upper() if looks_like_grid(dx_grid) else "",
                        source="WSJT-X", kind="qso", mode=mode,
                        frequency_hz=freq)

    def _adif(self, r: _Reader) -> Optional[DxTarget]:
        adif = r.utf8()
        call = _adif_field(adif, "CALL")
        grid = _adif_field(adif, "GRIDSQUARE")
        if not call:
            return None
        return DxTarget(call=call.upper(),
                        grid=grid.upper() if looks_like_grid(grid) else "",
                        source="WSJT-X", kind="qso", text=adif)


def _adif_field(adif: str, name: str) -> str:
    m = re.search(r"<" + name + r":(\d+)(?::[^>]*)?>", adif, re.I)
    if not m:
        return ""
    start = m.end()
    n = int(m.group(1))
    return adif[start:start + n].strip()


def parse_ft8_message(message: str, my_call: str = "") -> tuple:
    """
    Estrae (nominativo DX, locatore) da un messaggio FT8/FT4 decodificato.

      "CQ IK0ABC JN61"        -> ("IK0ABC", "JN61")
      "IK0ABC F1XYZ JN18"     -> ("F1XYZ", "JN18")  se my_call == IK0ABC
      "IK0ABC F1XYZ -12"      -> ("F1XYZ", "")
    """
    if not message:
        return ("", "")
    msg = message.strip().upper()
    msg = msg.strip("<>")
    tokens = [t.strip("<>") for t in msg.split() if t.strip("<>")]
    if not tokens:
        return ("", "")

    grid = ""
    if looks_like_grid(tokens[-1]):
        grid = tokens[-1]
        tokens = tokens[:-1]

    # scarta i prefissi di indirizzamento
    while tokens and tokens[0] in ("CQ", "QRZ", "DE"):
        tokens = tokens[1:]
        # "CQ DX", "CQ EU", "CQ TEST", "CQ 014"
        if tokens and (tokens[0] in _NOT_GRID or tokens[0].isdigit()):
            tokens = tokens[1:]

    calls = [t for t in tokens if _is_callish(t)]
    if not calls:
        return ("", grid)

    my = (my_call or "").upper()
    dx = calls[0]
    if len(calls) >= 2:
        # messaggio diretto: il primo e' il destinatario, il secondo il mittente
        dx = calls[1] if (not my or calls[0] == my or calls[1] != my) else calls[0]
        if my and calls[1] == my:
            dx = calls[0]
    return (dx, grid)


def _is_callish(token: str) -> bool:
    if not token or len(token) < 3:
        return False
    if looks_like_grid(token):
        return False
    if token in _NOT_GRID:
        return False
    if re.match(r"^[+-]?\d+$", token):
        return False
    return bool(re.match(r"^[A-Z0-9/]{3,}$", token) and re.search(r"\d", token))


# --------------------------------------------------------------------------
# N1MM+
# --------------------------------------------------------------------------

class N1mmDecoder:
    """
    Decodifica i pacchetti XML di N1MM+.

    Riconosce:
      <N1MMRotor><rotor><goazi>...   -> azimut gia' calcolato da N1MM
      <contactinfo> / <contactreplace> -> call + gridsquare
      <spot> / <dxspot>              -> dxcall
      <RadioInfo>                    -> frequenza/modo (solo contesto)
    """

    def decode(self, data: bytes) -> Optional[DxTarget]:
        try:
            text = data.decode("utf-8", "replace").strip()
        except Exception:
            return None
        if "<" not in text:
            return None
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            # a volte arrivano piu' documenti concatenati: prendi il primo
            m = re.search(r"<([A-Za-z_][\w\-]*)[^>]*>.*?</\1>", text, re.S)
            if not m:
                return None
            try:
                root = ET.fromstring(m.group(0))
            except ET.ParseError:
                return None

        flat = _flatten(root)
        tag = root.tag.lower()

        # 1) N1MM ha gia' calcolato l'azimut (broadcast "Rotor")
        azi = _first(flat, ("goazi", "azimuth", "bearing"))
        if azi is not None:
            try:
                return DxTarget(
                    call=_first(flat, ("call", "dxcall", "stationcall")) or "",
                    azimuth=float(azi) % 360.0,
                    source="N1MM", kind="rotor",
                    text=_first(flat, ("rotorname",)) or "",
                )
            except ValueError:
                pass

        call = _first(flat, ("dxcall", "call", "callsign", "contactcall"))
        grid = _first(flat, ("gridsquare", "grid", "dxgrid", "locator"))
        if not call and not grid:
            return None

        kind = "spot" if "spot" in tag else ("qso" if "contact" in tag else "info")
        freq = _first(flat, ("frequency", "freq", "txfreq"))
        try:
            # N1MM esprime le frequenze in decine di Hz (kHz * 100)
            freq_hz = int(float(freq) * 10) if freq else 0
        except (TypeError, ValueError):
            freq_hz = 0

        return DxTarget(
            call=(call or "").upper(),
            grid=(grid or "").upper() if looks_like_grid(grid or "") else "",
            source="N1MM",
            kind=kind,
            mode=_first(flat, ("mode",)) or "",
            frequency_hz=freq_hz,
        )


def _flatten(elem: ET.Element, out: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Appiattisce un albero XML in un dict tag_minuscolo -> testo (primo vince)."""
    if out is None:
        out = {}
    for child in elem:
        key = child.tag.lower()
        txt = (child.text or "").strip()
        if txt and key not in out:
            out[key] = txt
        _flatten(child, out)
    for k, v in elem.attrib.items():
        out.setdefault(k.lower(), v)
    return out


def _first(d: Dict[str, str], keys) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


# --------------------------------------------------------------------------
# Listener UDP
# --------------------------------------------------------------------------

class UdpListener(threading.Thread):
    """
    Thread di ascolto UDP. Ogni datagramma viene passato a `decoder.decode()`
    e il DxTarget risultante inoltrato a `callback`.

    Supporta indirizzi multicast (es. 224.0.0.1 usato da WSJT-X in modalita'
    multicast) e la modalita' "non esclusiva" per convivere con altri
    programmi in ascolto sulla stessa porta.
    """

    def __init__(self, name: str, host: str, port: int, decoder,
                 callback: Callable[[DxTarget], None],
                 on_error: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(daemon=True, name=f"udp-{name}")
        self.label = name
        self.host = host or "0.0.0.0"
        self.port = int(port)
        self.decoder = decoder
        self.callback = callback
        self.on_error = on_error
        self._stop = threading.Event()
        self._sock: Optional[socket.socket] = None
        self.packets = 0
        self.last_packet_at: float = 0.0
        self.error = ""

    # ------------------------------------------------------------------
    def _make_socket(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        is_multicast = _is_multicast(self.host)
        s.bind(("" if is_multicast else self.host, self.port))
        if is_multicast:
            mreq = struct.pack("4sl", socket.inet_aton(self.host),
                               socket.INADDR_ANY)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.settimeout(0.5)
        return s

    def run(self) -> None:
        try:
            self._sock = self._make_socket()
        except Exception as exc:
            self.error = f"{self.label}: impossibile aprire UDP {self.host}:{self.port} ({exc})"
            log.warning(self.error)
            if self.on_error:
                self.on_error(self.error)
            return

        while not self._stop.is_set():
            try:
                data, _addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                continue
            self.packets += 1
            self.last_packet_at = time.time()
            try:
                target = self.decoder.decode(data)
            except Exception as exc:      # pragma: no cover
                log.debug("%s: errore di decodifica: %s", self.label, exc)
                continue
            if target is not None and not target.is_empty:
                try:
                    self.callback(target)
                except Exception as exc:  # pragma: no cover
                    log.warning("%s: errore nella callback: %s", self.label, exc)

        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass

    def stop(self) -> None:
        self._stop.set()

    @property
    def alive(self) -> bool:
        return self.is_alive() and not self._stop.is_set()


def _is_multicast(host: str) -> bool:
    try:
        first = int(host.split(".")[0])
    except (ValueError, IndexError):
        return False
    return 224 <= first <= 239
