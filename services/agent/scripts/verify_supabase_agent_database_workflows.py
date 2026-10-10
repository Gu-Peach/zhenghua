from __future__ import annotations

import asyncio
import base64
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import httpx

from agent_service.domain.enums import (
    AgentStage,
    CorrectionIssueKind,
    EvalCaseKind,
    ProfileCandidateStatus,
    ProfileCandidateType,
    RootCauseCategory,
    RunType,
    ScopeType,
)
from agent_service.domain.models.improvement import (
    AffectedScope,
    CandidatePatchOperation,
    Diagnosis,
    EvalCaseResult,
    EvalMetrics,
    EvalReport,
    ProfileCandidate,
    ReleaseDecision,
)
from agent_service.domain.models.proposals import (
    ProposalOperation,
    ProposalValidation,
    ResultPatchProposal,
    ResultProposal,
)
from agent_service.domain.models.result_data import ConnectionSearchQuery, PrepareCorrectionRequest
from agent_service.domain.models.runs import CreateRunRequest, ModelRef, RunScope
from agent_service.infrastructure.correction_data import SupabaseCorrectionDataRepository
from agent_service.infrastructure.project_assets import SupabaseProjectAssetStore
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.infrastructure.supabase_improvement import (
    SupabaseCandidateRepository,
    SupabaseEvalRepository,
)
from agent_service.infrastructure.supabase_repositories import (
    SupabaseProposalRepository,
    SupabaseRunRepository,
    SupabaseTraceStore,
)
from agent_service.infrastructure.supabase_result_data import SupabaseResultDataRepository
from agent_service.profiles import ProfileRegistry
from agent_service.tools.result_data import ControlledResultDataTool

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


async def main() -> int:
    base_url = os.environ.get("AGENT_SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("AGENT_SUPABASE_SERVICE_ROLE_KEY", "")
    anon_key = os.environ.get("AGENT_SUPABASE_ANON_KEY", "")
    bucket = os.environ.get("AGENT_SUPABASE_STORAGE_BUCKET", "project-assets")
    if not base_url or not service_key:
        raise RuntimeError("Agent Supabase URL and service-role key are required.")
    if bucket != "project-assets":
        raise RuntimeError("Database workflow verification requires the private project-assets bucket.")

    client = SupabaseClient(base_url=base_url, service_role_key=service_key)
    project_id = str(uuid4())
    document_id = str(uuid4())
    candidate_id = str(uuid4())
    user_id: str | None = None
    uploaded_paths: list[str] = []
    email = f"agent-db-{uuid4().hex}@example.invalid"
    password = f"Agent-{uuid4().hex}!"
    async with httpx.AsyncClient(timeout=30.0) as http:
        response = await http.post(
            f"{base_url}/auth/v1/admin/users",
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            json={"email": email, "password": password, "email_confirm": True},
        )
        response.raise_for_status()
        user_id = str(response.json()["id"])

    try:
        await client.insert(
            "projects",
            {
                "id": project_id,
                "owner_id": user_id,
                "name": "Agent database workflow smoke test",
                "standard_profile": "zh",
                "status": "processing",
            },
        )
        assets = SupabaseProjectAssetStore(client, bucket=bucket)
        registry = ProfileRegistry(
            profile_root=WORKSPACE_ROOT / "services" / "agent" / "profiles",
            workspace_root=WORKSPACE_ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        profile = registry.bind("zh")
        runs = SupabaseRunRepository(client)
        proposals = SupabaseProposalRepository(client)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            correction_data = SupabaseCorrectionDataRepository(
                client,
                cache_root=root / "correction-cache",
            )
            pdf = root / "source.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
            await assets.upload_source_pdf(
                project_id=project_id,
                document_id=document_id,
                original_filename="source.pdf",
                pdf_path=pdf,
            )
            uploaded_paths.append(f"projects/{project_id}/original.pdf")
            output = root / "output"
            image = output / "pages" / "002.C" / "1.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_1X1)
            index = output / "agent" / "drawing_index.json"
            index.parent.mkdir(parents=True)
            index.write_text(
                '{"pages":[{"pdf_page":1,"function":"002.C","internal_page":1}]}',
                encoding="utf-8",
            )

            extraction_run = await runs.create(
                CreateRunRequest(
                    run_type=RunType.FULL_EXTRACTION,
                    project_id=project_id,
                    source_document_id=document_id,
                    requested_by=user_id,
                    profile_hint="zh",
                    expected_result_version=0,
                    scope=RunScope(type=ScopeType.PROJECT, id=project_id),
                ),
                f"db-smoke-extract-{uuid4()}",
            )
            published = await assets.publish_extraction_pages(extraction_run, output)
            uploaded_paths.extend(published.object_paths)
            result_data = SupabaseResultDataRepository(
                client,
                profiles=registry,
                drawing_cache_root=root / "drawing-cache",
            )
            extraction_proposal = ResultProposal(
                proposal_id=f"{extraction_run.agent_run_id}:result-proposal",
                agent_run_id=extraction_run.agent_run_id,
                project_id=project_id,
                base_result_version=0,
                profile=profile.profile,
                model=ModelRef(name="smoke-model"),
                scope=RunScope(type=ScopeType.PROJECT, id=project_id),
                operations=[
                    ProposalOperation(
                        op="add",
                        target_type="CONNECTION",
                        target_id="source-connection-1",
                        after={
                            "unit_id": "unit-X21",
                            "drawing_function": "002.C",
                            "pdf_page_number": 1,
                            "source_pages": [1],
                            "terminal_strip": "X21",
                            "voltage_level": "690V",
                            "line_number": "002C0101",
                            "start_device": "-XD21",
                            "start_name": "起点设备",
                            "start_terminal": "7",
                            "end_device": "-M1",
                            "end_name": "电机",
                            "end_terminal": "U1",
                            "current": "400A",
                            "color": "BK",
                            "remark": "smoke",
                            "is_cross_page": "same_page",
                            "confidence": 0.98,
                        },
                        evidence_ids=["source-page-1"],
                        reason="smoke extraction",
                        confidence=0.98,
                    )
                ],
                validation=ProposalValidation(schema_valid=True, business_rules_valid=True),
            )
            await proposals.submit(extraction_proposal)
            committed = await result_data.persist_extraction_proposal(extraction_proposal, user_id)
            repeated = await result_data.persist_extraction_proposal(extraction_proposal, user_id)
            assert repeated.result_version_id == committed.result_version_id
            assert committed.result_version == 1

            matches = await result_data.search_connections(
                ConnectionSearchQuery(project_id=project_id, terminal="7")
            )
            assert len(matches) == 1
            match = matches[0]
            assert match.wire_number == "1000"
            assert match.terminal_strip == "X21"

            tool = ControlledResultDataTool(repository=result_data, correction_data=correction_data)
            prepared = await tool.prepare_correction(
                PrepareCorrectionRequest(
                    query=ConnectionSearchQuery(connection_id=match.connection_id),
                    requested_by=user_id,
                    field="end_terminal",
                    observed_problem="终点端子错误",
                    suggested_value_present=True,
                    suggested_value="U2",
                    issue_kind=CorrectionIssueKind.DIRECT_VALUE_CHANGE,
                )
            )
            persisted_bundle = await correction_data.get_bundle(prepared.feedback_id)
            assert persisted_bundle.facts.target.id == match.connection_id

            correction_run = await runs.create(
                CreateRunRequest(
                    run_type=RunType.SCOPED_CORRECTION,
                    project_id=project_id,
                    source_document_id=document_id,
                    requested_by=user_id,
                    feedback_id=prepared.feedback_id,
                    expected_result_version=1,
                    scope=RunScope(type=ScopeType.CONNECTION, id=match.connection_id),
                ),
                f"db-smoke-correct-{uuid4()}",
            )
            before = dict(persisted_bundle.current_records[0])
            after = dict(before)
            after["end_terminal"] = "U2"
            patch = ResultPatchProposal(
                proposal_id=f"{correction_run.agent_run_id}:result-proposal",
                agent_run_id=correction_run.agent_run_id,
                project_id=project_id,
                base_result_version=1,
                profile=profile.profile,
                model=ModelRef(name="smoke-model"),
                scope=RunScope(type=ScopeType.CONNECTION, id=match.connection_id),
                feedback_id=prepared.feedback_id,
                operations=[
                    ProposalOperation(
                        op="replace",
                        target_type="CONNECTION",
                        target_id=match.connection_id,
                        expected_version=match.record_version,
                        before=before,
                        after=after,
                        evidence_ids=persisted_bundle.evidence_ids,
                        reason="confirmed smoke correction",
                        confidence=1.0,
                    )
                ],
                validation=ProposalValidation(schema_valid=True, business_rules_valid=True),
            )
            await proposals.submit(patch)
            corrected = await result_data.commit_result_patch(patch, user_id)
            assert corrected.result_version == 2
            accepted = await result_data.get_accepted_feedback(prepared.feedback_id)
            assert accepted.result_version_id == corrected.result_version_id
            corrected_matches = await result_data.search_connections(
                ConnectionSearchQuery(project_id=project_id, terminal="U2")
            )
            assert len(corrected_matches) == 1
            assert corrected_matches[0].result_version == 2

            if anon_key:
                async with httpx.AsyncClient(timeout=30.0) as http:
                    login = await http.post(
                        f"{base_url}/auth/v1/token",
                        params={"grant_type": "password"},
                        headers={"apikey": anon_key},
                        json={"email": email, "password": password},
                    )
                    login.raise_for_status()
                    owner_headers = {
                        "apikey": anon_key,
                        "Authorization": f"Bearer {login.json()['access_token']}",
                    }
                    visible_rows = await http.get(
                        f"{base_url}/rest/v1/wiring_connection_rows",
                        params={"project_id": f"eq.{project_id}", "select": "connection_id"},
                        headers=owner_headers,
                    )
                    internal_feedback = await http.get(
                        f"{base_url}/rest/v1/feedback_items",
                        params={"id": f"eq.{prepared.feedback_id}", "select": "id"},
                        headers=owner_headers,
                    )
                visible_rows.raise_for_status()
                assert len(visible_rows.json()) == 2
                assert internal_feedback.status_code in {401, 403}

            traces = SupabaseTraceStore(client)
            await traces.append(correction_run.agent_run_id, {"kind": "smoke", "secret": "redacted"})
            assert (await traces.list(correction_run.agent_run_id))[0]["kind"] == "smoke"
            logical_trace_key = f"candidate:{candidate_id}"
            await traces.append(logical_trace_key, {"kind": "candidate-smoke"})
            assert (await traces.list(logical_trace_key))[0]["kind"] == "candidate-smoke"

            candidates = SupabaseCandidateRepository(client)
            diagnosis = Diagnosis(
                category=RootCauseCategory.PROMPT_RULE_GAP,
                confidence=0.9,
                affected_stage=[AgentStage.PAGE_SCAN],
                affected_scope=AffectedScope(type=ScopeType.CONNECTION, ids=[match.connection_id]),
                explanation="smoke diagnosis",
                recommended_action="add regression case",
                profile_candidate_required=True,
            )
            candidate = ProfileCandidate(
                candidate_id=candidate_id,
                profile=profile.profile,
                candidate_type=ProfileCandidateType.PROMPT_PATCH,
                summary="smoke candidate",
                operations=[
                    CandidatePatchOperation(
                        op="replace",
                        relative_path="rules.json",
                        content='{"smoke":true}',
                        reason="smoke",
                    )
                ],
                source_feedback_ids=[prepared.feedback_id],
                diagnoses=[diagnosis],
                sandbox_path=".profile-sandbox/smoke",
                checksum="sha256:smoke",
            )
            await candidates.put(candidate)
            evaluating = await candidates.transition(candidate_id, ProfileCandidateStatus.EVALUATING)
            assert evaluating.status == ProfileCandidateStatus.EVALUATING
            gate = ReleaseDecision(passed=True, reasons=[])
            await candidates.record_gate(candidate_id, gate)
            approved = await candidates.transition(
                candidate_id,
                ProfileCandidateStatus.APPROVED,
                reviewer_id=user_id,
            )
            assert approved.status == ProfileCandidateStatus.APPROVED
            canary = await candidates.transition(
                candidate_id,
                ProfileCandidateStatus.CANARY,
                reviewer_id=user_id,
            )
            active = await candidates.transition(candidate_id, ProfileCandidateStatus.ACTIVE)
            assert canary.status == ProfileCandidateStatus.CANARY
            assert active.status == ProfileCandidateStatus.ACTIVE

            metrics = EvalMetrics(
                total_cases=1,
                passed_cases=1,
                target_pass_rate=1,
                protected_regressions=0,
                negative_hallucinations=0,
                schema_valid_rate=1,
                field_precision=1,
                field_recall=1,
                total_cost=0,
                p95_duration_seconds=0,
            )
            case = EvalCaseResult(
                case_id="smoke-case",
                kind=EvalCaseKind.TARGET,
                expected={"end_terminal": "U2"},
                actual={"end_terminal": "U2"},
            )
            report = EvalReport(
                candidate_id=candidate_id,
                baseline=metrics,
                candidate=metrics,
                baseline_results=[case],
                candidate_results=[case],
            )
            evals = SupabaseEvalRepository(client)
            await evals.put(report)
            assert (await evals.get(report.eval_run_id)).candidate_id == candidate_id
            assert len(await candidates.audit_log(candidate_id)) >= 5

        print(
            "Supabase Agent database workflows verified: "
            "extraction_version=1, correction_version=2, wire_number=1000, "
            "feedback=accepted, candidate=ACTIVE, eval=persisted"
        )
        return 0
    finally:
        await client.delete("agent_traces", filters={"run_key": f"eq.candidate:{candidate_id}"})
        await client.delete("profile_candidates", filters={"id": f"eq.{candidate_id}"})
        await client.remove_objects(bucket=bucket, object_paths=uploaded_paths)
        await client.delete("projects", filters={"id": f"eq.{project_id}"})
        if user_id is not None:
            async with httpx.AsyncClient(timeout=30.0) as http:
                await http.delete(
                    f"{base_url}/auth/v1/admin/users/{user_id}",
                    headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
                )


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"Supabase Agent database verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
