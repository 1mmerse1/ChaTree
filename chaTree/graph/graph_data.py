"""从 Workspace 构建 pyvis Network 对象。

节点 = 一次"用户提问 + AI 回答"的对话轮次。
边 = 对话内顺序流 + 跨对话链接（按轮次归属映射）。
"""

from __future__ import annotations

from pyvis.network import Network

from ..models import Conversation, MessageNode
from ..workspace import ws

# ── 节点颜色 ──────────────────────────────────────────────────────
NODE_BG = "#1a365d"
NODE_HIGHLIGHT = "#4299e1"

# ── 对话颜色（12 色调色板，用于节点边框区分对话） ────────────────
_CONV_COLORS = [
    "#4299e1", "#48bb78", "#ed8936", "#9f7aea",
    "#ed64a6", "#38b2ac", "#f6e05e", "#fc8181",
    "#63b3ed", "#68d391", "#fbd38d", "#b794f4",
]

# ── 边颜色 ────────────────────────────────────────────────────────
EDGE_SEQUENTIAL = "#4a5568"   # 对话内顺序边 — 灰色实线
EDGE_LINK = "#60a5fa"         # 跨对话链接边 — 蓝色虚线


def _conv_color(index: int) -> str:
    return _CONV_COLORS[index % len(_CONV_COLORS)]


def _round_id(conv_id: str, user_msg_id: str) -> str:
    """轮次节点 ID = 发起该轮的用户消息 ID。"""
    return f"{conv_id}::{user_msg_id}"


def _has_node(net: Network, nid: str) -> bool:
    try:
        net.get_node(nid)
        return True
    except KeyError:
        return False


def _build_round_map(conv: Conversation) -> dict[str, str]:
    """构建 msg_id → round_id 映射。

    一个 round = 一条 user 消息 + 紧随其后的 assistant 消息。
    连续的 user → assistant → user → assistant 产生两个 round。
    孤立的 user（最后一条无回复）也算一个 round。
    """
    mapping: dict[str, str] = {}
    current_user_id: str | None = None

    for msg in conv.messages:
        if msg.role == "user":
            current_user_id = msg.id
            mapping[msg.id] = current_user_id
        elif msg.role == "assistant":
            if current_user_id is not None:
                mapping[msg.id] = current_user_id
            # 如果 assistant 前面没有 user（异常），忽略

    return mapping


class GraphBuilder:
    """从 Workspace 构建 pyvis Network（每个对话轮次一个节点）。"""

    def build(
        self,
        conversation_ids: list[str] | None = None,
    ) -> Network:
        convs = ws.conversations
        target_ids = (
            set(conversation_ids)
            if conversation_ids is not None
            else set(convs.keys())
        )

        # 对话 → 颜色索引
        conv_index: dict[str, int] = {}
        for i, cid in enumerate(sorted(target_ids)):
            conv_index[cid] = i

        # 预计算每个对话的 round map
        round_maps: dict[str, dict[str, str]] = {}
        round_count = 0
        for cid in target_ids:
            conv = convs.get(cid)
            if conv:
                rm = _build_round_map(conv)
                round_maps[cid] = rm
                # 统计唯一 round 数
                round_count += len(set(rm.values()))

        net = Network(
            height="100%",
            width="100%",
            bgcolor="#0f1117",
            font_color="#a0aec0",
            directed=True,
        )

        # ── vis.js 物理配置 ──────────────────────────────────────
        spring_len = 250 if round_count > 30 else 200
        gravity = -1800 if round_count > 20 else -800

        net.set_options(f"""
        {{
          "physics": {{
            "barnesHut": {{
              "gravitationalConstant": {gravity},
              "springLength": {spring_len},
              "springConstant": 0.01,
              "damping": 0.15,
              "avoidOverlap": 0.2
            }},
            "minVelocity": 0.5,
            "solver": "barnesHut",
            "stabilization": {{
              "enabled": true,
              "iterations": 300,
              "updateInterval": 25
            }}
          }},
          "layout": {{
            "improvedLayout": true,
            "randomSeed": 2
          }},
          "interaction": {{
            "hover": true,
            "tooltipDelay": 150,
            "dragNodes": true,
            "zoomView": true,
            "navigationButtons": false
          }},
          "nodes": {{
            "font": {{ "color": "#a0aec0", "size": 12, "strokeWidth": 0 }},
            "shape": "dot",
            "scaling": {{ "min": 12, "max": 28 }}
          }},
          "edges": {{
            "smooth": {{ "type": "curvedCW", "roundness": 0.25 }},
            "arrows": {{ "to": {{ "enabled": true, "scaleFactor": 0.5 }} }}
          }}
        }}
        """)

        # ── 添加节点（每个 round 一个） ──────────────────────────
        # 同时收集 round 的辅助信息用于 tooltip
        round_info: dict[str, dict] = {}  # round_id → {question, answer, tags}

        for cid in sorted(target_ids):
            conv = convs.get(cid)
            if not conv:
                continue
            ci = conv_index[cid]
            border_color = _conv_color(ci)

            rm = round_maps[cid]
            seen_rounds: set[str] = set()

            for msg in conv.messages:
                rid = rm.get(msg.id)
                if rid is None or rid in seen_rounds:
                    continue
                seen_rounds.add(rid)

                nid = _round_id(cid, rid)

                # 找到该 round 的 user 消息
                user_msg = next(
                    (m for m in conv.messages if m.id == rid), None
                )
                if user_msg is None:
                    continue

                # 找到紧随其后的 assistant 消息
                user_idx = conv.messages.index(user_msg)
                assistant_msg = None
                if user_idx + 1 < len(conv.messages):
                    nxt = conv.messages[user_idx + 1]
                    if nxt.role == "assistant":
                        assistant_msg = nxt

                # 标签：用户问题截断
                label = user_msg.content[:35].replace("\n", " ")
                if len(user_msg.content) > 35:
                    label += "…"

                # Tooltip：用户问题 + AI 回答
                question = user_msg.content[:150].replace("\n", " ")
                title = f"<b>{conv.title}</b><br><br>❓ {question}"
                if assistant_msg:
                    answer = assistant_msg.content[:200].replace("\n", " ")
                    title += f"<br><br>💬 {answer}"
                if user_msg.tags:
                    title += f"<br><br>标签: {', '.join(user_msg.tags)}"

                color = {
                    "background": NODE_BG,
                    "border": border_color,
                    "highlight": {
                        "background": NODE_HIGHLIGHT,
                        "border": border_color,
                    },
                }

                net.add_node(
                    nid,
                    label=label,
                    title=title,
                    color=color,
                    size=22,
                    borderWidth=2,
                )

                round_info[nid] = {
                    "conv_id": cid,
                    "user_msg_id": rid,
                    "conv_title": conv.title,
                    "question": user_msg.content,
                    "tags": user_msg.tags,
                }

        # ── 1) 对话内顺序边（round 之间） ────────────────────────
        for cid in sorted(target_ids):
            conv = convs.get(cid)
            if not conv:
                continue

            # 按消息顺序提取所有 round ID（去重保持顺序）
            rm = round_maps.get(cid, {})
            ordered_rounds: list[str] = []
            seen: set[str] = set()
            for msg in conv.messages:
                rid = rm.get(msg.id)
                if rid and rid not in seen:
                    seen.add(rid)
                    ordered_rounds.append(rid)

            for i in range(len(ordered_rounds) - 1):
                src = _round_id(cid, ordered_rounds[i])
                tgt = _round_id(cid, ordered_rounds[i + 1])
                if _has_node(net, src) and _has_node(net, tgt):
                    net.add_edge(
                        src, tgt,
                        color=EDGE_SEQUENTIAL,
                        width=2,
                        title=f"对话流程 · {conv.title}",
                    )

        # ── 2) 跨对话 Link 边（按轮次归属映射） ──────────────────
        for cid in sorted(target_ids):
            conv = convs.get(cid)
            if not conv:
                continue
            src_rm = round_maps.get(cid, {})

            for link in conv.links:
                # 源消息所属 round
                src_round_user_id = src_rm.get(link.source_msg_id)
                if src_round_user_id is None:
                    continue
                src_nid = _round_id(cid, src_round_user_id)
                if not _has_node(net, src_nid):
                    continue

                # 目标消息所属 round
                tgt_rm = round_maps.get(link.target_conv_id, {})
                if link.target_msg_id:
                    tgt_round_user_id = tgt_rm.get(link.target_msg_id)
                else:
                    # 目标是整个对话 → 取第一个 round
                    target_conv = convs.get(link.target_conv_id)
                    tgt_round_user_id = None
                    if target_conv:
                        for m in target_conv.messages:
                            rid = tgt_rm.get(m.id)
                            if rid:
                                tgt_round_user_id = rid
                                break

                if tgt_round_user_id is None:
                    continue

                tgt_nid = _round_id(link.target_conv_id, tgt_round_user_id)
                if not _has_node(net, tgt_nid):
                    continue

                edge_title = "跨对话链接"
                if link.selected_text:
                    edge_title += f": {link.selected_text[:60]}"

                net.add_edge(
                    src_nid, tgt_nid,
                    color=EDGE_LINK,
                    width=1.5,
                    dashes=[6, 4],
                    title=edge_title,
                )

        return net
