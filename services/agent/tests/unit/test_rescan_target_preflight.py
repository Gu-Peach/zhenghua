"""Target catalog checks happen before queue writes, with no model or business writes."""

import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest

from src.agent.explain_agent.models import ExplainActor, ExplainError, ExplainTurn, RescanRequest
from src.agent.explain_agent.repository import SupabaseExplanationRepository


@pytest.mark.parametrize(
    "case", ["correct", "no_workspace", "wrong_workspace", "wrong_pdf", "unknown", "ambiguous", "denied"]
)
def test_target_preflight_checks_authorized_full_catalog_before_enqueue(case):
    project, owner, row = uuid4(), uuid4(), uuid4()
    pages = [{"pdf_page_number": 56, "drawing_page": "002M03", "workspace_code": "002.M"}]
    if case == "ambiguous":
        pages.append({**pages[0], "pdf_page_number": 99})
    original = deepcopy(pages)
    calls = []

    class Client:
        async def select(self, table, params):
            assert table == "extraction_projects"
            return (
                []
                if case == "denied"
                else [{"id": str(project), "owner_id": str(owner), "drawing_index": {"pages": pages}}]
            )

        async def rpc(self, name, body):
            calls.append((name, body))
            value = body["value"]
            return {
                "id": value["id"],
                "project_id": str(project),
                "conversation_id": value["conversation_id"],
                "batch_id": "batch",
                "request": value["request"],
                "status": "queued",
                "stage": "queued",
                "profile": {"key": "zh", "version": "1.0.0"},
                "created_at": "now",
                "updated_at": "now",
            }

    binding = {"connection_ids": [str(row)], "drawing_page": "002M03"}
    if case != "no_workspace":
        binding["workspace_code"] = "002.C" if case == "wrong_workspace" else "002.M"
    if case == "wrong_pdf":
        binding["pdf_page_number"] = 53
    if case == "unknown":
        binding["drawing_page"] = "002M99"
    request = RescanRequest.model_validate(
        {
            "scope": {"connection_ids": [str(row)], "workspace_code": "002.C"},
            "fields": "end",
            "instructions": "补终点",
            "target_bindings": [binding],
        }
    )
    before = request.model_dump(mode="json")
    repository = SupabaseExplanationRepository(Client())
    turn = ExplainTurn(project_id=project, batch_id="batch", connection_id=row, message="补终点")
    coroutine = repository.start_rescan(turn, ExplainActor(user_id=owner), str(uuid4()), request)
    if case in {"correct", "no_workspace"}:
        assert asyncio.run(coroutine).status == "queued"
        assert len(calls) == 1
        assert calls[0][1]["value"]["request"]["target_bindings"][0]["drawing_page"] == "002M03"
    else:
        with pytest.raises(ExplainError) as exc:
            asyncio.run(coroutine)
        assert not calls
        assert exc.value.code == ("PROJECT_NOT_FOUND" if case == "denied" else "RESCAN_TARGET_INVALID")
        if case == "wrong_workspace":
            assert all(value in exc.value.message for value in ("002M03", "002.M", "56", "002.C"))
        if case == "ambiguous":
            assert "多个" in exc.value.message and "99" in exc.value.message
    assert request.model_dump(mode="json") == before and pages == original
