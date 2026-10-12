from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_service.api.routes.improvement import router
from agent_service.application.candidate_release import CandidateReleaseService

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    "answers,expected_posts",
    [
        (["确认规则修改"], ["confirm"]),
        (["拒绝"], []),
        (["确认审核"], []),
    ],
)
def test_terminal_requires_one_confirmation_without_evaluation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    answers: list[str],
    expected_posts: list[str],
) -> None:
    spec = importlib.util.spec_from_file_location(
        "release_terminal", ROOT / "services/agent/agent_test/2.纠错agent/run_rule_release.py"
    )
    assert spec and spec.loader
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    script.__file__ = str(tmp_path / "run_rule_release.py")
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST":
            posts.append(path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={"run": {"agent_run_id": "eval"}})
        if path.endswith("model-outputs"):
            return httpx.Response(200, json={"items": []})
        if path.endswith("artifacts"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "artifact_id": "report",
                            "kind": "evaluation_report",
                            "gate": {"passed": False},
                            "report": {"cost_reported": False},
                        }
                    ]
                },
            )
        if "/runs/" in path:
            return httpx.Response(200, json={"run": {"status": "NEEDS_REVIEW"}})
        return httpx.Response(200, json={"profile": {"key": "zh-wrong"}})

    client_factory = httpx.Client
    monkeypatch.setattr(
        script.httpx,
        "Client",
        lambda **kwargs: client_factory(**kwargs, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setenv("AGENT_ACCEPTANCE_ALLOW_REAL_MODEL", "true")
    monkeypatch.setattr(script.sys, "argv", ["release", "--candidate-id", "c", "--user-id", "u"])
    choices = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt: next(choices))
    result = script.main()
    assert posts == expected_posts
    assert result == (0 if "confirm" in posts else 2)


def test_http_release_contract_and_internal_auth() -> None:
    app = FastAPI()
    app.state.settings = SimpleNamespace(internal_token="test-token", environment="test")
    service = AsyncMock(spec=CandidateReleaseService)
    service.start.side_effect = PermissionError("wrong owner")
    service.approve.side_effect = ValueError("no passing receipt")
    app.state.candidate_release = service
    app.include_router(router)
    client = TestClient(app)
    body = {"reviewer_id": "u", "evaluation_run_id": "eval", "confirmed": True}
    assert client.post("/v1/profile-candidates/c/approve", json=body).status_code == 401
    headers = {"Authorization": "Bearer test-token"}
    assert (
        client.post(
            "/v1/profile-candidates/c/approve", json={"reviewer_id": "u"}, headers=headers
        ).status_code
        == 422
    )
    assert client.post("/v1/profile-candidates/c/approve", json=body, headers=headers).status_code == 409
    assert (
        client.post(
            "/v1/profile-candidates/c/evaluations", json={"reviewer_id": "other"}, headers=headers
        ).status_code
        == 410
    )
    schema = app.openapi()
    assert "/v1/profile-candidates/{candidate_id}/publish" in schema["paths"]
    required = schema["components"]["schemas"]["ConfirmCandidateReleaseRequest"]["required"]
    assert "evaluation_run_id" in required


def test_http_direct_confirmation_is_authenticated_and_explicit() -> None:
    app = FastAPI()
    app.state.settings = SimpleNamespace(internal_token="test-token", environment="test")
    service = AsyncMock(spec=CandidateReleaseService)
    service.confirm.side_effect = ValueError("Explicit confirmation required")
    app.state.candidate_release = service
    app.include_router(router)
    client = TestClient(app)
    path = "/v1/profile-candidates/c/confirm"
    assert client.post(path, json={"reviewer_id": "u", "confirmed": True}).status_code == 401
    headers = {"Authorization": "Bearer test-token"}
    assert client.post(path, json={"reviewer_id": "u"}, headers=headers).status_code == 409
    service.confirm.assert_awaited_once_with("c", "u", False)
    service.confirm.side_effect = PermissionError("wrong owner")
    assert (
        client.post(path, json={"reviewer_id": "other", "confirmed": True}, headers=headers).status_code
        == 403
    )
    service.start.assert_not_called()
    schema = app.openapi()
    assert "/v1/profile-candidates/{candidate_id}/confirm" in schema["paths"]
    assert (
        "evaluation_run_id" not in schema["components"]["schemas"]["ConfirmRuleUpdateRequest"]["properties"]
    )
