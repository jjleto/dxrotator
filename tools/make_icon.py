#!/usr/bin/env python3
"""
make_icon.py - Genera l'icona dell'applicazione.

Disegna una rosa dei venti con la stessa grafica del quadrante e produce:

    icon.png              1024x1024, sorgente per tutto il resto
    icon.iconset/         le dimensioni richieste da macOS
    icon.icns             bundle macOS (solo su macOS, tramite iconutil)
    icon.ico              icona Windows (se Pillow e' installato)

    python tools/make_icon.py

Va rilanciato solo se si vuole cambiare l'aspetto dell'icona: i file
generati vengono versionati.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication,  # noqa: E402
                           QImage, QPainter, QPen, QPolygonF)

SIZE = 1024
# dimensioni richieste da macOS: (lato in punti, suffisso)
ICONSET = [(16, "16x16"), (32, "16x16@2x"), (32, "32x32"), (64, "32x32@2x"),
           (128, "128x128"), (256, "128x128@2x"), (256, "256x256"),
           (512, "256x256@2x"), (512, "512x512"), (1024, "512x512@2x")]


def _pt(cx: float, cy: float, r: float, deg: float) -> QPointF:
    a = math.radians(deg - 90.0)
    return QPointF(cx + r * math.cos(a), cy + r * math.sin(a))


def draw_icon(size: int = SIZE) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)

    cx = cy = size / 2.0
    r = size * 0.46

    # disco di fondo con bordo
    p.setBrush(QBrush(QColor(24, 28, 34)))
    p.setPen(QPen(QColor(58, 66, 78), size * 0.022))
    p.drawEllipse(QPointF(cx, cy), r, r)

    # tacche ogni 15 gradi, marcate ai quattro punti cardinali
    for deg in range(0, 360, 15):
        major = deg % 90 == 0
        length = r * (0.15 if major else 0.08)
        p.setPen(QPen(QColor(215, 222, 232) if major else QColor(120, 132, 148),
                      size * (0.016 if major else 0.008), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(_pt(cx, cy, r - length, deg), _pt(cx, cy, r - size * 0.03, deg))

    # tacca del fermo meccanico, come sul quadrante
    p.setPen(QPen(QColor(230, 170, 60), size * 0.018, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(_pt(cx, cy, r * 0.80, 335), _pt(cx, cy, r * 0.99, 335))

    # lancetta del bersaglio, tratteggiata
    p.setPen(QPen(QColor(255, 105, 97), size * 0.016, Qt.DashLine, Qt.RoundCap))
    p.drawLine(QPointF(cx, cy), _pt(cx, cy, r * 0.62, 288))

    # lancetta della posizione, con punta piena
    green = QColor(80, 200, 120)
    p.setPen(QPen(green, size * 0.030, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(cx, cy), _pt(cx, cy, r * 0.52, 42))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(green))
    p.drawPolygon(QPolygonF([_pt(cx, cy, r * 0.74, 42),
                             _pt(cx, cy, r * 0.46, 42 - 9),
                             _pt(cx, cy, r * 0.46, 42 + 9)]))

    # mozzo
    p.setBrush(QBrush(QColor(45, 52, 62)))
    p.setPen(QPen(QColor(58, 66, 78), size * 0.014))
    p.drawEllipse(QPointF(cx, cy), r * 0.20, r * 0.20)

    # N cardinale
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(size * 0.125))
    p.setFont(f)
    p.setPen(QPen(QColor(225, 232, 242)))
    # dentro la corona delle tacche, non sopra
    p.drawText(QRectF(cx - size * 0.12, cy - r * 0.80, size * 0.24, size * 0.16),
               Qt.AlignCenter, "N")
    p.end()
    return img


def main() -> int:
    QGuiApplication(sys.argv)

    master = draw_icon(SIZE)
    png = os.path.join(HERE, "icon.png")
    master.save(png)
    print("scritto", os.path.relpath(png, HERE))

    iconset = os.path.join(HERE, "icon.iconset")
    os.makedirs(iconset, exist_ok=True)
    for px, name in ICONSET:
        scaled = draw_icon(px) if px >= 128 else master.scaled(
            px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        scaled.save(os.path.join(iconset, f"icon_{name}.png"))
    print(f"scritte {len(ICONSET)} dimensioni in icon.iconset/")

    # macOS: assembla il .icns
    if sys.platform == "darwin":
        icns = os.path.join(HERE, "icon.icns")
        try:
            subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns],
                           check=True)
            print("scritto icon.icns")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print("iconutil non riuscito:", exc, file=sys.stderr)

    # Windows: .ico multi-risoluzione
    try:
        from PIL import Image
    except ImportError:
        print("Pillow non installato: icon.ico non generato "
              "(serve solo per il pacchetto Windows)")
        return 0

    ico = os.path.join(HERE, "icon.ico")
    Image.open(png).save(ico, sizes=[(16, 16), (32, 32), (48, 48),
                                     (64, 64), (128, 128), (256, 256)])
    print("scritto icon.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
