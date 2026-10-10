from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..domain.enums import EventType
from ..domain.models.runs import AgentEvent
from ..domain.models.supervisor import SupervisorUserEvent


class SupervisorEventPresenter:
    """Convert durable run events to stable user-facing conversation events."""

    def present(
        self,
        event: AgentEvent,
        *,
        conversation_id: str,
        turn_id: str | None = None,
        artifact_payloads: Sequence[Mapping[str, Any]] = (),
    ) -> SupervisorUserEvent:
        public_artifacts = self._public_artifacts(artifact_payloads)
        message = self._message(event, public_artifacts)
        payload: dict[str, Any] = {
            "seq": event.seq,
            "metrics": dict(event.metrics),
            "artifact_refs": list(event.artifact_refs),
            "error": event.error.model_dump(mode="json") if event.error else None,
        }
        if public_artifacts:
            payload["artifacts"] = public_artifacts
        return SupervisorUserEvent(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_run_id=event.agent_run_id,
            event_type=event.event_type.value,
            stage=event.stage.value if event.stage else None,
            user_message=message,
            requires_input=event.event_type
            in {EventType.HUMAN_INPUT_REQUIRED, EventType.PROFILE_REVIEW_REQUIRED},
            payload=payload,
            occurred_at=event.occurred_at,
        )

    @staticmethod
    def _message(event: AgentEvent, public_artifacts: Sequence[Mapping[str, Any]]) -> str:
        diagnosis = next(
            (item for item in public_artifacts if item.get("kind") == "improvement_diagnosis"),
            None,
        )
        if event.event_type == EventType.HUMAN_INPUT_REQUIRED and diagnosis is not None:
            diagnoses = diagnosis.get("diagnoses")
            first = diagnoses[0] if isinstance(diagnoses, list) and diagnoses else None
            if isinstance(first, Mapping):
                explanation = str(first.get("explanation") or "已完成问题归因。")
                recommendation = str(first.get("recommended_action") or "请人工复核诊断结果。")
                if diagnosis.get("candidate_recommended") is True:
                    return (
                        f"改进诊断完成：{explanation} 建议：{recommendation} "
                        "请确认是否授权创建 Profile 规则候选；候选不会自动发布。"
                    )
                return f"改进诊断完成：{explanation} 建议：{recommendation}"

        candidate = next(
            (item for item in public_artifacts if item.get("kind") == "profile_candidate"),
            None,
        )
        if event.event_type == EventType.HUMAN_INPUT_REQUIRED and candidate is not None:
            return "Profile 规则候选已生成，等待离线评测和人工审核；当前生产 Profile 未被修改。"

        stage = event.stage.value if event.stage else "任务"
        processed = event.metrics.get("processed")
        total = event.metrics.get("total")
        progress = f"（{processed}/{total}）" if processed is not None and total is not None else ""
        mapping = {
            EventType.RUN_CREATED: "任务已创建，等待执行。",
            EventType.RUN_STARTED: "任务已开始执行。",
            EventType.PROFILE_DETECTED: "图纸 Profile 已识别。",
            EventType.PROFILE_REVIEW_REQUIRED: "图纸类型需要人工确认。",
            EventType.STAGE_STARTED: f"{stage} 阶段已开始。",
            EventType.ITEM_COMPLETED: f"{stage} 已完成一个处理项{progress}。",
            EventType.STAGE_COMPLETED: f"{stage} 阶段已完成{progress}。",
            EventType.PROPOSAL_CREATED: "候选结果已生成，等待业务校验或人工复核。",
            EventType.HUMAN_INPUT_REQUIRED: "任务需要补充信息或人工确认后才能继续。",
            EventType.RUN_FAILED: "任务执行失败，旧结果未被修改。",
            EventType.RUN_CANCELLED: "任务已取消。",
            EventType.RUN_COMPLETED: "任务已完成。",
        }
        base = mapping[event.event_type]
        if event.event_type == EventType.RUN_FAILED and event.error:
            return f"{base} 错误码：{event.error.code}。"
        return base

    @staticmethod
    def _public_artifacts(
        artifact_payloads: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        public: list[dict[str, Any]] = []
        for artifact in artifact_payloads:
            kind = artifact.get("kind")
            if kind == "improvement_diagnosis":
                diagnoses = artifact.get("diagnoses")
                safe_diagnoses: list[dict[str, Any]] = []
                if isinstance(diagnoses, list):
                    for item in diagnoses:
                        if not isinstance(item, Mapping):
                            continue
                        safe_diagnoses.append(
                            {
                                "category": item.get("category"),
                                "confidence": item.get("confidence"),
                                "explanation": item.get("explanation"),
                                "recommended_action": item.get("recommended_action"),
                                "profile_candidate_required": item.get("profile_candidate_required", False),
                            }
                        )
                public.append(
                    {
                        "kind": kind,
                        "candidate_recommended": artifact.get("candidate_recommended", False),
                        "authorization_required": artifact.get("authorization_required", False),
                        "reason": artifact.get("reason"),
                        "diagnoses": safe_diagnoses,
                    }
                )
            elif kind == "profile_candidate":
                candidate = artifact.get("candidate")
                candidate_id = candidate.get("candidate_id") if isinstance(candidate, Mapping) else None
                summary = candidate.get("summary") if isinstance(candidate, Mapping) else None
                public.append(
                    {
                        "kind": kind,
                        "candidate_id": candidate_id,
                        "summary": summary,
                        "reason": artifact.get("reason"),
                        "status": "awaiting_evaluation_and_review",
                    }
                )
        return public
