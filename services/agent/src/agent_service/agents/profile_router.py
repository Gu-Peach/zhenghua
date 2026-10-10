from __future__ import annotations

import base64
import json
from pathlib import Path

from ..domain.enums import ProfileDetectionStatus, ProfileStatus
from ..domain.models.profile_detection import (
    FirstPageEvidence,
    ProfileCandidateScore,
    ProfileDetectionResult,
    ProfileRouterModelOutput,
)
from ..domain.models.profiles import ProfileBinding
from ..harness.model_gateway import ModelGateway, ModelRequest
from ..profiles import ProfileRegistry
from ..tools.pdf_first_page import FirstPageImage


class ProfileRouterAgent:
    def __init__(
        self,
        *,
        gateway: ModelGateway,
        registry: ProfileRegistry,
        prompt_path: Path,
        auto_select_threshold: float = 0.85,
    ) -> None:
        if not 0.0 <= auto_select_threshold <= 1.0:
            raise ValueError("auto_select_threshold must be between 0 and 1.")
        self._gateway = gateway
        self._registry = registry
        self._prompt = prompt_path.read_text(encoding="utf-8")
        self._auto_select_threshold = auto_select_threshold

    async def detect(
        self,
        *,
        first_page: FirstPageImage,
        run_id: str,
        project_id: str,
    ) -> ProfileDetectionResult:
        bindings = self._candidate_bindings()
        rules_payload = [
            {
                "profile_key": binding.profile.key,
                "profile_version": binding.profile.version,
                "status": binding.status.value,
                "display_name": binding.rules.display_name,
                "detection": binding.rules.detection.model_dump(mode="json"),
            }
            for binding in bindings.values()
        ]
        image_data = base64.b64encode(first_page.content).decode("ascii")
        response = await self._gateway.invoke(
            ModelRequest(
                agent_name="profile_router",
                run_id=run_id,
                output_model=ProfileRouterModelOutput,
                messages=[
                    {"role": "system", "content": self._prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "候选 Profile 规则：\n"
                                + json.dumps(rules_payload, ensure_ascii=False, indent=2),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{first_page.mime_type};base64,{image_data}"},
                            },
                        ],
                    },
                ],
                metadata={
                    "project_id": project_id,
                    "pdf_page_number": 1,
                    "candidate_profiles": sorted(bindings),
                },
            )
        )
        if not isinstance(response.parsed, ProfileRouterModelOutput):
            raise TypeError("Profile router returned an unexpected structured result.")
        return self._finalize(
            model_output=response.parsed,
            bindings=bindings,
            first_page=first_page,
            run_id=run_id,
            project_id=project_id,
        )

    def _candidate_bindings(self) -> dict[str, ProfileBinding]:
        bindings: dict[str, ProfileBinding] = {}
        for snapshot in self._registry.list_profiles():
            if snapshot.manifest.status == ProfileStatus.RETIRED:
                continue
            binding = self._registry.bind(
                snapshot.manifest.key,
                snapshot.manifest.version,
                allow_experimental=True,
            )
            bindings[binding.profile.key] = binding
        if not bindings:
            raise RuntimeError("Profile Router has no candidate profiles.")
        return bindings

    def _finalize(
        self,
        *,
        model_output: ProfileRouterModelOutput,
        bindings: dict[str, ProfileBinding],
        first_page: FirstPageImage,
        run_id: str,
        project_id: str,
    ) -> ProfileDetectionResult:
        evidence = FirstPageEvidence(
            image_checksum=first_page.checksum,
            width=first_page.width,
            height=first_page.height,
            mime_type=first_page.mime_type,
        )
        candidates = self._normalized_candidates(model_output.candidates, bindings)
        selected = bindings.get(model_output.selected_profile_key or "")
        recognized = model_output.recognized and selected is not None
        can_auto_select = (
            recognized
            and selected is not None
            and model_output.confidence >= self._auto_select_threshold
            and selected.status == ProfileStatus.ACTIVE
        )
        if can_auto_select and selected is not None:
            return ProfileDetectionResult(
                run_id=run_id,
                project_id=project_id,
                status=ProfileDetectionStatus.PROFILE_SELECTED,
                detected_profile=selected.profile,
                assigned_profile=selected.profile,
                confidence=model_output.confidence,
                candidates=candidates,
                observed_signals=model_output.observed_signals,
                reason=model_output.reason,
                evidence=evidence,
                needs_user_confirmation=False,
            )

        detected_profile = selected.profile if recognized and selected is not None else None
        if recognized and selected is not None and selected.status == ProfileStatus.EXPERIMENTAL:
            reason = f"{model_output.reason}；该 Profile 尚处于 experimental，需用户确认。"
        elif recognized and model_output.confidence < self._auto_select_threshold:
            reason = f"{model_output.reason}；识别置信度低于自动分配阈值。"
        elif model_output.selected_profile_key and selected is None:
            reason = "模型返回了未注册的 Profile，不能自动分配。"
        else:
            reason = model_output.reason
        options = "、".join(
            f"{binding.rules.display_name}（{key}）" for key, binding in sorted(bindings.items())
        )
        return ProfileDetectionResult(
            run_id=run_id,
            project_id=project_id,
            status=ProfileDetectionStatus.WAITING_INPUT,
            detected_profile=detected_profile,
            assigned_profile=None,
            confidence=model_output.confidence,
            candidates=candidates,
            observed_signals=model_output.observed_signals,
            reason=reason,
            evidence=evidence,
            needs_user_confirmation=True,
            user_question=f"无法自动确认图纸类型，请选择：{options}。",
        )

    @staticmethod
    def _normalized_candidates(
        candidates: list[ProfileCandidateScore],
        bindings: dict[str, ProfileBinding],
    ) -> list[ProfileCandidateScore]:
        by_key: dict[str, ProfileCandidateScore] = {}
        for candidate in candidates:
            if candidate.profile_key in bindings:
                existing = by_key.get(candidate.profile_key)
                if existing is None or candidate.score > existing.score:
                    by_key[candidate.profile_key] = candidate
        return sorted(by_key.values(), key=lambda item: (-item.score, item.profile_key))
