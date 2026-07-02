"""AI 自动推荐链接确认对话框。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..models import Conversation
from ..styles import BTN_GHOST, BTN_PRIMARY, BTN_SECONDARY


class LinkSuggestionDialog(QDialog):
    """展示 AI 推荐的链接建议，由用户确认后创建。

    构造函数:
        suggestions: list[dict] — 每个 dict 含 conv_id, msg_id, reason
        conversations: dict[str, Conversation] — 用于查找对话标题和消息内容
    """

    def __init__(
        self,
        suggestions: list[dict],
        conversations: dict[str, Conversation],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("AI 推荐链接")
        self.setMinimumWidth(480)
        self.setMaximumWidth(560)
        self.setStyleSheet(
            """
            QDialog { background: #1a202c; border: 1px solid #2d3748; border-radius: 10px; }
            QDialog QWidget { background: #1a202c; }
            """
        )
        self._suggestions = suggestions
        self._conversations = conversations
        self._checks: list[QCheckBox] = []
        self._build()
        self.adjustSize()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)

        # 标题
        n = len(self._suggestions)
        title = QLabel(f"🔗 AI 发现 {n} 个可能关联")
        title.setStyleSheet(
            "color:#e2e8f0;font-size:16px;font-weight:700;"
        )
        lay.addWidget(title)

        hint = QLabel("确认要创建链接的建议（默认全选）：")
        hint.setStyleSheet("color:#718096;font-size:12px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # 建议列表（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: 1px solid #2d3748;"
            "border-radius: 8px; }"
        )
        scroll.setMaximumHeight(260)

        list_widget = QWidget()
        list_widget.setStyleSheet("background: transparent;")
        list_lay = QVBoxLayout(list_widget)
        list_lay.setContentsMargins(12, 8, 12, 8)
        list_lay.setSpacing(6)
        list_lay.addStretch()

        for s in self._suggestions:
            row = self._build_suggestion_row(s)
            list_lay.insertWidget(list_lay.count() - 1, row)

        scroll.setWidget(list_widget)
        lay.addWidget(scroll, 1)

        # 全选 / 取消
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        all_btn = QPushButton("全选")
        all_btn.setStyleSheet(BTN_SECONDARY)
        all_btn.clicked.connect(lambda: self._set_all(True))
        btn_row.addWidget(all_btn)
        none_btn = QPushButton("取消全选")
        none_btn.setStyleSheet(BTN_SECONDARY)
        none_btn.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(none_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # 底部按钮
        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(10)
        skip_btn = QPushButton("跳过")
        skip_btn.setStyleSheet(BTN_GHOST)
        skip_btn.clicked.connect(self.reject)
        btn_row2.addWidget(skip_btn)
        btn_row2.addStretch()
        create_btn = QPushButton("创建选中链接  →")
        create_btn.setStyleSheet(BTN_PRIMARY)
        create_btn.clicked.connect(self.accept)
        btn_row2.addWidget(create_btn)
        lay.addLayout(btn_row2)

    def _build_suggestion_row(self, s: dict) -> QWidget:
        """构建单条建议行。"""
        row = QWidget()
        row.setStyleSheet(
            "background:#0f1117;border-radius:8px;padding:2px;"
        )
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 8, 10, 8)
        rl.setSpacing(10)

        cb = QCheckBox()
        cb.setChecked(True)
        cb.setStyleSheet(
            "QCheckBox { spacing: 0px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        self._checks.append(cb)
        rl.addWidget(cb, alignment=Qt.AlignTop)

        # 信息区
        info = QVBoxLayout()
        info.setSpacing(2)

        conv_id = s.get("conv_id", "")
        msg_id = s.get("msg_id", "")
        title_text = conv_id
        question_preview = ""
        conv = self._conversations.get(conv_id)
        if conv:
            title_text = conv.title
            for m in conv.messages:
                if m.id == msg_id:
                    q = m.content[:60].replace("\n", " ")
                    question_preview = f'"{q}…"' if len(m.content) > 60 else f'"{q}"'
                    break

        # 对话标题 + 问题摘要
        title_lbl = QLabel(f"{title_text}")
        title_lbl.setStyleSheet(
            "color:#e2e8f0;font-size:13px;font-weight:600;"
        )
        info.addWidget(title_lbl)

        if question_preview:
            q_lbl = QLabel(question_preview)
            q_lbl.setStyleSheet("color:#718096;font-size:11px;")
            q_lbl.setWordWrap(True)
            info.addWidget(q_lbl)

        # 关联理由
        reason = s.get("reason", "")
        if reason:
            r_lbl = QLabel(f"关联理由: {reason}")
            r_lbl.setStyleSheet("color:#81e6d9;font-size:11px;")
            r_lbl.setWordWrap(True)
            info.addWidget(r_lbl)

        rl.addLayout(info, 1)
        return row

    def _set_all(self, checked: bool):
        for cb in self._checks:
            cb.setChecked(checked)

    def selected_suggestions(self) -> list[dict]:
        """返回用户勾选的建议列表。"""
        result: list[dict] = []
        for i, cb in enumerate(self._checks):
            if cb.isChecked() and i < len(self._suggestions):
                result.append(self._suggestions[i])
        return result
