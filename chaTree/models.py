"""领域模型：对话、消息、文件夹、注释。"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field


@dataclass
class Annotation:
    id: str
    quoted_text: str
    user_question: str
    ai_answer: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "quoted_text": self.quoted_text,
            "user_question": self.user_question,
            "ai_answer": self.ai_answer,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Annotation:
        return cls(**d)


@dataclass
class MessageNode:
    id: str
    role: str  # "user" | "assistant"
    content: str
    annotations: list = field(default_factory=list)  # list[Annotation]
    tags: list = field(default_factory=list)  # list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "annotations": [a.to_dict() for a in self.annotations],
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MessageNode:
        anns = [Annotation.from_dict(a) for a in d.get("annotations", [])]
        return cls(
            id=d["id"],
            role=d["role"],
            content=d["content"],
            annotations=anns,
            tags=d.get("tags", []),
        )


@dataclass
class Link:
    """跨对话/跨消息的双向链接。"""
    id: str
    source_msg_id: str       # 发起链接的消息 ID
    target_conv_id: str      # 目标对话 ID
    target_msg_id: str = ""  # 空字符串 = 链接目标是整个对话
    selected_text: str = ""  # 右键文本链接时的选中文字
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_msg_id": self.source_msg_id,
            "target_conv_id": self.target_conv_id,
            "target_msg_id": self.target_msg_id,
            "selected_text": self.selected_text,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Link:
        return cls(
            id=d["id"],
            source_msg_id=d["source_msg_id"],
            target_conv_id=d["target_conv_id"],
            target_msg_id=d.get("target_msg_id", ""),
            selected_text=d.get("selected_text", ""),
            created_at=d.get("created_at", ""),
        )


@dataclass
class Conversation:
    id: str
    title: str
    messages: list = field(default_factory=list)
    links: list = field(default_factory=list)  # list[Link]
    tags: list = field(default_factory=list)  # list[str]
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "messages": [m.to_dict() for m in self.messages],
            "links": [l.to_dict() for l in self.links],
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Conversation:
        msgs = [MessageNode.from_dict(m) for m in d.get("messages", [])]
        lnks = [Link.from_dict(ld) for ld in d.get("links", [])]
        return cls(
            id=d["id"],
            title=d["title"],
            created_at=d.get("created_at", ""),
            messages=msgs,
            links=lnks,
            tags=d.get("tags", []),
        )


@dataclass
class Folder:
    id: str
    name: str
    conv_ids: list = field(default_factory=list)
    subfolders: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "conv_ids": self.conv_ids,
            "subfolders": [sf.to_dict() for sf in self.subfolders],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Folder:
        fo = cls(id=d["id"], name=d["name"], conv_ids=d.get("conv_ids", []))
        fo.subfolders = [Folder.from_dict(sd) for sd in d.get("subfolders", [])]
        return fo
