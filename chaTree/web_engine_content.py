"""WebEngine 内容组件：封装 QWebEngineView，提供 KaTeX 渲染与 ann:// 导航。"""
from __future__ import annotations

import json as _json
from typing import Callable, Optional

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QMenu, QVBoxLayout, QWidget

import re as _re

from .katex_loader import KATEX_CSS, KATEX_JS
from .markdown_render import MD_CSS

# MD_CSS 自带 <style>...</style> 包裹，需剥离后嵌入模板
_MD_CSS_RAW = _re.sub(r"</?style[^>]*>", "", MD_CSS).strip()

_BASE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin:0; padding:0; background:transparent; overflow:hidden; }}
  {md_css}
  {katex_css}
  .katex-display {{ margin:8px 0 !important; overflow-x:auto; }}
  .katex {{ font-size:1.1em; }}
</style>
<script>{katex_js}</script>
<script>
  window.ChainTree = {{
    updateContent: function(body, showCursor) {{
      document.getElementById('content').innerHTML = body;
      document.getElementById('cursor').style.display = showCursor ? 'inline' : 'none';
      try {{
        renderMathInElement(document.getElementById('content'), {{
          delimiters: [
            {{left: "$$", right: "$$", display: true}},
            {{left: "$", right: "$", display: false}}
          ]
        }});
      }} catch(e) {{}}
    }},
    getHeight: function() {{
      var c = document.getElementById('content');
      if (!c) return 24;
      return Math.max(c.scrollHeight, c.offsetHeight) + c.offsetTop + 12;
    }},
    getSelection: function() {{
      var s = window.getSelection();
      return s ? s.toString().trim() : '';
    }}
  }};
</script>
</head>
<body style="color:#e2e8f0;font-size:14px;line-height:1.85;background:transparent;">
<div id="content">{body}</div>
<span id="cursor" style="opacity:.55;display:{cursor_display};">&#x258C;</span>
<script>
  // 初始渲染：在 DOM 就绪后执行 KaTeX
  try {{
    renderMathInElement(document.getElementById('content'), {{
      delimiters: [
        {{left: "$$", right: "$$", display: true}},
        {{left: "$", right: "$", display: false}}
      ]
    }});
  }} catch(e) {{}}
</script>
</body></html>"""


class _AnnInterceptorPage(QWebEnginePage):
    """拦截 ann:// 导航，阻止页面跳转并发射信号。"""

    def __init__(self, parent: WebEngineContentView):
        super().__init__(parent)
        self._content = parent

    def acceptNavigationRequest(
        self, url: QUrl, _nav_type: QWebEnginePage.NavigationType, _is_main_frame: bool
    ) -> bool:
        if url.scheme() == "ann":
            self._content._on_ann_navigation(url)
            return False
        if url.scheme() == "link":
            self._content.link_clicked.emit(url.host())
            return False
        return True


class WebEngineContentView(QWidget):
    """封装 QWebEngineView 的内容组件。

    信号:
        annotation_clicked(MessageNode, Annotation)  -- 与旧 MessageBubble 兼容
        link_clicked(str)  -- link_id，点击内联链接标记时发射
    """

    annotation_clicked = Signal(object, object)
    link_clicked = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._loaded = False
        self._pending_update: Optional[tuple[str, bool]] = None
        self._node = None
        self._ann_map: dict[str, object] = {}
        self._ctx_menu_builder: Optional[Callable[[str], Optional[QMenu]]] = None
        self._selection_callback: Optional[Callable[[str], None]] = None
        self._build()

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._view = QWebEngineView(self)
        self._view.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Minimum)
        self._view.setAutoFillBackground(False)
        self._view.setStyleSheet("background:transparent;border:none;")

        page = _AnnInterceptorPage(self)
        page.setBackgroundColor(QColor("#0f1117"))
        page.contentsSizeChanged.connect(self._adjust_height)
        page.loadFinished.connect(self._on_load_finished)
        self._view.setPage(page)

        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._on_context_menu)

        lay.addWidget(self._view)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def set_html(self, body: str, cursor_visible: bool = False):
        """完整加载页面（首次渲染）。"""
        full = _BASE_HTML.format(
            md_css=_MD_CSS_RAW,
            katex_css=KATEX_CSS,
            katex_js=KATEX_JS,
            body=body,
            cursor_display="inline" if cursor_visible else "none",
        )
        self._loaded = False
        self._view.setHtml(full)

    def update_body(self, body: str, cursor_visible: bool = False):
        """增量更新正文（流式渲染阶段，通过 JS 替换 DOM）。"""
        if not self._loaded:
            self._pending_update = (body, cursor_visible)
            return
        self._run_body_update(body, cursor_visible)

    def set_page_color(self, hex_color: str):
        """设置页面背景色以匹配父级气泡，避免透明合成导致的渲染问题。"""
        self._view.page().setBackgroundColor(QColor(hex_color))

    def set_annotation_data(self, node, annotations):
        """存储节点和注释，供 ann:// 点击时查找。"""
        self._node = node
        self._ann_map = {ann.id: ann for ann in annotations}

    def set_context_menu_builder(
        self, builder: Callable[[str], Optional[QMenu]]
    ):
        """设置右键菜单构建回调。builder(selected_text) -> QMenu | None。"""
        self._ctx_menu_builder = builder

    def get_selected_text(self, callback: Callable[[str], None]):
        """异步获取选中文字，结果通过 callback 返回。"""
        self._selection_callback = callback
        self._view.page().runJavaScript(
            "ChainTree.getSelection();", 0, self._on_selection_result
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _run_body_update(self, body: str, cursor_visible: bool):
        js_body = _json.dumps(body)
        js_cursor = "true" if cursor_visible else "false"
        view = self._view

        def _apply(result):
            try:
                h = max(int(float(result)), 24) if result else 24
            except (ValueError, TypeError):
                h = 24
            view.setFixedHeight(h)

        self._view.page().runJavaScript(
            f"ChainTree.updateContent({js_body}, {js_cursor}); ChainTree.getHeight();",
            0,
            _apply,
        )

    def _adjust_height(self):
        if not self._loaded:
            return
        view = self._view

        def _apply(result):
            try:
                h = max(int(float(result)), 24) if result else 24
            except (ValueError, TypeError):
                h = 24
            view.setFixedHeight(h)

        view.page().runJavaScript("ChainTree.getHeight();", 0, _apply)

    def _on_load_finished(self, ok: bool):
        self._loaded = ok
        if ok:
            self._adjust_height()
            if self._pending_update:
                body, cursor = self._pending_update
                self._pending_update = None
                self._run_body_update(body, cursor)

    def _on_ann_navigation(self, url: QUrl):
        ann_id = url.host()
        ann = self._ann_map.get(ann_id)
        if ann is not None and self._node is not None:
            self.annotation_clicked.emit(self._node, ann)

    def _on_context_menu(self, pos):
        if not self._ctx_menu_builder:
            return

        def _on_text(text: str):
            menu = self._ctx_menu_builder(text)  # type: ignore[misc]
            if menu:
                menu.exec(self._view.mapToGlobal(pos))

        self.get_selected_text(_on_text)

    def _on_selection_result(self, result):
        if self._selection_callback:
            cb = self._selection_callback
            self._selection_callback = None
            cb(result if result else "")
