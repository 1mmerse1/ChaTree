"""对话持久化：抽象接口与 JSON 实现。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .models import Conversation


class ConversationRepository(ABC):
    @abstractmethod
    def save(self, conv: Conversation) -> None: ...

    @abstractmethod
    def load(self, conv_id: str) -> Optional[Conversation]: ...

    @abstractmethod
    def delete(self, conv_id: str) -> None: ...

    @abstractmethod
    def load_all(self) -> list: ...


class JsonConversationRepository(ConversationRepository):
    def __init__(self, base_dir: Path):
        self._dir = base_dir / "conversations"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, conv_id: str) -> Path:
        return self._dir / f"{conv_id}.json"

    def save(self, conv: Conversation) -> None:
        self._path(conv.id).write_text(
            json.dumps(conv.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, conv_id: str) -> Optional[Conversation]:
        p = self._path(conv_id)
        if p.exists():
            try:
                return Conversation.from_dict(
                    json.loads(p.read_text(encoding="utf-8"))
                )
            except Exception as e:
                print(f"Load {conv_id} error:", e)
        return None

    def delete(self, conv_id: str) -> None:
        p = self._path(conv_id)
        if p.exists():
            p.unlink()

    def load_all(self) -> list:
        result = []
        for p in sorted(self._dir.glob("*.json")):
            try:
                result.append(
                    Conversation.from_dict(
                        json.loads(p.read_text(encoding="utf-8"))
                    )
                )
            except Exception as e:
                print(f"Skip {p.name}:", e)
        return result
