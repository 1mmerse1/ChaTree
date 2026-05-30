"""加载内置 KaTeX JS/CSS，将字体 URL 转为绝对 file:// 路径。"""
from __future__ import annotations

import re as _re

from .constants import app_base_dir

_RESOURCES = app_base_dir() / "chaTree" / "resources" / "katex"

_KATEX_JS = (_RESOURCES / "katex.min.js").read_text(encoding="utf-8")
_KATEX_AUTO_RENDER_JS = (_RESOURCES / "auto-render.min.js").read_text(encoding="utf-8")

_RAW_CSS = (_RESOURCES / "katex.min.css").read_text(encoding="utf-8")
_FONTS_DIR = _RESOURCES / "fonts"
_KATEX_CSS = _re.sub(
    r"url\(fonts/([^)]+)\)",
    lambda m: f"url(file:///{_FONTS_DIR.as_posix()}/{m.group(1)})",
    _RAW_CSS,
)

KATEX_JS = _KATEX_JS + "\n" + _KATEX_AUTO_RENDER_JS
KATEX_CSS = _KATEX_CSS
