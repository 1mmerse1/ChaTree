"""对话导出为 Markdown 文件 —— 树状拓扑扁平化。

- 主线对话线性展示
- 追问/批注用 <details>/<summary> 折叠（GitHub / Obsidian 原生兼容）
- 跨对话链接用 Obsidian [[]] wikilink 语法
- 标签: frontmatter tags: [...] + 行内 #tag（Obsidian 可直接识别）
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .constants import CIRCLE
from .models import Conversation, Folder, Link, MessageNode
from .workspace import ws


# ── 工具函数 ──────────────────────────────────────────────────────────


def sanitize_filename(title: str) -> str:
    """替换文件系统非法字符，截断到合理长度。"""
    result = re.sub(r'[<>:"/\\|?*]', "-", title)
    result = result.strip()
    if len(result) > 100:
        result = result[:100]
    return result or "未命名对话"


def _yaml_str(s: str) -> str:
    """YAML 字符串转义（含引号/冒号/换行时用双引号包裹）。"""
    if any(c in s for c in ('"', "'", ":", "\n")):
        return json.dumps(s, ensure_ascii=False)
    return s


def _resolve_wikilink_title(
    target_conv_id: str, target_msg_id: str = "", *, use_anchor: bool = False
) -> str:
    """将 (对话ID, 消息ID) 解析为 Obsidian wikilink 显示文本。
    """
    target_conv = ws.conversations.get(target_conv_id)
    if not target_conv:
        return "未知对话"

    title = target_conv.title

    if target_msg_id:
        if use_anchor:
            return f"{title}#msg-{target_msg_id}"
        # 单文件模式：用消息预览文本
        for msg in target_conv.messages:
            if msg.id == target_msg_id:
                preview = msg.content.replace("\n", " ").strip()
                if len(preview) > 40:
                    preview = preview[:40] + "…"
                return f"{title}#{preview}"

    return title


def _find_conv_folder(conv_id: str) -> str:
    """递归查找对话所在文件夹路径。

    Returns:
        "父 > 子" 或 "未归档"。
    """

    def _search(folders: list[Folder], path: str = "") -> Optional[str]:
        for fo in folders:
            current = f"{path} > {fo.name}" if path else fo.name
            if conv_id in fo.conv_ids:
                return current
            result = _search(fo.subfolders, current)
            if result:
                return result
        return None

    if conv_id in ws._unfiled:
        return "未归档"

    result = _search(ws.folders)
    return result if result else "未归档"


def _find_source_conv_for_link(link: Link) -> Optional[Conversation]:
    """查找包含指定 Link 对象的源对话（该 link 存储在源对话的 links 列表中）。"""
    for conv in ws.conversations.values():
        for cl in conv.links:
            if cl.id == link.id:
                return conv
    return None


# ── 格式化函数 ────────────────────────────────────────────────────────


def _format_frontmatter(conv: Conversation) -> str:
    """生成 YAML frontmatter 块（Obsidian 原生识别 tags / title / created）。"""
    folder = _find_conv_folder(conv.id)
    return "\n".join(
        [
            "---",
            f"title: {_yaml_str(conv.title)}",
            f"created: {conv.created_at}",
            f"tags: {json.dumps(conv.tags, ensure_ascii=False)}",
            f"folder: {json.dumps(folder, ensure_ascii=False)}",
            "---",
            "",
        ]
    )


def _format_message_tags(msg: MessageNode) -> str:
    """消息级行内标签，Obsidian 可直接识别 #tag。"""
    if not msg.tags:
        return ""
    return "  ".join(f"#{t}" for t in msg.tags)


def _format_outgoing_links(msg: MessageNode, conv: Conversation) -> str:
    """渲染消息发出的跨对话链接。"""
    outgoing = [lk for lk in conv.links if lk.source_msg_id == msg.id]
    if not outgoing:
        return ""

    lines = []
    for lk in outgoing:
        target_title = _resolve_wikilink_title(lk.target_conv_id, lk.target_msg_id)
        text = lk.selected_text or "链接"
        lines.append(f"> 🔗 → [[{target_title}]] — *{text}*")

    return "\n".join(lines)


def _format_annotations(msg: MessageNode) -> str:
    """渲染消息的追问折叠块（<details>/<summary>，GitHub & Obsidian 兼容）。"""
    if not msg.annotations:
        return ""

    parts = []
    for i, ann in enumerate(msg.annotations):
        circle = CIRCLE[i] if i < len(CIRCLE) else f"({i + 1})"

        quoted = ann.quoted_text
        if len(quoted) > 60:
            quoted = quoted[:60] + "…"

        parts.append(
            f"<details>\n"
            f'<summary>📎 追问{circle}: "{quoted}"</summary>\n'
            f"\n"
            f"**追问:** {ann.user_question}\n"
            f"\n"
            f"**回答:** {ann.ai_answer}\n"
            f"\n"
            f"</details>"
        )

    return "\n\n".join(parts)


def _format_message(msg: MessageNode, conv: Conversation) -> str:
    """渲染单条消息（角色头 + 标签 + 内容 + 链接 + 追问折叠）。"""
    role_emoji = "👤" if msg.role == "user" else "🤖"
    role_label = "用户" if msg.role == "user" else "助手"

    parts = [f"## {role_emoji} {role_label}"]

    # 消息级标签
    tags_line = _format_message_tags(msg)
    if tags_line:
        parts.append("")
        parts.append(tags_line)

    # 消息正文（原样保留 Markdown）
    parts.append("")
    parts.append(msg.content)

    # 外向链接
    links_section = _format_outgoing_links(msg, conv)
    if links_section:
        parts.append("")
        parts.append(links_section)

    # 追问折叠
    annotations_section = _format_annotations(msg)
    if annotations_section:
        parts.append("")
        parts.append(annotations_section)

    return "\n".join(parts)


def _format_backlinks_section(conv: Conversation) -> str:
    """渲染文末「反向链接」节 —— 收集所有指向本对话的消息。"""
    all_backlinks: list[tuple[Link, str]] = []  # [(link, source_conv_title)]
    seen_ids: set[str] = set()

    # 对话级反向链接
    for link in ws.get_backlinks(conv.id, ""):
        if link.id not in seen_ids:
            seen_ids.add(link.id)
            src = _find_source_conv_for_link(link)
            all_backlinks.append((link, src.title if src else "未知对话"))

    # 每条消息的反向链接
    for msg in conv.messages:
        for link in ws.get_backlinks(conv.id, msg.id):
            if link.id not in seen_ids:
                seen_ids.add(link.id)
                src = _find_source_conv_for_link(link)
                all_backlinks.append((link, src.title if src else "未知对话"))

    parts = ["## 🔙 反向链接", ""]

    if not all_backlinks:
        parts.append("_暂无反向链接_")
        return "\n".join(parts)

    for link, src_title in all_backlinks:
        if link.target_msg_id:
            # 查找被链接的消息预览
            preview = ""
            target_conv = ws.conversations.get(link.target_conv_id)
            if target_conv:
                for m in target_conv.messages:
                    if m.id == link.target_msg_id:
                        preview = m.content.replace("\n", " ")[:40]
                        break
            if preview:
                parts.append(f"- ← **[[{src_title}#{preview}]]** — *{link.selected_text or '消息链接'}*")
            else:
                parts.append(f"- ← **[[{src_title}]]** — *{link.selected_text or '消息链接'}*")
        else:
            parts.append(f"- ← **[[{src_title}]]** — *对话链接*")

    return "\n".join(parts)


# ── 多文件模式格式化（Obsidian Vault）─────────────────────────────────


def _format_message_mf(msg: MessageNode, conv: Conversation) -> str:
    """多文件版消息渲染 —— 标题前插入 HTML anchor，使 ``[[file#msg-id]]`` 可跳转。"""
    role_emoji = "👤" if msg.role == "user" else "🤖"
    role_label = "用户" if msg.role == "user" else "助手"

    parts = [
        f'<a id="msg-{msg.id}"></a>',
        "",
        f"## {role_emoji} {role_label}",
    ]

    tags_line = _format_message_tags(msg)
    if tags_line:
        parts.append("")
        parts.append(tags_line)

    parts.append("")
    parts.append(msg.content)

    links_section = _format_outgoing_links_mf(msg, conv)
    if links_section:
        parts.append("")
        parts.append(links_section)

    annotations_section = _format_annotations(msg)
    if annotations_section:
        parts.append("")
        parts.append(annotations_section)

    return "\n".join(parts)


def _format_outgoing_links_mf(msg: MessageNode, conv: Conversation) -> str:
    """多文件版外向链接 —— 使用 ``#msg-id`` anchor 实现精确跳转。"""
    outgoing = [lk for lk in conv.links if lk.source_msg_id == msg.id]
    if not outgoing:
        return ""

    lines = []
    for lk in outgoing:
        target = _resolve_wikilink_title(
            lk.target_conv_id, lk.target_msg_id, use_anchor=True
        )
        text = lk.selected_text or "链接"
        lines.append(f"> 🔗 → [[{target}]] — *{text}*")

    return "\n".join(lines)


def _format_backlinks_mf(conv: Conversation) -> str:
    """多文件版反向链接 —— 使用 ``#msg-id`` anchor。"""
    all_backlinks: list[tuple[Link, str]] = []
    seen_ids: set[str] = set()

    for link in ws.get_backlinks(conv.id, ""):
        if link.id not in seen_ids:
            seen_ids.add(link.id)
            src = _find_source_conv_for_link(link)
            all_backlinks.append((link, src.title if src else "未知对话"))

    for msg in conv.messages:
        for link in ws.get_backlinks(conv.id, msg.id):
            if link.id not in seen_ids:
                seen_ids.add(link.id)
                src = _find_source_conv_for_link(link)
                all_backlinks.append((link, src.title if src else "未知对话"))

    parts = ["## 🔙 反向链接", ""]

    if not all_backlinks:
        parts.append("_暂无反向链接_")
        return "\n".join(parts)

    for link, src_title in all_backlinks:
        # 源链接的 source_msg_id → 定位到源消息的 anchor
        src_anchor = f"[[{src_title}#msg-{link.source_msg_id}]]"
        if link.target_msg_id:
            text = link.selected_text or "消息链接"
            parts.append(f"- ← **{src_anchor}** — *{text}*")
        else:
            src_ref = f"[[{src_title}]]"
            parts.append(f"- ← **{src_ref}** — *对话链接*")

    return "\n".join(parts)


def _build_export_paths(base_dir: Path) -> dict[str, Path]:
    """构建 conv_id → 绝对 .md 文件路径 的映射。

    按 ws.folders 树组织目录，未归档对话放入 ``未归档/`` 子目录。
    处理同名对话冲突：追加 `` (2)``, `` (3)`` 后缀。
    """

    def _walk_folders(folders: list[Folder], parent_dir: Path) -> dict[str, Path]:
        mapping: dict[str, Path] = {}
        for fo in folders:
            fo_name = sanitize_filename(fo.name)
            fo_dir = parent_dir / fo_name
            fo_dir.mkdir(parents=True, exist_ok=True)
            for cid in fo.conv_ids:
                if cid in ws.conversations:
                    mapping[cid] = fo_dir
            mapping.update(_walk_folders(fo.subfolders, fo_dir))
        return mapping

    # 先映射所有 conv_id → 目标目录
    conv_dirs: dict[str, Path] = {}
    conv_dirs.update(_walk_folders(ws.folders, base_dir))

    # 未归档对话
    unfiled_dir = base_dir / "未归档"
    for cid in ws._unfiled:
        if cid in ws.conversations:
            conv_dirs[cid] = unfiled_dir

    # 生成文件路径，处理同名冲突
    used_names: set[str] = set()
    result: dict[str, Path] = {}

    for cid, directory in conv_dirs.items():
        conv = ws.conversations[cid]
        base_name = sanitize_filename(conv.title)
        name = base_name
        counter = 2
        while f"{directory}/{name}.md" in used_names:
            name = f"{base_name} ({counter})"
            counter += 1
        used_names.add(f"{directory}/{name}.md")
        directory.mkdir(parents=True, exist_ok=True)
        result[cid] = directory / f"{name}.md"

    return result


def export_conversation_to_md_mf(conv: Conversation) -> str:
    """多文件版单对话导出 —— 使用 anchor 机制，无反向链接节（由各文件独立渲染）。"""
    parts: list[str] = []

    parts.append(_format_frontmatter(conv))
    parts.append(f"# {conv.title}")
    parts.append("")

    if conv.tags:
        parts.append("  ".join(f"#{t}" for t in conv.tags))
        parts.append("")

    if not conv.messages:
        parts.append("_暂无消息_")
    else:
        for i, msg in enumerate(conv.messages):
            if i > 0:
                parts.append("")
                parts.append("---")
                parts.append("")
            parts.append(_format_message_mf(msg, conv))

    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(_format_backlinks_mf(conv))
    parts.append("")
    return "\n".join(parts)


def export_workspace_to_files(base_dir: str | Path) -> int:
    """将所有对话导出为独立 .md 文件，按文件夹树组织目录。

    每个对话一个 ``.md`` 文件，消息标题带 HTML anchor，
    wikilink 使用 ``[[Title#msg-id]]`` 格式，可在 Obsidian 中精确跳转。

    Args:
        base_dir: 导出根目录（会被创建如果不存在）。

    Returns:
        成功写入的文件数量。
    """
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)

    paths = _build_export_paths(base)
    count = 0

    for cid, file_path in paths.items():
        conv = ws.conversations.get(cid)
        if not conv:
            continue
        md = export_conversation_to_md_mf(conv)
        file_path.write_text(md, encoding="utf-8")
        count += 1

    return count


# ── 公共入口 ──────────────────────────────────────────────────────────


def export_conversation_to_md(conv: Conversation) -> str:
    """将单场对话导出为完整的 Markdown 字符串。"""
    parts: list[str] = []

    # YAML frontmatter
    parts.append(_format_frontmatter(conv))

    # 标题
    parts.append(f"# {conv.title}")
    parts.append("")

    # 对话级标签（行内，Obsidian 可直接识别）
    if conv.tags:
        parts.append("  ".join(f"#{t}" for t in conv.tags))
        parts.append("")

    # 消息体
    if not conv.messages:
        parts.append("_暂无消息_")
    else:
        for i, msg in enumerate(conv.messages):
            if i > 0:
                parts.append("")
                parts.append("---")
                parts.append("")
            parts.append(_format_message(msg, conv))

    # 反向链接节
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(_format_backlinks_section(conv))

    parts.append("")  # 末尾换行
    return "\n".join(parts)


def export_workspace_to_md(conv_ids: list[str]) -> str:
    """将多个对话合并导出到一个 Markdown 文件。

    每个对话之间用 ``---`` 分隔。
    """
    valid_ids = [cid for cid in conv_ids if cid in ws.conversations]
    parts: list[str] = []

    for i, cid in enumerate(valid_ids):
        conv = ws.conversations[cid]
        if i > 0:
            parts.append("")
            parts.append("---")
            parts.append("")
            parts.append("---")
            parts.append("")
        parts.append(export_conversation_to_md(conv))

    return "\n".join(parts)
