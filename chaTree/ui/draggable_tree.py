"""支持将对话项拖入文件夹的树控件。"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
)


class DraggableTree(QTreeWidget):
    """对话节点可拖到文件夹或根目录；完成后发出 conv_moved 信号。"""

    conv_moved = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self._drag_item: Optional[QTreeWidgetItem] = None

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if item:
                d = item.data(0, Qt.UserRole)
                if d and d[0] == "conv":
                    self._drag_item = item
                else:
                    self._drag_item = None
            else:
                self._drag_item = None

    def dropEvent(self, event):
        if not self._drag_item:
            event.ignore()
            return

        drag_d = self._drag_item.data(0, Qt.UserRole)
        if not drag_d or drag_d[0] != "conv":
            event.ignore()
            return

        conv_id = drag_d[1]
        target = self.itemAt(event.position().toPoint())

        if target is None:
            self.conv_moved.emit(conv_id, None)
        else:
            t_data = target.data(0, Qt.UserRole)
            if t_data is None:
                event.ignore()
                return
            if t_data[0] == "folder":
                self.conv_moved.emit(conv_id, t_data[1])
            elif t_data[0] == "conv":
                parent = target.parent()
                if parent:
                    pd = parent.data(0, Qt.UserRole)
                    folder_id = pd[1] if (pd and pd[0] == "folder") else None
                else:
                    folder_id = None
                self.conv_moved.emit(conv_id, folder_id)
            else:
                event.ignore()
                return

        event.accept()
        self._drag_item = None

    def dragEnterEvent(self, event):
        if self._drag_item:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        target = self.itemAt(event.position().toPoint())
        if target:
            t_data = target.data(0, Qt.UserRole)
            if t_data and t_data[0] in ("folder", "conv"):
                event.accept()
                return
        event.accept()
