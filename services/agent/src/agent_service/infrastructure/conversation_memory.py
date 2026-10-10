from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from ..domain.models.profile_detection import ProfileAssignment, ProfileDetectionResult
from ..graphs.supervisor.graph import SupervisorGraphResult


@dataclass
class ConversationAttachment:
    attachment_id: str
    filename: str
    path: Path
    size: int


@dataclass
class ConversationMemory:
    conversation_id: str
    user_id: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    project_id: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    attachments: dict[str, ConversationAttachment] = field(default_factory=dict)
    current_attachment_ids: list[str] = field(default_factory=list)
    pending_detection: ProfileDetectionResult | None = None
    assignment: ProfileAssignment | None = None
    agent_run_id: str | None = None
    responses: OrderedDict[str, tuple[str, SupervisorGraphResult]] = field(default_factory=OrderedDict)


class ShortTermConversationStore:
    """Single-process bounded conversation memory; task checkpoints are separate."""

    def __init__(self, *, max_conversations: int = 256) -> None:
        self._maximum = max_conversations
        self._items: OrderedDict[str, ConversationMemory] = OrderedDict()

    def get(self, conversation_id: str, user_id: str) -> ConversationMemory:
        if not conversation_id.strip() or not user_id.strip():
            raise ValueError("conversation_id and user_id are required.")
        memory = self._items.get(conversation_id)
        if memory is not None and memory.user_id != user_id:
            raise PermissionError("Conversation belongs to a different user.")
        if memory is None:
            if len(self._items) >= self._maximum:
                removable = next((key for key, item in self._items.items() if not item.lock.locked()), None)
                if removable is None:
                    raise ValueError("Conversation capacity is busy; retry later.")
                del self._items[removable]
            memory = ConversationMemory(conversation_id=conversation_id, user_id=user_id)
            self._items[conversation_id] = memory
        self._items.move_to_end(conversation_id)
        return memory
