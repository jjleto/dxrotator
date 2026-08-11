"""
compass.py - Rosa dei venti interattiva (PySide6).

Mostra:
  * posizione stimata del rotore (lancetta piena)
  * azimut della stazione DX (lancetta tratteggiata + punta)
  * settore della soglia di auto-rotazione attorno alla posizione attuale
  * fermo meccanico del rotore
Cliccando sul quadrante si emette il segnale `bearingClicked`.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
                           QPolygonF)
from PySide6.QtWidgets import QWidget

from .geo import normalize_deg

CARDINALS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]


class CompassWidget(QWidget):
    bearingClicked = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # minimo molto basso: il quadrante si adatta allo spazio disponibile e
        # non deve impedire di rimpicciolire la finestra
        self.setMinimumSize(110, 110)
        self.current: float = 0.0
        self.target: Optional[float] = None
        self.threshold: float = 30.0
        self.show_threshold: bool = True
        self.stop_bearing: Optional[float] = 180.0
        self.span: float = 360.0
        self.blind: Optional[tuple] = None   # (da_bearing, a_bearing) orario
        self.moving: bool = False
        self.label: str = ""
        self.setCursor(Qt.CrossCursor)
        self.setToolTip("Clicca sul quadrante per ruotare verso quella direzione")

    # ------------------------------------------------------------------
    def set_state(self, current: float, target: Optional[float],
                  threshold: float, moving: bool, label: str = "",
                  stop_bearing: Optional[float] = None,
                  span: float = 360.0,
                  blind: Optional[tuple] = None) -> None:
        self.current = normalize_deg(current)
        self.target = None if target is None else normalize_deg(target)
        self.threshold = threshold
        self.moving = moving
        self.label = label
        self.stop_bearing = stop_bearing
        self.span = span
        self.blind = blind
        self.update()

    # ------------------------------------------------------------------
    def _geom(self):
        w, h = self.width(), self.height()
        size = min(w, h) - 16
        cx, cy = w / 2.0, h / 2.0
        return cx, cy, size / 2.0

    @staticmethod
    def _pt(cx: float, cy: float, r: float, deg: float) -> QPointF:
        a = math.radians(deg - 90.0)
        return QPointF(cx + r * math.cos(a), cy + r * math.sin(a))

    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        cx, cy, r = self._geom()
        dx = event.position().x() - cx
        dy = event.position().y() - cy
        if math.hypot(dx, dy) > r * 1.05:
            return
        deg = normalize_deg(math.degrees(math.atan2(dx, -dy)))
        self.bearingClicked.emit(round(deg))

    # ------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx, cy, r = self._geom()

        bg = QColor(24, 28, 34)
        ring = QColor(58, 66, 78)
        text = QColor(215, 222, 232)
        dim = QColor(130, 140, 155)
        cur_col = QColor(80, 200, 120)
        tgt_col = QColor(255, 105, 97)
        thr_col = QColor(80, 200, 120, 40)

        # sfondo
        p.setBrush(QBrush(bg))
        p.setPen(QPen(ring, 2))
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

        # zona cieca attorno al fermo meccanico (margine di sicurezza)
        if self.blind:
            a, b = self.blind
            span = normalize_deg(b - a)
            if span > 0.01:
                path = QPainterPath()
                path.moveTo(QPointF(cx, cy))
                rect = QRectF(cx - r * 0.94, cy - r * 0.94, 1.88 * r, 1.88 * r)
                path.arcTo(rect, 90.0 - (a + span), span)
                path.closeSubpath()
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(190, 60, 55, 55)))
                p.drawPath(path)

        # settore della soglia
        if self.show_threshold and self.threshold > 0:
            path = QPainterPath()
            path.moveTo(QPointF(cx, cy))
            rect = QRectF(cx - r * 0.94, cy - r * 0.94, 1.88 * r, 1.88 * r)
            start = 90.0 - (self.current + self.threshold)
            path.arcTo(rect, start, 2 * self.threshold)
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(thr_col))
            p.drawPath(path)

        # tacche
        for deg in range(0, 360, 2):
            major = deg % 30 == 0
            mid = deg % 10 == 0
            if not (major or mid) and r < 140:
                continue
            length = r * (0.12 if major else (0.07 if mid else 0.035))
            width = 2.0 if major else 1.0
            col = text if major else dim
            p.setPen(QPen(col, width))
            p.drawLine(self._pt(cx, cy, r - length, deg), self._pt(cx, cy, r - 2, deg))

        # numeri ogni 30 gradi
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, r * 0.062))
        p.setFont(f)
        p.setPen(QPen(dim))
        for deg in range(0, 360, 30):
            if deg % 90 == 0:
                continue
            pt = self._pt(cx, cy, r * 0.79, deg)
            p.drawText(QRectF(pt.x() - 18, pt.y() - 10, 36, 20),
                       Qt.AlignCenter, str(deg))

        # cardinali
        f2 = QFont(self.font())
        f2.setBold(True)
        f2.setPointSizeF(max(9.0, r * 0.10))
        p.setFont(f2)
        p.setPen(QPen(text))
        for i, name in enumerate(CARDINALS):
            if i % 2:
                continue
            pt = self._pt(cx, cy, r * 0.79, i * 45)
            p.drawText(QRectF(pt.x() - 20, pt.y() - 12, 40, 24),
                       Qt.AlignCenter, name)

        # fermo meccanico
        if self.stop_bearing is not None and self.span <= 360.5:
            p.setPen(QPen(QColor(230, 170, 60), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(self._pt(cx, cy, r * 0.86, self.stop_bearing),
                       self._pt(cx, cy, r * 1.0, self.stop_bearing))

        # lancetta target
        if self.target is not None:
            pen = QPen(tgt_col, 2.5, Qt.DashLine, Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(cx, cy), self._pt(cx, cy, r * 0.80, self.target))
            tip = self._pt(cx, cy, r * 0.90, self.target)
            a = self._pt(cx, cy, r * 0.78, self.target - 4)
            b = self._pt(cx, cy, r * 0.78, self.target + 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(tgt_col))
            p.drawPolygon(QPolygonF([tip, a, b]))

        # lancetta corrente
        pen = QPen(cur_col, 4.0, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(cx, cy), self._pt(cx, cy, r * 0.68, self.current))
        tip = self._pt(cx, cy, r * 0.80, self.current)
        a = self._pt(cx, cy, r * 0.64, self.current - 6)
        b = self._pt(cx, cy, r * 0.64, self.current + 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(cur_col))
        p.drawPolygon(QPolygonF([tip, a, b]))

        # mozzo
        p.setBrush(QBrush(QColor(45, 52, 62)))
        p.setPen(QPen(ring, 2))
        p.drawEllipse(QPointF(cx, cy), r * 0.20, r * 0.20)

        # testo centrale
        f3 = QFont(self.font())
        f3.setBold(True)
        f3.setPointSizeF(max(12.0, r * 0.16))
        p.setFont(f3)
        p.setPen(QPen(cur_col if not self.moving else QColor(255, 200, 80)))
        p.drawText(QRectF(cx - r * 0.5, cy - r * 0.22, r, r * 0.28),
                   Qt.AlignCenter, f"{self.current:03.0f}°")

        f4 = QFont(self.font())
        f4.setPointSizeF(max(7.5, r * 0.065))
        p.setFont(f4)
        p.setPen(QPen(dim))
        sub = self.label or ("in rotazione" if self.moving else "fermo")
        p.drawText(QRectF(cx - r * 0.6, cy + r * 0.06, r * 1.2, r * 0.16),
                   Qt.AlignCenter, sub)
        p.end()
