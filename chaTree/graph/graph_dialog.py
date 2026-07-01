"""知识图谱对话框 — pyvis + QWebEngineView 图谱可视化。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models import Conversation
from ..styles import BTN_GHOST, BTN_PRIMARY, BTN_SECONDARY, INPUT_STYLE
from ..workspace import ws
from .graph_data import GraphBuilder, _conv_color, _CONV_COLORS
from .graph_view import GraphWebView


class GraphDialog(QDialog):
    """知识图谱可视化对话框（非模态）。

    Signals:
        navigate_requested(conv_id, msg_id): 请求在主窗口跳转到指定消息。
    """

    navigate_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("知识图谱")
        self.setModal(False)  # 非模态：允许同时操作主窗口
        self.resize(1150, 720)
        self.setMinimumSize(850, 550)
        self.setStyleSheet(
            """
            QDialog { background: #0f1117; border: 1px solid #2d3748; border-radius: 12px; }
            QDialog QWidget { background: #0f1117; }
            """
        )

        self._builder = GraphBuilder()
        self._conv_checkboxes: dict[str, QCheckBox] = {}
        self._current_conv_id: str = ""
        self._current_msg_id: str = ""
        self._node_info_cache: dict[str, dict] = {}

        self._build()
        self._load_graph()

    # ── 构建 UI ────────────────────────────────────────────────────

    def _build(self):
        """三栏布局：筛选面板 | 图谱 | 详情面板。"""
        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # ── 左侧：筛选面板 ──
        self._filter_panel = self._build_filter_panel()
        main_lay.addWidget(self._filter_panel)

        # ── 中间：图谱 + 工具栏 ──
        center = QWidget()
        center.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center.setStyleSheet("background: #0f1117;")
        c_lay = QVBoxLayout(center)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(0)

        # 工具栏
        toolbar = self._build_toolbar()
        c_lay.addWidget(toolbar)

        # WebEngine 图谱（双击节点 → 导航 + 关闭）
        self._graph_view = GraphWebView()
        self._graph_view.navigate_requested.connect(
            lambda cid, mid: (
                self.navigate_requested.emit(cid, mid),
                self.accept(),
            )
        )
        self._graph_view.node_selected.connect(self._on_node_selected)
        c_lay.addWidget(self._graph_view, 1)

        main_lay.addWidget(center, 1)

        # ── 右侧：详情面板 ──
        self._detail_panel = self._build_detail_panel()
        main_lay.addWidget(self._detail_panel)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(42)
        bar.setStyleSheet(
            "background: #1a202c; border-bottom: 1px solid #2d3748;"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(8)

        title = QLabel("🕸️  知识图谱")
        title.setStyleSheet(
            "color: #e2e8f0; font-size: 14px; font-weight: 600;"
        )
        lay.addWidget(title)

        # 节点/边统计
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet(
            "color: #718096; font-size: 11px;"
        )
        lay.addWidget(self._stats_label)

        lay.addStretch()

        refresh_btn = QPushButton("🔄  刷新")
        refresh_btn.setStyleSheet(BTN_SECONDARY)
        refresh_btn.clicked.connect(self._load_graph)
        lay.addWidget(refresh_btn)

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(BTN_PRIMARY)
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn)

        return bar

    def _build_filter_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(200)
        panel.setStyleSheet("background: #0a0d14;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)

        # 标题
        lbl = QLabel("筛选对话")
        lbl.setStyleSheet(
            "color: #e2e8f0; font-size: 13px; font-weight: 600; padding: 4px 0;"
        )
        lay.addWidget(lbl)

        # 搜索框
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("搜索节点...")
        self._search_box.setStyleSheet(
            INPUT_STYLE
            + "QLineEdit { padding: 5px 8px; font-size: 12px; }"
        )
        self._search_box.setFixedHeight(28)
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search)
        lay.addWidget(self._search_box)

        # 全选 / 清除
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        all_btn = QPushButton("全选")
        all_btn.setStyleSheet(BTN_SECONDARY)
        all_btn.clicked.connect(lambda: self._set_all_checked(True))
        btn_row.addWidget(all_btn)
        none_btn = QPushButton("清除")
        none_btn.setStyleSheet(BTN_SECONDARY)
        none_btn.clicked.connect(lambda: self._set_all_checked(False))
        btn_row.addWidget(none_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # 对话 checkbox 列表（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self._conv_list = QWidget()
        self._conv_list.setStyleSheet("background: transparent;")
        self._conv_layout = QVBoxLayout(self._conv_list)
        self._conv_layout.setContentsMargins(0, 4, 0, 0)
        self._conv_layout.setSpacing(2)
        self._conv_layout.addStretch()
        scroll.setWidget(self._conv_list)
        lay.addWidget(scroll, 1)

        return panel

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(260)
        panel.setStyleSheet(
            "background: #1a202c; border-left: 1px solid #2d3748;"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)

        header = QLabel("节点详情")
        header.setStyleSheet(
            "color: #e2e8f0; font-size: 14px; font-weight: 600;"
        )
        lay.addWidget(header)

        self._detail_title = QLabel("点击节点查看详情")
        self._detail_title.setStyleSheet(
            "color: #a0aec0; font-size: 12px;"
        )
        self._detail_title.setWordWrap(True)
        lay.addWidget(self._detail_title)

        self._detail_content = QTextEdit()
        self._detail_content.setReadOnly(True)
        self._detail_content.setStyleSheet(
            INPUT_STYLE
            + "QTextEdit { background: #0f1117; font-size: 12px;"
            " border: 1px solid #2d3748; }"
        )
        self._detail_content.setMinimumHeight(80)
        self._detail_content.setMaximumHeight(200)
        lay.addWidget(self._detail_content)

        self._detail_tags = QLabel()
        self._detail_tags.setStyleSheet(
            "color: #7dd3fc; font-size: 11px;"
        )
        self._detail_tags.setWordWrap(True)
        lay.addWidget(self._detail_tags)

        self._nav_btn = QPushButton("跳转到对话  →")
        self._nav_btn.setStyleSheet(BTN_PRIMARY)
        self._nav_btn.setEnabled(False)
        self._nav_btn.clicked.connect(self._on_nav_clicked)
        lay.addWidget(self._nav_btn)

        lay.addStretch()

        return panel

    # ── 数据加载 ───────────────────────────────────────────────────

    def _load_graph(self):
        """构建 pyvis Network 并加载到 WebEngine。"""
        # 收集当前选中的对话 ID
        visible_ids = {
            cid
            for cid, cb in self._conv_checkboxes.items()
            if cb.isChecked()
        }

        # 如果没有筛选条件，显示全部
        if not visible_ids:
            visible_ids = set(ws.conversations.keys())

        net = self._builder.build(conversation_ids=list(visible_ids))

        # 缓存节点信息（用于详情面板）— 按 round 结构
        self._node_info_cache.clear()
        for cid in visible_ids:
            conv = ws.conversations.get(cid)
            if not conv:
                continue
            # 按轮次分组：user_msg_id → {question, answer}
            current_user_id: str | None = None
            for i, msg in enumerate(conv.messages):
                if msg.role == "user":
                    current_user_id = msg.id
                    nid = f"{cid}::{msg.id}"
                    # 找紧随其后的 assistant
                    answer = ""
                    if i + 1 < len(conv.messages):
                        nxt = conv.messages[i + 1]
                        if nxt.role == "assistant":
                            answer = nxt.content
                    self._node_info_cache[nid] = {
                        "conv_id": cid,
                        "msg_id": msg.id,
                        "conv_title": conv.title,
                        "question": msg.content,
                        "answer": answer,
                        "tags": msg.tags,
                    }

        self._graph_view.load_graph(net)

        # 更新统计
        node_count = len(net.nodes)
        edge_count = len(net.edges)
        self._stats_label.setText(f"节点: {node_count}  ·  边: {edge_count}")

    def _populate_filter(self):
        """（重新）填充筛选面板的对话列表。"""
        # 清除旧的 checkbox
        for cb in self._conv_checkboxes.values():
            cb.deleteLater()
        self._conv_checkboxes.clear()

        # 移除旧 widget（保留最后的 stretch）
        while self._conv_layout.count() > 1:
            item = self._conv_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, (cid, conv) in enumerate(
            sorted(ws.conversations.items(), key=lambda x: x[1].title)
        ):
            color = _conv_color(i)
            cb = QCheckBox(conv.title)
            cb.setChecked(True)
            cb.setStyleSheet(
                f"color: {color}; font-size: 12px; padding: 3px 4px;"
                "spacing: 6px;"
            )
            cb.toggled.connect(lambda checked, cid=cid: self._on_filter_toggled())
            self._conv_layout.insertWidget(self._conv_layout.count() - 1, cb)
            self._conv_checkboxes[cid] = cb

    # ── 筛选 ───────────────────────────────────────────────────────

    def _on_filter_toggled(self):
        """对话 checkbox 切换 → 重建图谱。"""
        self._load_graph()

    def _set_all_checked(self, checked: bool):
        for cb in self._conv_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._load_graph()

    def _on_search(self, text: str):
        """搜索过滤：重建图谱，只包含匹配的对话。"""
        q = text.strip().lower()
        if not q:
            # 恢复全部选中
            for cb in self._conv_checkboxes.values():
                cb.blockSignals(True)
                cb.setChecked(True)
                cb.blockSignals(False)
            self._load_graph()
            return

        # 筛选匹配的对话
        for cid, conv in ws.conversations.items():
            match = (
                q in conv.title.lower()
                or any(q in msg.content.lower() for msg in conv.messages)
            )
            cb = self._conv_checkboxes.get(cid)
            if cb:
                cb.blockSignals(True)
                cb.setChecked(match)
                cb.blockSignals(False)

        self._load_graph()

    # ── 交互 ───────────────────────────────────────────────────────

    def _on_node_selected(self, conv_id: str, msg_id: str, node_id: str):
        """单击节点 → 更新右侧详情面板（显示 Q&A 轮次）。"""
        info = self._node_info_cache.get(node_id, {})
        if not info:
            return

        self._current_conv_id = conv_id
        self._current_msg_id = msg_id

        self._detail_title.setText(
            f"<b>{info.get('conv_title', '')}</b>"
            f"<br><span style='color:#718096;'>对话轮次</span>"
        )

        question = info.get("question", "")
        answer = info.get("answer", "")
        display = f"❓ {question[:300]}"
        if answer:
            display += f"\n\n💬 {answer[:300]}"
        self._detail_content.setPlainText(display)

        tags = info.get("tags", [])
        if tags:
            self._detail_tags.setText("标签: " + ", ".join(tags))
        else:
            self._detail_tags.setText("")

        self._nav_btn.setEnabled(True)

    def _on_nav_clicked(self):
        """详情面板「跳转到对话」按钮 → 导航并关闭。"""
        if self._current_conv_id:
            self.navigate_requested.emit(
                self._current_conv_id, self._current_msg_id
            )
            self.accept()

    # ── 公开方法 ───────────────────────────────────────────────────

    def showEvent(self, event):
        """对话框显示时刷新筛选列表和图谱。"""
        super().showEvent(event)
        self._populate_filter()
        self._load_graph()
