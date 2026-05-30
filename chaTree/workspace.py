"""工作区：索引、文件夹树、设置与会话聚合。"""

from __future__ import annotations

import json
import uuid
from typing import Optional

from .constants import DATA_DIR, INDEX_FILE, OLD_FILE
from .models import Conversation, Folder, Link
from .repository import JsonConversationRepository


class Workspace:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)
        self.api_key = ""
        self.base_url = "https://api.openai.com/v1"
        self.model = "gpt-4o-mini"
        self.folders: list[Folder] = []
        self._unfiled: list[str] = []
        self.conversations: dict[str, Conversation] = {}
        self._backlink_index: dict[tuple, list[Link]] = {}
        self._repo = JsonConversationRepository(DATA_DIR)
        self._migrate_old()
        self._load()
        self._rebuild_backlink_index()

    def _migrate_old(self):
        if not OLD_FILE.exists() or INDEX_FILE.exists():
            return
        try:
            d = json.loads(OLD_FILE.read_text(encoding="utf-8"))
            self.api_key = d.get("api_key", "")
            self.base_url = d.get("base_url", self.base_url)
            self.model = d.get("model", self.model)
            self.folders = [Folder.from_dict(fd) for fd in d.get("folders", [])]
            self._unfiled = d.get("unfiled", [])
            for cd in d.get("conversations", []):
                c = Conversation.from_dict(cd)
                self.conversations[c.id] = c
                self._repo.save(c)
            self._save_index()
            OLD_FILE.rename(OLD_FILE.with_suffix(".json.bak"))
            print("已从旧版 workspace.json 迁移数据。")
        except Exception as e:
            print("迁移失败:", e)

    def _load(self):
        if INDEX_FILE.exists():
            try:
                d = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
                self.api_key = d.get("api_key", "")
                self.base_url = d.get("base_url", self.base_url)
                self.model = d.get("model", self.model)
                self.folders = [Folder.from_dict(fd) for fd in d.get("folders", [])]
                self._unfiled = d.get("unfiled", [])
            except Exception as e:
                print("Index load error:", e)
        for conv in self._repo.load_all():
            self.conversations[conv.id] = conv

    def _save_index(self):
        INDEX_FILE.write_text(
            json.dumps(
                {
                    "api_key": self.api_key,
                    "base_url": self.base_url,
                    "model": self.model,
                    "folders": [f.to_dict() for f in self.folders],
                    "unfiled": self._unfiled,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def save_conversation(self, conv: Conversation):
        self._repo.save(conv)
        self._rebuild_backlink_index()

    def _rebuild_backlink_index(self):
        """从所有已加载对话重建反向链接索引。"""
        self._backlink_index = {}
        for conv in self.conversations.values():
            for link in conv.links:
                key = (link.target_conv_id, link.target_msg_id)
                self._backlink_index.setdefault(key, []).append(link)

    def get_backlinks(self, conv_id: str, msg_id: str = "") -> list[Link]:
        """返回所有指向 (conv_id, msg_id) 的链接。msg_id="" 表示对话级。"""
        return self._backlink_index.get((conv_id, msg_id), [])

    def get_outgoing_links(self, conv_id: str, msg_id: str) -> list[Link]:
        """返回某条消息发出的所有链接。"""
        conv = self.conversations.get(conv_id)
        if not conv:
            return []
        return [l for l in conv.links if l.source_msg_id == msg_id]

    def save_settings(self):
        self._save_index()

    def find_folder(
        self, fid: str, src: Optional[list] = None
    ) -> Optional[Folder]:
        if src is None:
            src = self.folders
        for f in src:
            if f.id == fid:
                return f
            found = self.find_folder(fid, f.subfolders)
            if found:
                return found
        return None

    def add_folder(self, name: str, parent_id: Optional[str] = None) -> Folder:
        fo = Folder(id=str(uuid.uuid4()), name=name)
        if parent_id:
            parent = self.find_folder(parent_id)
            if parent:
                parent.subfolders.append(fo)
        else:
            self.folders.append(fo)
        self._save_index()
        return fo

    def add_conversation(
        self, conv: Conversation, folder_id: Optional[str] = None
    ):
        self.conversations[conv.id] = conv
        if folder_id:
            fo = self.find_folder(folder_id)
            if fo:
                fo.conv_ids.append(conv.id)
        else:
            self._unfiled.append(conv.id)
        self._repo.save(conv)
        self._save_index()

    def delete_conversation(self, cid: str):
        self.conversations.pop(cid, None)
        self._repo.delete(cid)
        if cid in self._unfiled:
            self._unfiled.remove(cid)
        self._rm_from_folders(cid, self.folders)
        self._save_index()

    def _rm_from_folders(self, cid: str, folders: list):
        for fo in folders:
            if cid in fo.conv_ids:
                fo.conv_ids.remove(cid)
            self._rm_from_folders(cid, fo.subfolders)

    def move_conversation(self, cid: str, new_folder_id: Optional[str]) -> bool:
        """将对话从当前位置移动到 new_folder_id（None = 根目录）。"""
        if cid not in self.conversations:
            return False
        if cid in self._unfiled:
            self._unfiled.remove(cid)
        self._rm_from_folders(cid, self.folders)
        if new_folder_id:
            fo = self.find_folder(new_folder_id)
            if fo and cid not in fo.conv_ids:
                fo.conv_ids.append(cid)
        else:
            if cid not in self._unfiled:
                self._unfiled.append(cid)
        self._save_index()
        return True

    def search(self, keyword: str) -> list[tuple[Conversation, object, str]]:
        """搜索对话标题、标签、消息内容和消息标签。
        返回 [(Conversation, MessageNode|None, match_info), ...]
        MessageNode 为 None 表示对话级匹配。
        """
        kw = keyword.lower()
        results: list[tuple[Conversation, object, str]] = []
        for conv in self.conversations.values():
            # 匹配对话标题
            if kw in conv.title.lower():
                results.append((conv, None, f"标题：{conv.title}"))
            # 匹配对话标签
            for tag in conv.tags:
                if kw in tag.lower():
                    results.append((conv, None, f"标签「{tag}」"))
                    break
            # 匹配消息内容和标签
            for msg in conv.messages:
                if kw in msg.content.lower():
                    preview = msg.content[:80].replace("\n", " ")
                    if len(msg.content) > 80:
                        preview += "…"
                    results.append((conv, msg, preview))
                    continue  # 同一条消息不重复
                for tag in msg.tags:
                    if kw in tag.lower():
                        results.append((conv, msg, f"标签「{tag}」"))
                        break
        return results


ws = Workspace()
