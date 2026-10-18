"""Explain HTTP/SSE failures remain distinguishable without leaking provider data."""

import logging

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent.explain_agent.api import create_explain_router
from src.agent.explain_agent.models import ExplainActor
from src.domain.enums import ErrorCode
from src.domain.errors import AgentServiceError
from src.harness.model_gateway import OpenAICompatibleModelGateway
from src.harness.retry import RetryPolicy
from tests.unit.test_explain_agent import OWNER, setup, turn


@pytest.mark.parametrize(
    "status,label",
    [
        (400, "拒绝请求"),
        (401, "鉴权失败"),
        (403, "无权访问"),
        (413, "超出服务限制"),
        (429, "限流"),
        (503, "暂时不可用"),
        (200, "流式响应中返回错误"),
    ],
)
def test_model_failure_after_sse_open_is_classified_and_logged(status, label, caplog):
    def provider(request):
        if status == 200:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text='data: {"error":{"message":"PRIVATE-PROVIDER-TOKEN"}}\n\n',
            )
        return httpx.Response(status, json={"error": {"message": "PRIVATE-PROVIDER-TOKEN"}})

    _, _, _, agent = setup()
    client = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    agent.gateway = OpenAICompatibleModelGateway(
        base_url="https://model.invalid",
        default_model="fake",
        client=client,
        retry_policy=RetryPolicy(max_retries=0),
    )
    app = FastAPI()

    async def actor():
        return ExplainActor(user_id=OWNER)

    app.include_router(create_explain_router(agent, actor))
    body = turn().model_dump(mode="json")
    with caplog.at_level(logging.ERROR), TestClient(app) as browser:
        result = browser.post("/v1/explain/turns/stream", json=body)
        assert result.status_code == 200  # Opening a stream does not certify model success.
        assert "event: context" in result.text and "event: error" in result.text
        assert "event: completed" not in result.text
        assert label in result.text
        assert "EXPLAIN_UPSTREAM_FAILED" in result.text
    assert body["turn_id"] in caplog.text and "ModelGatewayError" in caplog.text
    if status != 200:
        assert f"upstream_status={status}" in caplog.text
    assert "PRIVATE-PROVIDER-TOKEN" not in result.text + caplog.text


def test_storage_failure_is_not_misreported_as_model_failure(caplog):
    _, _, _, agent = setup([AgentServiceError(ErrorCode.PERSISTENCE_UNAVAILABLE, "PRIVATE-STORAGE-DETAIL")])
    app = FastAPI()

    async def actor():
        return ExplainActor(user_id=OWNER)

    app.include_router(create_explain_router(agent, actor))
    with caplog.at_level(logging.ERROR), TestClient(app) as browser:
        result = browser.post("/v1/explain/turns", json=turn().model_dump(mode="json"))
    assert result.status_code == 502
    assert "数据服务读取失败" in result.json()["detail"]["message"]
    assert "PRIVATE-STORAGE-DETAIL" not in result.text + caplog.text
