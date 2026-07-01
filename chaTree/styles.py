"""Qt 样式表字符串。"""

APP_QSS = """
* { font-family: 'PingFang SC', 'Microsoft YaHei UI', 'Segoe UI', sans-serif; }
QMainWindow, QWidget { background: #0f1117; color: #e2e8f0; }
QScrollBar:vertical { width: 5px; background: transparent; }
QScrollBar::handle:vertical {
    background: #2d3748; border-radius: 3px; min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 0; }
QScrollArea { border: none; background: transparent; }
QMenu {
    background: #1a202c; color: #e2e8f0;
    border: 1px solid #2d3748; border-radius: 8px; padding: 4px;
}
QMenu::item { padding: 7px 18px; border-radius: 5px; }
QMenu::item:selected { background: #2d3748; }
"""

BTN_PRIMARY = """
QPushButton {
    background: #22543d; color: #9ae6b4; border: 1px solid #276749;
    border-radius: 7px; padding: 7px 0; font-size: 13px; font-weight: 600;
}
QPushButton:hover   { background: #276749; color: #c6f6d5; }
QPushButton:pressed { background: #1c4532; }
QPushButton:disabled { background: #1a202c; color: #4a5568; border-color: #2d3748; }
"""

BTN_GHOST = """
QPushButton {
    background: transparent; color: #718096; border: none;
    border-radius: 5px; padding: 5px 10px; font-size: 12px;
}
QPushButton:hover { background: #1a202c; color: #e2e8f0; }
"""

BTN_SECONDARY = """
QPushButton {
    background: #1a202c; color: #a0aec0; border: 1px solid #2d3748;
    border-radius: 6px; padding: 5px 12px; font-size: 12px;
}
QPushButton:hover { background: #2d3748; color: #e2e8f0; }
"""

INPUT_STYLE = """
QLineEdit, QTextEdit {
    background: #0f1117; border: 1px solid #2d3748; border-radius: 7px;
    padding: 9px 12px; font-size: 13px; color: #e2e8f0;
}
QLineEdit:focus, QTextEdit:focus { border-color: #4299e1; }
"""

DIALOG_BASE = """
QDialog { background: #1a202c; border: 1px solid #2d3748; border-radius: 12px; }
/* 全局 QWidget { background: #0f1117 } 会通过 parent chain 泄漏到 Dialog 子控件；
   此规则用更高 specificity 覆盖，使对话框内所有 QWidget 统一为 #1a202c */
QDialog QWidget { background: #1a202c; }
/* 输入框恢复为近黑色以与对话框表面区分 */
QDialog QLineEdit, QDialog QTextEdit {
    background: #0f1117; border: 1px solid #2d3748; border-radius: 7px;
    padding: 9px 12px; font-size: 13px; color: #e2e8f0;
}
QDialog QLineEdit:focus, QDialog QTextEdit:focus { border-color: #4299e1; }
QLabel  { font-size: 11px; color: #718096; }
"""

LINK_BADGE = """
QPushButton {
    background: #1e3a5f; color: #60a5fa; border: 1px solid #2c5282;
    border-radius: 8px; padding: 3px 10px; font-size: 11px;
}
QPushButton:hover { background: #2c5282; color: #93c5fd; }
"""

LINK_ACTION_BTN = """
QPushButton {
    background: transparent; color: #60a5fa; border: none;
    border-radius: 5px; padding: 5px 10px; font-size: 12px;
}
QPushButton:hover { background: #1e3a5f; color: #93c5fd; }
"""

BACKLINK_CARD = """
QFrame {
    background: #161f2e; border: 1px solid #2d3748; border-radius: 8px;
    padding: 8px 12px;
}
"""

TAG_CHIP = """
QPushButton {
    background: #1e2a3a; color: #7dd3fc; border: 1px solid #2d3748;
    border-radius: 10px; padding: 2px 10px; font-size: 11px;
}
QPushButton:hover { background: #2d3748; color: #bae6fd; }
"""
