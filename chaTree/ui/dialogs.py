"""模态对话框：追问、新建对话、API 设置、链接选择、反向链接。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QInputDialog,
    QWidget,
)

from ..model_presets import MODEL_PRESETS, preset_index_for_workspace
from ..models import Conversation, Folder, Link, MessageNode
from ..styles import (
    BACKLINK_CARD,
    BTN_GHOST,
    BTN_PRIMARY,
    BTN_SECONDARY,
    DIALOG_BASE,
    INPUT_STYLE,
    LINK_ACTION_BTN,
    LINK_BADGE,
)
from ..workspace import ws


class FollowUpDialog(QDialog):
    def __init__(self, selected: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("追问")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(DIALOG_BASE + INPUT_STYLE)
        self._build(selected)
        self.adjustSize()

    def _build(self, selected: str):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)

        h = QLabel("追问")
        h.setStyleSheet("color:#e2e8f0;font-size:17px;font-weight:700;")
        lay.addWidget(h)

        short = selected[:42] + ("…" if len(selected) > 42 else "")
        badge = QLabel(f"❝  {short}  ❞")
        badge.setStyleSheet(
            "color:#fde68a;background:#451a03;border-radius:7px;"
            "padding:8px 12px;font-size:12px;"
        )
        badge.setWordWrap(True)
        lay.addWidget(badge)

        lay.addWidget(QLabel("你的追问："))
        self.inp = QTextEdit()
        self.inp.setPlainText(f"请简明扼要地进一步解释「{selected}」。")
        self.inp.setFixedHeight(72)
        lay.addWidget(self.inp)

        row = QHBoxLayout()
        cc = QPushButton("取消")
        cc.setStyleSheet(BTN_GHOST)
        cc.clicked.connect(self.reject)
        ok = QPushButton("提交追问  →")
        ok.setStyleSheet(BTN_PRIMARY)
        ok.setFixedHeight(36)
        ok.setMinimumWidth(120)
        ok.clicked.connect(self.accept)
        row.addWidget(cc)
        row.addStretch()
        row.addWidget(ok)
        lay.addLayout(row)

    def question(self) -> str:
        return self.inp.toPlainText().strip()


class NewConversationDialog(QDialog):
    """新建对话：动态文件夹树与实时同步。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("新建对话")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setStyleSheet(
            DIALOG_BASE
            + INPUT_STYLE
            + """
            QTreeWidget {
                background: #0f1117; border: 1px solid #2d3748;
                border-radius: 7px; color: #d1d5db; font-size: 12px;
                outline: none;
            }
            QTreeWidget::item { padding: 5px 8px; border-radius: 4px; }
            QTreeWidget::item:selected { background: #1f2937; }
            QTreeWidget::item:hover:!selected { background: #1a202c; }
        """
        )
        self._fid: Optional[str] = None
        self._build()
        self.adjustSize()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 26, 30, 24)
        lay.setSpacing(0)

        hl = QLabel("新建对话")
        hl.setStyleSheet(
            "color:#f9fafb;font-size:20px;font-weight:700;letter-spacing:-0.3px;"
        )
        lay.addWidget(hl)
        lay.addSpacing(4)
        lay.addWidget(self._sub("填写标题并选择保存位置"))
        lay.addSpacing(20)

        lay.addWidget(self._sub("对话标题"))
        lay.addSpacing(5)
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("给这个对话起个名字…")
        self._title_edit.setFixedHeight(40)
        lay.addWidget(self._title_edit)
        lay.addSpacing(16)

        folder_hdr = QHBoxLayout()
        folder_hdr.addWidget(self._sub("保存位置（可选）"))
        folder_hdr.addStretch()
        add_fo_btn = QPushButton("+ 新建文件夹")
        add_fo_btn.setStyleSheet(BTN_SECONDARY)
        add_fo_btn.setFixedHeight(24)
        add_fo_btn.clicked.connect(self._add_folder)
        folder_hdr.addWidget(add_fo_btn)
        lay.addLayout(folder_hdr)
        lay.addSpacing(5)

        self._folder_tree = QTreeWidget()
        self._folder_tree.setHeaderHidden(True)
        self._folder_tree.setFixedHeight(130)
        self._folder_tree.setIndentation(14)
        self._folder_tree.itemClicked.connect(
            lambda item, _: setattr(self, "_fid", item.data(0, Qt.UserRole))
        )
        lay.addWidget(self._folder_tree)
        lay.addSpacing(24)

        row = QHBoxLayout()
        cc = QPushButton("取消")
        cc.setStyleSheet(BTN_GHOST)
        cc.setFixedHeight(40)
        cc.clicked.connect(self.reject)
        ok = QPushButton("创建对话  →")
        ok.setStyleSheet(BTN_PRIMARY)
        ok.setFixedHeight(40)
        ok.setMinimumWidth(130)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(cc)
        row.addStretch()
        row.addWidget(ok)
        lay.addLayout(row)

        self._rebuild_folder_tree()

    def showEvent(self, event):
        super().showEvent(event)
        self._rebuild_folder_tree()

    def _rebuild_folder_tree(self):
        self._folder_tree.clear()
        root_item = QTreeWidgetItem(["📂  根目录（不归类）"])
        root_item.setData(0, Qt.UserRole, None)
        self._folder_tree.addTopLevelItem(root_item)

        for fo in ws.folders:
            self._add_fo_item(self._folder_tree, fo)

        if self._fid is not None:
            self._reselect(self._folder_tree.invisibleRootItem(), self._fid)
        else:
            root_item.setSelected(True)

        self._folder_tree.expandAll()

    def _add_fo_item(self, parent, fo: Folder):
        item = QTreeWidgetItem(parent, [f"📁  {fo.name}"])
        item.setData(0, Qt.UserRole, fo.id)
        for sf in fo.subfolders:
            self._add_fo_item(item, sf)

    def _reselect(self, parent_item: QTreeWidgetItem, fid: str):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, Qt.UserRole) == fid:
                child.setSelected(True)
                return True
            if self._reselect(child, fid):
                return True
        return False

    def _add_folder(self):
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称：")
        if ok and name.strip():
            ws.add_folder(name.strip())
            self._rebuild_folder_tree()

    @staticmethod
    def _sub(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#9ca3af;font-size:11px;")
        return lbl

    def result_data(self) -> tuple:
        return self._title_edit.text().strip(), self._fid


class EditMessageDialog(QDialog):
    """编辑用户消息后重新生成助手回答。"""

    def __init__(
        self,
        initial: str,
        parent: Optional[QWidget] = None,
        title: str = "编辑并重新生成",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(DIALOG_BASE + INPUT_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)

        h = QLabel(title)
        h.setStyleSheet("color:#e2e8f0;font-size:17px;font-weight:700;")
        lay.addWidget(h)
        sub = QLabel("可修改你的提问，确认后将删除本条之后的对话并重新生成回答。")
        sub.setStyleSheet("color:#9ca3af;font-size:12px;")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        self._edit = QTextEdit()
        self._edit.setPlainText(initial)
        self._edit.setMinimumHeight(120)
        lay.addWidget(self._edit)

        row = QHBoxLayout()
        cc = QPushButton("取消")
        cc.setStyleSheet(BTN_GHOST)
        cc.clicked.connect(self.reject)
        ok = QPushButton("重新生成  →")
        ok.setStyleSheet(BTN_PRIMARY)
        ok.setMinimumWidth(120)
        ok.clicked.connect(self.accept)
        row.addWidget(cc)
        row.addStretch()
        row.addWidget(ok)
        lay.addLayout(row)

    def text(self) -> str:
        return self._edit.toPlainText().strip()


class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("API 设置")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet(
            DIALOG_BASE
            + INPUT_STYLE
            + """
            QListWidget {
                background: #0f1117;
                border: 1px solid #2d3748;
                border-radius: 8px;
                color: #e2e8f0;
                font-size: 13px;
                outline: none;
                padding: 4px;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: #2c5282;
                color: #e2e8f0;
            }
            QListWidget::item:hover:!selected {
                background: #1a202c;
            }
        """
        )
        self._build()
        self.adjustSize()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(8)

        h = QLabel("API 设置")
        h.setStyleSheet("color:#e2e8f0;font-size:17px;font-weight:700;")
        lay.addWidget(h)
        lay.addSpacing(4)

        hint = QLabel(
            "选择模型后自动匹配接口地址（无需填写 Base URL）。"
            "使用 Gemini 时请填写 Google AI Studio 的 API Key。"
        )
        hint.setStyleSheet("color:#4a5568;font-size:11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addSpacing(10)

        ll = QLabel("API Key")
        ll.setStyleSheet("color:#9ca3af;font-size:11px;")
        lay.addWidget(ll)
        self._key = QLineEdit(ws.api_key)
        self._key.setPlaceholderText("在各服务商控制台获取的密钥")
        self._key.setFixedHeight(40)
        self._key.setEchoMode(QLineEdit.Password)
        lay.addWidget(self._key)

        lay.addSpacing(10)
        lm = QLabel("模型")
        lm.setStyleSheet("color:#9ca3af;font-size:11px;")
        lay.addWidget(lm)

        self._model_list = QListWidget()
        for p in MODEL_PRESETS:
            it = QListWidgetItem(f"{p.display_name}\n{p.model_id}")
            self._model_list.addItem(it)
        self._model_list.setCurrentRow(
            preset_index_for_workspace(ws.model, ws.base_url)
        )
        self._model_list.setMinimumHeight(220)
        lay.addWidget(self._model_list)

        lay.addSpacing(8)
        self._auto_link_cb = QCheckBox("AI 自动推荐链接（每轮回答后分析关联并建议建立链接）")
        self._auto_link_cb.setChecked(ws.auto_link_suggestions)
        self._auto_link_cb.setStyleSheet(
            "color:#a0aec0;font-size:12px;spacing:8px;"
        )
        lay.addWidget(self._auto_link_cb)

        lay.addSpacing(14)
        row = QHBoxLayout()
        cc = QPushButton("取消")
        cc.setStyleSheet(BTN_GHOST)
        cc.clicked.connect(self.reject)
        ok = QPushButton("保存")
        ok.setStyleSheet(BTN_PRIMARY)
        ok.setFixedHeight(38)
        ok.clicked.connect(self._save)
        row.addWidget(cc)
        row.addStretch()
        row.addWidget(ok)
        lay.addLayout(row)

    def _save(self):
        ws.api_key = self._key.text().strip()
        row = self._model_list.currentRow()
        if row < 0:
            row = 0
        preset = MODEL_PRESETS[row]
        ws.model = preset.model_id
        ws.base_url = preset.base_url
        ws.auto_link_suggestions = self._auto_link_cb.isChecked()
        ws.save_settings()
        self.accept()


class LinkPickerDialog(QDialog):
    """选择链接目标的对话框 — 双 Tab：当前对话 + 浏览其他。"""

    def __init__(
        self,
        source_conv: Conversation,
        source_msg: MessageNode,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("建立连接")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setMinimumHeight(460)
        self.setStyleSheet(DIALOG_BASE + INPUT_STYLE)
        self._source_conv = source_conv
        self._source_msg = source_msg
        self._target_conv_id: str = ""
        self._target_msg_id: str = ""
        self._selected_text: str = ""
        self._build()
        self.adjustSize()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        h = QLabel("建立连接")
        h.setStyleSheet("color:#e2e8f0;font-size:17px;font-weight:700;")
        lay.addWidget(h)

        # 来源消息预览
        src_preview = (
            self._source_msg.content[:100] + "…"
            if len(self._source_msg.content) > 100
            else self._source_msg.content
        )
        role_label = "你" if self._source_msg.role == "user" else "助手"
        src_badge = QLabel(f"来源：{role_label}：{src_preview}")
        src_badge.setStyleSheet(
            "color:#94a3b8;background:#161f2e;border-radius:7px;"
            "padding:8px 12px;font-size:12px;"
        )
        src_badge.setWordWrap(True)
        lay.addWidget(src_badge)

        # 选中文字（如果有）
        if self._selected_text:
            tbadge = QLabel(f"❝  {self._selected_text[:60]}  ❞")
            tbadge.setStyleSheet(
                "color:#fde68a;background:#451a03;border-radius:6px;"
                "padding:5px 10px;font-size:11px;"
            )
            tbadge.setWordWrap(True)
            lay.addWidget(tbadge)

        # Tab 区
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #2d3748; border-radius: 8px; background: #0f1117; }"
            "QTabBar::tab { background: #1a202c; color: #94a3b8; padding: 8px 18px; "
            "border: 1px solid #2d3748; border-bottom: none; border-top-left-radius: 6px; "
            "border-top-right-radius: 6px; font-size: 13px; }"
            "QTabBar::tab:selected { background: #0f1117; color: #e2e8f0; }"
        )
        self._build_current_conv_tab()
        self._build_browse_tab()
        lay.addWidget(self._tabs)

        # 目标描述
        self._target_label = QLabel("选择目标对话或消息…")
        self._target_label.setStyleSheet("color:#60a5fa;font-size:12px;padding:4px 0;")
        lay.addWidget(self._target_label)

        # 按钮
        row = QHBoxLayout()
        cc = QPushButton("取消")
        cc.setStyleSheet(BTN_GHOST)
        cc.clicked.connect(self.reject)
        self._confirm_btn = QPushButton("建立连接  →")
        self._confirm_btn.setStyleSheet(BTN_PRIMARY)
        self._confirm_btn.setMinimumWidth(130)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self.accept)
        row.addWidget(cc)
        row.addStretch()
        row.addWidget(self._confirm_btn)
        lay.addLayout(row)

    def _build_current_conv_tab(self):
        tab = QWidget()
        vl = QVBoxLayout(tab)
        vl.setContentsMargins(10, 10, 10, 10)
        vl.setSpacing(6)

        search = QLineEdit()
        search.setPlaceholderText("搜索消息…")
        search.setFixedHeight(32)
        search.textChanged.connect(self._filter_current)
        vl.addWidget(search)

        self._current_list = QListWidget()
        self._current_list.setStyleSheet(
            "QListWidget { background: #0f1117; border: none; color: #d1d5db; font-size: 12px; }"
            "QListWidget::item { padding: 8px 10px; border-radius: 5px; }"
            "QListWidget::item:selected { background: #1e3a5f; color: #93c5fd; }"
            "QListWidget::item:hover:!selected { background: #1a202c; }"
        )
        # "整个对话" 选项
        conv_tags = ""
        if self._source_conv.tags:
            conv_tags = "  [" + ", ".join(self._source_conv.tags[:5]) + "]"
        whole_item = QListWidgetItem(f"📄  整个对话（不指定消息）{conv_tags}")
        whole_item.setData(Qt.UserRole, ("__conv__", self._source_conv.id))
        self._current_list.addItem(whole_item)

        for msg in self._source_conv.messages:
            if msg.id == self._source_msg.id:
                continue  # 跳过来源消息自身
            role_icon = "👤" if msg.role == "user" else "🤖"
            preview = msg.content[:80].replace("\n", " ") + ("…" if len(msg.content) > 80 else "")
            msg_tags = ""
            if msg.tags:
                msg_tags = "  [" + ", ".join(msg.tags[:3]) + "]"
            item = QListWidgetItem(f"{role_icon}  {preview}{msg_tags}")
            item.setData(Qt.UserRole, (msg.id, self._source_conv.id))
            self._current_list.addItem(item)

        self._current_list.itemClicked.connect(self._on_select_in_list)
        vl.addWidget(self._current_list)
        self._all_current_items = [
            self._current_list.item(i)
            for i in range(self._current_list.count())
        ]
        self._tabs.addTab(tab, "当前对话")

    def _build_browse_tab(self):
        tab = QWidget()
        vl = QVBoxLayout(tab)
        vl.setContentsMargins(10, 10, 10, 10)
        vl.setSpacing(6)

        self._browse_tree = QTreeWidget()
        self._browse_tree.setHeaderHidden(True)
        self._browse_tree.setIndentation(14)
        self._browse_tree.setStyleSheet(
            "QTreeWidget { background: #0f1117; border: none; color: #d1d5db; font-size: 12px; }"
            "QTreeWidget::item { padding: 5px 8px; border-radius: 4px; }"
            "QTreeWidget::item:selected { background: #1e3a5f; color: #93c5fd; }"
            "QTreeWidget::item:hover:!selected { background: #1a202c; }"
        )
        self._browse_tree.itemClicked.connect(self._on_tree_select)
        self._rebuild_browse_tree()
        vl.addWidget(self._browse_tree)
        self._tabs.addTab(tab, "浏览其他")

    def _rebuild_browse_tree(self):
        self._browse_tree.clear()
        for cid in ws._unfiled:
            self._add_conv_item(self._browse_tree, cid)
        for fo in ws.folders:
            self._add_folder_item(self._browse_tree, fo)

    def _add_folder_item(self, parent, fo: Folder):
        folder_item = QTreeWidgetItem(parent, [f"📁  {fo.name}"])
        folder_item.setData(0, Qt.UserRole, ("__folder__", fo.id))
        for cid in fo.conv_ids:
            self._add_conv_item(folder_item, cid)
        for sf in fo.subfolders:
            self._add_folder_item(folder_item, sf)

    def _add_conv_item(self, parent, cid: str):
        conv = ws.conversations.get(cid)
        if not conv:
            return
        if cid == self._source_conv.id:
            return  # 跳过来源对话本身
        conv_label = f"💬  {conv.title}"
        if conv.tags:
            conv_label += "  [" + ", ".join(conv.tags[:5]) + "]"
        conv_item = QTreeWidgetItem(parent, [conv_label])
        conv_item.setData(0, Qt.UserRole, ("__conv__", cid))
        # 展开消息
        for msg in conv.messages:
            role_icon = "👤" if msg.role == "user" else "🤖"
            preview = msg.content[:60].replace("\n", " ") + ("…" if len(msg.content) > 60 else "")
            msg_tags = ""
            if msg.tags:
                msg_tags = "  [" + ", ".join(msg.tags[:3]) + "]"
            msg_item = QTreeWidgetItem(conv_item, [f"{role_icon}  {preview}{msg_tags}"])
            msg_item.setData(0, Qt.UserRole, (msg.id, cid))

    def _on_tree_select(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data[0] == "__folder__":
            return  # 文件夹不可选
        if data[0] == "__conv__":
            self._target_conv_id = data[1]
            self._target_msg_id = ""
            conv = ws.conversations.get(self._target_conv_id, None)
            self._target_label.setText(f"目标：{conv.title if conv else '未知对话'}（整个对话）")
        else:
            self._target_conv_id = data[1]
            self._target_msg_id = data[0]
            conv = ws.conversations.get(self._target_conv_id, None)
            conv_title = conv.title if conv else "未知对话"
            self._target_label.setText(f"目标：{conv_title} / 消息")
        self._confirm_btn.setEnabled(True)

    def _on_select_in_list(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        if data[0] == "__conv__":
            self._target_conv_id = data[1]
            self._target_msg_id = ""
            conv = ws.conversations.get(self._target_conv_id, None)
            self._target_label.setText(f"目标：{conv.title if conv else '当前对话'}（整个对话）")
        else:
            self._target_conv_id = data[1]
            self._target_msg_id = data[0]
            self._target_label.setText("目标：当前对话 / 消息")
        self._confirm_btn.setEnabled(True)

    def _filter_current(self, text: str):
        text_lower = text.lower()
        for item in self._all_current_items:
            item.setHidden(
                text_lower not in item.text().lower() if text_lower else False
            )

    def set_selected_text(self, text: str):
        self._selected_text = text

    def result(self) -> tuple[str, str]:
        return self._target_conv_id, self._target_msg_id


class BacklinksDialog(QDialog):
    """显示反向链接列表的对话框。"""

    navigate_requested = Signal(str, str)  # (conv_id, msg_id)

    def __init__(
        self,
        backlinks: list[Link],
        conversations: dict[str, Conversation],
        target_node: Optional[MessageNode] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("反向链接")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setMinimumHeight(300)
        self.setStyleSheet(DIALOG_BASE)
        self._backlinks = backlinks
        self._conv_map = conversations
        self._target_node = target_node
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        h = QLabel("反向链接")
        h.setStyleSheet("color:#e2e8f0;font-size:17px;font-weight:700;")
        lay.addWidget(h)

        target_preview = (
            self._target_node.content[:40] + "..."
            if self._target_node and self._target_node.content
            else ""
        )
        desc = "以下对话/消息链接到了" + (f' "{target_preview}"' if target_preview else "当前消息")
        desc_label = QLabel(desc)
        desc_label.setStyleSheet("color:#718096;font-size:11px;")
        desc_label.setWordWrap(True)
        lay.addWidget(desc_label)

        if not self._backlinks:
            empty = QLabel("暂无反向链接")
            empty.setStyleSheet("color:#4a5568;font-size:13px;padding:20px;")
            empty.setAlignment(Qt.AlignCenter)
            lay.addWidget(empty)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("background:transparent;border:none;")
            cards_widget = QWidget()
            cards_lay = QVBoxLayout(cards_widget)
            cards_lay.setContentsMargins(0, 0, 0, 0)
            cards_lay.setSpacing(8)

            for link in self._backlinks:
                card = self._build_card(link)
                cards_lay.addWidget(card)
            cards_lay.addStretch()
            scroll.setWidget(cards_widget)
            lay.addWidget(scroll)

        row = QHBoxLayout()
        row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(BTN_GHOST)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        lay.addLayout(row)

    def _build_card(self, link: Link) -> QFrame:
        card = QFrame()
        card.setStyleSheet(BACKLINK_CARD)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(4)

        source_conv = self._conv_map.get(link.source_msg_id)
        conv_title = "未知对话"
        # 找到来源对话
        for c in self._conv_map.values():
            for l in c.links:
                if l.id == link.id:
                    conv_title = c.title
                    break

        title_lbl = QLabel(f"← 来自：{conv_title}")
        title_lbl.setStyleSheet("color:#93c5fd;font-size:12px;font-weight:600;")
        cl.addWidget(title_lbl)

        if link.selected_text:
            ctx = QLabel(f"❝  {link.selected_text[:80]}  ❞")
            ctx.setStyleSheet("color:#fde68a;font-size:11px;")
            ctx.setWordWrap(True)
            cl.addWidget(ctx)

        # 找到来源消息内容
        source_conv_obj = None
        source_msg = None
        for c in self._conv_map.values():
            for l in c.links:
                if l.id == link.id:
                    source_conv_obj = c
                    for m in c.messages:
                        if m.id == l.source_msg_id:
                            source_msg = m
                            break
                    break

        if source_msg:
            preview = source_msg.content[:100].replace("\n", " ") + ("…" if len(source_msg.content) > 100 else "")
            msg_lbl = QLabel(f"{'👤 你' if source_msg.role == 'user' else '🤖 助手'}：{preview}")
            msg_lbl.setStyleSheet("color:#94a3b8;font-size:11px;")
            msg_lbl.setWordWrap(True)
            cl.addWidget(msg_lbl)

        if source_conv_obj:
            nav_btn = QPushButton(f"跳转到 {conv_title}")
            nav_btn.setStyleSheet(LINK_ACTION_BTN)
            nav_btn.setCursor(Qt.PointingHandCursor)
            nav_btn.clicked.connect(
                lambda checked, c=source_conv_obj, l=link: self.navigate_requested.emit(
                    c.id, l.source_msg_id
                )
            )
            cl.addWidget(nav_btn)

        return card


class SearchDialog(QDialog):
    """搜索对话和消息。"""

    navigate_requested = Signal(str, str)  # (conv_id, msg_id)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("搜索")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(420)
        self.setStyleSheet(
            DIALOG_BASE
            + INPUT_STYLE
            + """
            QListWidget {
                background: #0f1117; border: 1px solid #2d3748;
                border-radius: 8px; color: #d1d5db; font-size: 12px;
                outline: none; padding: 4px;
            }
            QListWidget::item { padding: 10px 12px; border-radius: 6px; }
            QListWidget::item:selected { background: #1e3a5f; color: #93c5fd; }
            QListWidget::item:hover:!selected { background: #1a202c; }
        """
        )
        self._results: list = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        h = QLabel("搜索对话 / 消息")
        h.setStyleSheet("color:#e2e8f0;font-size:17px;font-weight:700;")
        lay.addWidget(h)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("输入关键词搜索标题、标签、内容…")
        self._search_input.setFixedHeight(40)
        self._search_input.textChanged.connect(self._do_search)
        lay.addWidget(self._search_input)

        self._result_list = QListWidget()
        self._result_list.itemClicked.connect(self._on_result_click)
        lay.addWidget(self._result_list)

        row = QHBoxLayout()
        row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(BTN_GHOST)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        lay.addLayout(row)

    def _do_search(self, text: str):
        self._result_list.clear()
        self._results.clear()
        if not text.strip() or len(text.strip()) < 1:
            return

        results = ws.search(text.strip())
        if not results:
            item = QListWidgetItem("无匹配结果")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self._result_list.addItem(item)
            return

        from ..styles import TAG_CHIP
        for conv, msg, info in results[:30]:
            self._results.append((conv, msg))
            role_icon = {"user": "👤", "assistant": "🤖"}.get(msg.role if msg else "", "💬")
            title = f"{role_icon}  {conv.title}"
            if msg:
                preview = msg.content[:60].replace("\n", " ") + ("…" if len(msg.content) > 60 else "")
                title += f"  /  {preview}"
            # 附加标签信息
            tag_info = ""
            relevant_tags = conv.tags if not msg else msg.tags
            if relevant_tags:
                tag_info = "  [" + ", ".join(relevant_tags[:5]) + "]"
            item_text = f"{title}\n{info}{tag_info}"
            item = QListWidgetItem(item_text)
            self._result_list.addItem(item)

    def _on_result_click(self, item: QListWidgetItem):
        idx = self._result_list.row(item)
        if 0 <= idx < len(self._results):
            conv, msg = self._results[idx]
            msg_id = msg.id if msg else ""
            self.navigate_requested.emit(conv.id, msg_id)
            self.accept()
