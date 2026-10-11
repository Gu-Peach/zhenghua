from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx

from agent_service.domain.enums import ScopeType
from agent_service.domain.models.improvement import AcceptedFeedback
from agent_service.domain.models.proposals import ProposalOperation, ProposalValidation, ResultPatchProposal
from agent_service.domain.models.runs import ModelRef, ProfileRef, RunScope
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.infrastructure.supabase_result_data import SupabaseResultDataRepository
from agent_service.profiles import ProfileRegistry


def test_scoped_commit_updates_only_target_and_replays_receipt(tmp_path: Path) -> None:
    async def run() -> None:
        project, connection, unit, result, actor, run_id = [str(uuid4()) for _ in range(6)]
        proposal = ResultPatchProposal(
            proposal_id=f"{run_id}:result-proposal",
            agent_run_id=run_id,
            project_id=project,
            base_result_version=3,
            base_result_revision=1,
            profile=ProfileRef(key="zh", version="1.0.0"),
            model=ModelRef(name="fake"),
            scope=RunScope(type=ScopeType.CONNECTION, id=connection),
            feedback_id="feedback",
            operations=[
                ProposalOperation(
                    op="replace",
                    target_type="CONNECTION",
                    target_id=connection,
                    expected_version=3,
                    before={"connection_id": connection, "end_terminal": "999"},
                    after={"connection_id": connection, "end_terminal": "2"},
                    evidence_ids=["evidence"],
                    reason="test",
                    confidence=1,
                )
            ],
            validation=ProposalValidation(schema_valid=True, business_rules_valid=True),
        )
        receipt = {
            "result_version_id": result,
            "result_version": 3,
            "result_revision": 2,
            "update_mode": "in_place",
            "updated_connection_ids": [connection],
        }
        accepted: dict = {}
        rpc_calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/rpc/apply_confirmed_result_patch"):
                body = json.loads(request.content)["value"]
                rpc_calls.append(body)
                accepted.update(body["feedback_updates"][0]["accepted_payload"])
                accepted["result_version_id"] = result
                return httpx.Response(200, json=receipt)
            table = request.url.path.rsplit("/", 1)[-1]
            if table == "result_proposals":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "confirmed_by": actor,
                            "committed_result_version_id": result,
                            "commit_receipt": receipt,
                        }
                    ]
                    if rpc_calls
                    else [],
                )
            if table == "result_versions":
                return httpx.Response(200, json=[{"id": result, "version": 3, "revision": 1}])
            if table == "wiring_connections":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": connection,
                            "wiring_unit_id": unit,
                            "record_version": 3,
                            "core_order": 1,
                            "end_terminal": "999",
                            "is_cross_page": "same_page",
                        }
                    ],
                )
            if table == "wiring_units":
                assert request.url.params.get("id") == f"eq.{unit}"
                return httpx.Response(200, json=[{"id": unit}])
            if table == "feedback_items":
                return httpx.Response(
                    200,
                    json=[{"accepted_payload": accepted}]
                    if accepted
                    else [{"correction_bundle": {"facts": {"target": {"id": connection}}}}],
                )
            raise AssertionError(f"Unexpected call: {table}")

        client = SupabaseClient(
            base_url="http://supabase.local", service_role_key="test", transport=httpx.MockTransport(handler)
        )
        registry = ProfileRegistry(profile_root=tmp_path, workspace_root=tmp_path)
        repo = SupabaseResultDataRepository(client, profiles=registry, drawing_cache_root=tmp_path)
        first = await repo.commit_result_patch(proposal, actor)
        second = await repo.commit_result_patch(proposal, actor)
        assert first == second
        assert first.result_version_id == result
        assert first.result_revision == 2
        assert first.updated_connection_ids == [connection]
        assert len(rpc_calls) == 1
        assert rpc_calls[0]["changes"][0]["record"]["end_terminal"] == "2"
        AcceptedFeedback.model_validate(accepted)

    asyncio.run(run())
