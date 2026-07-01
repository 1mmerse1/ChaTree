"""活动热力图对话框 — GitHub 风格贡献图 + 统计摘要。"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..styles import BTN_GHOST, BTN_PRIMARY, DIALOG_BASE
from ..workspace import ws
from .heatmap_widget import HeatmapWidget


class HeatmapDialog(QDialog):
    """以 GitHub 风格热力图展示每日对话活跃情况。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("活动统计")
        self.setModal(True)
        self.setMinimumWidth(720)
        self.setStyleSheet(DIALOG_BASE)
        self._build()
        self.adjustSize()

    # ── 构建 ──────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)

        # ---- 标题 ----
        title = QLabel("📊 对话活跃度")
        title.setStyleSheet(
            "color:#e2e8f0;font-size:17px;font-weight:700;"
        )
        lay.addWidget(title)

        # ---- 统计摘要 ----
        stats = self._collect_data()
        summary = self._build_summary(stats)
        summary.setStyleSheet(
            "color:#8b949e;font-size:12px;padding:0;margin:0;"
        )
        lay.addWidget(summary)

        # ---- 热力图 ----
        self._heatmap = HeatmapWidget()
        self._heatmap.set_data(stats["date_counts"])
        lay.addWidget(self._heatmap, 1)

        # ---- 底部按钮 ----
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(8)
        btn_lay.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(BTN_PRIMARY)
        close_btn.clicked.connect(self.accept)
        btn_lay.addWidget(close_btn)

        lay.addLayout(btn_lay)

    # ── 数据 ──────────────────────────────────────────────────────

    def _collect_data(self) -> dict:
        """从 Workspace 聚合每日活动数据。

        Returns:
            dict with keys:
            - "date_counts": {date_str: int}  每日对话数
            - "total_convs": int              总对话数
            - "total_msgs": int               总消息数
            - "active_days": int              活跃天数
            - "streak": int                   当前连续活跃天数
        """
        counter: Counter[date] = Counter()
        total_msgs = 0

        for conv in ws.conversations.values():
            total_msgs += len(conv.messages)
            if conv.created_at:
                try:
                    d = datetime.fromisoformat(conv.created_at).date()
                    counter[d] += 1
                except (ValueError, TypeError):
                    pass

        total_convs = sum(counter.values())
        active_days = len(counter)

        # 计算连续活跃天数（从今天往回数）
        streak = 0
        today = date.today()
        for i in range(365):
            check = today - timedelta(days=i)
            if counter.get(check, 0) > 0:
                streak += 1
            else:
                break

        # 转为字符串键，并补全日期范围使热力图连续
        date_counts: dict[str, int] = {}
        if counter:
            all_dates = sorted(counter.keys())
            grid_start = all_dates[0]
            grid_end = all_dates[-1]
            # 对齐到周一
            grid_start -= timedelta(days=grid_start.weekday())
            grid_end += timedelta(days=6 - grid_end.weekday())
            cursor = grid_start
            while cursor <= grid_end:
                date_counts[cursor.isoformat()] = counter.get(cursor, 0)
                cursor += timedelta(days=1)

        return {
            "date_counts": date_counts,
            "total_convs": total_convs,
            "total_msgs": total_msgs,
            "active_days": active_days,
            "streak": streak,
        }

    def _build_summary(self, stats: dict) -> QLabel:
        total_convs = stats["total_convs"]
        total_msgs = stats["total_msgs"]
        active_days = stats["active_days"]
        streak = stats["streak"]

        parts = [
            f"共 {total_convs} 场对话",
            f"· {total_msgs} 条消息",
            f"· {active_days} 个活跃日",
        ]
        if streak > 0:
            parts.append(f"· 🔥 {streak} 天连续活跃")

        return QLabel("  ".join(parts))
