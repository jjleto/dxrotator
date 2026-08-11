"""Punto di ingresso: python -m dxrotator"""

import argparse
import logging
import sys


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="dxrotator",
        description="Controllo rotore Hy-Gain TX2 via DCU-1 con dati da "
                    "WSJT-X e N1MM+.")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="log dettagliato sulla console")
    ap.add_argument("--headless", action="store_true",
                    help="esegue senza GUI: stampa gli azimut calcolati "
                         "e comanda il rotore secondo la configurazione salvata")
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    if args.version:
        from . import __version__
        print(f"DXRotator {__version__}")
        return 0

    if args.headless:
        from .headless import run_headless
        return run_headless()

    try:
        from .gui import run
    except ImportError as exc:
        print("PySide6 non disponibile:", exc, file=sys.stderr)
        print("Installare con:  pip install PySide6 pyserial", file=sys.stderr)
        print("Oppure usare la modalità senza interfaccia:  "
              "python -m dxrotator --headless", file=sys.stderr)
        return 2
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
