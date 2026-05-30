"""后台线程：主对话流式输出与注释生成。"""

from PySide6.QtCore import QThread, Signal

from .constants import HAS_OPENAI
from .prompts import (
    ANNOTATION_MAX_CHARS,
    ANNOTATION_MAX_TOKENS,
    ANNOTATION_SYSTEM_PROMPT,
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
            # 直接用 user message，避免某些模型忽略 system prompt 返回空
            content = (
                f"根据以下对话，生成3-5个简短的标签（每个1-3词），只输出逗号分隔的标签：\n\n"
                f"用户：{self._user_msg[:500]}\n\n"
                f"助手：{self._assistant_msg[:800]}"
            )
            msgs = [{"role": "user", "content": content}]
            full = ""
            with client.chat.completions.create(
                model=ws.model,
                messages=msgs,
                max_tokens=80,
                stream=True,
            ) as stream:
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    full += delta
            text = full.strip()
            print(f"[TagWorker] API 返回: {text!r}")
            # 同时支持中英文逗号分隔
            import re
            tags = [t.strip() for t in re.split(r"[，,]", text) if t.strip()]
            tags = tags[:5]
            if tags:
                print(f"[TagWorker] 生成标签: {tags}")
            self.finished.emit(tags)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"TagWorker: {e}")
