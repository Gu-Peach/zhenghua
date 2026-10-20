"""Requirements cannot silently lose a start or request fields an operation cannot write."""

import asyncio
import json
from uuid import uuid4

import pytest

from src.agent.explain_agent import ExplainActor, ExplainTurn
from src.agent.explain_agent.models import ExplainError, RescanRequest
from src.agent.explain_agent.tools.rescan import RescanConnectionsTool

from .test_explain_agent import OWNER, PROJECT, ROW
from .test_explain_edits import agent
from .test_explain_rescan_receipts import RescanBackend


def requirements(**values):
    return {
        "required_fields": ["end_terminal"],
        "expected_start_terminals": [],
        "connection_set": "preserve",
        "endpoint_location": "same_page",
        **values,
    }


def test_tool_requires_structured_requirements_but_legacy_dto_stays_readable():
    schema = RescanConnectionsTool.definition()["function"]["parameters"]
    assert "requirements" in schema["required"]
    assert schema["properties"]["requirements"] == {"$ref": "#/$defs/RescanRequirements"}
    assert set(schema["$defs"]["RescanRequirements"]["required"]) == {
        "required_fields",
        "expected_start_terminals",
        "connection_set",
        "endpoint_location",
    }
    assert RescanRequest(scope={"connection_ids": [ROW]}, fields="end").requirements is None


@pytest.mark.parametrize(
    "params",
    [
        {"fields": "end", "requirements": requirements(required_fields=["end_terminal", "principle_number"])},
        {"fields": "end", "requirements": requirements(connection_set="rebuild")},
        {"fields": "all", "requirements": requirements(connection_set="rebuild")},
    ],
)
def test_incompatible_operation_is_rejected_before_enqueue(params):
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(backend, [])
        with pytest.raises(ExplainError) as error:
            await RescanConnectionsTool.execute(
                assistant.repository,
                ExplainTurn(project_id=PROJECT, connection_id=ROW),
                ExplainActor(user_id=OWNER),
                RescanRequest(scope={"connection_ids": [ROW]}, **params),
            )
        assert error.value.code == "RESCAN_PLAN_INCOMPATIBLE" and not backend.enqueues

    asyncio.run(run())


def test_five_expected_starts_cannot_be_silently_narrowed_to_existing_one():
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(backend, [])
        with pytest.raises(ExplainError) as error:
            await RescanConnectionsTool.execute(
                assistant.repository,
                ExplainTurn(project_id=PROJECT, connection_id=ROW),
                ExplainActor(user_id=OWNER),
                RescanRequest(
                    scope={"connection_ids": [ROW]},
                    fields="end",
                    requirements=requirements(expected_start_terminals=["XA:8", "PE-BAR"]),
                ),
            )
        assert error.value.code == "RESCAN_SCOPE_INCOMPLETE" and not backend.enqueues

    asyncio.run(run())


def test_expected_coverage_is_reported_and_missing_principle_number_is_not_success():
    from src.agent.explain_agent.models import RescanCandidate, RescanChange
    from src.agent.explain_agent.rescan_planning import check_candidate_requirements

    change = RescanChange(
        action="insert",
        connection_id=uuid4(),
        record_version=0,
        source_pdf_page_number=1,
        before={},
        after={"start_terminal": "XA:8", "end_terminal": "X1:U"},
    )
    candidate = check_candidate_requirements(
        {
            "baseline": [],
            "request": {
                "scope": {"drawing_page": "002C01"},
                "fields": "all",
                "requirements": requirements(
                    required_fields=["start_terminal", "end_terminal", "principle_number"],
                    connection_set="rebuild",
                    expected_start_terminals=["XA:8", "PE-BAR"],
                ),
            },
        },
        RescanCandidate(changes=[change]),
    )
    assert any("PE-BAR" in text for text in candidate.warnings)
    assert any("原理号" in text for text in candidate.warnings)
    assert candidate.changes[0].after.needs_review


def test_duplicate_old_anchors_cannot_claim_the_same_scanned_connection():
    from src.agent.explain_agent.rescan_planning import freeze_same_page_matches

    old = {"id": str(uuid4()), "source_pdf_page_number": 1, "start_terminal": "XA:4"}
    duplicate = {**old, "id": str(uuid4())}
    assert freeze_same_page_matches([old, duplicate], [{**old, "end_terminal": "XD1:N"}]) == []


def test_whole_page_replacement_cannot_claim_to_preserve_the_connection_set():
    from src.agent.explain_agent.rescan_planning import RescanPlanError, validate_requirements

    with pytest.raises(RescanPlanError, match="范围替换"):
        validate_requirements(
            RescanRequest(scope={"drawing_page": "002C01"}, fields="all", requirements=requirements())
        )


def test_complete_selected_start_set_can_enqueue_after_authorized_preflight():
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(backend, [])
        result = await RescanConnectionsTool.execute(
            assistant.repository,
            ExplainTurn(project_id=PROJECT, connection_id=ROW, batch_id="batch-a"),
            ExplainActor(user_id=OWNER),
            RescanRequest(
                scope={"connection_ids": [ROW]},
                fields="end",
                requirements=requirements(expected_start_terminals=["XA:8"]),
            ),
        )
        assert result.status == "queued" and len(backend.enqueues) == 1

    asyncio.run(run())


def test_model_can_replan_incompatible_endpoint_request_as_full_page_candidate():
    from .test_explain_edits import tool

    async def run():
        backend = RescanBackend()
        expected = ["XA:4", "XA:5", "XA:6", "XA:7", "PE-BAR"]
        plan = requirements(
            required_fields=["start_terminal", "end_terminal", "principle_number"],
            connection_set="rebuild",
            expected_start_terminals=expected,
        )
        assistant, gateway = agent(
            backend,
            [
                tool(
                    "rescan_connections",
                    {"scope": {"connection_ids": [str(ROW)]}, "fields": "end", "requirements": plan},
                ),
                tool(
                    "rescan_connections",
                    {"scope": {"drawing_page": "003C01"}, "fields": "all", "requirements": plan},
                ),
                "已提交重扫任务。",
            ],
        )
        result = await assistant.ask(
            ExplainTurn(
                project_id=PROJECT, connection_id=ROW, message="本页只有五个起点，重提起终点并读取原理号"
            ),
            ExplainActor(user_id=OWNER),
        )
        assert len(backend.enqueues) == 1 and len(result.rescans) == 1
        request = backend.enqueues[0]["request"]
        assert request["fields"] == "all" and request["result_mode"] == "replace_scope"
        assert not request["scope"]["connection_ids"]
        assert request["requirements"]["expected_start_terminals"] == expected
        failures = [
            json.loads(message["content"])
            for message in gateway.calls[1].messages
            if message["role"] == "tool"
        ]
        assert failures[0]["error"] == "RESCAN_PLAN_INCOMPATIBLE"

    asyncio.run(run())


def test_new_tool_call_cannot_omit_its_scope_and_location_requirements():
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(backend, [])
        with pytest.raises(ExplainError) as error:
            await RescanConnectionsTool.execute(
                assistant.repository,
                ExplainTurn(project_id=PROJECT, connection_id=ROW),
                ExplainActor(user_id=OWNER),
                RescanRequest(
                    scope={"connection_ids": [ROW]},
                    fields="end",
                    requirements={"required_fields": ["end_terminal"]},
                ),
            )
        assert error.value.code == "RESCAN_REQUIREMENTS_MISSING" and not backend.enqueues

    asyncio.run(run())
