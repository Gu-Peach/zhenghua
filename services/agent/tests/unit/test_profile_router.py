from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent_service.agents.profile_router import ProfileRouterAgent
from agent_service.application.profile_assignment import ProfileAssignmentService
from agent_service.domain.enums import ProfileDetectionStatus
from agent_service.harness import FakeModelGateway
from agent_service.profiles import ProfileRegistry
from agent_service.tools.pdf_first_page import FirstPageImage

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROFILE_ROOT = REPOSITORY_ROOT / "services" / "agent" / "profiles"
ROUTER_PROMPT = REPOSITORY_ROOT / "services" / "agent" / "prompts" / "profile_router.md"


def registry() -> ProfileRegistry:
    value = ProfileRegistry(
        profile_root=PROFILE_ROOT,
        workspace_root=REPOSITORY_ROOT,
        allow_legacy_references=True,
    )
    value.load_all()
    return value


def first_page() -> FirstPageImage:
    return FirstPageImage(
        content=b"first-page-image",
        mime_type="image/png",
        width=1200,
        height=800,
        checksum="sha256:" + "a" * 64,
    )


def model_output(
    *,
    recognized: bool,
    selected: str | None,
    confidence: float,
) -> str:
    return json.dumps(
        {
            "recognized": recognized,
            "selected_profile_key": selected,
            "confidence": confidence,
            "candidates": [
                {
                    "profile_key": selected or "zh",
                    "score": confidence,
                    "matched_signals": ["visible logo"],
                }
            ],
            "observed_signals": ["visible logo"],
            "reason": "首页标题栏存在明确公司标识",
        },
        ensure_ascii=False,
    )


def test_active_zh_is_selected_and_bound_automatically() -> None:
    async def run() -> None:
        profile_registry = registry()
        gateway = FakeModelGateway([model_output(recognized=True, selected="zh", confidence=0.98)])
        router = ProfileRouterAgent(
            gateway=gateway,
            registry=profile_registry,
            prompt_path=ROUTER_PROMPT,
        )
        result = await router.detect(
            first_page=first_page(),
            run_id="run-1",
            project_id="project-1",
        )
        assert result.status == ProfileDetectionStatus.PROFILE_SELECTED
        assert result.assigned_profile is not None
        assert result.assigned_profile.key == "zh"
        assignment = ProfileAssignmentService(profile_registry).from_automatic_detection(result)
        assert assignment.binding.profile.key == "zh"
        assert assignment.binding.rules.extraction.output_contract == "wiring_connection_v1"
        assert "page_scan_prompt" in assignment.binding.resolved_resources
        assert gateway.calls[0].metadata["pdf_page_number"] == 1
        assert gateway.calls[0].metadata["candidate_profiles"] == ["abb", "zh"]

    asyncio.run(run())


def test_experimental_abb_waits_for_user_then_binds_confirmed_profile() -> None:
    async def run() -> None:
        profile_registry = registry()
        router = ProfileRouterAgent(
            gateway=FakeModelGateway([model_output(recognized=True, selected="abb", confidence=0.99)]),
            registry=profile_registry,
            prompt_path=ROUTER_PROMPT,
        )
        result = await router.detect(
            first_page=first_page(),
            run_id="run-2",
            project_id="project-2",
        )
        assert result.status == ProfileDetectionStatus.WAITING_INPUT
        assert result.detected_profile is not None
        assert result.detected_profile.key == "abb"
        assert result.assigned_profile is None
        assert result.user_question is not None

        assignment = ProfileAssignmentService(profile_registry).confirm(
            result,
            profile_key="abb",
            confirmed_by="user-1",
        )
        assert assignment.source == "user_confirmation"
        assert assignment.binding.profile.key == "abb"
        assert assignment.confirmed_by == "user-1"

    asyncio.run(run())


def test_unknown_profile_requests_user_selection() -> None:
    async def run() -> None:
        router = ProfileRouterAgent(
            gateway=FakeModelGateway([model_output(recognized=False, selected=None, confidence=0.2)]),
            registry=registry(),
            prompt_path=ROUTER_PROMPT,
        )
        result = await router.detect(
            first_page=first_page(),
            run_id="run-3",
            project_id="project-3",
        )
        assert result.status == ProfileDetectionStatus.WAITING_INPUT
        assert result.detected_profile is None
        assert result.needs_user_confirmation is True
        assert "zh" in (result.user_question or "")
        assert "abb" in (result.user_question or "")

    asyncio.run(run())


def test_unregistered_model_selection_cannot_be_assigned() -> None:
    async def run() -> None:
        router = ProfileRouterAgent(
            gateway=FakeModelGateway([model_output(recognized=True, selected="other", confidence=0.99)]),
            registry=registry(),
            prompt_path=ROUTER_PROMPT,
        )
        result = await router.detect(
            first_page=first_page(),
            run_id="run-4",
            project_id="project-4",
        )
        assert result.status == ProfileDetectionStatus.WAITING_INPUT
        assert result.assigned_profile is None
        assert "未注册" in result.reason

    asyncio.run(run())
