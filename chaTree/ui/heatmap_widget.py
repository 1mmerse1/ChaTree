"""GitHub 风格活动热力图 — 自定义 QWidget + paintEvent 手绘。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from PySide6.QtCore import QDate, QPoint, QRect, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QToolTip, QWidget

# ── 颜色等级（GitHub 暗色主题） ─────────────────────────────────────

_EMPTY = QColor("#161b22")
_CELL_COLORS = [
    QColor("#161b22"),  # 0  — 无活动
    QColor("#0e4429"),  # 1-2
    QColor("#006d32"),  # 3-5
    QColor("#26a641"),  # 6-10
    QColor("#39d353"),  # 11+
]
_TEXT_COLOR = QColor("#c9d1d9")
_TEXT_DIM = QColor("#484f58")
_LABEL_COLOR = QColor("#8b949e")
_LEGEND_LABEL_COLOR = QColor("#8b949e")

_CELL_SIZE = 14
_CELL_GAP = 3
_CELL_STEP = _CELL_SIZE + _CELL_GAP
_LEFT_MARGIN = 32
_TOP_MARGIN = 22
_BOTTOM_LEGEND_H = 20

# 星期标签（周一 = 索引 0）
_DAY_LABELS = ["Mon", "", "Wed", "", "Fri", "", ""]


def _count_to_level(n: int) -> int:
    """将每日计数映射到 0-4 颜色等级。"""
    if n <= 0:
        return 0
    if n <= 2:
        return 1
    if n <= 5:
        return 2
    if n <= 10:
        return 3
    return 4


class HeatmapWidget(QWidget):
    """GitHub 风格贡献热力图。

    Usage::

        w = HeatmapWidget()
        w.set_data({"2026-06-01": 3, "2026-06-02": 7, ...})
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._data: dict[str, int] = {}
        self._start_date: Optional[date] = None
        self._end_date: Optional[date] = None
        self._cols = 0
        self._cell_rects: dict[date, QRect] = {}

    # ── 公共接口 ──────────────────────────────────────────────────

    def set_data(self, date_counts: dict[str, int]):
        """设置每日计数字典 ``{"YYYY-MM-DD": N}`` 并重绘。"""
        self._data = date_counts

        # 解析日期范围
        parsed: list[date] = []
        for d_str in date_counts:
            try:
                parsed.append(date.fromisoformat(d_str))
            except ValueError:
                pass

        if not parsed:
            self._start_date = self._end_date = None
            self._cols = 0
            self._cell_rects.clear()
            self.update()
            return

        parsed.sort()
        self._start_date = parsed[0]
        self._end_date = parsed[-1]

        # 对齐到周一（weekday=0）与周日（weekday=6）
        iso_start = self._start_date.isocalendar()
        iso_end = self._end_date.isocalendar()
        start_weekday = self._start_date.weekday()  # 0=Mon
        # 扩展范围覆盖整周
        grid_start = self._start_date - timedelta(days=start_weekday)
        end_weekday = self._end_date.weekday()
        grid_end = self._end_date + timedelta(days=6 - end_weekday)

        self._cols = (grid_end - grid_start).days // 7 + 1

        # 预计算每个日期的像素矩形
        self._cell_rects.clear()
        cursor = grid_start
        for col in range(self._cols):
            for row in range(7):
                self._cell_rects[cursor] = QRect(
                    _LEFT_MARGIN + col * _CELL_STEP,
                    _TOP_MARGIN + row * _CELL_STEP,
                    _CELL_SIZE,
                    _CELL_SIZE,
                )
                cursor += timedelta(days=1)

        self.updateGeometry()
        self.update()

    def _date_at_pos(self, pos: QPoint) -> Optional[date]:
        """返回鼠标位置对应的日期，无匹配返回 None。"""
        for d, r in self._cell_rects.items():
            if r.contains(pos):
                return d
        return None

    # ── 尺寸提示 ──────────────────────────────────────────────────

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def sizeHint(self) -> QSize:
        cols = max(self._cols, 1)
        w = _LEFT_MARGIN + cols * _CELL_STEP + 8
        h = _TOP_MARGIN + 7 * _CELL_STEP + _BOTTOM_LEGEND_H + 8
        return QSize(w, h)

    # ── 绘制 ──────────────────────────────────────────────────────

    def paintEvent(self, _event):
        if self._cols == 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        self._draw_cells(p)
        self._draw_day_labels(p)
        self._draw_month_labels(p)
        self._draw_legend(p)

        p.end()

    def _draw_cells(self, p: QPainter):
        font = QFont("Segoe UI", 8)
        font.setWeight(QFont.Bold)
        p.setFont(font)

        for d, r in self._cell_rects.items():
            count = self._data.get(d.isoformat(), 0)
            level = _count_to_level(count)

            # 填充
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(_CELL_COLORS[level]))
            p.drawRoundedRect(r, 2, 2)

            # 数字（颜色足够深时显示）
            if count > 0:
                p.setPen(QPen(_TEXT_COLOR))
                fm = QFontMetrics(font)
                text = str(count)
                tw = fm.horizontalAdvance(text)
                th = fm.height()
                tx = r.x() + (r.width() - tw) // 2
                ty = r.y() + (r.height() - th) // 2 + fm.ascent()
                p.drawText(tx, ty, text)

    def _draw_day_labels(self, p: QPainter):
        font = QFont("Segoe UI", 9)
        p.setFont(font)
        p.setPen(QPen(_LABEL_COLOR))

        for row in range(7):
            label = _DAY_LABELS[row]
            if not label:
                continue
            y = _TOP_MARGIN + row * _CELL_STEP + _CELL_SIZE // 2
            fm = QFontMetrics(font)
            th = fm.height()
            ty = y + th // 2 - fm.descent()
            p.drawText(2, ty, label)

    def _draw_month_labels(self, p: QPainter):
        if not self._start_date:
            return

        font = QFont("Segoe UI", 9)
        p.setFont(font)
        p.setPen(QPen(_LABEL_COLOR))

        months: dict[int, int] = {}  # month_number → first_col_index
        cursor = self._start_date
        # 对齐到周一
        cursor -= timedelta(days=cursor.weekday())
        for col in range(self._cols):
            for _row in range(7):
                m = cursor.month
                if m not in months:
                    months[m] = col
                cursor += timedelta(days=1)

        month_names = [
            "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        for m, col in months.items():
            x = _LEFT_MARGIN + col * _CELL_STEP
            p.drawText(x, 10, month_names[m])

    def _draw_legend(self, p: QPainter):
        legend_y = _TOP_MARGIN + 7 * _CELL_STEP + 6
        label_font = QFont("Segoe UI", 9)
        p.setFont(label_font)

        # "Less" 标签
        p.setPen(QPen(_LEGEND_LABEL_COLOR))
        p.drawText(_LEFT_MARGIN, legend_y + 12, "Less")

        # 5 色块
        for i in range(5):
            rx = _LEFT_MARGIN + 40 + i * (_CELL_SIZE + 3)
            ry = legend_y
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(_CELL_COLORS[i]))
            p.drawRoundedRect(rx, ry, _CELL_SIZE, _CELL_SIZE, 2, 2)

        # "More" 标签
        mx = _LEFT_MARGIN + 48 + 5 * (_CELL_SIZE + 3)
        p.setPen(QPen(_LEGEND_LABEL_COLOR))
        p.drawText(mx, legend_y + 12, "More")

    # ── 交互 ──────────────────────────────────────────────────────

    def mouseMoveEvent(self, event: QMouseEvent):
        d = self._date_at_pos(event.pos())
        if d:
            count = self._data.get(d.isoformat(), 0)
            label = "轮对话" if count else "无活动"
            tip = f"{d.isoformat()} · {count} {label}"
            QToolTip.showText(event.globalPos(), tip, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)
