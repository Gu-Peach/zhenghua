from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from src.harness.model_gateway import ModelGateway

from .graph import EventSink, build_explain_graph
from .models import ConnectionQuery, ExplainActor, ExplainError, ExplainEvent, ExplainResponse, ExplainTurn
from .repository import ExplanationRepository


@dataclass
class _Session:
    target: tuple[str, str]
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    fingerprint: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    responses: OrderedDict[str, tuple[str, str, str, list[ConnectionQuery], list[int], bool, list[str]]] = (
        field(default_factory=OrderedDict)
    )
    queries: list[ConnectionQuery] = field(default_factory=list)
    visual_pages: list[int] = field(default_factory=list)


class ExplainAgent:
    """Bounded process-local conversation; each turn rechecks the authorized database facts."""

    def __init__(
        self,
        repository: ExplanationRepository,
        gateway: ModelGateway,
        *,
        max_sessions: int = 128,
        max_tokens: int = 2000,
    ) -> None:
        if max_sessions < 1 or max_tokens < 1:
            raise ValueError("Session/token limits must be positive")
        self.repository, self.gateway = repository, gateway
        self.max_sessions, self.max_tokens = max_sessions, max_tokens
        self._sessions: OrderedDict[tuple[str, str], _Session] = OrderedDict()

    async def ask(
        self, turn: ExplainTurn, actor: ExplainActor, *, on_event: EventSink | None = None
    ) -> ExplainResponse:
        key = (str(actor.user_id), str(turn.conversation_id))
        assert turn.connection_id is not None or turn.query is not None
        selection = (
            str(turn.connection_id)
            if turn.connection_id
            else (turn.query.model_dump_json() if turn.query else "")
        )
        target = (str(turn.project_id), selection)
        session = self._sessions.get(key)
        if session is None:
            if len(self._sessions) >= self.max_sessions:
                removable = next((k for k, v in self._sessions.items() if not v.lock.locked()), None)
                if removable is None:
                    raise ExplainError("AGENT_BUSY", "解释会话繁忙，请稍后重试。", 429)
                del self._sessions[removable]
            session = _Session(target)
            self._sessions[key] = session
        if session.target != target:
            raise ExplainError("CONVERSATION_TARGET_CONFLICT", "更换初始行或查询条件时请创建新的会话。", 409)
        if session.lock.locked():
            raise ExplainError("CONVERSATION_BUSY", "该会话仍在回复，请等待或取消后重试。", 409)
        self._sessions.move_to_end(key)
        digest = hashlib.sha256(turn.model_dump_json().encode()).hexdigest()
        cached = session.responses.get(str(turn.turn_id))
        if cached and cached[0] != digest:
            raise ExplainError("TURN_CONFLICT", "同一turn_id不能用于不同的问题或版本。", 409)
        async with session.lock:
            state: dict[str, Any] = {
                "turn": turn,
                "actor": actor,
                "history": list(session.history),
                "previous_fingerprint": session.fingerprint,
                "cached_answer": cached[1] if cached else None,
                "cached_fingerprint": cached[2] if cached else None,
                "saved_queries": cached[3] if cached else session.queries,
                "saved_visual_pages": cached[4] if cached else session.visual_pages,
                "cached_limited": cached[5] if cached else False,
                "cached_proposals": cached[6] if cached else [],
            }
            result_state = await build_explain_graph(
                self.repository,
                self.gateway,
                on_event=on_event,
                max_tokens=self.max_tokens,
            ).ainvoke(state, config={"recursion_limit": 32})
            result = ExplainResponse.model_validate(result_state["result"])
            if not result.cached or result.history_reset:
                history = [] if result.history_reset else session.history
                session.history = [
                    *history,
                    {"role": "user", "content": turn.message},
                    {"role": "assistant", "content": result.answer},
                ][-24:]
                while (
                    len(session.history) > 2 and sum(len(item["content"]) for item in session.history) > 24000
                ):
                    session.history = session.history[2:]
            session.fingerprint = result_state["fingerprint"]
            session.queries = [item.query for item in result.retrievals][-8:]
            session.visual_pages = result.visual_pages
            session.responses[str(turn.turn_id)] = (
                digest,
                result.answer,
                session.fingerprint,
                session.queries,
                session.visual_pages,
                result.retrieval_limited,
                [str(p.proposal_id) for p in result.proposals],
            )
            while len(session.responses) > 12:
                session.responses.popitem(last=False)
            if on_event:
                await on_event(
                    ExplainEvent(
                        type="completed",
                        conversation_id=turn.conversation_id,
                        turn_id=turn.turn_id,
                        result=result,
                    )
                )
            return result
