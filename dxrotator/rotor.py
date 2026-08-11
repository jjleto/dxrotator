"""
rotor.py - Driver protocollo DCU-1 (Hy-Gain / Rotor-EZ / Green Heron)
per rotori Hy-Gain TX2 (T2X) e compatibili.

Protocollo DCU-1 (comandi ASCII, terminatore ';'):

    AP1xxx;    imposta l'azimut di destinazione (xxx = 000..359)
    AM1;       avvia la rotazione verso la destinazione impostata
    AI1;       richiede l'azimut corrente  (NON usato: il TX2 con interfaccia
               DCU-1 in sola uscita non risponde)
    ;          arresta immediatamente la rotazione

Poiche' non c'e' lettura di posizione, la posizione corrente viene stimata
per "dead reckoning": si integra la velocita' angolare nominale del rotore
nel tempo, rispettando il fermo meccanico. La stima e' ricalibrabile
manualmente dalla GUI.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .geo import normalize_deg

log = logging.getLogger(__name__)

try:  # pyserial e' opzionale finche' non si usa una porta vera
    import serial  # type: ignore
    from serial.tools import list_ports  # type: ignore
    HAVE_SERIAL = True
except Exception:  # pragma: no cover
    serial = None  # type: ignore
    list_ports = None  # type: ignore
    HAVE_SERIAL = False


# --------------------------------------------------------------------------
# Configurazione
# --------------------------------------------------------------------------

@dataclass
class RotorConfig:
    port: str = ""                    # es. "COM3", "/dev/ttyUSB0", "" = simulatore
    baudrate: int = 4800              # standard DCU-1
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    rtscts: bool = False
    dsrdtr: bool = False

    terminator: str = ";"             # terminatore comandi
    send_move_with_target: bool = True  # invia "AP1xxx;AM1;" in un colpo solo
    command_gap: float = 0.15         # pausa fra AP1 e AM1 quando separati
    settle_delay: float = 0.20        # attesa dopo l'apertura della porta
    stop_command: str = ";"           # comando di arresto
    # come fermare il rotore:
    #   "command"      -> invia stop_command (';' secondo protocollo)
    #   "target_only"  -> AP1<posizione attuale>; SENZA AM1: sposta il set
    #                     point senza far ripartire la sequenza meccanica
    #   "goto_current" -> AP1<posizione attuale>; + AM1;
    #   "both"         -> comando di stop, poi AP1 + AM1
    stop_strategy: str = "both"
    stop_repeat: int = 3              # quante volte insistere
    stop_repeat_gap: float = 0.6      # pausa fra un tentativo e il successivo

    # geometria / meccanica
    range_start: float = 180.0        # bearing del fermo meccanico (180 = Nord centrato)
    range_span: float = 360.0         # escursione totale in gradi (360 o 450)
    offset: float = 0.0               # correzione di calibrazione, sommata al comando
    speed_deg_s: float = 6.0          # velocita' nominale (T2X ~ 6 gradi/s)
    safety_margin: float = 10.0       # gradi da tenere liberi a ogni estremo corsa

    # comportamento
    min_move: float = 2.0             # non muovere per differenze inferiori

    # lettura di posizione dal controller (AI1;)
    read_position: bool = False       # usa la lettura invece della stima
    poll_interval: float = 1.0        # secondi fra due letture
    read_timeout: float = 0.5         # attesa massima della risposta
    stop_on_margin: bool = True       # arresta se entra nel margine di sicurezza


# --------------------------------------------------------------------------
# Trasporti
# --------------------------------------------------------------------------

class RotorTransport:
    """Interfaccia astratta verso il controller."""

    name = "base"

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def read(self, size: int = 64) -> bytes:
        """Legge i byte disponibili senza bloccare a lungo. b'' se non ce ne sono."""
        return b""

    def reset_input(self) -> None:
        """Svuota il buffer di ricezione."""
        return None

    @property
    def is_open(self) -> bool:
        raise NotImplementedError


class SerialTransport(RotorTransport):
    """Porta seriale reale via pyserial."""

    name = "seriale"

    def __init__(self, cfg: RotorConfig) -> None:
        if not HAVE_SERIAL:
            raise RuntimeError(
                "pyserial non installato: eseguire 'pip install pyserial'"
            )
        self.cfg = cfg
        self._ser = None

    def open(self) -> None:
        parity_map = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
        }
        stop_map = {1: serial.STOPBITS_ONE, 2: serial.STOPBITS_TWO,
                    1.5: serial.STOPBITS_ONE_POINT_FIVE}
        self._ser = serial.Serial(
            port=self.cfg.port,
            baudrate=self.cfg.baudrate,
            bytesize=self.cfg.bytesize,
            parity=parity_map.get(self.cfg.parity.upper(), serial.PARITY_NONE),
            stopbits=stop_map.get(self.cfg.stopbits, serial.STOPBITS_ONE),
            rtscts=self.cfg.rtscts,
            dsrdtr=self.cfg.dsrdtr,
            timeout=0.3,
            write_timeout=1.0,
        )
        # molti adattatori USB-seriale muovono DTR/RTS all'apertura e i primi
        # byte vanno persi: si aspetta che la linea si stabilizzi
        if self.cfg.settle_delay > 0:
            time.sleep(self.cfg.settle_delay)
        try:
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
        except Exception:
            pass

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def write(self, data: bytes) -> None:
        if self._ser is None:
            raise RuntimeError("porta non aperta")
        self._ser.write(data)
        self._ser.flush()

    def read(self, size: int = 64) -> bytes:
        if self._ser is None:
            return b""
        waiting = getattr(self._ser, "in_waiting", 0)
        if not waiting:
            return b""
        return self._ser.read(min(size, waiting))

    def reset_input(self) -> None:
        if self._ser is not None:
            try:
                self._ser.reset_input_buffer()
            except Exception:
                pass

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open


class SimulatedTransport(RotorTransport):
    """
    Trasporto fittizio: registra i comandi, utile per test e demo.

    Se `answer_ai1` e' True simula anche un controller che risponde alla
    lettura di posizione, muovendosi verso l'ultimo target a `speed` gradi/s
    e applicando `scale_error` (errore di scala percentuale, per riprodurre
    il comportamento di un potenziometro con cavo lungo).
    """

    name = "simulatore"

    def __init__(self, answer_ai1: bool = False, start: float = 0.0,
                 speed: float = 6.0, scale_error: float = 0.0) -> None:
        self.sent: List[str] = []
        self._open = False
        self.answer_ai1 = answer_ai1
        self.speed = speed
        self.scale_error = scale_error
        self._pos = float(start)
        self._target = float(start)
        self._t = time.monotonic()
        self._rx = bytearray()

    def open(self) -> None:
        self._open = True
        self._t = time.monotonic()

    def close(self) -> None:
        self._open = False

    def _advance(self) -> None:
        now = time.monotonic()
        dt, self._t = now - self._t, now
        delta = self._target - self._pos
        step = self.speed * dt
        if abs(delta) <= step:
            self._pos = self._target
        else:
            self._pos += step if delta > 0 else -step

    def write(self, data: bytes) -> None:
        if not self._open:
            raise RuntimeError("simulatore non aperto")
        text = data.decode("ascii", "replace")
        self.sent.append(text)
        if not self.answer_ai1:
            return
        self._advance()
        for m in re.finditer(r"AP1(\d{3})", text):
            want = float(m.group(1))
            self._target = want * (1.0 + self.scale_error)
        if "AI1" in text:
            self._rx += f";{int(round(self._pos)) % 360:03d}\r".encode()

    def read(self, size: int = 64) -> bytes:
        out = bytes(self._rx[:size])
        del self._rx[:size]
        return out

    def reset_input(self) -> None:
        self._rx.clear()

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def simulated_bearing(self) -> float:
        self._advance()
        return self._pos % 360.0


def available_ports() -> List[str]:
    """Elenco delle porte seriali del sistema (vuoto se pyserial manca)."""
    if not HAVE_SERIAL or list_ports is None:
        return []
    try:
        return [p.device for p in list_ports.comports()]
    except Exception:  # pragma: no cover
        return []


# --------------------------------------------------------------------------
# Geometria del rotore
# --------------------------------------------------------------------------

def bearing_to_rotor(bearing: float, cfg: RotorConfig,
                     near: Optional[float] = None) -> Optional[float]:
    """
    Converte un azimut geografico nella coordinata interna del rotore
    (0 = fermo meccanico, crescente in senso orario).

    Restituisce None se l'azimut non e' raggiungibile.
    Con escursione > 360 gradi (rotori con overlap) sceglie la soluzione
    piu' vicina a `near` (coordinata rotore corrente).
    """
    u = normalize_deg(bearing - cfg.range_start)
    candidates = [u]
    # Con escursione >= 360 gradi lo stesso azimut puo' essere raggiunto anche
    # dall'altro lato del fermo. Il caso limite e' l'azimut del fermo stesso
    # (u = 0), raggiungibile sia a inizio sia a fine corsa.
    if cfg.range_span >= 360.0 and u + 360.0 <= cfg.range_span + 1e-9:
        candidates.append(u + 360.0)
    candidates = [c for c in candidates if 0.0 <= c <= cfg.range_span]
    if not candidates:
        return None
    if near is None or len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda c: abs(c - near))


def rotor_to_bearing(u: float, cfg: RotorConfig) -> float:
    """Converte la coordinata interna del rotore in azimut geografico."""
    return normalize_deg(u + cfg.range_start)


def clamp_rotor(u: float, cfg: RotorConfig) -> tuple:
    """
    Applica il margine di sicurezza dal fermo meccanico.

    Restituisce (u_limitata, e_stata_limitata). Il margine vale a entrambi
    gli estremi della corsa; se e' cosi' grande da non lasciare corsa utile
    viene ignorato.
    """
    lo = max(0.0, cfg.safety_margin)
    hi = cfg.range_span - lo
    if hi <= lo:
        return (u, False)
    if u < lo:
        return (lo, True)
    if u > hi:
        return (hi, True)
    return (u, False)


def blind_sector(cfg: RotorConfig) -> Optional[tuple]:
    """
    Settore di azimut non comandabili a causa del margine di sicurezza,
    come (da_bearing, a_bearing) in senso orario. None se non ce n'e'.
    """
    lo = max(0.0, cfg.safety_margin)
    if lo <= 0.0 or cfg.range_span - lo <= lo:
        return None
    if cfg.range_span >= 360.0:
        # i due estremi si toccano: un unico settore a cavallo del fermo
        return (rotor_to_bearing(cfg.range_span - lo, cfg),
                rotor_to_bearing(lo, cfg))
    return (rotor_to_bearing(cfg.range_span - lo, cfg),
            rotor_to_bearing(lo, cfg))


# --------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------

_AI1_RE = re.compile(rb"(\d{1,3})")


def parse_ai1_response(data: bytes) -> Optional[float]:
    """
    Interpreta la risposta a AI1;.

    Il DCU-1 risponde ';xxx'; alcuni cloni omettono il punto e virgola o
    aggiungono CR/LF. Si prende il primo gruppo di cifre.
    """
    if not data:
        return None
    m = _AI1_RE.search(data)
    if not m:
        return None
    try:
        return float(int(m.group(1)) % 360)
    except ValueError:
        return None


@dataclass
class RotorState:
    connected: bool = False
    current: float = 0.0          # azimut geografico (letto o stimato)
    target: Optional[float] = None
    moving: bool = False
    last_command: str = ""
    last_error: str = ""
    history: List[str] = field(default_factory=list)
    # lettura di posizione
    reading: bool = False         # polling attivo e funzionante
    last_read: Optional[float] = None
    last_read_at: float = 0.0
    read_failures: int = 0
    last_raw_response: str = ""


class Dcu1Controller:
    """
    Controller DCU-1 con stima di posizione (nessuna lettura dal rotore).

    Uso tipico:
        ctrl = Dcu1Controller(cfg)
        ctrl.connect()
        ctrl.goto(135.0)
        ...  # chiamare ctrl.tick() periodicamente (es. ogni 200 ms)
        ctrl.stop()
    """

    def __init__(self, cfg: Optional[RotorConfig] = None,
                 transport: Optional[RotorTransport] = None,
                 on_event: Optional[Callable[[str], None]] = None) -> None:
        self.cfg = cfg or RotorConfig()
        self._transport = transport
        self._auto_transport = transport is None   # creato da noi -> ricreabile
        self._on_event = on_event
        self._lock = threading.RLock()
        self.state = RotorState()
        # posizione iniziale stimata: meta' escursione (con fermo a 180 gradi
        # corrisponde al Nord). Va comunque ricalibrata dall'utente.
        self._u_current = min(self.cfg.range_span, 360.0) / 2.0
        self._u_target: Optional[float] = None
        self._last_tick = time.monotonic()
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_stop = threading.Event()
        self._margin_hits = 0

    # -- eventi -----------------------------------------------------------
    def _emit(self, msg: str) -> None:
        self.state.history.append(msg)
        if len(self.state.history) > 500:
            del self.state.history[:-500]
        log.debug(msg)
        if self._on_event:
            try:
                self._on_event(msg)
            except Exception:  # pragma: no cover
                pass

    # -- connessione ------------------------------------------------------
    def connect(self) -> bool:
        with self._lock:
            try:
                if self._transport is None:
                    self._auto_transport = True
                    if self.cfg.port:
                        self._transport = SerialTransport(self.cfg)
                    else:
                        self._transport = SimulatedTransport()
                elif self._transport.is_open:
                    self._transport.close()
                self._transport.open()
                self.state.connected = True
                self.state.last_error = ""
                self._last_tick = time.monotonic()
                self._emit(f"Connesso ({self._transport.name} "
                           f"{self.cfg.port or 'demo'} @ {self.cfg.baudrate})")
                self.start_polling()
                return True
            except Exception as exc:
                if self._auto_transport:
                    self._transport = None
                self.state.connected = False
                self.state.last_error = str(exc)
                self._emit(f"ERRORE connessione: {exc}")
                return False

    def disconnect(self) -> None:
        self.stop_polling()
        with self._lock:
            if self._transport is not None:
                try:
                    self._transport.close()
                except Exception:
                    pass
            if self._auto_transport:
                # il trasporto verra' ricreato dalla configurazione corrente
                self._transport = None
            self.state.connected = False
            self.state.moving = False

    @property
    def transport(self) -> Optional[RotorTransport]:
        return self._transport

    # -- comandi ----------------------------------------------------------
    def _send(self, payload: str) -> bool:
        if self._transport is None or not self._transport.is_open:
            self.state.last_error = "non connesso"
            self._emit(f"NON INVIATO ({payload}): rotore non connesso")
            return False
        try:
            self._transport.write(payload.encode("ascii", "replace"))
            self.state.last_command = payload
            self._emit(f"TX: {payload}")
            return True
        except Exception as exc:
            self.state.last_error = str(exc)
            self._emit(f"ERRORE TX: {exc}")
            return False

    def goto(self, bearing: float, force: bool = False) -> bool:
        """
        Invia la rotazione verso `bearing` (azimut geografico, gradi).

        force=True ignora la soglia `min_move`.
        """
        with self._lock:
            bearing = normalize_deg(bearing)
            u = bearing_to_rotor(bearing, self.cfg, near=self._u_current)
            if u is None:
                self.state.last_error = (
                    f"{bearing:.0f}° fuori dall'escursione del rotore")
                self._emit(f"IGNORATO: {self.state.last_error}")
                return False

            u, clamped = clamp_rotor(u, self.cfg)
            if clamped:
                requested = bearing
                bearing = rotor_to_bearing(u, self.cfg)
                self._emit(
                    f"LIMITATO: {requested:.0f}° troppo vicino al fermo "
                    f"({self.cfg.range_start:.0f}°), comando portato a "
                    f"{bearing:.0f}° (margine {self.cfg.safety_margin:.0f}°)")

            if not force and abs(u - self._u_current) < self.cfg.min_move:
                self._emit(f"IGNORATO: differenza < {self.cfg.min_move:.0f}°")
                return False

            ok = self._send_goto(bearing)
            if ok:
                self._u_target = u
                self.state.target = bearing
                self.state.moving = True
                self._last_tick = time.monotonic()
            return ok

    def _send_goto(self, bearing: float) -> bool:
        """Trasmette la coppia AP1/AM1 verso `bearing` (gia' normalizzato)."""
        term = self.cfg.terminator
        cmd = int(round(normalize_deg(bearing + self.cfg.offset))) % 360
        if self.cfg.send_move_with_target:
            return self._send(f"AP1{cmd:03d}{term}AM1{term}")
        if not self._send(f"AP1{cmd:03d}{term}"):
            return False
        if self.cfg.command_gap > 0:
            time.sleep(self.cfg.command_gap)
        return self._send(f"AM1{term}")

    def stop(self, blocking: bool = False) -> bool:
        """
        Arresta la rotazione.

        Due accorgimenti nati dal comportamento reale di alcuni DCU-1:

        * il comando viene ripetuto piu' volte a distanza di qualche decimo
          di secondo, perche' il controller scarta i comandi che riceve
          mentre sta eseguendo la sequenza di avvio (sblocco del freno e
          controrotazione), che dura qualche secondo;
        * `AM1;` viene inviato SOLO se il rotore risulta in movimento: a
          rotore fermo farebbe sbloccare il freno e ripartire la meccanica
          per nulla.

        La sequenza gira in un thread separato per non congelare l'interfaccia:
        `blocking=True` la esegue subito (usato nei test).
        """
        with self._lock:
            was_moving = self.state.moving
            here = self.current_bearing
            u = bearing_to_rotor(here, self.cfg, near=self._u_current)
            if u is not None:
                u, _ = clamp_rotor(u, self.cfg)
                here = rotor_to_bearing(u, self.cfg)

            strategy = (self.cfg.stop_strategy or "command").lower()
            repeats = max(1, int(self.cfg.stop_repeat))

            # lo stato interno si ferma subito, comunque vada la trasmissione
            self._u_target = None
            self.state.target = None
            self.state.moving = False
            self._margin_hits = 0

            self._emit(f"STOP ({strategy}, {repeats} tentativi) — "
                       f"posizione {here:.0f}°"
                       + ("" if was_moving else ", rotore già fermo: niente AM1"))

        if blocking:
            return self._stop_sequence(strategy, here, was_moving, repeats)
        threading.Thread(target=self._stop_sequence, daemon=True,
                         name="dcu1-stop",
                         args=(strategy, here, was_moving, repeats)).start()
        return True

    def _stop_sequence(self, strategy: str, here: float, was_moving: bool,
                       repeats: int) -> bool:
        term = self.cfg.terminator
        gap = max(0.02, self.cfg.command_gap)
        cmd = int(round(normalize_deg(here + self.cfg.offset))) % 360
        ok = False

        for attempt in range(repeats):
            if attempt:
                time.sleep(max(0.05, self.cfg.stop_repeat_gap))
            if not self.state.connected:
                break

            if strategy in ("command", "both"):
                ok = self._send(self.cfg.stop_command) or ok

            if strategy in ("target_only", "goto_current", "both"):
                if strategy == "both":
                    time.sleep(gap)
                ok = self._send(f"AP1{cmd:03d}{term}") or ok
                # AM1 solo se stava davvero girando: a rotore fermo
                # sbloccherebbe il freno senza motivo
                if was_moving and strategy in ("goto_current", "both"):
                    time.sleep(gap)
                    ok = self._send(f"AM1{term}") or ok

        return ok

    def send_raw(self, text: str, read_timeout: float = 0.4) -> str:
        """
        Invia una stringa qualsiasi al controller e restituisce cio' che
        risponde entro `read_timeout`. Serve per la diagnostica manuale.
        Le sequenze \\r e \\n scritte a mano vengono interpretate.
        """
        payload = (text.replace("\\r", "\r").replace("\\n", "\n")
                       .replace("\\t", "\t"))
        with self._lock:
            if self._transport is None or not self._transport.is_open:
                self.state.last_error = "non connesso"
                self._emit("NON INVIATO: rotore non connesso")
                return ""
            try:
                self._transport.reset_input()
                self._transport.write(payload.encode("ascii", "replace"))
                self._emit(f"TX grezzo: {payload!r}")
            except Exception as exc:
                self._emit(f"ERRORE TX grezzo: {exc}")
                return ""
            transport = self._transport

        deadline = time.monotonic() + max(0.05, read_timeout)
        buf = bytearray()
        while time.monotonic() < deadline:
            with self._lock:
                try:
                    chunk = transport.read(64)
                except Exception:
                    break
            if chunk:
                buf += chunk
            else:
                time.sleep(0.02)
        out = bytes(buf).decode("ascii", "replace")
        if out:
            self._emit(f"RX grezzo: {out!r}")
        return out

    # -- lettura di posizione (AI1;) --------------------------------------
    def query_position(self, timeout: Optional[float] = None) -> Optional[float]:
        """
        Invia AI1; e aspetta la risposta del controller.

        Restituisce l'azimut letto, oppure None se il controller non risponde
        (tipico se il cavo ha solo TX e massa). La risposta grezza resta in
        `state.last_raw_response` per la diagnostica.
        """
        timeout = self.cfg.read_timeout if timeout is None else timeout
        with self._lock:
            if self._transport is None or not self._transport.is_open:
                self.state.last_error = "non connesso"
                return None
            try:
                self._transport.reset_input()
                self._transport.write(f"AI1{self.cfg.terminator}".encode("ascii"))
            except Exception as exc:
                self.state.last_error = str(exc)
                self._emit(f"ERRORE invio AI1: {exc}")
                return None
            transport = self._transport

        deadline = time.monotonic() + max(0.05, timeout)
        buf = bytearray()
        while time.monotonic() < deadline:
            try:
                with self._lock:
                    chunk = transport.read(64)
            except Exception:
                break
            if chunk:
                buf += chunk
                value = parse_ai1_response(bytes(buf))
                if value is not None:
                    self.state.last_raw_response = bytes(buf).decode(
                        "ascii", "replace")
                    self.state.last_read = value
                    self.state.last_read_at = time.time()
                    return value
            else:
                time.sleep(0.02)

        self.state.last_raw_response = bytes(buf).decode("ascii", "replace")
        self.state.read_failures += 1
        return None

    def _apply_measured(self, bearing: float) -> None:
        """Allinea la posizione interna alla lettura del controller."""
        with self._lock:
            u = bearing_to_rotor(normalize_deg(bearing), self.cfg,
                                 near=self._u_current)
            if u is None:
                return
            self._u_current = u
            self.state.current = self.current_bearing
            if self._u_target is not None and abs(u - self._u_target) <= 2.0:
                self.state.moving = False

            # protezione: la posizione reale e' entrata nel margine di sicurezza
            lo = max(0.0, self.cfg.safety_margin)
            hi = self.cfg.range_span - lo
            if lo > 0.0 and hi > lo and (u < lo or u > hi):
                self._margin_hits += 1
                if self._margin_hits >= 2:
                    self._margin_hits = 0
                    self._emit(f"ATTENZIONE: posizione reale {bearing:.0f}° "
                               f"dentro il margine di sicurezza dal fermo "
                               f"({self.cfg.range_start:.0f}°)")
                    if self.cfg.stop_on_margin and self.state.moving:
                        self._emit("Arresto automatico per protezione fermo")
                        self.stop()
            else:
                self._margin_hits = 0

    def _poll_loop(self) -> None:
        while not self._poll_stop.is_set():
            if self.cfg.read_position and self.state.connected:
                value = self.query_position()
                if value is not None:
                    self.state.reading = True
                    self._apply_measured(value)
                elif self.state.read_failures >= 3:
                    if self.state.reading:
                        self._emit("Lettura di posizione persa: torno alla stima")
                    self.state.reading = False
            self._poll_stop.wait(max(0.2, self.cfg.poll_interval))

    def start_polling(self) -> None:
        self.stop_polling()
        if not self.cfg.read_position:
            return
        self._poll_stop.clear()
        self.state.read_failures = 0
        self._poll_thread = threading.Thread(target=self._poll_loop,
                                             daemon=True, name="dcu1-poll")
        self._poll_thread.start()
        self._emit(f"Lettura di posizione attiva (AI1; ogni "
                   f"{self.cfg.poll_interval:.1f} s)")

    def stop_polling(self) -> None:
        self._poll_stop.set()
        t = self._poll_thread
        self._poll_thread = None
        if t is not None and t.is_alive():
            t.join(timeout=1.5)
        self.state.reading = False

    # -- stima di posizione ----------------------------------------------
    def tick(self) -> None:
        """Aggiorna la posizione stimata. Chiamare periodicamente."""
        with self._lock:
            now = time.monotonic()
            dt = now - self._last_tick
            self._last_tick = now
            if self.state.reading:
                # la posizione arriva dal controller: niente stima
                return
            if not self.state.moving or self._u_target is None:
                return
            step = max(0.0, self.cfg.speed_deg_s) * dt
            delta = self._u_target - self._u_current
            if abs(delta) <= step or step == 0.0:
                self._u_current = self._u_target
                self.state.moving = False
                self._emit(f"Arrivato a {self.current_bearing:.0f}° (stima)")
            else:
                self._u_current += step if delta > 0 else -step
            self.state.current = self.current_bearing

    def set_current_bearing(self, bearing: float) -> None:
        """Ricalibra manualmente la posizione stimata (senza muovere il rotore)."""
        with self._lock:
            u = bearing_to_rotor(normalize_deg(bearing), self.cfg,
                                 near=self._u_current)
            if u is None:
                return
            self._u_current = u
            self.state.current = self.current_bearing
            self._emit(f"Posizione ricalibrata a {self.current_bearing:.0f}°")

    @property
    def current_bearing(self) -> float:
        return rotor_to_bearing(self._u_current, self.cfg)

    @property
    def target_bearing(self) -> Optional[float]:
        return self.state.target

    def travel_to(self, bearing: float) -> Optional[float]:
        """Gradi di rotazione necessari per raggiungere `bearing`, None se irraggiungibile."""
        u = bearing_to_rotor(normalize_deg(bearing), self.cfg, near=self._u_current)
        if u is None:
            return None
        u, _ = clamp_rotor(u, self.cfg)
        return abs(u - self._u_current)

    def reachable_bearing(self, bearing: float) -> Optional[float]:
        """
        Azimut che il rotore raggiungerebbe davvero, tenuto conto del margine
        di sicurezza. Uguale a `bearing` se non serve limitare.
        """
        u = bearing_to_rotor(normalize_deg(bearing), self.cfg, near=self._u_current)
        if u is None:
            return None
        u, _ = clamp_rotor(u, self.cfg)
        return rotor_to_bearing(u, self.cfg)

    def eta_seconds(self, bearing: float) -> Optional[float]:
        t = self.travel_to(bearing)
        if t is None or self.cfg.speed_deg_s <= 0:
            return None
        return t / self.cfg.speed_deg_s
