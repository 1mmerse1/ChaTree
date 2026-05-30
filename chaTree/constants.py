"""路径与全局常量。"""

from __future__ import annotations

import sys
from pathlib import Path

# 设为 False 可回退到 QTextBrowser（无 KaTeX 数学渲染）
USE_WEBENGINE = True

CIRCLE = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]

DATA_DIR = Path("workspace_data")
INDEX_FILE = DATA_DIR / "index.json"
OLD_FILE = Path("workspace.json")

try:
    import openai  # noqa: F401

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

HAS_MARKDOWN = False
md_lib = None


def ensure_markdown():
    """延迟加载 markdown（兼容 PyInstaller 冻结环境）。"""
    global HAS_MARKDOWN, md_lib
    if md_lib is not None:
        return md_lib
    try:
        import markdown

        md_lib = markdown
        HAS_MARKDOWN = True
        return markdown
    except ImportError:
        HAS_MARKDOWN = False
        md_lib = None
        return None


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent
