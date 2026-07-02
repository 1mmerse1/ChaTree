"""Markdown 与数学公式渲染（供 QTextBrowser 使用）。"""

from __future__ import annotations

import html as html_mod
import re
from functools import lru_cache

from .constants import CIRCLE, ensure_markdown

_MATH_BLOCK_STYLE = (
    "background:#1a2744;border-left:3px solid #4299e1;"
    "padding:10px 14px;font-family:Consolas,Monaco,'Courier New',monospace;"
    "color:#90cdf4;border-radius:0 6px 6px 0;display:block;"
    "white-space:pre-wrap;margin:8px 0;line-height:1.6;font-size:13px;"
)
_MATH_INLINE_STYLE = (
    "background:#1a2744;color:#90cdf4;"
    "font-family:Consolas,Monaco,'Courier New',monospace;"
    "padding:2px 6px;border-radius:4px;font-size:13px;"
)


def _preprocess_math(text: str) -> tuple[str, list[tuple[str, str, bool]]]:
    """
    将所有数学公式提取为占位符，防止 Markdown 解析器破坏公式内容。
    支持：\\[...\\]  \\(...\\)  $$...$$  $...$
    返回：(替换后的文本, [(占位符, 原始内容, 是否块级), ...])
    """
    placeholders: list[tuple[str, str, bool]] = []

    def add(content: str, is_block: bool) -> str:
        token = f"⟦MATH{len(placeholders)}⟧"
        placeholders.append((token, content.strip(), is_block))
        # 块级公式前后加空行，确保 Markdown 不把它并入段落
        return f"\n\n{token}\n\n" if is_block else token

    # 块级：\[...\]
    text = re.sub(
        r"\\\[(.*?)\\\]",
        lambda m: add(m.group(1), True),
        text,
        flags=re.DOTALL,
    )
    # 行内：\(...\)
    text = re.sub(
        r"\\\((.*?)\\\)",
        lambda m: add(m.group(1), False),
        text,
        flags=re.DOTALL,
    )
    # 块级：$$...$$
    text = re.sub(
        r"\$\$(.*?)\$\$",
        lambda m: add(m.group(1), True),
        text,
        flags=re.DOTALL,
    )
    # 行内：$...$ （排除连续 $$ 及跨行情况）
    text = re.sub(
        r"(?<!\$)\$([^$\n]{1,300}?)\$(?!\$)",
        lambda m: add(m.group(1), False),
        text,
    )
    return text, placeholders


def _restore_math(
    html: str, placeholders: list[tuple[str, str, bool]]
) -> str:
    """将占位符替换回带样式的公式 HTML，原样展示 LaTeX 源码。"""
    for token, content, is_block in placeholders:
        # 直接 escape，不做任何符号转换
        escaped = html_mod.escape(content)
        if is_block:
            rendered = f'<div style="{_MATH_BLOCK_STYLE}">{escaped}</div>'
        else:
            rendered = f'<span style="{_MATH_INLINE_STYLE}">{escaped}</span>'
        # Markdown 可能把独占一行的占位符包在 <p> 里
        for variant in (token, html_mod.escape(token)):
            html = html.replace(f"<p>{variant}</p>", rendered)
            html = html.replace(variant, rendered)
    return html


# ── Markdown 扩展优先级链（PyInstaller 下部分扩展可能缺失） ──────
_MD_EXTENSION_CHAIN: tuple[tuple[str, ...], ...] = (
    ("tables", "fenced_code", "nl2br", "sane_lists", "attr_list"),
    ("tables", "fenced_code", "nl2br", "sane_lists"),
    ("tables", "fenced_code", "nl2br"),
    ("extra",),
    ("fenced_code", "nl2br"),
    (),
)

MD_CSS = """
<style>
body { margin:0; padding:0; }
p  { margin:0 0 6px 0; }
h1 { font-size:18px; font-weight:700; color:#f3f4f6; margin:8px 0 4px 0; }
h2 { font-size:16px; font-weight:700; color:#e5e7eb; margin:6px 0 4px 0; }
h3 { font-size:14px; font-weight:700; color:#d1d5db; margin:4px 0 2px 0; }
strong, b { color:#fde68a; font-weight:700; }
em, i { color:#a5b4fc; font-style:italic; }
code {
    background:#1e2a3a; color:#7dd3fc;
    font-family: Consolas, Monaco, monospace;
    padding: 1px 5px; border-radius: 3px; font-size: 12px;
}
pre {
    background:#1e2a3a; border:1px solid #2d3748; border-radius:6px;
    padding:10px 12px; margin:6px 0; overflow-x:auto;
}
pre code { background:transparent; padding:0; color:#86efac; font-size:12px; }
table {
    border-collapse:collapse; width:100%; margin:8px 0; font-size:13px;
}
th {
    background:#1e3a5f; color:#93c5fd;
    padding:6px 10px; border:1px solid #2d3748;
    font-weight:600; text-align:left;
}
td { padding:5px 10px; border:1px solid #2d3748; color:#d1d5db; }
tr:nth-child(even) td { background:#161f2e; }
blockquote {
    border-left:3px solid #4a5568; margin:4px 0; padding:4px 12px;
    color:#9ca3af; font-style:italic;
}
ul, ol { margin:4px 0 4px 20px; padding:0; }
li { margin:4px 0; }
li p { margin:0; }
ul ul, ol ol, ul ol, ol ul { margin:3px 0 3px 16px; }
a { color:#60a5fa; text-decoration:none; }
hr { border:none; border-top:1px solid #2d3748; margin:8px 0; }
</style>
"""


def markdown_ready() -> bool:
    return _get_markdown_converter() is not None


@lru_cache(maxsize=1)
def _get_markdown_converter():
    md_mod = ensure_markdown()
    if md_mod is None:
        return None
    last_err: Exception | None = None
    for exts in _MD_EXTENSION_CHAIN:
        try:
            return md_mod.Markdown(extensions=list(exts))
        except Exception as e:
            last_err = e
            continue
    if last_err:
        print("Markdown 初始化失败，使用纯文本回退:", last_err)
    return None


def md_to_html(text: str) -> str:
    text_proc, placeholders = _preprocess_math(text)
    converter = _get_markdown_converter()

    if converter is not None:
        try:
            converter.reset()
            html_body = converter.convert(text_proc)
        except Exception as e:
            print("Markdown 转换失败:", e)
            html_body = html_mod.escape(text_proc).replace("\n", "<br/>")
    else:
        html_body = _basic_md_fallback(text_proc)

    html_body = _restore_math(html_body, placeholders)
    return html_body


def _basic_md_fallback(text: str) -> str:
    """无 markdown 库时的简易渲染。"""
    lines = text.split("\n")
    out: list[str] = []
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    for raw in lines:
        line = raw.rstrip()
        if re.match(r"^[-*]\s+", line):
            close_lists()
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = html_mod.escape(re.sub(r"^[-*]\s+", "", line))
            out.append(f"<li>{item}</li>")
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            close_lists()
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{html_mod.escape(m.group(2))}</li>")
            continue
        close_lists()
        if not line.strip():
            out.append("<br/>")
            continue
        esc = html_mod.escape(line)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"\*(.+?)\*", r"<em>\1</em>", esc)
        out.append(f"<p>{esc}</p>")
    close_lists()
    return "".join(out)


def render_msg_html(
    content: str, annotations: list, streaming: bool = False,
    links: list | None = None,
) -> str:
    links = links or []
    cursor = '<span style="opacity:.55;">▌</span>' if streaming else ""

    if not annotations and not [l for l in links if l.selected_text]:
        body = md_to_html(content)
        return (
            f"<html><head>{MD_CSS}</head>"
            f'<body style="color:#e2e8f0;font-size:14px;line-height:1.85;">'
            f"{body}{cursor}</body></html>"
        )

    merged, token_data = _inject_inline_markers(content, annotations, links)
    html_body = md_to_html(merged)
    html_body = _restore_inline_markers(html_body, token_data)

    return (
        f"<html><head>{MD_CSS}</head>"
        f'<body style="color:#e2e8f0;font-size:14px;line-height:1.85;">'
        f"{html_body}{cursor}</body></html>"
    )


# ── KaTeX / WebEngine 路径（新增，不影响旧 QTextBrowser 路径） ──────


def _restore_math_katex(
    html: str, placeholders: list[tuple[str, str, bool]]
) -> str:
    """将占位符替换为 KaTeX 可识别的 $...$ / $$...$$ 分隔符。"""
    for token, content, is_block in placeholders:
        escaped = html_mod.escape(content)
        if is_block:
            rendered = f'<div class="math-block">$${escaped}$$</div>'
        else:
            rendered = f'<span class="math-inline">${escaped}$</span>'
        for variant in (token, html_mod.escape(token)):
            html = html.replace(f"<p>{variant}</p>", rendered)
            html = html.replace(variant, rendered)
    return html


def md_to_html_katex(text: str) -> str:
    """与 md_to_html 相同，但使用 _restore_math_katex 输出 KaTeX 分隔符。"""
    text_proc, placeholders = _preprocess_math(text)
    converter = _get_markdown_converter()

    if converter is not None:
        try:
            converter.reset()
            html_body = converter.convert(text_proc)
        except Exception as e:
            print("Markdown 转换失败:", e)
            html_body = html_mod.escape(text_proc).replace("\n", "<br/>")
    else:
        html_body = _basic_md_fallback(text_proc)

    html_body = _restore_math_katex(html_body, placeholders)
    return html_body


def _math_regions(content: str) -> list[tuple[int, int]]:
    """找出所有数学公式区域（起始位置, 结束位置），这些区域内不应注入标记。"""
    regions: list[tuple[int, int]] = []

    for pattern, is_block in [
        (r"\$\$(.+?)\$\$", True),
        (r"\\\[(.+?)\\\]", True),
        (r"\\\((.+?)\\\)", False),
        (r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", False),
    ]:
        flags = re.DOTALL if is_block else 0
        for m in re.finditer(pattern, content, flags=flags):
            regions.append((m.start(), m.end()))

    regions.sort(key=lambda x: x[0])
    return regions


def _in_text_region(pos: int, regions: list[tuple[int, int]]) -> bool:
    """检查 pos 是否在任意数学区域外（可以安全注入标记）。"""
    for start, end in regions:
        if start <= pos < end:
            return False
    return True


def _inject_inline_markers(
    content: str, annotations: list, links: list
) -> tuple[str, list[tuple[str, str, str, str, str, bool]]]:
    """将注释和文本链接替换为占位符 token，避开数学公式区域。

    返回: (合并后的文本, [(token, 原始文本, 类型, ID, 徽章, is_branch), ...])
    """
    math_reg = _math_regions(content)
    positions: list[tuple[int, int, str, int]] = []

    for i, ann in enumerate(annotations):
        pos = content.find(ann.quoted_text)
        if pos >= 0 and _in_text_region(pos, math_reg):
            positions.append((pos, pos + len(ann.quoted_text), "ann", i))

    text_links = [l for l in links if l.selected_text]
    for i, link in enumerate(text_links):
        pos = content.find(link.selected_text)
        if pos >= 0 and _in_text_region(pos, math_reg):
            positions.append((pos, pos + len(link.selected_text), "link", i))

    positions.sort(key=lambda x: (x[0], 0 if x[2] == "ann" else 1))

    pieces: list[str] = []
    prev = 0
    token_data: list[tuple[str, str, str, str, str, bool]] = []

    for start, end, typ, idx in positions:
        if start < prev:
            continue  # 跳过重叠
        pieces.append(content[prev:start])
        if typ == "ann":
            ann = annotations[idx]
            badge = CIRCLE[idx] if idx < len(CIRCLE) else f"({idx + 1})"
            token = f"\x00ANN{ann.id}\x00"
            is_branch = bool(getattr(ann, "branch_id", ""))
            token_data.append((token, ann.quoted_text, "ann", ann.id, badge, is_branch))
        else:
            link = text_links[idx]
            token = f"\x00LINK{link.id}\x00"
            token_data.append((token, link.selected_text, "link", link.id, "🔗", False))
        pieces.append(token)
        prev = end

    pieces.append(content[prev:])
    return "".join(pieces), token_data


def _restore_inline_markers(html_body: str, token_data: list) -> str:
    """将占位符 token 替换为内联 HTML 标记。"""
    for item in token_data:
        token, quoted, typ, obj_id, badge = item[:5]
        is_branch = item[5] if len(item) > 5 else False
        esc_q = html_mod.escape(quoted)
        if typ == "ann":
            if is_branch:
                # 支线样式：青色
                rendered = (
                    f'<span style="border-bottom:1.5px dashed #38b2ac;color:#81e6d9;">'
                    f"{esc_q}</span>"
                    f'<a href="ann://{obj_id}" style="color:#81e6d9;font-size:11px;'
                    f"font-weight:700;text-decoration:none;background:#234e52;"
                    f"border-radius:3px;padding:0 3px;margin-left:1px;"
                    f'vertical-align:super;">{badge}</a>'
                )
            else:
                # 普通注释样式：琥珀色
                rendered = (
                    f'<span style="border-bottom:1.5px dashed #d97706;color:#fde68a;">'
                    f"{esc_q}</span>"
                    f'<a href="ann://{obj_id}" style="color:#d97706;font-size:11px;'
                    f"font-weight:700;text-decoration:none;background:#451a03;"
                    f"border-radius:3px;padding:0 3px;margin-left:1px;"
                    f'vertical-align:super;">{badge}</a>'
                )
        else:
            rendered = (
                f'<span style="border-bottom:1.5px dashed #60a5fa;color:#93c5fd;">'
                f"{esc_q}</span>"
                f'<a href="link://{obj_id}" style="color:#60a5fa;font-size:11px;'
                f"font-weight:700;text-decoration:none;background:#1e3a5f;"
                f"border-radius:3px;padding:0 3px;margin-left:1px;"
                f'vertical-align:super;">{badge}</a>'
            )
        html_body = html_body.replace(html_mod.escape(token), rendered)
        html_body = html_body.replace(token, rendered)
    return html_body


def render_msg_body(
    content: str, annotations: list, streaming: bool = False,
    links: list | None = None,
) -> str:
    """返回 body 片段（无 <html><head> 包裹），供 WebEngineContentView 使用。"""
    links = links or []
    cursor = '<span style="opacity:.55;">&#x258C;</span>' if streaming else ""

    if not annotations and not [l for l in links if l.selected_text]:
        body = md_to_html_katex(content)
        return f"{body}{cursor}"

    merged, token_data = _inject_inline_markers(content, annotations, links)
    html_body = md_to_html_katex(merged)
    html_body = _restore_inline_markers(html_body, token_data)
    return f"{html_body}{cursor}"
