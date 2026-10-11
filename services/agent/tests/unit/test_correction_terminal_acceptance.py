from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location(
    "correction_terminal", ROOT / "services/agent/agent_test" / "2.纠错agent/run_acceptance.py"
)
assert SPEC is not None and SPEC.loader is not None
SCRIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCRIPT)


@pytest.mark.parametrize(
    "recommend,category,outcome",
    [
        (False, "MODEL_PERCEPTION_ERROR", "PASS"),
        (True, "PROMPT_RULE_GAP", "FAIL"),
        (False, "SOURCE_INSUFFICIENT", "INCOMPLETE"),
        (False, "MODEL_PERCEPTION_ERROR", "STOP_BEFORE_CONFIRM"),
    ],
)
def test_http_only_mixed_flow_and_optional_rejection(
    tmp_path: Path, recommend: bool, category: str, outcome: str
) -> None:
    state = {"committed": False, "rejected": False}
    posts = []
    rows = [
        {"connection_id": key, "wiring_unit_id": f"unit-{key}", "wire_number": index, "end_terminal": "999"}
        for index, key in enumerate(("d", "s", "c"), 1000)
    ]
    proposal = {
        "proposal_id": "correction:result-proposal",
        "operations": [
            {"target_id": key, "before": {"end_terminal": "999"}, "after": {"end_terminal": "2"}}
            for key in ("d", "s", "c")
        ],
        "validation": {"schema_valid": True, "business_rules_valid": True},
    }

    def sse(event: str, value: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(value)}\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST":
            assert path == "/v1/supervisor/turns/stream"
            payload = json.loads(request.content)
            posts.append(payload)
            if len(posts) == 1:
                receipt = {"workflow": "CORRECTION", "agent_run_id": "correction"}
            elif len(posts) == 2:
                state["committed"] = True
                receipt = {
                    "agent_run_id": "improvement",
                    "payload": {
                        "correction_committed": True,
                        "result_version_id": "version",
                        "result_revision": 2,
                        "update_mode": "in_place",
                        "improvement_run_id": "improvement",
                    },
                }
            else:
                assert payload["message"] == "拒绝规则候选"
                state["rejected"] = True
                receipt = {"agent_run_id": "improvement"}
            return httpx.Response(
                200,
                text=sse(
                    "response",
                    {
                        "decision": {"reason": "公开计划"},
                        "receipt": receipt,
                        "user_event": {"user_message": "处理中"},
                    },
                ),
            )
        if path.endswith("/results"):
            return httpx.Response(
                200,
                json={
                    "result_version_id": "version",
                    "result_revision": 2 if state["committed"] else 1,
                    "has_more": False,
                    "items": [{**row, "end_terminal": "2" if state["committed"] else "999"} for row in rows],
                },
            )
        if path == "/v1/profiles":
            return httpx.Response(200, json={"items": [{"key": "zh", "checksum": "baseline"}]})
        if path.endswith("/model-output"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "trace_id": path,
                            "agent": "supervisor",
                            "model": "fake",
                            "output_available": True,
                            "output": {"reason": "公开计划"},
                        }
                    ]
                },
            )
        correction = "/correction/" in path or path.endswith("/correction")
        if path.endswith("/model-outputs"):
            agents = ["page_scan", "cross_page_completion"] if correction else ["improvement_diagnoser"]
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "trace_id": agent,
                            "agent": agent,
                            "model": "fake",
                            "output_available": True,
                            "output": {"result": "fake"},
                        }
                        for agent in agents
                    ]
                },
            )
        if path.endswith("/artifacts"):
            items = (
                [
                    {
                        "artifact_id": "batch",
                        "kind": "correction_batch",
                        "batch": {"direct_patch": ["d"], "stage2": ["s"], "stage2_stage3": ["c"]},
                    },
                    {
                        "artifact_id": "scan",
                        "kind": "correction_stage_item",
                        "stage": "PAGE_SCAN",
                        "result": {},
                    },
                    {
                        "artifact_id": "completion",
                        "kind": "correction_stage_item",
                        "stage": "CROSS_PAGE_COMPLETION",
                        "result": {},
                    },
                    {
                        "artifact_id": "proposal",
                        "kind": "result_proposal",
                        "proposal_id": proposal["proposal_id"],
                    },
                ]
                if correction
                else [
                    {
                        "artifact_id": "diagnosis",
                        "kind": "improvement_diagnosis",
                        "candidate_recommended": recommend,
                        "diagnoses": [{"category": category, "profile_candidate_required": recommend}],
                    }
                ]
            )
            return httpx.Response(200, json={"items": items})
        if "/proposals/" in path:
            return httpx.Response(200, json=proposal)
        if path.endswith("/events/stream"):
            return httpx.Response(200, text=sse("RUN_COMPLETED", {"seq": 0, "event_type": "RUN_COMPLETED"}))
        if path.endswith("/events"):
            return httpx.Response(
                200, json={"items": [{"metrics": {"candidate_declined": state["rejected"]}}]}
            )
        if "/runs/" in path:
            status = (
                "NEEDS_REVIEW"
                if correction
                else "WAITING_INPUT"
                if recommend and not state["rejected"]
                else "SUCCEEDED"
            )
            return httpx.Response(200, json={"run": {"status": status}})
        raise AssertionError(path)

    with httpx.Client(base_url="http://agent.local", transport=httpx.MockTransport(handler)) as client:
        acceptance = SCRIPT.Acceptance(
            client, project="project", user="owner", conversation="case", output=tmp_path, max_wait=2
        )
        answers = iter(["确认提交", "拒绝规则候选"])
        acceptance.ask = lambda _prompt: next(answers)
        if outcome == "STOP_BEFORE_CONFIRM":

            def stop(_prompt: str) -> str:
                raise SCRIPT.Stopped("人工不确认")

            acceptance.ask = stop
            with pytest.raises(SCRIPT.Stopped):
                acceptance.execute("直接修改d、同页重识别s、跨页重识别c", None)
            assert len(posts) == 1
            assert state["committed"] is False
            return
        acceptance.execute("直接修改d、同页重识别s、跨页重识别c", None)
        assert acceptance.report["acceptance"] == outcome
        assert len(posts) == (3 if recommend else 2)
        assert acceptance.report["checks"]["stable_ids"] is True
        assert acceptance.report["checks"]["no_candidate_created"] is True
        assert acceptance.report["candidate_rejection"] == ("declined" if recommend else "not_needed")
        assert not any("AUTHORIZE_PROFILE_CANDIDATE" in json.dumps(post) for post in posts)
        assert (tmp_path / "transcript.jsonl").is_file()


def test_real_model_gate_stops_before_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_ACCEPTANCE_ALLOW_REAL_MODEL", raising=False)
    monkeypatch.setattr("sys.argv", ["run_acceptance.py"])
    with pytest.raises(SystemExit, match="AGENT_ACCEPTANCE_ALLOW_REAL_MODEL"):
        SCRIPT.main()
