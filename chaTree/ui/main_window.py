"""主窗口布局与演示数据。"""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from ..export import (
    export_conversation_to_md,
    export_workspace_to_files,
    export_workspace_to_md,
    sanitize_filename,
)
from ..models import Annotation, Conversation, MessageNode
from ..styles import APP_QSS
from ..workspace import ws
from .annotation_panel import AnnotationPanel
from .branch_panel import BranchPanel
from .chat_panel import ChatPanel
from .sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 对话管理")
        self.resize(1300, 820)
        self.setStyleSheet(APP_QSS)
        self._build()
        self._seed_demo()

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.ann_panel = AnnotationPanel()
        self.branch_panel = BranchPanel()

        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(self.ann_panel)    # Page 0
        self._right_stack.addWidget(self.branch_panel)  # Page 1
        self._right_stack.hide()  # 默认隐藏，打开注释/支线时才显示

        self.chat_panel = ChatPanel(self.ann_panel)
        self.sidebar = Sidebar()
        self.sidebar.conversation_selected.connect(self.chat_panel.load_conversation)
        self.sidebar.search_navigate.connect(
            lambda cid, mid: self.chat_panel._navigate_to(cid, mid)
        )

        # ── 右栏信号连接 ──
        # 注释扩展为支线
        self.ann_panel.branch_created.connect(self._on_branch_created)
        # 点击已扩展的注释 → 打开支线面板
        self.ann_panel.branch_requested.connect(self._open_branch_panel)
        # 注释面板打开时 → 显示右栏并切到注释页
        self.ann_panel.annotation_shown.connect(self._show_annotation_panel)
        # 任一面板关闭 → 隐藏右栏
        self.ann_panel.closed.connect(self._right_stack.hide)
        self.branch_panel.closed.connect(self._right_stack.hide)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.chat_panel)
        self._splitter.addWidget(self._right_stack)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes([980, 300])
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)

        lay.addWidget(self.sidebar)
        lay.addWidget(self._splitter, 1)

        self._build_menu_bar()

    def _build_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")

        export_cur = file_menu.addAction("导出当前对话...")
        export_cur.setShortcut("Ctrl+E")
        export_cur.triggered.connect(self._export_current)

        export_all = file_menu.addAction("导出全部对话（Obsidian Vault）...")
        export_all.setShortcut("Ctrl+Shift+E")
        export_all.triggered.connect(self._export_all)

        view_menu = menubar.addMenu("视图")

        graph_action = view_menu.addAction("知识图谱")
        graph_action.setShortcut("Ctrl+G")
        graph_action.triggered.connect(self._open_graph)

    def _export_current(self):
        """导出当前打开的对话为单个 .md 文件。"""
        conv = self.chat_panel.conv
        if not conv:
            return
        default_name = sanitize_filename(conv.title) + ".md"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出当前对话", default_name, "Markdown 文件 (*.md)"
        )
        if path:
            try:
                md = export_conversation_to_md(conv)
                Path(path).write_text(md, encoding="utf-8")
            except OSError:
                pass

    def _export_all(self):
        """导出全部对话为多文件 Obsidian Vault 结构（按文件夹树组织目录）。"""
        if not ws.conversations:
            return
        dir_path = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if dir_path:
            try:
                export_workspace_to_files(dir_path)
            except OSError:
                pass

    def _open_graph(self):
        """打开知识图谱对话框。"""
        from ..graph.graph_dialog import GraphDialog

        dlg = GraphDialog(self)
        dlg.navigate_requested.connect(
            lambda cid, mid: self.chat_panel._navigate_to(cid, mid)
        )
        dlg.show()

    def _on_branch_created(self, conv_id: str, branch_id: str):
        """注释扩展为支线后的回调 — 刷新主视图并打开支线面板。"""
        conv = ws.conversations.get(conv_id)
        if not conv:
            return
        # 如果当前对话是支线所属的对话，重新加载以更新内联标记
        if self.chat_panel.conv and self.chat_panel.conv.id == conv_id:
            from ..constants import USE_WEBENGINE
            if USE_WEBENGINE:
                self.chat_panel.conv_view.reload_all(conv)
        self._open_branch_panel(conv_id, branch_id)

    def _show_annotation_panel(self):
        """显示右栏注释面板。"""
        self._right_stack.setCurrentIndex(0)
        self._right_stack.show()

    def _open_branch_panel(self, conv_id: str, branch_id: str):
        """打开支线面板。"""
        conv = ws.conversations.get(conv_id)
        if not conv:
            return
        branch = None
        for b in conv.branches:
            if b.id == branch_id:
                branch = b
                break
        if branch:
            self.branch_panel.show_branch(conv, branch)
            self._right_stack.setCurrentIndex(1)
            self._right_stack.show()

    def _seed_demo(self):
        if ws.conversations:
            first = next(iter(ws.conversations.values()), None)
            if first:
                self.chat_panel.load_conversation(first)
            return

        folder = ws.add_folder("示例项目")
        conv = Conversation(id=str(uuid.uuid4()), title="量子计算入门")
        conv.messages = [
            MessageNode(
                id=str(uuid.uuid4()),
                role="user",
                content="量子计算和经典计算有什么本质区别？",
            ),
            MessageNode(
                id=str(uuid.uuid4()),
                role="assistant",
                content=(
                    "量子计算与经典计算的核心区别在于信息的基本单元。\n\n"
                    "| 特性 | 经典计算 | 量子计算 |\n"
                    "|------|---------|--------|\n"
                    "| 基本单元 | 比特（0或1）| 量子比特（qubit）|\n"
                    "| 状态 | 确定 | 叠加态 / 纠缠态 |\n"
                    "| 优势领域 | 通用计算 | 大数分解、量子模拟 |\n\n"
                    "量子计算机使用**量子比特（qubit）**，"
                    "它可以处于叠加态（superposition）——即同时是 0 和 1 的概率叠加，"
                    "用狄拉克符号表示为：\n\n"
                    "$$|\\psi\\rangle = \\alpha|0\\rangle + \\beta|1\\rangle$$\n\n"
                    "其中 $|\\alpha|^2 + |\\beta|^2 = 1$。\n\n"
                    "另一个关键特性是**纠缠（entanglement）**：多个量子比特可以相互关联，"
                    "对一个的操作会瞬间影响另一个，无论距离多远。\n\n"
                    "> Einstein 称此为「鬼魅般的超距作用」，贝尔实验已证明纠缠确实存在。"
                ),
                annotations=[
                    Annotation(
                        id="demo-ann-1",
                        quoted_text="叠加态（superposition）",
                        user_question="叠加态在数学上怎么表示？",
                        ai_answer=(
                            "叠加态用狄拉克符号表示为：\n\n"
                            "$$|\\psi\\rangle = \\alpha|0\\rangle + \\beta|1\\rangle$$\n\n"
                            "- $\\alpha$ 和 $\\beta$ 是**复数振幅**\n"
                            "- 满足归一化条件 $|\\alpha|^2 + |\\beta|^2 = 1$\n"
                            "- $|\\alpha|^2$ 是测量得 0 的概率，$|\\beta|^2$ 是测量得 1 的概率\n\n"
                            "在被测量之前，量子比特同时「携带」两种可能性。"
                        ),
                    ),
                    Annotation(
                        id="demo-ann-2",
                        quoted_text="纠缠（entanglement）",
                        user_question="纠缠和经典关联有什么本质不同？",
                        ai_answer=(
                            "| | 经典关联 | 量子纠缠 |\n"
                            "|--|---------|--------|\n"
                            "| 信息是否预先确定 | ✅ 是 | ❌ 否 |\n"
                            "| 测量结果 | 确定性 | 随机但关联 |\n"
                            "| 能否用隐变量解释 | ✅ 能 | ❌ 贝尔不等式排除 |\n\n"
                            "**经典关联**如一双手套——看到左手套即知另一只是右手套，"
                            "但信息在分开时就已确定。\n\n"
                            "**量子纠缠**不同：两个粒子在测量前都没有确定状态，"
                            "测量一个时结果是随机的，但另一个会瞬间呈现对应状态。"
                        ),
                    ),
                ],
            ),
        ]
        ws.add_conversation(conv, folder.id)
        self.sidebar.refresh()
        self.chat_panel.load_conversation(conv)
