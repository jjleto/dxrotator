"""
headless.py - Modalita' senza interfaccia grafica.

Usa la stessa configurazione della GUI (config.json) ed e' utile su
Raspberry Pi o su macchine senza display: ascolta WSJT-X/N1MM, calcola
l'azimut e comanda il rotore applicando la stessa soglia di auto-rotazione.
"""

from __future__ import annotations

import queue
import signal
import time

from .config import AppConfig
from .engine import RotatorEngine
from .rotor import RotorConfig
from .sources import N1mmDecoder, UdpListener, WsjtxDecoder


def run_headless() -> int:
    cfg = AppConfig.load()
    engine = RotatorEngine(cfg)
    engine.controller.cfg = RotorConfig(
        port=cfg.serial_port,
        baudrate=cfg.baudrate,
        terminator=cfg.terminator,
        stop_command=cfg.stop_command,
        stop_strategy=cfg.stop_strategy,
        stop_repeat=cfg.stop_repeat,
        stop_repeat_gap=cfg.stop_repeat_gap,
        send_move_with_target=cfg.send_move_with_target,
        command_gap=cfg.command_gap,
        settle_delay=cfg.settle_delay,
        range_start=cfg.rotor_range_start,
        range_span=cfg.rotor_range_span,
        offset=cfg.rotor_offset,
        speed_deg_s=cfg.rotor_speed,
        min_move=cfg.rotor_min_move,
        safety_margin=cfg.rotor_safety_margin,
        read_position=cfg.rotor_read_position,
        poll_interval=cfg.rotor_poll_interval,
        stop_on_margin=cfg.rotor_stop_on_margin,
    )
    engine.controller._on_event = lambda m: print(f"[rotore] {m}", flush=True)
    engine.controller.connect()

    q: "queue.Queue" = queue.Queue()
    listeners = []
    if cfg.wsjtx_enabled:
        listeners.append(UdpListener("WSJT-X", cfg.wsjtx_host, cfg.wsjtx_port,
                                     WsjtxDecoder(), q.put,
                                     lambda m: print(m, flush=True)))
    if cfg.n1mm_enabled:
        listeners.append(UdpListener("N1MM", cfg.n1mm_host, cfg.n1mm_port,
                                     N1mmDecoder(), q.put,
                                     lambda m: print(m, flush=True)))
    if cfg.n1mm_rotor_enabled:
        listeners.append(UdpListener("N1MM-rotore", cfg.n1mm_rotor_host,
                                     cfg.n1mm_rotor_port, N1mmDecoder(), q.put,
                                     lambda m: print(m, flush=True)))
    for l in listeners:
        l.start()
        print(f"Ascolto {l.label} su UDP {l.host}:{l.port}", flush=True)

    print(f"Auto-rotazione: {'ON' if cfg.auto_rotate else 'OFF'} "
          f"(soglia {cfg.auto_threshold:.0f}°)", flush=True)

    running = {"go": True}

    def _stop(*_a):
        running["go"] = False

    signal.signal(signal.SIGINT, _stop)
    try:
        signal.signal(signal.SIGTERM, _stop)
    except (AttributeError, ValueError):
        pass

    last_tick = time.monotonic()
    while running["go"]:
        try:
            target = q.get(timeout=0.2)
        except queue.Empty:
            target = None
        if time.monotonic() - last_tick > 0.2:
            engine.controller.tick()
            last_tick = time.monotonic()
        if target is None:
            continue
        sol, sent, reason = engine.handle_target(target)
        if sol is None:
            print(f"  {target.label()}: {reason}", flush=True)
            continue
        flag = "RUOTA" if sent else "     "
        print(f"{flag} {sol.describe():<40} {sol.azimuth:6.1f}°  "
              f"({sol.precision}) — {reason}", flush=True)

    for l in listeners:
        l.stop()
    engine.controller.disconnect()
    print("Terminato.")
    return 0
