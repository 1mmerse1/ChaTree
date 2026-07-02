"""右侧注释详情面板。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..constants import CIRCLE, USE_WEBENGINE
from ..markdown_render import MD_CSS, md_to_html, md_to_html_katex, render_msg_body
from ..models import Annotation, Branch, Conversation, MessageNode
from ..styles import BTN_GHOST, BTN_PRIMARY
from ..workers import AnnotationWorker
from ..workspace import ws

if USE_WEBENGINE:
    from ..web_engine_content import WebEngineContentView
else:
    from PySide6.QtWidgets import QTextBrowser


class AnnotationPanel(QWidget):
    closed = Signal()
    annotation_shown = Signal()           # 非支线注释显示时发射
    branch_created = Signal(str, str)     # (conv_id, branch_id)
    branch_requested = Signal(str, str)   # (conv_id, branch_id)

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(200)
        self.setMaximumWidth(480)
        self.setStyleSheet(
            "background:#1a202c;border-left:1px solid #2d3748;"
        )
        self._worker: Optional[AnnotationWorker] = None
        self._buf = ""
        self._current_conv: Optional[Conversation] = None
        self._current_node: Optional[MessageNode] = None
        self._current_ann: Optional[Annotation] = None
        self._ans: Optional[QTextBrowser] = None
        self._build()
        self.hide()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr = QWidget()
        hdr.setFixedHeight(50)
        hdr.setStyleSheet(
            "background:#0f1117;border-bottom:1px solid #2d3748;"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 12, 0)
        self._title = QLabel("注释")
        self._title.setStyleSheet(
            "color:#e2e8f0;font-size:13px;font-weight:600;border:none;"
        )
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet(BTN_GHOST)
        close_btn.clicked.connect(self._close)
        hl.addWidget(self._title)
        hl.addStretch()
        hl.addWidget(close_btn)
        lay.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none;")
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        self._body_lay = QVBoxLayout(body)
        self._body_lay.setContentsMargins(16, 16, 16, 16)
        self._body_lay.setSpacing(10)
        self._body_lay.addStretch()
        scroll.setWidget(body)
        lay.addWidget(scroll)

    def show_annotation(self, conv: Conversation, node: MessageNode, ann: Annotation):
        self._current_conv = conv
        self._current_node = node
        self._current_ann = ann
        self._ans = None

        # 如果已扩展为支线 → 通知打开 BranchPanel
        if ann.branch_id:
            self.branch_requested.emit(conv.id, ann.branch_id)
            return

        while self._body_lay.count() > 1:
            item = self._body_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        idx = node.annotations.index(ann)
        badge = CIRCLE[idx] if idx < len(CIRCLE) else f"({idx + 1})"
        self._title.setText(f"注释  {badge}")

        qbox = QLabel(f"❝  {ann.quoted_text}  ❞")
        qbox.setStyleSheet(
            "color:#fde68a;background:#451a03;border-radius:8px;"
            "padding:10px 12px;font-size:12px;"
        )
        qbox.setWordWrap(True)
        self._ins(qbox)

        self._ins(self._sep("追问"))
        ql = QLabel(ann.user_question)
        ql.setStyleSheet("color:#cbd5e0;font-size:13px;")
        ql.setWordWrap(True)
        self._ins(ql)

        self._ins(self._sep("回答"))
        if USE_WEBENGINE:
            self._ans = WebEngineContentView(self)  # type: ignore[reportUnboundVariable]
            self._ans.set_page_color('#1a202c')
            self._ans.setStyleSheet("background:transparent;border:none;")
            self._ins(self._ans)  # type: ignore[reportArgumentType]
        else:
            self._ans = QTextBrowser()  # type: ignore[reportUnboundVariable]
            self._ans.setOpenLinks(False)
            self._ans.setFrameShape(QTextBrowser.NoFrame)
            self._ans.setStyleSheet(
                "background:transparent;border:none;color:#e2e8f0;font-size:13px;"
            )
            self._ans.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            self._ans.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._ins(self._ans)

        if ann.ai_answer:
            self._set_ans(ann.ai_answer, done=True)
        else:
            self._set_ans("正在生成…", done=False)
            self._start_worker(node.content, ann)

        # 「扩展为支线」按钮
        expand_btn = QPushButton("📂  扩展为支线")
        expand_btn.setStyleSheet(BTN_PRIMARY)
        expand_btn.setCursor(Qt.PointingHandCursor)
        expand_btn.clicked.connect(self._expand_to_branch)
        self._ins(expand_btn)

        self.annotation_shown.emit()
        self.show()

    def _expand_to_branch(self):
        """将当前注释扩展为支线。"""
        if not self._current_conv or not self._current_ann or not self._current_node:
            return
        import uuid

        ann = self._current_ann
        branch = Branch(
            id=str(uuid.uuid4()),
            annotation_id=ann.id,
            source_msg_id=self._current_node.id,
        )
        ann.branch_id = branch.id
        self._current_conv.branches.append(branch)
        ws.save_conversation(self._current_conv)

        # 重新渲染主对话以更新内联标记样式
        # 通知打开 BranchPanel
        self.branch_created.emit(self._current_conv.id, branch.id)

    def _ins(self, w: QWidget):
        self._body_lay.insertWidget(self._body_lay.count() - 1, w)

    @staticmethod
    def _sep(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#718096;font-size:10px;font-weight:600;margin-top:4px;"
        )
        return lbl

    def _answer_text_width(self) -> int:
        return max(120, self.width() - 36)

    def _layout_answer_height(self) -> None:
        if USE_WEBENGINE or self._ans is None:
            return
        self._ans.document().setTextWidth(self._answer_text_width())
        h = int(self._ans.document().size().height()) + 4
        self._ans.setFixedHeight(max(h, 40))

    def _set_ans(self, text: str, done: bool):
        if USE_WEBENGINE:
            cursor = "" if done else '<span style="opacity:.5;">&#x258C;</span>'
            body = f"{md_to_html_katex(text)}{cursor}"
            if not self._ans._loaded:
                self._ans.set_html(body, cursor_visible=not done)
            else:
                self._ans.update_body(body, cursor_visible=not done)
        else:
            cursor_html = "" if done else '<span style="opacity:.5;">▌</span>'
            html = (
                f"<html><head>{MD_CSS}</head>"
                f'<body style="color:#e2e8f0;font-size:13px;line-height:1.8;">'
                f"{md_to_html(text)}{cursor_html}</body></html>"
            )
            self._ans.setHtml(html)
            self._layout_answer_height()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if not USE_WEBENGINE:
            self._layout_answer_height()

    def _start_worker(self, context: str, ann: Annotation):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self._buf = ""
        self._worker = AnnotationWorker(context, ann.quoted_text, ann.user_question)
        self._worker.token_received.connect(lambda t, a=ann: self._on_token(t, a))
        self._worker.finished.connect(lambda f, a=ann: self._on_done(f, a))
        self._worker.error.connect(lambda e: self._set_ans(f"❌ {e}", done=True))
        self._worker.start()

    def _on_token(self, token: str, ann: Annotation):
        self._buf += token
        self._set_ans(self._buf, done=False)

    def _on_done(self, full: str, ann: Annotation):
        ann.ai_answer = full
        self._set_ans(full, done=True)
        if self._current_conv:
            ws.save_conversation(self._current_conv)

    def _close(self):
        self.hide()
        self.closed.emit()
