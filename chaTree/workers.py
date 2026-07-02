"""后台线程：主对话流式输出与注释生成。"""

from PySide6.QtCore import QThread, Signal

from .constants import HAS_OPENAI
from .prompts import (
    ANNOTATION_MAX_CHARS,
    ANNOTATION_MAX_TOKENS,
    ANNOTATION_SYSTEM_PROMPT,
    AUTO_LINK_MAX_TOKENS,
    AUTO_LINK_SYSTEM_PROMPT,
    BRANCH_MAX_TOKENS,
    BRANCH_SYSTEM_PROMPT,
    CHAT_MAX_TOKENS,
    CHAT_SYSTEM_PROMPT,
    TAG_SYSTEM_PROMPT,
)
from .workspace import ws

if HAS_OPENAI:
    import openai


def _prepend_system(messages: list, system: str) -> list:
    if messages and messages[0].get("role") == "system":
        return messages
    return [{"role": "system", "content": system}, *messages]


class ChatWorker(QThread):
    token_received = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, messages: list):
        super().__init__()
        self._msgs = messages
        self._full = ""

    def run(self):
        if not HAS_OPENAI:
            self.error.emit("请安装 openai：pip install openai")
            return
        if not ws.api_key:
            self.error.emit("请先在 ⚙ 设置 中填入 API Key")
            return
        try:
            client = openai.OpenAI(api_key=ws.api_key, base_url=ws.base_url)
            msgs = _prepend_system(self._msgs, CHAT_SYSTEM_PROMPT)
            with client.chat.completions.create(
                model=ws.model,
                messages=msgs,
                stream=True,
                max_tokens=CHAT_MAX_TOKENS,
            ) as stream:
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    self._full += delta
                    self.token_received.emit(delta)
            self.finished.emit(self._full)
        except Exception as e:
            self.error.emit(str(e))


class AnnotationWorker(QThread):
    token_received = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, context: str, quoted: str, question: str):
        super().__init__()
        self._context = context
        self._quoted = quoted
        self._question = question
        self._full = ""

    @staticmethod
    def _trim_annotation(text: str) -> str:
        t = text.strip()
        if len(t) <= ANNOTATION_MAX_CHARS:
            return t
        cut = t[:ANNOTATION_MAX_CHARS]
        for sep in ("。", "！", "？", "\n", "；", ".", " "):
            pos = cut.rfind(sep)
            if pos > ANNOTATION_MAX_CHARS // 2:
                return cut[: pos + 1].strip()
        return cut.rstrip() + "…"

    def run(self):
        if not HAS_OPENAI:
            self.error.emit("未安装 openai")
            return
        if not ws.api_key:
            self.error.emit("未填入 API Key")
            return
        try:
            client = openai.OpenAI(api_key=ws.api_key, base_url=ws.base_url)
            msgs = [
                {"role": "system", "content": ANNOTATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"原文语境（节选）：\n{self._context[:1200]}\n\n"
                        f"选中片段：「{self._quoted}」\n"
                        f"追问：{self._question}\n\n"
                        "请用不超过 200 字回答。"
                    ),
                },
            ]
            with client.chat.completions.create(
                model=ws.model,
                messages=msgs,
                stream=True,
                max_tokens=ANNOTATION_MAX_TOKENS,
            ) as stream:
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    self._full += delta
                    self.token_received.emit(delta)
            self.finished.emit(self._trim_annotation(self._full))
        except Exception as e:
            self.error.emit(str(e))


class BranchWorker(QThread):
    """支线多轮对话流式生成器（与主对话相同的 token 预算，无特殊截断）。"""

    token_received = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, messages: list):
        super().__init__()
        self._msgs = messages
        self._full = ""

    def run(self):
        if not HAS_OPENAI:
            self.error.emit("请安装 openai：pip install openai")
            return
        if not ws.api_key:
            self.error.emit("请先在 ⚙ 设置 中填入 API Key")
            return
        try:
            client = openai.OpenAI(api_key=ws.api_key, base_url=ws.base_url)
            msgs = _prepend_system(self._msgs, BRANCH_SYSTEM_PROMPT)
            with client.chat.completions.create(
                model=ws.model,
                messages=msgs,
                stream=True,
                max_tokens=BRANCH_MAX_TOKENS,
            ) as stream:
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    self._full += delta
                    self.token_received.emit(delta)
            self.finished.emit(self._full)
        except Exception as e:
            self.error.emit(str(e))


class AutoLinkWorker(QThread):
    """分析当前 Q&A 轮次与历史轮次的关联，推荐建立链接。"""

    finished = Signal(object)   # list[dict]
    error = Signal(str)

    def __init__(
        self,
        current_conv_id: str,
        current_msg_id: str,
        current_user_msg: str,
        current_assistant_msg: str,
        all_convs: list,
        round_index: int = -1,
    ):
        super().__init__()
        self._current_conv_id = current_conv_id
        self._current_msg_id = current_msg_id
        self._current_user_msg = current_user_msg
        self._current_assistant_msg = current_assistant_msg
        self._all_convs = all_convs
        self._round_index = round_index

    def run(self):
        import json as _json
        import re as _re

        print("[AutoLink] ── 开始分析关联 ──")

        if not HAS_OPENAI:
            print("[AutoLink] 跳过：未安装 openai")
            self.finished.emit([])
            return
        if not ws.api_key:
            print("[AutoLink] 跳过：未配置 API Key")
            self.finished.emit([])
            return

        # ── 构建候选轮次 ──
        candidates: list[dict] = []
        for conv in self._all_convs:
            if conv.id == self._current_conv_id:
                # 同对话：跳过当前轮次前后 5 轮
                for i, msg in enumerate(conv.messages):
                    if msg.role != "user":
                        continue
                    if self._round_index >= 0 and abs(i - self._round_index) < 10:
                        continue
                    candidates.append({
                        "conv_id": conv.id,
                        "msg_id": msg.id,
                        "title": conv.title,
                        "question": msg.content[:80].replace("\n", " "),
                    })
            else:
                # 跨对话：取所有 user 消息
                for msg in conv.messages:
                    if msg.role != "user":
                        continue
                    candidates.append({
                        "conv_id": conv.id,
                        "msg_id": msg.id,
                        "title": conv.title,
                        "question": msg.content[:80].replace("\n", " "),
                    })

        print(f"[AutoLink] 候选轮次: {len(candidates)} 个")
        if not candidates:
            print("[AutoLink] 跳过：无候选轮次")
            self.finished.emit([])
            return

        # ── 构建 prompt ──
        cand_lines: list[str] = []
        for c in candidates:
            cand_lines.append(
                f"- {c['conv_id']}::{c['msg_id']} | {c['title']} | {c['question']}"
            )
        cand_text = "\n".join(cand_lines)

        user_prompt = (
            f"当前轮次：\n"
            f"❓ 用户问题：{self._current_user_msg[:500]}\n"
            f"💬 AI 回答：{self._current_assistant_msg[:300]}\n\n"
            f"候选轮次（格式：conv_id::msg_id | 标题 | 问题摘要）：\n"
            f"{cand_text}"
        )

        try:
            client = openai.OpenAI(api_key=ws.api_key, base_url=ws.base_url)
            msgs = [
                {"role": "system", "content": AUTO_LINK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            resp = client.chat.completions.create(
                model=ws.model,
                messages=msgs,
                max_tokens=AUTO_LINK_MAX_TOKENS,
                stream=False,
            )
            choice = resp.choices[0] if resp.choices else None
            if choice is None:
                print("[AutoLink] 跳过：API 返回空 choices")
                self.finished.emit([])
                return

            text = (choice.message.content or "").strip()
            print(f"[AutoLink] LLM 返回: {text[:200]}")
            # 提取 JSON（可能被 markdown 代码块包裹）
            json_match = _re.search(r"\{.*\}", text, _re.DOTALL)
            if not json_match:
                print("[AutoLink] 跳过：无法从返回中提取 JSON")
                self.finished.emit([])
                return

            data = _json.loads(json_match.group(0))
            raw_suggestions = data.get("suggestions", [])
            print(f"[AutoLink] LLM 建议数: {len(raw_suggestions)}")
        except Exception as e:
            print(f"[AutoLink] 异常：{e}")
            self.finished.emit([])
            return

        # ── 去重 + 截断 ──
        existing = set()
        current_conv = None
        for c in self._all_convs:
            if c.id == self._current_conv_id:
                current_conv = c
                break
        if current_conv:
            for link in current_conv.links:
                if link.source_msg_id == self._current_msg_id:
                    existing.add((link.target_conv_id, link.target_msg_id))

        suggestions: list[dict] = []
        skipped_dup = 0
        for s in raw_suggestions:
            key = (s.get("conv_id", ""), s.get("msg_id", ""))
            if key in existing:
                skipped_dup += 1
                continue
            suggestions.append(s)
            if len(suggestions) >= 3:
                break

        if skipped_dup:
            print(f"[AutoLink] 去重移除: {skipped_dup} 个（已有链接）")
        print(f"[AutoLink] 最终建议: {len(suggestions)} 个")
        if suggestions:
            for s in suggestions:
                print(f"  → {s.get('conv_id', '?')}「{s.get('reason', '?')}」")
        else:
            print("[AutoLink] 结论：无强关联，不弹窗")

        self.finished.emit(suggestions)


class TagWorker(QThread):
    """非流式标签生成器（使用流式 API + 收集全部 token）。"""
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, user_msg: str, assistant_msg: str):
        super().__init__()
        self._user_msg = user_msg
        self._assistant_msg = assistant_msg

    def run(self):
        if not HAS_OPENAI:
            self.error.emit("TagWorker: 未安装 openai")
            return
        if not ws.api_key:
            self.error.emit("TagWorker: 未填入 API Key")
            return
        try:
            client = openai.OpenAI(api_key=ws.api_key, base_url=ws.base_url)
            msgs = [
                {"role": "system", "content": TAG_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"用户问题：{self._user_msg[:500]}\n\n"
                        f"助手回答：{self._assistant_msg[:800]}"
                    ),
                },
            ]

            # 用非流式（标签极短，流式无益；reasoning 模型流式常返回空）
            resp = client.chat.completions.create(
                model=ws.model,
                messages=msgs,
                max_tokens=200,  # reasoning 模型需要额外 token 预算
                stream=False,
            )
            choice = resp.choices[0] if resp.choices else None
            if choice is None:
                self.finished.emit([])
                return

            text = (choice.message.content or "").strip()

            # 某些模型（如 deepseek-reasoner）content 为空但 reasoning_content 有值
            if not text:
                self.finished.emit([])
                return

            import re
            tags = [t.strip() for t in re.split(r"[，,]", text) if t.strip()]
            tags = tags[:5]
            self.finished.emit(tags)
        except Exception as e:
            self.error.emit(f"TagWorker: {e}")
