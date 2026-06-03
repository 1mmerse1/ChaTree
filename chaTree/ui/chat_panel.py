"""主对话区：单一 WebView 消息列表 + 输入栏。"""

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
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..constants import USE_WEBENGINE
from ..conversation_view import ConversationView
from ..markdown_render import markdown_ready, render_msg_body
from ..models import Annotation, Conversation, Link, MessageNode
from ..styles import BTN_PRIMARY
from ..workers import ChatWorker, TagWorker
from ..workspace import ws
from .annotation_panel import AnnotationPanel
from .dialogs import BacklinksDialog, EditMessageDialog, LinkPickerDialog

if not USE_WEBENGINE:
    from .message_bubble import MessageBubble


class ChatPanel(QWidget):
    def __init__(self, ann_panel: AnnotationPanel):
        super().__init__()
        self.ann_panel = ann_panel
        self.conv: Optional[Conversation] = None
        self._worker: Optional[ChatWorker] = None
        self._tag_worker: Optional[TagWorker] = None
        self._streaming_msg_id: str = ""
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(80)
        self._refresh_timer.timeout.connect(self._flush_stream)
        self._buf = ""
        self._build()

    def _build(self):
        self.stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stack)

        self._welcome = self._build_welcome()
        self.stack.addWidget(self._welcome)

        page = QWidget()
        page.setStyleSheet("background:#0f1117;")
        cl = QVBoxLayout(page)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        tbar = QWidget()
        tbar.setFixedHeight(68)
        tbar.setStyleSheet("background:#0f1117;border-bottom:1px solid #1a202c;")
        tbar_layout = QVBoxLayout(tbar)
        tbar_layout.setContentsMargins(24, 6, 24, 2)
        tbar_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._conv_title = QLabel("—")
        self._conv_title.setStyleSheet(
            "color:#e2e8f0;font-size:14px;font-weight:600;"
        )
        self._conv_title.mouseDoubleClickEvent = self._on_title_dbl_click
        title_row.addWidget(self._conv_title)
        title_row.addStretch()
        md_lbl = QLabel("Markdown")
        md_lbl.setStyleSheet(
            "color:#276749;background:#1c4532;border-radius:4px;"
            "padding:2px 7px;font-size:10px;font-weight:600;"
        )
        if not markdown_ready():
            md_lbl.setText("纯文本")
            md_lbl.setStyleSheet(
                "color:#744210;background:#3c2a09;border-radius:4px;"
                "padding:2px 7px;font-size:10px;font-weight:600;"
            )
        title_row.addWidget(md_lbl)
        tbar_layout.addLayout(title_row)

        self._tags_layout = QHBoxLayout()
        self._tags_layout.setSpacing(4)
        self._tags_layout.addStretch()
        tbar_layout.addLayout(self._tags_layout)
        cl.addWidget(tbar)

        if USE_WEBENGINE:
            self.conv_view = ConversationView(self)
            self.conv_view.annotation_clicked.connect(self._on_annotation_clicked)
            self.conv_view.annotation_created.connect(self._on_ann_created)
            self.conv_view.link_clicked.connect(self._on_inline_link_clicked)
            self.conv_view.link_create_requested.connect(self._on_link_create)
            self.conv_view.backlinks_requested.connect(self._on_show_backlinks)
            self.conv_view.retry_requested.connect(self._on_retry_assistant)
            self.conv_view.tag_add_requested.connect(self._on_msg_tag_add)
            self.conv_view.tag_remove_requested.connect(self._on_msg_tag_remove)
            self.conv_view.link_delete_requested.connect(self._on_link_delete)
            self.conv_view.set_context_menu_builder(self._build_ctx_menu)
            cl.addWidget(self.conv_view, 1)
        else:
            from PySide6.QtWidgets import QScrollArea
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setStyleSheet("background:#0f1117;border:none;")
            self.sw = QWidget()
            self.sw.setStyleSheet("background:#0f1117;")
            self.msg_lay = QVBoxLayout(self.sw)
            self.msg_lay.setContentsMargins(32, 24, 32, 24)
            self.msg_lay.setSpacing(18)
            self.msg_lay.addStretch()
            self.scroll.setWidget(self.sw)
            self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_moved)
            self._bubbles: list[MessageBubble] = []
            self._user_scrolled_away = False
            cl.addWidget(self.scroll, 1)

        self.stack.addWidget(page)

        ibar = QWidget()
        ibar.setFixedHeight(80)
        ibar.setStyleSheet("background:#1a202c;border-top:1px solid #2d3748;")
        il = QHBoxLayout(ibar)
        il.setContentsMargins(20, 14, 20, 14)
        il.setSpacing(10)

        self.input = QTextEdit()
        self.input.setPlaceholderText("输入消息…  Ctrl+Enter 发送")
        self.input.setFixedHeight(52)
        self.input.setStyleSheet(
            """
            QTextEdit {
                background: #1e2430; border: none;
                border-radius: 16px; padding: 12px 16px;
                font-size: 15px; color: #e2e8f0;
            }
            QTextEdit:focus { background: #232a36; }
        """
        )
        self.input.installEventFilter(self)
        il.addWidget(self.input)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedSize(72, 48)
        self.send_btn.setStyleSheet(BTN_PRIMARY)
        self.send_btn.clicked.connect(self.send_message)
        il.addWidget(self.send_btn)
        root.addWidget(ibar)

    def _build_welcome(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#0f1117;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)

        title = QLabel("Hello, I'm ChaTree")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:#e2e8f0;font-size:36px;font-weight:700;")

        sub = QLabel("Ask me anything.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color:#718096;font-size:18px;")

        lay.addStretch()
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addStretch()
        return w

    # ── 对话加载 ──

    def load_conversation(self, conv: Conversation):
        self.conv = conv
        self._conv_title.setText(conv.title)
        self._update_conv_tags_display()
        self._streaming_msg_id = ""

        if USE_WEBENGINE:
            self.conv_view._conv_titles = {c.id: c.title for c in ws.conversations.values()}
            self.conv_view.load_conversation(conv)
        else:
            self.sw.setUpdatesEnabled(False)
            while self.msg_lay.count() > 1:
                item = self.msg_lay.takeAt(0)
                if item.widget():
                    item.widget().setVisible(False)
                    item.widget().deleteLater()
            self._bubbles.clear()
            for node in conv.messages:
                self._add_bubble(node)
            self._user_scrolled_away = False
            self.sw.setUpdatesEnabled(True)
            self._refresh_all_bubble_links()

        if conv.messages:
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)

    # ── 发送消息 ──

    def send_message(self):
        if not self.conv or (self._worker and self._worker.isRunning()):
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.stack.setCurrentIndex(1)
        self.input.clear()
        self.send_btn.setEnabled(False)

        unode = MessageNode(id=str(uuid.uuid4()), role="user", content=text)
        self.conv.messages.append(unode)

        anode = MessageNode(id=str(uuid.uuid4()), role="assistant", content="")
        self.conv.messages.append(anode)

        if USE_WEBENGINE:
            self.conv_view.append_message(unode)
            self.conv_view.start_streaming(anode.id)
            self._streaming_msg_id = anode.id
            self._buf = ""
        else:
            self._add_bubble(unode)
            self._stream_bubble = self._add_bubble(anode, streaming=True)
            self._user_scrolled_away = False
            self._scroll_to_bottom(force=True)

        api_msgs = [{"role": m.role, "content": m.content} for m in self.conv.messages[:-1]]
        self._worker = ChatWorker(api_msgs)
        self._worker.token_received.connect(self._on_token)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_token(self, token: str):
        if USE_WEBENGINE:
            self._buf += token
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        else:
            if self._stream_bubble:
                self._stream_bubble.node.content += token
                if not self._refresh_timer.isActive():
                    self._refresh_timer.start()

    def _flush_stream(self):
        if USE_WEBENGINE:
            body = render_msg_body(self._buf, [], streaming=True)
            self.conv_view.append_token(body)
        else:
            if self._stream_bubble:
                self._stream_bubble.refresh()
                self._scroll_to_bottom()

    def _on_done(self, full: str):
        self._refresh_timer.stop()
        if USE_WEBENGINE:
            body = render_msg_body(full, [], streaming=False)
            msg_id = self._streaming_msg_id
            assistant_node = None
            if self.conv:
                for m in self.conv.messages:
                    if m.id == msg_id:
                        m.content = full
                        assistant_node = m
                        break
            self.conv_view.finalize_streaming(body, msg_id, assistant_node.tags if assistant_node else [])
            self._streaming_msg_id = ""
        else:
            assistant_node = None
            if self._stream_bubble:
                self._stream_bubble.node.content = full
                self._stream_bubble.finalize()
                assistant_node = self._stream_bubble.node
                self._stream_bubble = None
            self._scroll_to_bottom()
        self.send_btn.setEnabled(True)
        if self.conv:
            ws.save_conversation(self.conv)
        if assistant_node:
            self._start_tag_generation(assistant_node)

    def _on_error(self, err: str):
        self._refresh_timer.stop()
        if USE_WEBENGINE:
            body = render_msg_body(f"❌ {err}", [], streaming=False)
            msg_id = self._streaming_msg_id
            if self.conv:
                for m in self.conv.messages:
                    if m.id == msg_id:
                        m.content = f"❌ {err}"
                        break
            self.conv_view.finalize_streaming(body, msg_id, [])
            self._streaming_msg_id = ""
        else:
            if self._stream_bubble:
                self._stream_bubble.node.content = f"❌ {err}"
                self._stream_bubble.finalize()
                self._stream_bubble = None
            self._scroll_to_bottom()
        self.send_btn.setEnabled(True)

    # ── 标签 ──

    def _start_tag_generation(self, assistant_node: MessageNode):
        if not self.conv:
            return
        try:
            idx = self.conv.messages.index(assistant_node)
        except ValueError:
            return
        if idx < 1 or self.conv.messages[idx - 1].role != "user":
            return
        user_node = self.conv.messages[idx - 1]
        if user_node.tags and assistant_node.tags:
            return
        print("[TagWorker] 启动标签生成...")
        self._tag_worker = TagWorker(user_node.content, assistant_node.content)
        self._tag_worker.finished.connect(
            lambda tags: self._on_tags_generated(user_node, assistant_node, tags)
        )
        self._tag_worker.error.connect(
            lambda err: print(f"[TagWorker error] {err}")
        )
        self._tag_worker.start()

    def _on_tags_generated(
        self, user_node: MessageNode, assistant_node: MessageNode, tags: list[str]
    ):
        if not tags:
            return
        print(f"[TagWorker] 写入标签: user={tags}, assistant={tags}")
        user_node.tags = list(set(user_node.tags + tags))
        assistant_node.tags = list(set(assistant_node.tags + tags))
        if USE_WEBENGINE:
            self.conv_view.update_message_tags(user_node.id, user_node)
            self.conv_view.update_message_tags(assistant_node.id, assistant_node)
        else:
            for b in self._bubbles:
                if b.node is user_node or b.node is assistant_node:
                    b.update_tags(self.conv)
        if self.conv:
            ws.save_conversation(self.conv)

    def _update_conv_tags_display(self):
        if not self.conv:
            return
        while self._tags_layout.count():
            item = self._tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from ..styles import TAG_CHIP
        for tag in self.conv.tags:
            chip = QPushButton(tag)
            chip.setToolTip("右键删除标签")
            chip.setStyleSheet(TAG_CHIP)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setContextMenuPolicy(Qt.CustomContextMenu)
            chip.customContextMenuRequested.connect(
                lambda pos, t=tag, btn=chip: self._tag_ctx_menu(pos, t, btn)
            )
            self._tags_layout.addWidget(chip)

        add_btn = QPushButton("+")
        add_btn.setToolTip("添加标签")
        add_btn.setStyleSheet(TAG_CHIP)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_conv_tag)
        self._tags_layout.addWidget(add_btn)
        self._tags_layout.addStretch()

    def _tag_ctx_menu(self, pos, tag: str, chip: QPushButton):
        menu = QMenu(self)
        menu.addAction(f"删除「{tag}」").triggered.connect(
            lambda: self._remove_conv_tag(tag)
        )
        menu.exec(chip.mapToGlobal(pos))

    def _add_conv_tag(self):
        tag, ok = QInputDialog.getText(self, "添加标签", "标签名：")
        if ok and tag.strip() and self.conv:
            tag = tag.strip()
            if tag not in self.conv.tags:
                self.conv.tags.append(tag)
                self.conv.tags.sort()
                self._update_conv_tags_display()
                ws.save_conversation(self.conv)

    def _remove_conv_tag(self, tag: str):
        if self.conv and tag in self.conv.tags:
            self.conv.tags.remove(tag)
            self._update_conv_tags_display()
            ws.save_conversation(self.conv)

    def _on_msg_tag_add(self, msg_id: str):
        if not self.conv:
            return
        node = None
        for m in self.conv.messages:
            if m.id == msg_id:
                node = m
                break
        if not node:
            return
        tag, ok = QInputDialog.getText(self, "添加标签", "标签名：")
        if ok and tag.strip():
            tag = tag.strip()
            if tag not in node.tags:
                node.tags.append(tag)
                self.conv_view.update_message_tags(msg_id, node)
                ws.save_conversation(self.conv)

    def _on_msg_tag_remove(self, msg_id: str, tag: str):
        if not self.conv:
            return
        node = None
        for m in self.conv.messages:
            if m.id == msg_id:
                node = m
                break
        if node and tag in node.tags:
            node.tags.remove(tag)
            self.conv_view.update_message_tags(msg_id, node)
            ws.save_conversation(self.conv)

    def _on_title_dbl_click(self, event):
        if not self.conv:
            return
        title, ok = QInputDialog.getText(
            self, "重命名对话", "新标题：", text=self.conv.title
        )
        if ok and title.strip():
            self.conv.title = title.strip()
            self._conv_title.setText(self.conv.title)
            ws.save_conversation(self.conv)

    # ── 上下文菜单（WebEngine 路径） ──

    def _build_ctx_menu(self, sel: str, msg_id: str):
        """ConversationView 右键回调：(选中文字, 消息ID) -> QMenu"""
        menu = QMenu(self)
        if sel and msg_id:
            node = None
            if self.conv:
                for m in self.conv.messages:
                    if m.id == msg_id:
                        node = m
                        break
            if node:
                lbl = (
                    f"💬  追问「{sel[:20]}…」"
                    if len(sel) > 20
                    else f"💬  追问「{sel}」"
                )
                menu.addAction(lbl).triggered.connect(
                    lambda checked=False, n=node, s=sel: self._start_followup(n, s)
                )
                link_lbl = (
                    f"🔗  链接「{sel[:20]}…」到..."
                    if len(sel) > 20
                    else f"🔗  链接「{sel}」到..."
                )
                menu.addAction(link_lbl).triggered.connect(
                    lambda checked=False, n=node, s=sel: self._on_link_create(n, s)
                )
                if node.role == "assistant":
                    menu.addAction("↻  重试").triggered.connect(
                        lambda checked=False, n=node: self._on_retry_assistant(n)
                    )
        else:
            a = menu.addAction("💬  追问（请先选中文字）")
            a.setEnabled(False)
        return menu

    def _start_followup(self, node: MessageNode, sel: str):
        from .dialogs import FollowUpDialog
        dlg = FollowUpDialog(sel, self)
        if dlg.exec() == QDialog.Accepted:
            q = dlg.question()
            if q:
                self.conv_view.annotation_created.emit(node, sel, q)

    def _on_annotation_clicked(self, node: MessageNode, ann: Annotation):
        self.ann_panel.show_annotation(self.conv, node, ann)

    def _on_ann_created(self, node: MessageNode, quoted: str, question: str):
        ann = Annotation(
            id=str(uuid.uuid4()), quoted_text=quoted, user_question=question
        )
        node.annotations.append(ann)
        if self.conv:
            ws.save_conversation(self.conv)
            if USE_WEBENGINE:
                self.conv_view.reload_all(self.conv)
            self.ann_panel.show_annotation(self.conv, node, ann)

    def _on_retry_assistant(self, assistant_node: MessageNode):
        if not self.conv or (self._worker and self._worker.isRunning()):
            return
        try:
            idx = self.conv.messages.index(assistant_node)
        except ValueError:
            return
        if idx < 1 or self.conv.messages[idx - 1].role != "user":
            return
        user_node = self.conv.messages[idx - 1]

        dlg = EditMessageDialog(user_node.content, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_text = dlg.text()
        if not new_text:
            return

        user_node.content = new_text
        self.conv.messages = self.conv.messages[:idx]
        remaining_ids = {m.id for m in self.conv.messages}
        self.conv.links = [
            l for l in self.conv.links if l.source_msg_id in remaining_ids
        ]

        anode = MessageNode(id=str(uuid.uuid4()), role="assistant", content="")
        self.conv.messages.append(anode)

        if USE_WEBENGINE:
            self.conv_view.reload_all(self.conv)
            self.conv_view.start_streaming(anode.id)
            self._streaming_msg_id = anode.id
            self._buf = ""
        else:
            bi = next((i for i, b in enumerate(self._bubbles) if b.node is assistant_node), None)
            if bi is not None:
                if bi > 0 and self._bubbles[bi - 1].node is user_node:
                    self._bubbles[bi - 1].refresh()
                for b in self._bubbles[bi:]:
                    self.msg_lay.removeWidget(b)
                    b.deleteLater()
                self._bubbles = self._bubbles[:bi]
            self._stream_bubble = self._add_bubble(anode, streaming=True)
            self._user_scrolled_away = False
            self._scroll_to_bottom(force=True)

        self.send_btn.setEnabled(False)
        api_msgs = [{"role": m.role, "content": m.content} for m in self.conv.messages[:-1]]
        self._worker = ChatWorker(api_msgs)
        self._worker.token_received.connect(self._on_token)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()
        ws.save_conversation(self.conv)

    # ── 链接相关 ──

    def _on_inline_link_clicked(self, link_id: str):
        if not self.conv:
            return
        for link in self.conv.links:
            if link.id == link_id:
                self._navigate_to(link.target_conv_id, link.target_msg_id)
                return

    link_create_requested = Signal(object, str)

    def _on_link_create(self, node, selected_text: str = ""):
        if not self.conv or not isinstance(node, MessageNode):
            return
        dlg = LinkPickerDialog(self.conv, node, self)
        if selected_text:
            dlg.set_selected_text(selected_text)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_conv_id, target_msg_id = dlg.result()
        if not target_conv_id:
            return
        new_link = Link(
            id=str(uuid.uuid4()),
            source_msg_id=node.id,
            target_conv_id=target_conv_id,
            target_msg_id=target_msg_id,
            selected_text=selected_text,
        )
        self.conv.links.append(new_link)
        ws.save_conversation(self.conv)
        if USE_WEBENGINE:
            self.conv_view.reload_all(self.conv)
        else:
            self._refresh_all_bubble_links()

    def _on_link_delete(self, link_id: str):
        if not self.conv:
            return
        self.conv.links = [l for l in self.conv.links if l.id != link_id]
        ws.save_conversation(self.conv)
        if USE_WEBENGINE:
            self.conv_view._conv_titles = {c.id: c.title for c in ws.conversations.values()}
            self.conv_view.reload_all(self.conv)

    def _on_show_backlinks(self, node: MessageNode):
        if not self.conv:
            return
        msg_backlinks = ws.get_backlinks(self.conv.id, node.id)
        conv_backlinks = ws.get_backlinks(self.conv.id, "")
        all_backlinks = msg_backlinks + conv_backlinks
        if not all_backlinks:
            return
        dlg = BacklinksDialog(all_backlinks, ws.conversations, node, self)
        dlg.navigate_requested.connect(lambda cid, mid: self._navigate_to(cid, mid))
        dlg.exec()

    def _navigate_to(self, conv_id: str, msg_id: str = ""):
        target_conv = ws.conversations.get(conv_id)
        if not target_conv:
            return
        if self.conv and self.conv.id != conv_id:
            ws.save_conversation(self.conv)
        if self.conv is None or self.conv.id != conv_id:
            if msg_id:
                self.conv_view._pending_scroll_msg_id = msg_id
            self.load_conversation(target_conv)
        elif msg_id:
            if USE_WEBENGINE:
                self.conv_view.scroll_to_message(msg_id)
            else:
                self._scroll_to_message(msg_id)

    # ── QTextBrowser 回退路径 ──

    def _add_bubble(self, node: MessageNode, streaming: bool = False) -> MessageBubble:
        b = MessageBubble(node, streaming=streaming)
        b.annotation_clicked.connect(
            lambda nd, an, c=self.conv: self.ann_panel.show_annotation(c, nd, an)
        )
        b.annotation_created.connect(self._on_ann_created)
        b.retry_requested.connect(self._on_retry_assistant)
        b.link_navigate.connect(lambda cid, mid: self._navigate_to(cid, mid))
        b.link_create_requested.connect(lambda n, t: self._on_link_create(n, t))
        b.backlinks_requested.connect(lambda n: self._on_show_backlinks(n))
        self.msg_lay.insertWidget(self.msg_lay.count() - 1, b)
        self._bubbles.append(b)
        if self.conv and not streaming:
            self._refresh_bubble_links(b)
        b.update_tags(self.conv)
        return b

    def _refresh_bubble_links(self, bubble: MessageBubble):
        if not self.conv:
            return
        node = bubble.node
        outgoing = [l for l in self.conv.links if l.source_msg_id == node.id]
        msg_backlinks = ws.get_backlinks(self.conv.id, node.id)
        conv_backlinks = ws.get_backlinks(self.conv.id, "")
        backlinks_count = len(msg_backlinks) + len(conv_backlinks)
        conv_map = {c.id: c.title for c in ws.conversations.values()}
        bubble.refresh_links(outgoing, backlinks_count, conv_map)

    def _refresh_all_bubble_links(self):
        for b in self._bubbles:
            self._refresh_bubble_links(b)

    def _near_bottom(self, margin: int = 72) -> bool:
        bar = self.scroll.verticalScrollBar()
        return bar.maximum() - bar.value() <= margin

    def _on_scroll_moved(self, _value: int):
        if self._near_bottom():
            self._user_scrolled_away = False
        else:
            self._user_scrolled_away = True

    def _scroll_to_bottom(self, force: bool = False):
        if not force and self._user_scrolled_away:
            return
        QTimer.singleShot(
            0,
            lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()
            ),
        )

    def _scroll_to_message(self, msg_id: str):
        for b in self._bubbles:
            if b.node.id == msg_id:
                self.scroll.ensureWidgetVisible(b, 50, 100)
                orig = b.styleSheet()
                b.setStyleSheet(
                    "background:#1e3a5f;border:1px solid #60a5fa;border-radius:12px;"
                )
                QTimer.singleShot(1500, lambda w=b, s=orig: w.setStyleSheet(s))
                break

    # ── 事件 ──

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
                self.send_message()
                return True
        return super().eventFilter(obj, event)
