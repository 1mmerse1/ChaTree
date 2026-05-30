"""主窗口布局与演示数据。"""

from __future__ import annotations

import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QSplitter, QWidget

from ..models import Annotation, Conversation, MessageNode
from ..styles import APP_QSS
from ..workspace import ws
from .annotation_panel import AnnotationPanel
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
        self.chat_panel = ChatPanel(self.ann_panel)
        self.sidebar = Sidebar()
        self.sidebar.conversation_selected.connect(self.chat_panel.load_conversation)
        self.sidebar.search_navigate.connect(
            lambda cid, mid: self.chat_panel._navigate_to(cid, mid)
        )

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.chat_panel)
        self._splitter.addWidget(self.ann_panel)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes([980, 300])
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)

        lay.addWidget(self.sidebar)
        lay.addWidget(self._splitter, 1)

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
