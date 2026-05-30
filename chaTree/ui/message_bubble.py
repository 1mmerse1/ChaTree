"""单条消息气泡（Markdown、注释锚点、追问、重试）。"""

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..constants import USE_WEBENGINE
from ..markdown_render import render_msg_body, render_msg_html
from ..models import Link, MessageNode
from ..styles import BTN_GHOST, LINK_ACTION_BTN
from .dialogs import FollowUpDialog

if USE_WEBENGINE:
    from ..web_engine_content import WebEngineContentView
else:
    from PySide6.QtWidgets import QTextBrowser


class MessageBubble(QWidget):
    annotation_clicked = Signal(object, object)
    annotation_created = Signal(object, str, str)
    retry_requested = Signal(object)
    link_navigate = Signal(str, str)  # (conv_id, msg_id)
    link_create_requested = Signal(object, str)  # (MessageNode, selected_text_or_empty)
    backlinks_requested = Signal(object)  # MessageNode

    def __init__(self, node: MessageNode, streaming: bool = False):
        super().__init__()
        self.node = node
        self.streaming = streaming
        self._is_user = node.role == "user"
        self._links: list = []
        self._build()

    def _build(self):
        is_user = self._is_user
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        if is_user:
            outer.addStretch()

        wrap = QWidget()
        wrap.setMaximumWidth(700)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        rl = QLabel("你" if is_user else "助手")
        rl.setStyleSheet(
            f"color:{'#63b3ed' if is_user else '#68d391'};"
            "font-size:11px;font-weight:600;"
        )
        v.addWidget(rl)

        bubble = QWidget()
        bubble.setStyleSheet(
            f"background:{'#1a365d' if is_user else '#1a202c'};"
            f"border:1px solid {'#2c5282' if is_user else '#2d3748'};"
            "border-radius:12px;"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(14, 12, 14, 12)

        if USE_WEBENGINE:
            self._web = WebEngineContentView(self)
            self._web.set_page_color('#1a365d' if is_user else '#1a202c')
            self._web.annotation_clicked.connect(self.annotation_clicked)
            self._web.link_clicked.connect(self._on_inline_link_clicked)
            self._web.set_annotation_data(self.node, self.node.annotations)
            self._web.set_context_menu_builder(self._build_ctx_menu)
            self._update_html()
            bl.addWidget(self._web)
        else:
            self.browser = QTextBrowser()  # type: ignore[reportUnboundVariable]
            self.browser.setOpenLinks(False)
            self.browser.setFrameShape(QTextBrowser.NoFrame)
            self.browser.setStyleSheet("background:transparent;border:none;")
            self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            self.browser.anchorClicked.connect(self._on_anchor)
            if not is_user:
                self.browser.setContextMenuPolicy(Qt.CustomContextMenu)
                self.browser.customContextMenuRequested.connect(self._ctx_menu)

            self._update_html()
            bl.addWidget(self.browser)
        v.addWidget(bubble)

        self._actions = QWidget()
        ar = QHBoxLayout(self._actions)
        ar.setContentsMargins(4, 0, 0, 0)
        ar.addStretch()

        # 建立连接按钮
        link_btn = QPushButton("🔗  建立连接")
        link_btn.setToolTip("将本条消息连接到其他对话或消息")
        link_btn.setCursor(Qt.PointingHandCursor)
        link_btn.setStyleSheet(LINK_ACTION_BTN)
        link_btn.clicked.connect(lambda: self.link_create_requested.emit(self.node, ""))
        ar.addWidget(link_btn)

        if not is_user:
            retry = QPushButton("↻  重试")
            retry.setToolTip("编辑上一条提问并重新生成本条回答")
            retry.setCursor(Qt.PointingHandCursor)
            retry.setStyleSheet(
                BTN_GHOST
                + "QPushButton{color:#718096;font-size:11px;padding:2px 8px;}"
                "QPushButton:hover{color:#90cdf4;background:#1a2744;}"
            )
            retry.clicked.connect(lambda: self.retry_requested.emit(self.node))
            ar.addWidget(retry)

        # 反向链接按钮（初始隐藏，由 refresh_links 控制）
        self._backlink_btn = QPushButton("← 反向链接")
        self._backlink_btn.setToolTip("查看谁链接到了本条消息")
        self._backlink_btn.setCursor(Qt.PointingHandCursor)
        self._backlink_btn.setStyleSheet(BTN_GHOST + "QPushButton{color:#718096;font-size:11px;padding:2px 8px;}"
            "QPushButton:hover{color:#c4b5fd;background:#2d1b69;}")
        self._backlink_btn.clicked.connect(lambda: self.backlinks_requested.emit(self.node))
        self._backlink_btn.setVisible(False)
        ar.addWidget(self._backlink_btn)

        self._actions.setVisible(not self.streaming)
        v.addWidget(self._actions)

        # 消息标签行
        self._tag_row = QWidget()
        self._tag_row.setVisible(True)
        self._tag_layout = QHBoxLayout(self._tag_row)
        self._tag_layout.setContentsMargins(4, 2, 0, 0)
        self._tag_layout.setSpacing(4)
        self._tag_layout.addStretch()
        v.addWidget(self._tag_row)

        # 链接徽章行
        self._link_badges = QWidget()
        self._link_badges.setVisible(False)
        bl_lo = QHBoxLayout(self._link_badges)
        bl_lo.setContentsMargins(4, 2, 0, 0)
        bl_lo.setSpacing(6)
        bl_lo.addStretch()
        v.addWidget(self._link_badges)

        outer.addWidget(wrap)
        if not is_user:
            outer.addStretch()

    def _update_html(self):
        if USE_WEBENGINE:
            body = render_msg_body(
                self.node.content, self.node.annotations, self.streaming,
                links=self._links,
            )
            if not self._web._loaded:
                self._web.set_html(body, cursor_visible=self.streaming)
            else:
                self._web.update_body(body, cursor_visible=self.streaming)
        else:
            html = render_msg_html(
                self.node.content, self.node.annotations, self.streaming,
                links=self._links,
            )
            self.browser.setHtml(html)
            w = self.browser.viewport().width() or 660
            self.browser.document().setTextWidth(w)
            h = int(self.browser.document().size().height()) + 8
            self.browser.setFixedHeight(max(h, 24))

    def refresh(self):
        self._update_html()

    def finalize(self):
        self.streaming = False
        self._update_html()
        self._actions.setVisible(True)

    # ── QTextBrowser 路径专用 ──

    def _on_anchor(self, url: QUrl):
        if url.scheme() == "ann":
            ann_id = url.host()
            for ann in self.node.annotations:
                if ann.id == ann_id:
                    self.annotation_clicked.emit(self.node, ann)
                    break
        elif url.scheme() == "link":
            self._on_inline_link_clicked(url.host())

    def _ctx_menu(self, pos):
        sel = self.browser.textCursor().selectedText().strip()
        menu = QMenu(self)
        if sel:
            lbl = (
                f"💬  追问「{sel[:20]}…」"
                if len(sel) > 20
                else f"💬  追问「{sel}」"
            )
            menu.addAction(lbl).triggered.connect(lambda: self._start_followup(sel))
            link_lbl = (
                f"🔗  链接「{sel[:20]}…」到..."
                if len(sel) > 20
                else f"🔗  链接「{sel}」到..."
            )
            menu.addAction(link_lbl).triggered.connect(lambda: self._start_link_from_text(sel))
        else:
            a = menu.addAction("💬  追问（请先选中文字）")
            a.setEnabled(False)
        menu.exec(self.browser.viewport().mapToGlobal(pos))

    # ── WebEngine 路径专用 ──

    def _build_ctx_menu(self, sel: str):
        """WebEngine 路径：异步获取选中文字后构建右键菜单。"""
        menu = QMenu(self)
        if sel:
            lbl = (
                f"💬  追问「{sel[:20]}…」"
                if len(sel) > 20
                else f"💬  追问「{sel}」"
            )
            menu.addAction(lbl).triggered.connect(lambda: self._start_followup(sel))
            link_lbl = (
                f"🔗  链接「{sel[:20]}…」到..."
                if len(sel) > 20
                else f"🔗  链接「{sel}」到..."
            )
            menu.addAction(link_lbl).triggered.connect(lambda: self._start_link_from_text(sel))
        else:
            a = menu.addAction("💬  追问（请先选中文字）")
            a.setEnabled(False)
        return menu

    def _start_followup(self, sel: str):
        dlg = FollowUpDialog(sel, self)
        if dlg.exec() == QDialog.Accepted:
            q = dlg.question()
            if q:
                self.annotation_created.emit(self.node, sel, q)

    def _start_link_from_text(self, sel: str):
        self.link_create_requested.emit(self.node, sel)

    def _on_inline_link_clicked(self, link_id: str):
        """点击内联链接标记时导航到目标。"""
        for link in self._links:
            if link.id == link_id:
                self.link_navigate.emit(link.target_conv_id, link.target_msg_id)
                return

    def refresh_links(self, outgoing: list, backlinks_count: int, conv_map: dict):
        """刷新链接徽章和反向链接按钮，同时更新内联标记。"""
        # 存储链接用于内联渲染
        self._links = outgoing
        self._update_html()

        # 清空现有徽章（保留最后的 stretch）
        lo = self._link_badges.layout()
        while lo and lo.count() > 1:
            item = lo.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not outgoing:
            self._link_badges.setVisible(False)
        else:
            from ..styles import LINK_BADGE
            for link in outgoing:
                target_title = conv_map.get(link.target_conv_id, "(未知对话)")
                badge_text = f"→ {target_title}"
                if link.target_msg_id:
                    badge_text += " / 消息"
                if link.selected_text:
                    badge_text += f" [{link.selected_text[:15]}...]"
                btn = QPushButton(badge_text)
                btn.setToolTip(f"导航到: {target_title}")
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet(LINK_BADGE)
                btn.clicked.connect(
                    lambda checked, l=link: self.link_navigate.emit(
                        l.target_conv_id, l.target_msg_id
                    )
                )
                lo.insertWidget(lo.count() - 1, btn)
            self._link_badges.setVisible(True)

        # 更新反向链接按钮
        if backlinks_count > 0:
            self._backlink_btn.setText(f"← 反向链接 ({backlinks_count})")
            self._backlink_btn.setVisible(True)
        else:
            self._backlink_btn.setVisible(False)

    def update_tags(self, conv: object = None):
        """刷新消息级标签 chip 显示。"""
        lo = self._tag_layout
        while lo and lo.count() > 1:
            item = lo.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from ..styles import TAG_CHIP
        for tag in self.node.tags:
            chip = QPushButton(tag)
            chip.setToolTip("右键删除标签")
            chip.setStyleSheet(TAG_CHIP)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setContextMenuPolicy(Qt.CustomContextMenu)
            chip.customContextMenuRequested.connect(
                lambda pos, t=tag, c=conv, btn=chip: self._msg_tag_ctx_menu(pos, t, c, btn)
            )
            lo.insertWidget(lo.count() - 1, chip)

        add_btn = QPushButton("+")
        add_btn.setToolTip("添加标签")
        add_btn.setStyleSheet(TAG_CHIP)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: self._add_msg_tag(conv))
        lo.insertWidget(lo.count() - 1, add_btn)
        self._tag_row.setVisible(True)

    def _msg_tag_ctx_menu(self, pos, tag: str, conv: object, chip):
        menu = QMenu(self)
        menu.addAction(f"删除「{tag}」").triggered.connect(
            lambda: self._remove_msg_tag(tag, conv)
        )
        menu.exec(chip.mapToGlobal(pos))

    def _add_msg_tag(self, conv: object = None):
        tag, ok = QInputDialog.getText(self, "添加标签", "标签名：")
        if ok and tag.strip():
            tag = tag.strip()
            if tag not in self.node.tags:
                self.node.tags.append(tag)
                self.update_tags(conv)
                if conv:
                    from ..workspace import ws
                    all_tags = set(conv.tags)
                    for m in conv.messages:
                        all_tags.update(m.tags)
                    conv.tags = sorted(all_tags)
                    ws.save_conversation(conv)

    def _remove_msg_tag(self, tag: str, conv: object = None):
        if tag in self.node.tags:
            self.node.tags.remove(tag)
            self.update_tags(conv)
            if conv:
                from ..workspace import ws
                ws.save_conversation(conv)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not USE_WEBENGINE:
            self._update_html()
