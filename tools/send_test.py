#!/usr/bin/env python3
"""
send_test.py - Simulatore di WSJT-X e N1MM+ per provare DXRotator
senza avere i programmi (e la radio) in funzione.

Esempi:
    python tools/send_test.py wsjtx VK3ABC QF22
    python tools/send_test.py decode "CQ JA1XYZ PM95"
    python tools/send_test.py n1mm  ZL2ABC RE78
    python tools/send_test.py rotor 275
    python tools/send_test.py demo          # sequenza di stazioni sparse
"""

from __future__ import annotations

import socket
import struct
import sys
import time

MAGIC = 0xADBCCBDA
SCHEMA = 2


def _u32(v):
    return struct.pack(">I", v)


def _u64(v):
    return struct.pack(">Q", v)


def _i32(v):
    return struct.pack(">i", v)


def _f64(v):
    return struct.pack(">d", v)


def _b(v):
    return struct.pack(">B", 1 if v else 0)


def _s(text: str) -> bytes:
    if text is None:
        return _u32(0xFFFFFFFF)
    raw = text.encode("utf-8")
    return _u32(len(raw)) + raw


def _header(mtype: int, ident: str = "WSJT-X") -> bytes:
    return _u32(MAGIC) + _u32(SCHEMA) + _u32(mtype) + _s(ident)


def wsjtx_status(dx_call: str, dx_grid: str, de_call: str = "IK0TEST",
                 de_grid: str = "JN61fu", freq: int = 14074000,
                 mode: str = "FT8") -> bytes:
    return (
        _header(1)
        + _u64(freq)
        + _s(mode)
        + _s(dx_call)
        + _s("-12")            # report
        + _s(mode)             # tx mode
        + _b(True)             # tx enabled
        + _b(False)            # transmitting
        + _b(True)             # decoding
        + _u32(1500)           # rx df
        + _u32(1500)           # tx df
        + _s(de_call)
        + _s(de_grid)
        + _s(dx_grid)
        + _b(False)            # watchdog
        + _s("")               # sub mode
        + _b(False)            # fast mode
        + struct.pack(">B", 0)  # special op mode
        + _u32(0)              # freq tolerance
        + _u32(15)             # T/R period
        + _s("Default")        # configuration name
        + _s(f"{de_call} {dx_call} {de_grid}")
    )


def wsjtx_decode(message: str, mode: str = "FT8", snr: int = -10) -> bytes:
    return (
        _header(2)
        + _b(True)             # new
        + _u32(43200000)       # ms dalla mezzanotte
        + _i32(snr)
        + _f64(0.2)
        + _u32(1200)
        + _s(mode)
        + _s(message)
        + _b(False)            # low confidence
        + _b(False)            # off air
    )


def n1mm_contact(call: str, grid: str, freq_khz: float = 14074.0,
                 mode: str = "FT8") -> bytes:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<contactinfo>
  <app>N1MM</app>
  <contestname>DX</contestname>
  <timestamp>{time.strftime('%Y-%m-%d %H:%M:%S')}</timestamp>
  <mycall>IK0TEST</mycall>
  <band>20</band>
  <rxfreq>{int(freq_khz * 100)}</rxfreq>
  <txfreq>{int(freq_khz * 100)}</txfreq>
  <mode>{mode}</mode>
  <call>{call}</call>
  <countryprefix>{call[:2]}</countryprefix>
  <gridsquare>{grid}</gridsquare>
  <continent>OC</continent>
</contactinfo>"""
    return xml.encode("utf-8")


def n1mm_rotor(azimuth: float, name: str = "Rotor1") -> bytes:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<N1MMRotor>
  <rotor>
    <goazi>{azimuth:.1f}</goazi>
    <offset>0.0</offset>
    <bidirectional>0</bidirectional>
    <freqband>14</freqband>
    <radio>1</radio>
    <rotorname>{name}</rotorname>
  </rotor>
</N1MMRotor>"""
    return xml.encode("utf-8")


def send(data: bytes, port: int, host: str = "127.0.0.1") -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(data, (host, port))
    s.close()
    print(f"inviati {len(data)} byte a {host}:{port}")


DEMO = [
    ("VK3ABC", "QF22"),      # Australia
    ("JA1XYZ", "PM95"),      # Giappone
    ("W6ABC", "DM03"),       # California
    ("ZS6ABC", "KG44"),      # Sudafrica
    ("LU1ABC", "GF05"),      # Argentina
    ("VE3ABC", "FN03"),      # Canada
]


def main(argv) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1].lower()

    if cmd == "wsjtx":
        call = argv[2] if len(argv) > 2 else "VK3ABC"
        grid = argv[3] if len(argv) > 3 else ""
        send(wsjtx_status(call, grid), 2237)
    elif cmd == "decode":
        msg = argv[2] if len(argv) > 2 else "CQ VK3ABC QF22"
        send(wsjtx_decode(msg), 2237)
    elif cmd == "n1mm":
        call = argv[2] if len(argv) > 2 else "ZL2ABC"
        grid = argv[3] if len(argv) > 3 else ""
        send(n1mm_contact(call, grid), 12060)
    elif cmd == "rotor":
        az = float(argv[2]) if len(argv) > 2 else 90.0
        send(n1mm_rotor(az), 12040)
    elif cmd == "demo":
        for call, grid in DEMO:
            print(f"--- {call} {grid}")
            send(wsjtx_status(call, grid), 2237)
            time.sleep(6)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
