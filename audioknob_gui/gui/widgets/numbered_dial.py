from __future__ import annotations

import math

from PySide6.QtCore import Property, QPoint, QPointF, QRectF, QEasingCurve, Qt, QPropertyAnimation
from PySide6.QtGui import QColor, QPainterPath, QPen, QPainter, QPixmap
from PySide6.QtWidgets import QDial


class NumberedDial(QDial):
    """Custom-rendered dial with numeric ring and animated knob rotation."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setNotchesVisible(True)
        self.setWrapping(False)
        self.setPageStep(1)
        self.setSingleStep(1)
        self.setFixedSize(320, 320)
        self._center_pixmap: QPixmap | None = None
        self._center_scale = 0.60
        self._display_ratio = self._value_ratio(float(self.value()))
        self._rotation_anim = QPropertyAnimation(self, b"displayRatio", self)
        self._rotation_anim.setDuration(120)
        self._rotation_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.valueChanged.connect(self._on_value_changed)

    def _span(self) -> int:
        span = int(self.maximum()) - int(self.minimum())
        return span if span > 0 else 1

    def _off_detent_enabled(self) -> bool:
        return int(self.minimum()) <= 0 and int(self.maximum()) >= 1

    def _ring_min(self) -> int:
        if self._off_detent_enabled():
            return 1
        return int(self.minimum())

    def _ring_span(self) -> int:
        return max(1, int(self.maximum()) - self._ring_min())

    def _step_ratio(self) -> float:
        return 1.0 / float(self._ring_span())

    def _value_ratio(self, value: float) -> float:
        value_f = float(value)
        if self._off_detent_enabled():
            if value_f <= 0.0:
                return -self._step_ratio()
            ratio = (value_f - 1.0) / float(self._ring_span())
        else:
            minimum = float(self.minimum())
            ratio = (value_f - minimum) / float(self._span())
        min_ratio = -self._step_ratio() if self._off_detent_enabled() else 0.0
        if ratio < min_ratio:
            return min_ratio
        if ratio > 1.0:
            return 1.0
        return ratio

    def _angle_for_ratio(self, ratio: float) -> float:
        # Increasing level rotates clockwise in screen coordinates.
        return 225.0 + (ratio * 270.0)

    def _clamp_ratio(self, ratio: float) -> float:
        min_ratio = -self._step_ratio() if self._off_detent_enabled() else 0.0
        if ratio < min_ratio:
            return min_ratio
        if ratio > 1.0:
            return 1.0
        return ratio

    def _get_display_ratio(self) -> float:
        return float(self._display_ratio)

    def _set_display_ratio(self, ratio: float) -> None:
        self._display_ratio = self._clamp_ratio(float(ratio))
        self.update()

    displayRatio = Property(float, _get_display_ratio, _set_display_ratio)

    def _on_value_changed(self, value: int) -> None:
        target = self._value_ratio(float(value))
        if abs(target - self._display_ratio) < 0.0001:
            self._set_display_ratio(target)
            return
        if self._rotation_anim.state() == QPropertyAnimation.Running:
            self._rotation_anim.stop()
        self._rotation_anim.setStartValue(self._display_ratio)
        self._rotation_anim.setEndValue(target)
        self._rotation_anim.start()

    def set_center_image(self, path: str) -> bool:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self._center_pixmap = pixmap
        self.update()
        return True

    def clear_center_image(self) -> None:
        self._center_pixmap = None
        self.update()

    def set_center_scale(self, scale: float) -> None:
        try:
            value = float(scale)
        except Exception:
            return
        self._center_scale = max(0.05, min(0.95, value))
        self.update()

    def _build_scalloped_path(self, radius: float, *, lobes: int = 8) -> QPainterPath:
        path = QPainterPath()
        samples = max(64, lobes * 24)
        for i in range(samples + 1):
            t = (2.0 * math.pi * i) / samples
            # Rounded lobe profile similar to Make Noise-style knob skirts.
            mod = 0.5 + (0.5 * math.cos(float(lobes) * t))
            r = radius * (0.91 + (0.10 * (mod ** 1.65)))
            x = r * math.cos(t)
            y = -r * math.sin(t)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        return path

    def paintEvent(self, event) -> None:
        minimum = int(self.minimum())
        maximum = int(self.maximum())
        span = maximum - minimum
        if span <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(10, 10, -10, -10)
        center = rect.center()
        cx = center.x()
        cy = center.y()
        dial_radius = min(rect.width(), rect.height()) * 0.50
        label_radius = dial_radius * 0.92
        knob_outer_radius = dial_radius * 0.57
        knob_inner_radius = knob_outer_radius * 0.87
        top_radius = knob_outer_radius * 0.68
        angle_deg = self._angle_for_ratio(self._display_ratio)

        # Numeric settings ring.
        painter.setPen(QColor("#d9d9d9"))
        font = painter.font()
        font.setPointSize(max(8, font.pointSize() + 1))
        painter.setFont(font)

        # Preserve original 1..11 label-ring orientation (min near lower-left, max near lower-right).
        start_deg = 225.0
        arc_deg = 270.0
        ring_min = self._ring_min()
        ring_span = self._ring_span()

        for value in range(ring_min, maximum + 1):
            ratio = (value - ring_min) / ring_span
            value_angle = start_deg - (ratio * arc_deg)
            value_rad = math.radians(value_angle)
            x = cx + (label_radius * math.cos(value_rad))
            y = cy - (label_radius * math.sin(value_rad))
            text = str(value)
            text_rect = painter.fontMetrics().boundingRect(text)
            text_rect.moveCenter(QPoint(int(round(x)), int(round(y))))
            painter.drawText(text_rect, Qt.AlignCenter, text)

        if self._off_detent_enabled():
            step_deg = arc_deg / float(ring_span)
            zero_angle = start_deg + step_deg
            zero_rad = math.radians(zero_angle)
            x = cx + (label_radius * math.cos(zero_rad))
            y = cy - (label_radius * math.sin(zero_rad))
            text_rect = painter.fontMetrics().boundingRect("0")
            text_rect.moveCenter(QPoint(int(round(x)), int(round(y))))
            painter.drawText(text_rect, Qt.AlignCenter, "0")

        # Knob ground shadow.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawEllipse(QPointF(cx + 2.2, cy + 3.2), knob_outer_radius, knob_outer_radius)

        # Outer fixed trim ring.
        painter.setBrush(QColor("#13161a"))
        painter.drawEllipse(QPointF(cx, cy), knob_outer_radius + 4.0, knob_outer_radius + 4.0)

        # Rotating knob body.
        painter.save()
        painter.translate(QPointF(cx, cy))
        painter.rotate(angle_deg)
        skirt_path = self._build_scalloped_path(knob_outer_radius, lobes=8)
        painter.setPen(QPen(QColor("#0f1114"), 1.1))
        painter.setBrush(QColor("#2e3137"))
        painter.drawPath(skirt_path)

        painter.setPen(QPen(QColor("#101217"), 1.0))
        painter.setBrush(QColor("#171a1f"))
        painter.drawEllipse(QPointF(0.0, 0.0), knob_inner_radius, knob_inner_radius)

        cap_color = QColor("#f2f2f2")
        painter.setPen(Qt.NoPen)
        painter.setBrush(cap_color)
        painter.drawEllipse(QPointF(0.0, 0.0), top_radius, top_radius)

        # White indicator bar from inside the center cap to slightly beyond the knob skirt.
        painter.save()
        # Phase-align pointer with the minimum ring label.
        # One step on a 270° ring is 270/ring_span degrees (27° for 1..11).
        pointer_phase = -28.0 + (270.0 / float(ring_span))
        painter.rotate(pointer_phase)
        marker_width = max(10.0, knob_outer_radius * 0.16)
        marker_inner = top_radius * 0.72
        marker_outer = knob_outer_radius + 5.0
        marker_rect = QRectF(
            -(marker_width * 0.5),
            -marker_outer,
            marker_width,
            marker_outer - marker_inner,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(cap_color)
        painter.drawRect(marker_rect)
        painter.restore()

        # Optional center art.
        if self._center_pixmap is not None and not self._center_pixmap.isNull():
            target = int((top_radius * 2.0) * self._center_scale)
            target = max(1, target)
            scaled = self._center_pixmap.scaled(
                target,
                target,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            x = -(scaled.width() // 2)
            y = -(scaled.height() // 2)
            painter.drawPixmap(x, y, scaled)

        painter.restore()

        painter.end()
