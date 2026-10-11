from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_service.application.correction_workflow import CorrectionWorkflowExecutor
from agent_service.application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
from agent_service.domain.enums import CorrectionIssueKind, RunType, ScopeType
from agent_service.domain.models.correction import (
    CorrectionConstraints,
    CorrectionContext,
    CorrectionEvidenceBundle,
    CorrectionFacts,
    FeedbackTarget,
)
from agent_service.domain.models.runs import AgentRun, RunOptions, RunScope
from agent_service.harness import InMemoryArtifactRepository
from agent_service.harness.stores import CancellationToken
from agent_service.infrastructure.correction_data import InMemoryCorrectionDataProvider
from agent_service.profiles import ProfileRegistry
from agent_service.profiles.package import build_package, verify_package
from agent_service.tools.extraction_runner import ScopedExtractionRunner

ROOT = Path(__file__).resolve().parents[4]


def registry() -> ProfileRegistry:
    value = ProfileRegistry(
        profile_root=ROOT / "services/agent/profiles", workspace_root=ROOT, allow_legacy_references=True
    )
    value.load_all()
    return value


def test_batch_merges_fields_and_reuses_persisted_items() -> None:
    async def execute() -> None:
        data = InMemoryCorrectionDataProvider()
        artifacts = InMemoryArtifactRepository()
        for key, field, answer in (("feedback-a", "end_terminal", "12"), ("feedback-b", "end_code", "FC2")):
            await data.register(
                CorrectionEvidenceBundle(
                    facts=CorrectionFacts(
                        feedback_id=key,
                        issue_kind=CorrectionIssueKind.DIRECT_VALUE_CHANGE,
                        suggested_value_present=True,
                        target=FeedbackTarget(
                            type=ScopeType.CONNECTION,
                            id="connection-1",
                            field=field,
                            project_id="project-1",
                            result_version_id="version-1",
                        ),
                    ),
                    context=CorrectionContext(
                        feedback_id=key,
                        field=field,
                        observed_problem="人工注错",
                        suggested_value=answer,
                        constraints=CorrectionConstraints(
                            allowed_connection_ids=["connection-1"], allowed_fields=[field]
                        ),
                    ),
                    profile=registry().bind("zh"),
                    base_result_version=1,
                    current_records=[
                        {"connection_id": "connection-1", "end_code": "FC1", "end_terminal": "11"}
                    ],
                    record_versions={"connection-1": 1},
                    evidence_ids=["source-1"],
                )
            )
        executor = CorrectionWorkflowExecutor(
            data=data,
            stages=ScopedExtractionRunner(ProfileBoundStageDispatcher()),
            model_name="fake",
            artifacts=artifacts,
        )
        run = AgentRun(
            idempotency_key="batch-1",
            run_type=RunType.SCOPED_CORRECTION,
            project_id="project-1",
            source_document_id="pdf-1",
            requested_by="user-1",
            feedback_id="feedback-a",
            expected_result_version=1,
            scope=RunScope(type=ScopeType.PROJECT, id="project-1"),
            options=RunOptions(correction_feedback_ids=["feedback-a", "feedback-b"]),
        )
        result = await executor.execute(run, CancellationToken())
        assert result.proposal is not None
        assert len(result.proposal.operations) == 1
        assert result.proposal.operations[0].after == {
            "connection_id": "connection-1",
            "end_code": "FC2",
            "end_terminal": "12",
        }
        repeated = await executor.execute(run, CancellationToken())
        assert repeated.proposal == result.proposal
        assert len(await artifacts.list_for_run(run.agent_run_id)) == 3

    asyncio.run(execute())


def test_profile_package_copies_external_assets_and_rejects_tampering(tmp_path: Path) -> None:
    snapshot = registry().resolve("zh")
    root = tmp_path / "package"
    manifest = build_package(snapshot, root)
    verify_package(root, manifest)
    assert (root / "resources/page_scan_prompt.md").is_file()
    assert (root / "resources/wiring_examples/images/002c11.png").is_file()
    assert any(entry.path.endswith("wiring_examples/manifest.json") for entry in manifest.files)
    (root / "resources/page_scan_prompt.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        verify_package(root, manifest)
