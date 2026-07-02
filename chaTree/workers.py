"""后台线程：主对话流式输出与注释生成。"""

from PySide6.QtCore import QThread, Signal

from .constants import HAS_OPENAI
from .prompts import (
    ANNOTATION_MAX_CHARS,
    ANNOTATION_MAX_TOKENS,
    ANNOTATION_SYSTEM_PROMPT,
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
            print(f"[TagWorker] 模型: {ws.model}  base_url: {ws.base_url}")
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
                print("[TagWorker] API 返回空 choices")
                self.finished.emit([])
                return

            text = (choice.message.content or "").strip()
            print(f"[TagWorker] API 返回: {text!r}")

            # 某些模型（如 deepseek-reasoner）content 为空但 reasoning_content 有值
            if not text:
                reasoning = getattr(choice.message, "reasoning_content", None)
                if reasoning:
                    print(f"[TagWorker] reasoning_content: {reasoning!r}")
                finish = getattr(choice, "finish_reason", "?")
                print(f"[TagWorker] finish_reason={finish}, 无 content")
                self.finished.emit([])
                return

            import re
            tags = [t.strip() for t in re.split(r"[，,]", text) if t.strip()]
            tags = tags[:5]
            if tags:
                print(f"[TagWorker] 生成标签: {tags}")
            else:
                print("[TagWorker] 未能解析出任何标签")
            self.finished.emit(tags)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"TagWorker: {e}")
