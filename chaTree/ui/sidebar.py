"""左侧边栏：文件夹树、新建对话、设置入口。"""

from __future__ import annotations

import uuid
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from ..models import Conversation, Folder
from ..styles import BTN_GHOST, BTN_PRIMARY
from ..workspace import ws
from .dialogs import NewConversationDialog, SearchDialog, SettingsDialog
from .draggable_tree import DraggableTree


class Sidebar(QWidget):
    conversation_selected = Signal(object)
    search_navigate = Signal(str, str)  # (conv_id, msg_id)

    def __init__(self):
        super().__init__()
        self.setFixedWidth(224)
        self.setStyleSheet(
            """
            QWidget { background: #0a0d14; }
            DraggableTree, QTreeWidget {
                background: transparent; border: none; outline: none;
                font-size: 13px; color: #a0aec0;
            }
            QTreeWidget::item {
                padding: 5px 8px; border-radius: 6px; margin: 1px 6px;
            }
            QTreeWidget::item:selected { background:#1a202c; color:#e2e8f0; }
            QTreeWidget::item:hover:!selected { background:#111827; }
            QTreeWidget::branch { background:transparent; }
        """
        )
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        logo = QLabel("✦ AI 对话")
        logo.setStyleSheet(
            "color:#e2e8f0;font-size:15px;font-weight:700;"
            "padding:18px 16px 10px 16px;"
            "border-bottom:1px solid #1a202c;"
        )
        lay.addWidget(logo)

        nb = QPushButton("+ 新建对话")
        nb.setStyleSheet(
            BTN_PRIMARY
            + """
            QPushButton {
                margin: 8px 12px 4px 12px;
                padding: 10px 14px;
                min-height: 22px;
            }
        """
        )
        nb.setMinimumHeight(42)
        nb.clicked.connect(self._new_conv)
        lay.addWidget(nb)

        sb = QPushButton("🔍  搜索")
        sb.setStyleSheet(
            BTN_GHOST
            + """
            QPushButton {
                margin: 0px 12px 8px 12px; padding: 8px 14px;
                text-align: left; font-size: 12px;
            }
        """
        )
        sb.clicked.connect(self._open_search)
        lay.addWidget(sb)

        self.tree = DraggableTree()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.itemClicked.connect(self._on_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._ctx)
        self.tree.conv_moved.connect(self._on_conv_moved)
        lay.addWidget(self.tree, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#1a202c;")
        lay.addWidget(sep)

        sb = QPushButton("⚙  设置")
        sb.setStyleSheet(
            BTN_GHOST + "QPushButton{padding:12px 18px;text-align:left;}"
        )
        sb.clicked.connect(lambda: SettingsDialog(self).exec())
        lay.addWidget(sb)

        self.refresh()

    def _on_conv_moved(self, conv_id: str, folder_id: Optional[str]):
        if ws.move_conversation(conv_id, folder_id):
            self.refresh()

    def refresh(self):
        self.tree.clear()
        for cid in ws._unfiled:
            c = ws.conversations.get(cid)
            if c:
                self._mk_conv(self.tree, c)
        for fo in ws.folders:
            self._mk_folder(self.tree, fo)

    def _mk_folder(self, parent, fo: Folder) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [f"📁  {fo.name}"])
        item.setData(0, Qt.UserRole, ("folder", fo.id))
        item.setExpanded(True)
        for sf in fo.subfolders:
            self._mk_folder(item, sf)
        for cid in fo.conv_ids:
            c = ws.conversations.get(cid)
            if c:
                self._mk_conv(item, c)
        return item

    def _mk_conv(self, parent, c: Conversation) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [f"💬  {c.title}"])
        item.setData(0, Qt.UserRole, ("conv", c.id))
        return item

    def _on_click(self, item: QTreeWidgetItem, _col: int):
        d = item.data(0, Qt.UserRole)
        if d and d[0] == "conv":
            c = ws.conversations.get(d[1])
            if c:
                self.conversation_selected.emit(c)

    def _ctx(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        if item:
            d = item.data(0, Qt.UserRole)
            if d and d[0] == "conv":
                menu.addAction("🗑  删除对话").triggered.connect(
                    lambda: (ws.delete_conversation(d[1]), self.refresh())
                )
            elif d and d[0] == "folder":
                menu.addAction("📁  新建子文件夹").triggered.connect(
                    lambda: self._new_folder(d[1])
                )
                menu.addAction("✏️  重命名文件夹").triggered.connect(
                    lambda: self._rename_folder(d[1])
                )
        else:
            menu.addAction("📁  新建文件夹").triggered.connect(
                lambda: self._new_folder(None)
            )
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _new_folder(self, parent_id: Optional[str]):
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称：")
        if ok and name.strip():
            ws.add_folder(name.strip(), parent_id)
            self.refresh()

    def _rename_folder(self, fid: str):
        fo = ws.find_folder(fid)
        if not fo:
            return
        name, ok = QInputDialog.getText(
            self, "重命名文件夹", "新名称：", text=fo.name
        )
        if ok and name.strip():
            fo.name = name.strip()
            ws.save_settings()
            self.refresh()

    def _open_search(self):
        dlg = SearchDialog(self)
        dlg.navigate_requested.connect(
            lambda cid, mid: self.search_navigate.emit(cid, mid)
        )
        dlg.exec()

    def _new_conv(self):
        dlg = NewConversationDialog(self)
        if dlg.exec() == QDialog.Accepted:
            title, fid = dlg.result_data()
            c = Conversation(id=str(uuid.uuid4()), title=title or "新对话")
            ws.add_conversation(c, fid)
            self.refresh()
            self.conversation_selected.emit(c)
