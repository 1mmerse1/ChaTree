"""右侧支线面板 — 多轮子对话视图。"""

from __future__ import annotations

import uuid
from typing import Optional

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..constants import USE_WEBENGINE
from ..markdown_render import MD_CSS, md_to_html, md_to_html_katex, render_msg_body
from ..models import Annotation, Branch, Conversation, Link, MessageNode
from ..styles import BTN_GHOST, BTN_PRIMARY, BTN_SECONDARY, TAG_CHIP
from ..workers import BranchWorker
from ..workspace import ws

if USE_WEBENGINE:
    from ..web_engine_content import WebEngineContentView
else:
    from PySide6.QtWidgets import QTextBrowser


class BranchPanel(QWidget):
    """支线多轮对话侧栏面板。

    Signals:
        closed: 面板关闭时发射。
    """

    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(500)
        self.setStyleSheet(
            "background:#1a202c;border-left:1px solid #2d3748;"
        )
        self._worker: Optional[BranchWorker] = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(80)
        self._refresh_timer.timeout.connect(self._flush_stream)
        self._buf = ""
        self._streaming_started = False  # set_html 是否已调用（避免重复 reset）
        self._current_conv: Optional[Conversation] = None
        self._current_branch: Optional[Branch] = None
        self._streaming_msg_id: str = ""
        self._msg_widgets: list[QWidget] = []  # 支线消息 WebEngine/Browser
        self._build()
        self.hide()

    # ── 构建 UI ────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── 头部 ──
        hdr = QWidget()
        hdr.setFixedHeight(50)
        hdr.setStyleSheet(
            "background:#0f1117;border-bottom:1px solid #2d3748;"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 12, 0)
        self._title = QLabel("支线")
        self._title.setStyleSheet(
            "color:#38b2ac;font-size:13px;font-weight:600;border:none;"
        )
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet(BTN_GHOST)
        close_btn.clicked.connect(self._close)
        hl.addWidget(self._title)
        hl.addStretch()
        hl.addWidget(close_btn)
        lay.addWidget(hdr)

        # ── 可滚动内容区 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none;")
        self._body = QWidget()
        self._body.setStyleSheet("background:transparent;")
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(16, 16, 16, 16)
        self._body_lay.setSpacing(10)
        self._body_lay.addStretch()
        scroll.setWidget(self._body)
        lay.addWidget(scroll, 1)

        # ── 标签栏 ──
        self._tags_bar = QWidget()
        tags_lay = QHBoxLayout(self._tags_bar)
        tags_lay.setContentsMargins(16, 6, 16, 6)
        tags_lay.setSpacing(4)
        self._tags_container = QHBoxLayout()
        self._tags_container.setSpacing(4)
        self._tags_container.addStretch()
        tags_lay.addLayout(self._tags_container, 1)

        add_tag_btn = QPushButton("+ 标签")
        add_tag_btn.setStyleSheet(BTN_SECONDARY)
        add_tag_btn.clicked.connect(self._add_tag)
        tags_lay.addWidget(add_tag_btn)

        link_btn = QPushButton("🔗 链接")
        link_btn.setStyleSheet(BTN_SECONDARY)
        link_btn.clicked.connect(self._create_link)
        tags_lay.addWidget(link_btn)
        lay.addWidget(self._tags_bar)

        # ── 输入栏 ──
        ibar = QWidget()
        ibar.setFixedHeight(72)
        ibar.setStyleSheet("background:#1a202c;border-top:1px solid #2d3748;")
        il = QHBoxLayout(ibar)
        il.setContentsMargins(16, 10, 16, 10)
        il.setSpacing(8)

        self._input = QTextEdit()
        self._input.setPlaceholderText("支线消息…  Ctrl+Enter 发送")
        self._input.setFixedHeight(52)
        self._input.setStyleSheet(
            """
            QTextEdit {
                background: #1e2430; border: none;
                border-radius: 12px; padding: 10px 14px;
                font-size: 14px; color: #e2e8f0;
            }
            QTextEdit:focus { background: #232a36; }
            """
        )
        self._input.installEventFilter(self)
        il.addWidget(self._input)

        send_btn = QPushButton("发送")
        send_btn.setFixedSize(64, 44)
        send_btn.setStyleSheet(BTN_PRIMARY)
        send_btn.clicked.connect(self.send_message)
        il.addWidget(send_btn)
        lay.addWidget(ibar)

    # ── 公开方法 ───────────────────────────────────────────────────

    def show_branch(self, conv: Conversation, branch: Branch):
        """加载并显示支线。"""
        self._current_conv = conv
        self._current_branch = branch
        self._buf = ""

        # 查找原始注释
        ann: Optional[Annotation] = None
        for msg in conv.messages:
            for a in msg.annotations:
                if a.id == branch.annotation_id:
                    ann = a
                    break
            if ann:
                break

        # 清除旧内容
        while self._body_lay.count() > 1:
            item = self._body_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._msg_widgets.clear()

        # 标题
        main_title = conv.title
        self._title.setText(f"支线 · {main_title}")

        # 原始注释：引用文本
        if ann:
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

            # 回答 — 使用 WebEngine 以支持 LaTeX
            self._ins(self._sep("回答"))
            if USE_WEBENGINE:
                ans_view = WebEngineContentView(self)
                ans_view.set_page_color('#1a202c')
                ans_view.setStyleSheet("background:transparent;border:none;")
                ans_body = render_msg_body(ann.ai_answer, [], streaming=False)
                ans_view.set_html(ans_body)
                self._ins(ans_view)
            else:
                al = QLabel(ann.ai_answer)
                al.setStyleSheet("color:#e2e8f0;font-size:13px;")
                al.setWordWrap(True)
                self._ins(al)
        else:
            # 注释已被删除，显示提示
            hint = QLabel("（原始注释已丢失）")
            hint.setStyleSheet("color:#718096;font-size:12px;")
            self._ins(hint)

        # 支线消息
        if branch.messages:
            self._ins(self._sep("支线对话"))
            for msg in branch.messages:
                self._add_message(msg)

        # 标签
        self._refresh_tags()

        self.show()

    # ── 发送消息 ───────────────────────────────────────────────────

    def send_message(self):
        if not self._current_conv or not self._current_branch:
            return
        if self._worker and self._worker.isRunning():
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()

        branch = self._current_branch

        # 添加用户消息
        unode = MessageNode(id=str(uuid.uuid4()), role="user", content=text)
        branch.messages.append(unode)
        self._add_message(unode)

        # 添加助手占位
        anode = MessageNode(id=str(uuid.uuid4()), role="assistant", content="")
        branch.messages.append(anode)
        self._streaming_msg_id = anode.id
        self._buf = ""
        self._streaming_started = False

        # 构建 API 消息列表（初始 Q&A + 所有后续消息除了最后一个）
        ann = self._find_annotation()
        api_msgs: list[dict] = []
        if ann:
            api_msgs.append({"role": "user", "content": ann.user_question})
            api_msgs.append({"role": "assistant", "content": ann.ai_answer})
        for m in branch.messages[:-1]:
            api_msgs.append({"role": m.role, "content": m.content})

        self._worker = BranchWorker(api_msgs)
        self._worker.token_received.connect(self._on_token)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_token(self, token: str):
        self._buf += token
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _flush_stream(self):
        """80ms 刷新定时器回调 — 渲染流式内容（仅更新助手占位）。"""
        if not self._msg_widgets:
            return
        last = self._msg_widgets[-1]
        if USE_WEBENGINE:
            if not self._streaming_started:
                # 首次：设置完整 HTML（触发初始加载）
                body = render_msg_body(self._buf, [], streaming=True)
                last.set_html(body, cursor_visible=True)
                self._streaming_started = True
            else:
                # 后续：仅更新 body（通过 JS，不重置页面）
                body = render_msg_body(self._buf, [], streaming=True)
                last.update_body(body, cursor_visible=True)
        else:
            from ..markdown_render import MD_CSS, md_to_html
            html = (
                f"<html><head>{MD_CSS}</head>"
                f'<body style="color:#e2e8f0;font-size:13px;line-height:1.8;">'
                f"{md_to_html(self._buf)}"
                f'<span style="opacity:.5;">▌</span></body></html>'
            )
            last.setHtml(html)

    def _on_done(self, full: str):
        self._refresh_timer.stop()
        branch = self._current_branch
        if branch:
            for m in branch.messages:
                if m.id == self._streaming_msg_id:
                    m.content = full
                    break
        self._streaming_msg_id = ""
        self._streaming_started = False
        # 最终刷新
        if self._msg_widgets:
            last = self._msg_widgets[-1]
            body = render_msg_body(full, [], streaming=False)
            if USE_WEBENGINE:
                last.update_body(body, cursor_visible=False)
        if self._current_conv:
            ws.save_conversation(self._current_conv)

    def _on_error(self, err: str):
        self._refresh_timer.stop()
        branch = self._current_branch
        if branch:
            for m in branch.messages:
                if m.id == self._streaming_msg_id:
                    m.content = f"❌ {err}"
                    break
        self._streaming_msg_id = ""
        self._streaming_started = False
        if self._msg_widgets:
            last = self._msg_widgets[-1]
            body = render_msg_body(f"❌ {err}", [], streaming=False)
            if USE_WEBENGINE:
                if not hasattr(last, '_loaded') or not last._loaded:
                    last.set_html(body, cursor_visible=False)
                else:
                    last.update_body(body, cursor_visible=False)

    # ── 标签管理 ───────────────────────────────────────────────────

    def _refresh_tags(self):
        """重建标签栏显示。"""
        # 清除旧标签芯片
        while self._tags_container.count():
            item = self._tags_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        branch = self._current_branch
        if not branch:
            self._tags_container.addStretch()
            return

        for tag in branch.tags:
            chip = QPushButton(tag)
            chip.setToolTip("右键删除标签")
            chip.setStyleSheet(TAG_CHIP)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setContextMenuPolicy(Qt.CustomContextMenu)
            chip.customContextMenuRequested.connect(
                lambda pos, t=tag, btn=chip: self._tag_ctx_menu(pos, t, btn)
            )
            self._tags_container.addWidget(chip)

        self._tags_container.addStretch()

    def _add_tag(self):
        """添加标签到支线。"""
        if not self._current_branch:
            return
        tag, ok = QInputDialog.getText(self, "添加标签", "标签名：")
        if ok and tag.strip():
            tag = tag.strip()
            if tag not in self._current_branch.tags:
                self._current_branch.tags.append(tag)
                self._current_branch.tags.sort()
                self._refresh_tags()
                ws.save_conversation(self._current_conv)

    def _tag_ctx_menu(self, pos, tag: str, chip: QPushButton):
        """标签右键菜单 — 删除。"""
        menu = QMenu(self)
        menu.addAction(f"删除「{tag}」").triggered.connect(
            lambda: self._remove_tag(tag)
        )
        menu.exec(chip.mapToGlobal(pos))

    def _remove_tag(self, tag: str):
        """删除支线标签。"""
        if self._current_branch and tag in self._current_branch.tags:
            self._current_branch.tags.remove(tag)
            self._refresh_tags()
            if self._current_conv:
                ws.save_conversation(self._current_conv)

    # ── 链接 ───────────────────────────────────────────────────────

    def _create_link(self):
        """从支线消息创建跨对话链接。"""
        if not self._current_conv or not self._current_branch:
            return
        from .dialogs import LinkPickerDialog

        # 使用支线最后一个用户消息或注释作为源
        branch = self._current_branch
        source_msg_id = ""
        # 找最后一条用户消息
        for m in reversed(branch.messages):
            if m.role == "user":
                source_msg_id = m.id
                break
        if not source_msg_id:
            # 使用注释 ID 作为回退
            source_msg_id = branch.annotation_id

        # 创建临时 MessageNode 用于 LinkPickerDialog
        temp_node = MessageNode(id=source_msg_id, role="user", content="")

        dlg = LinkPickerDialog(self._current_conv, temp_node, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_conv_id, target_msg_id = dlg.result()
        if not target_conv_id:
            return

        new_link = Link(
            id=str(uuid.uuid4()),
            source_msg_id=source_msg_id,
            target_conv_id=target_conv_id,
            target_msg_id=target_msg_id,
        )
        branch.links.append(new_link)
        if self._current_conv:
            ws.save_conversation(self._current_conv)

    # ── 辅助方法 ───────────────────────────────────────────────────

    def _find_annotation(self) -> Optional[Annotation]:
        """查找当前支线对应的原始注释。"""
        if not self._current_conv or not self._current_branch:
            return None
        for msg in self._current_conv.messages:
            for a in msg.annotations:
                if a.id == self._current_branch.annotation_id:
                    return a
        return None

    def _add_message(self, msg: MessageNode):
        """向 body 添加一条消息 widget。"""
        role_tag = "👤" if msg.role == "user" else "🤖"
        role_color = "#63b3ed" if msg.role == "user" else "#68d391"

        # 角色标签
        role_lbl = QLabel(f"{role_tag}  {msg.role.upper()}")
        role_lbl.setStyleSheet(
            f"color:{role_color};font-size:11px;font-weight:600;margin-top:6px;"
        )
        self._ins(role_lbl)

        if USE_WEBENGINE:
            w = WebEngineContentView(self)
            w.set_page_color('#1a202c')
            w.setStyleSheet("background:transparent;border:none;")
            if msg.content:
                body = render_msg_body(msg.content, [], streaming=False)
                w.set_html(body)
            # 空内容占位：不调用 set_html，等待流式填充
            self._msg_widgets.append(w)
            self._ins(w)
        else:
            from ..markdown_render import MD_CSS, md_to_html
            w = QTextBrowser()
            w.setOpenLinks(False)
            w.setFrameShape(QTextBrowser.NoFrame)
            w.setStyleSheet(
                "background:transparent;border:none;color:#e2e8f0;font-size:13px;"
            )
            if msg.content:
                html = (
                    f"<html><head>{MD_CSS}</head>"
                    f'<body style="color:#e2e8f0;font-size:13px;line-height:1.8;">'
                    f"{md_to_html(msg.content)}</body></html>"
                )
                w.setHtml(html)
            self._msg_widgets.append(w)
            self._ins(w)

    def _ins(self, w: QWidget):
        """在 body 末尾（stretch 前）插入 widget。"""
        self._body_lay.insertWidget(self._body_lay.count() - 1, w)

    @staticmethod
    def _sep(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#718096;font-size:10px;font-weight:600;"
            "margin-top:6px;padding-top:6px;"
            "border-top:1px solid #2d3748;"
        )
        return lbl

    def _close(self):
        """关闭面板。"""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        if self._current_conv:
            ws.save_conversation(self._current_conv)
        self.hide()
        self.closed.emit()

    # ── 事件 ───────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._input and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
                self.send_message()
                return True
        return super().eventFilter(obj, event)
