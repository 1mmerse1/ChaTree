"""单一 QWebEngineView 渲染整个对话，替代多 MessageBubble 架构。"""

from __future__ import annotations

import json as _json
import re as _re
from typing import Callable, Optional

from PySide6.QtCore import QUrl, Qt, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QMenu, QVBoxLayout, QWidget

from .katex_loader import KATEX_CSS, KATEX_JS
from .markdown_render import MD_CSS, render_msg_body
from .models import Conversation, MessageNode

_MD_CSS_RAW = _re.sub(r"</?style[^>]*>", "", MD_CSS).strip()

# 消息气泡样式
_MSG_CSS = """
.msg-wrap { margin-bottom:18px; padding:0 32px; }
.msg-role { font-size:11px; font-weight:600; margin-bottom:4px; }
.msg-role.user { color:#63b3ed; }
.msg-role.assistant { color:#68d391; }
.msg-bubble { border-radius:12px; padding:14px 12px; line-height:1.85; }
.msg-bubble.user { background:#1a365d; border:1px solid #2c5282; }
.msg-bubble.assistant { background:#1a202c; border:1px solid #2d3748; }
.msg-tags { margin-top:4px; display:flex; flex-wrap:wrap; gap:4px; }
.msg-tag {
    background:#1e2a3a; color:#7dd3fc; border:1px solid #2d3748;
    border-radius:10px; padding:2px 10px; font-size:11px; display:inline-block;
    text-decoration:none; cursor:pointer;
}
.msg-tag:hover { background:#2d3748; }
.msg-tag-add {
    background:#1e2a3a; color:#7dd3fc; border:1px solid #2d3748;
    border-radius:10px; padding:2px 10px; font-size:11px; cursor:pointer;
    text-decoration:none;
}
.msg-tag-add:hover { background:#2d3748; }
.msg-actions { margin-top:4px; display:flex; gap:12px; font-size:12px; color:#718096; }
.msg-actions span, .msg-actions a { cursor:pointer; text-decoration:none; color:#718096; }
.msg-actions span:hover, .msg-actions a:hover { color:#90cdf4; }
.msg-link-badges { margin-top:4px; display:flex; flex-wrap:wrap; gap:4px; }
.msg-link-badge {
    background:#1e3a5f; color:#c4b5fd; border:1px solid #3b2666;
    border-radius:10px; padding:2px 10px; font-size:11px;
    text-decoration:none; cursor:pointer; display:inline-block;
}
.msg-link-badge:hover { background:#2d1b69; }
.msg-link-badge-del {
    color:#718096; font-size:10px; margin-left:2px;
    text-decoration:none; cursor:pointer; padding:0 2px;
}
.msg-link-badge-del:hover { color:#fc8181; background:#451a03; border-radius:4px; }
"""

_BASE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin:0; padding:0; background:{bg_color}; }}
  body {{ color:#e2e8f0; font-size:14px; line-height:1.85; }}
  {md_css}
  {katex_css}
  {msg_css}
  .katex-display {{ margin:8px 0 !important; overflow-x:auto; }}
  .katex {{ font-size:1.1em; }}
  #cursor {{ opacity:.55; }}
</style>
<script>{katex_js}</script>
<script>
  window.ChainTree = {{
    _rightClickedTag: null,
    updateStreaming: function(html) {{
      var el = document.getElementById('streaming-content');
      if (!el) return;
      el.innerHTML = html;
      try {{ renderMathInElement(el, {{delimiters:[
        {{left:"$$",right:"$$",display:true}},{{left:"$",right:"$",display:false}}
      ]}}); }} catch(e) {{}}
    }},
    finalizeStreaming: function(html, msgId) {{
      var el = document.getElementById('streaming-msg');
      if (!el) return;
      el.outerHTML = html;
      var cursor = document.getElementById('cursor');
      if (cursor) cursor.style.display = 'none';
      try {{ renderMathInElement(document.getElementById('msg-'+msgId), {{delimiters:[
        {{left:"$$",right:"$$",display:true}},{{left:"$",right:"$",display:false}}
      ]}}); }} catch(e) {{}}
    }},
    showCursor: function(visible) {{
      var c = document.getElementById('cursor');
      if (c) c.style.display = visible ? 'inline' : 'none';
    }},
    getHeight: function() {{
      return Math.max(document.body.scrollHeight, document.body.offsetHeight, 24);
    }},
    getSelection: function() {{
      var s = window.getSelection();
      var text = s ? s.toString().trim() : '';
      var result = text;
      if (window.ChainTree._rightClickedTag) {{
        var t = window.ChainTree._rightClickedTag;
        result = '\\x00' + t.msgId + '\\x00tag:' + t.tag;
        window.ChainTree._rightClickedTag = null;
        return result;
      }}
      if (!text) return '';
      var node = s.anchorNode;
      while (node) {{
        if (node.dataset && node.dataset.msgId) return text + '\\x00' + node.dataset.msgId;
        node = node.parentElement;
      }}
      return text;
    }},
    scrollToMsg: function(msgId) {{
      var el = document.getElementById('msg-'+msgId);
      if (el) el.scrollIntoView({{behavior:'smooth',block:'center'}});
    }}
  }};
  document.addEventListener('contextmenu', function(e) {{
    var tagEl = e.target.closest('.msg-tag');
    if (tagEl) {{
      window.ChainTree._rightClickedTag = {{
        msgId: tagEl.getAttribute('data-msg-id') || '',
        tag: tagEl.getAttribute('data-tag') || tagEl.textContent.trim()
      }};
    }} else {{
      window.ChainTree._rightClickedTag = null;
    }}
  }}, true);
</script>
</head>
<body>
<div id="messages">{messages}</div>
<span id="cursor" style="opacity:.55;display:{cursor_display};">&#x258C;</span>
<script>
  try {{ renderMathInElement(document.getElementById('messages'), {{delimiters:[
    {{left:"$$",right:"$$",display:true}},{{left:"$",right:"$",display:false}}
  ]}}); }} catch(e) {{}}
</script>
</body></html>"""


class _ConvInterceptorPage(QWebEnginePage):
    def __init__(self, parent):
        super().__init__(parent)
        self._conv = parent

    def acceptNavigationRequest(
        self, url: QUrl, _nav_type, _is_main_frame
    ) -> bool:
        if url.scheme() == "ann":
            ann_id = url.host()
            self._conv._on_ann_click(ann_id)
            return False
        if url.scheme() == "link":
            self._conv.link_clicked.emit(url.host())
            return False
        if url.scheme() == "action":
            action = url.host()
            msg_id = url.path().lstrip("/")
            if action == "retry":
                self._conv._on_action_retry(msg_id)
            elif action == "link-create":
                self._conv._on_action_link_create(msg_id)
            elif action == "backlinks":
                self._conv._on_action_backlinks(msg_id)
            elif action == "tag-add":
                self._conv.tag_add_requested.emit(msg_id)
            elif action == "tag-remove":
                raw_query = url.query()
                tag = raw_query.split("=", 1)[1] if "=" in raw_query else raw_query
                self._conv.tag_remove_requested.emit(msg_id, tag)
            elif action == "link-delete":
                self._conv.link_delete_requested.emit(msg_id)
            return False
        return True


class ConversationView(QWidget):
    annotation_clicked = Signal(object, object)  # (MessageNode, Annotation)
    annotation_created = Signal(object, str, str)  # (MessageNode, quoted, question)
    link_clicked = Signal(str)  # link_id
    link_create_requested = Signal(object, str)  # (MessageNode, selected_text)
    backlinks_requested = Signal(object)  # MessageNode
    retry_requested = Signal(object)  # MessageNode
    tag_add_requested = Signal(str)  # msg_id
    tag_remove_requested = Signal(str, str)  # msg_id, tag
    link_delete_requested = Signal(str)  # link_id

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.conv: Optional[Conversation] = None
        self._loaded = False
        self._pending_html: Optional[str] = None
        self._streaming_msg_id: str = ""
        self._ctx_menu_builder: Optional[Callable[[str, str], Optional[QMenu]]] = None
        self._ann_map: dict[str, tuple[MessageNode, object]] = {}
        self._conv_titles: dict[str, str] = {}
        self._pending_scroll_msg_id: str = ""
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._view = QWebEngineView(self)
        self._view.setAutoFillBackground(False)
        self._view.setStyleSheet("background:transparent;border:none;")

        page = _ConvInterceptorPage(self)
        page.setBackgroundColor(QColor("#0f1117"))
        page.loadFinished.connect(self._on_load_finished)
        self._view.setPage(page)

        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._on_context_menu)

        lay.addWidget(self._view)

    # ── 公共 API ──

    def load_conversation(self, conv: Conversation):
        self.conv = conv
        self._streaming_msg_id = ""
        self._ann_map.clear()
        for msg in conv.messages:
            for ann in msg.annotations:
                self._ann_map[ann.id] = (msg, ann)
        outgoing_map: dict[str, list] = {}
        for link in conv.links:
            outgoing_map.setdefault(link.source_msg_id, []).append(link)
        html_parts = []
        for msg in conv.messages:
            html_parts.append(self._render_message(msg, links=outgoing_map.get(msg.id, [])))
        messages_html = "\n".join(html_parts)
        full = _BASE_HTML.format(
            bg_color="#0f1117",
            md_css=_MD_CSS_RAW,
            katex_css=KATEX_CSS,
            katex_js=KATEX_JS,
            msg_css=_MSG_CSS,
            messages=messages_html,
            cursor_display="none",
        )
        self._loaded = False
        self._view.setHtml(full)

    def append_message(self, msg: MessageNode):
        """在 DOM 末尾追加一条已渲染好的消息（不会整页重载）。"""
        html = self._render_message(msg)
        js = _json.dumps(html)
        self._run_js(
            f"var d=document.getElementById('messages');"
            f"d.insertAdjacentHTML('beforeend',{js});"
            f"try{{renderMathInElement(d.lastElementChild,{{delimiters:["
            f"{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}"
            f"]}});}}catch(e){{}}"
            f"document.getElementById('cursor').scrollIntoView({{behavior:'smooth',block:'end'}});",
            None,
        )

    def start_streaming(self, msg_id: str):
        """在消息列表末尾插入流式占位 div。"""
        self._streaming_msg_id = msg_id
        self._run_js(
            """
            var d = document.getElementById('messages');
            d.insertAdjacentHTML('beforeend',
                '<div id="streaming-msg" class="msg-wrap">' +
                '<div class="msg-role assistant">助手</div>' +
                '<div class="msg-bubble assistant"><div id="streaming-content"></div></div>' +
                '</div>'
            );
            document.getElementById('cursor').style.display = 'inline';
            """,
            None,
        )

    def append_token(self, body_html: str):
        """流式更新：替换 streaming-content 的 innerHTML。"""
        if not self._streaming_msg_id:
            return
        js_body = _json.dumps(body_html)
        self._run_js(
            f"ChainTree.updateStreaming({js_body});",
            None,
        )

    def finalize_streaming(self, body_html: str, msg_id: str, tags: list):
        """完成流式：替换占位 div 为最终消息 div，触发高度调整。"""
        self._streaming_msg_id = ""
        final_html = self._render_message_html(body_html, msg_id, "assistant", tags)
        js = _json.dumps(final_html)
        js_id = _json.dumps(msg_id)
        self._run_js(
            f"ChainTree.finalizeStreaming({js}, {js_id}); ChainTree.getHeight();",
            self._on_height_result,
        )

    def update_message_tags(self, msg_id: str, msg: MessageNode):
        """更新某条消息的标签显示。"""
        tags_html = self._render_tags_interactive(msg)
        js_tags = _json.dumps(tags_html)
        self._run_js(
            f"var el=document.getElementById('tags-'+{_json.dumps(msg_id)});"
            f"if(el) el.innerHTML = {js_tags};",
            None,
        )

    def scroll_to_message(self, msg_id: str):
        self._run_js(f"ChainTree.scrollToMsg({_json.dumps(msg_id)});", None)

    def reload_all(self, conv: Conversation):
        """完全重载整个对话 HTML（用于注解创建、重试等场景）。"""
        self.load_conversation(conv)

    def set_context_menu_builder(
        self, builder: Callable[[str, str], Optional[QMenu]]
    ):
        """builder(selected_text, msg_id) -> QMenu | None"""
        self._ctx_menu_builder = builder

    # ── 内部渲染 ──

    def _render_message(self, msg: MessageNode, links: list | None = None) -> str:
        links = links or []
        body = render_msg_body(
            msg.content, msg.annotations, streaming=False, links=links
        )
        role_label = "你" if msg.role == "user" else "助手"
        role_css = "user" if msg.role == "user" else "assistant"
        tags_html = self._render_tags_interactive(msg)
        actions_html = self._render_actions(msg)
        link_badges_html = self._render_link_badges(links)
        return (
            f'<div class="msg-wrap" id="msg-{msg.id}" data-msg-id="{msg.id}">'
            f'<div class="msg-role {role_css}">{role_label}</div>'
            f'<div class="msg-bubble {role_css}">{body}</div>'
            f'{actions_html}'
            f'{link_badges_html}'
            f'<div class="msg-tags" id="tags-{msg.id}">{tags_html}</div>'
            f"</div>"
        )

    def _render_message_html(
        self, body_html: str, msg_id: str, role: str, tags: list
    ) -> str:
        role_label = "你" if role == "user" else "助手"
        role_css = "user" if role == "user" else "assistant"
        tags_html = self._render_tags_interactive_static(tags, msg_id)
        actions_html = self._render_actions_static(role, msg_id)
        return (
            f'<div class="msg-wrap" id="msg-{msg_id}" data-msg-id="{msg_id}">'
            f'<div class="msg-role {role_css}">{role_label}</div>'
            f'<div class="msg-bubble {role_css}">{body_html}</div>'
            f'{actions_html}'
            f'<div class="msg-tags" id="tags-{msg_id}">{tags_html}</div>'
            f"</div>"
        )

    def _render_tags(self, tags: list) -> str:
        if not tags:
            return ""
        return "".join(
            f'<span class="msg-tag">{t}</span>' for t in tags
        )

    def _render_tags_interactive(self, msg: MessageNode) -> str:
        parts = []
        for t in msg.tags:
            safe = _json.dumps(t, ensure_ascii=False)[1:-1].replace('"', "'")
            parts.append(
                f'<span class="msg-tag" data-msg-id="{msg.id}" data-tag="{safe}">{t}</span>'
            )
        parts.append(
            f'<a href="action://tag-add/{msg.id}" class="msg-tag-add">+</a>'
        )
        return "".join(parts)

    def _render_tags_interactive_static(self, tags: list, msg_id: str) -> str:
        parts = []
        for t in tags:
            safe = _json.dumps(t, ensure_ascii=False)[1:-1].replace('"', "'")
            parts.append(
                f'<span class="msg-tag" data-msg-id="{msg_id}" data-tag="{safe}">{t}</span>'
            )
        parts.append(
            f'<a href="action://tag-add/{msg_id}" class="msg-tag-add">+</a>'
        )
        return "".join(parts)

    def _render_actions(self, msg: MessageNode) -> str:
        parts = ['<div class="msg-actions">']
        parts.append(
            f'<a href="action://link-create/{msg.id}"'
            f' style="color:#718096;text-decoration:none;cursor:pointer;">🔗 建立连接</a>'
        )
        parts.append(
            f'<a href="action://backlinks/{msg.id}"'
            f' style="color:#718096;text-decoration:none;cursor:pointer;">← 反向链接</a>'
        )
        if msg.role == "assistant":
            parts.append(
                f'<a href="action://retry/{msg.id}"'
                f' style="color:#718096;text-decoration:none;cursor:pointer;">↻ 重试</a>'
            )
        parts.append("</div>")
        return "".join(parts)

    def _render_actions_static(self, role: str, msg_id: str) -> str:
        parts = ['<div class="msg-actions">']
        parts.append(
            f'<a href="action://link-create/{msg_id}"'
            f' style="color:#718096;text-decoration:none;cursor:pointer;">🔗 建立连接</a>'
        )
        parts.append(
            f'<a href="action://backlinks/{msg_id}"'
            f' style="color:#718096;text-decoration:none;cursor:pointer;">← 反向链接</a>'
        )
        if role == "assistant":
            parts.append(
                f'<a href="action://retry/{msg_id}"'
                f' style="color:#718096;text-decoration:none;cursor:pointer;">↻ 重试</a>'
            )
        parts.append("</div>")
        return "".join(parts)

    def _render_link_badges(self, links: list) -> str:
        if not links:
            return ""
        parts = ['<div class="msg-link-badges">']
        for link in links:
            title = self._conv_titles.get(link.target_conv_id, "未知对话")
            badge_text = f"→ {title}"
            if link.target_msg_id:
                badge_text += " / 消息"
            if link.selected_text:
                sel_preview = link.selected_text[:15]
                badge_text += f" [{sel_preview}...]" if len(link.selected_text) > 15 else f" [{link.selected_text}]"
            parts.append(
                f'<span style="display:inline-flex;align-items:center;">'
                f'<a href="link://{link.id}" class="msg-link-badge">{badge_text}</a>'
                f'<a href="action://link-delete/{link.id}" class="msg-link-badge-del" title="删除链接">✕</a>'
                f'</span>'
            )
        parts.append("</div>")
        return "".join(parts)

    # ── JS 调用 ──

    def _run_js(self, js: str, callback=None):
        try:
            page = self._view.page()
            if callback is not None:
                page.runJavaScript(js, callback)
            else:
                page.runJavaScript(js)
        except RuntimeError:
            pass

    def _on_load_finished(self, ok: bool):
        self._loaded = ok
        if ok and self._pending_html:
            self._view.setHtml(self._pending_html)
            self._pending_html = None
        if ok and self._pending_scroll_msg_id:
            pending = self._pending_scroll_msg_id
            self._pending_scroll_msg_id = ""
            self._run_js(f"ChainTree.scrollToMsg({_json.dumps(pending)});", None)

    def _on_height_result(self, result):
        # WebView 高度由外层 layout 的 stretch 控制，不设置固定高度，
        # 否则会撑爆窗口布局并导致内部滚动失效。
        pass

    # ── 导航处理 ──

    def _on_ann_click(self, ann_id: str):
        entry = self._ann_map.get(ann_id)
        if entry:
            self.annotation_clicked.emit(entry[0], entry[1])

    def _on_action_retry(self, msg_id: str):
        if not self.conv:
            return
        for msg in self.conv.messages:
            if msg.id == msg_id:
                self.retry_requested.emit(msg)
                return

    def _on_action_link_create(self, msg_id: str):
        if not self.conv:
            return
        for msg in self.conv.messages:
            if msg.id == msg_id:
                self.link_create_requested.emit(msg, "")
                return

    def _on_action_backlinks(self, msg_id: str):
        if not self.conv:
            return
        for msg in self.conv.messages:
            if msg.id == msg_id:
                self.backlinks_requested.emit(msg)
                return

    # ── 右键菜单 ──

    def _on_context_menu(self, pos):
        if not self._ctx_menu_builder:
            return

        def _on_text(raw: str):
            if not raw:
                menu = self._ctx_menu_builder("", "")
                if menu:
                    menu.exec(self._view.mapToGlobal(pos))
                return
            parts = raw.split("\x00", 2)
            sel = parts[0] if parts else ""
            msg_id = parts[1] if len(parts) > 1 else ""

            # 检测右键点在 tag chip 上
            if len(parts) > 2 and parts[2].startswith("tag:"):
                tag = parts[2][4:]  # 去掉 "tag:" 前缀
                menu = QMenu(self)
                menu.addAction(f"删除「{tag}」").triggered.connect(
                    lambda checked=False, t=tag, mid=msg_id: self.tag_remove_requested.emit(mid, t)
                )
                menu.exec(self._view.mapToGlobal(pos))
                return

            menu = self._ctx_menu_builder(sel, msg_id)
            if menu:
                menu.exec(self._view.mapToGlobal(pos))

        self._run_js("ChainTree.getSelection();", _on_text)
