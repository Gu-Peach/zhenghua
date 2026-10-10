from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from agent_service.domain.enums import EventType
from agent_service.domain.errors import AgentServiceError
from agent_service.domain.models.runs import AgentEvent
from agent_service.infrastructure.storage_paths import (
    drawing_image_path,
    project_source_pdf_path,
    run_artifact_path,
)
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.infrastructure.supabase_repositories import (
    SupabaseEventRepository,
    SupabaseRunQueue,
)


def test_project_asset_paths_are_uuid_scoped_and_nested() -> None:
    project_id = str(uuid4())
    workspace_id = str(uuid4())
    drawing_id = str(uuid4())
    run_id = str(uuid4())

    assert project_source_pdf_path(project_id) == f"projects/{project_id}/original.pdf"
    assert drawing_image_path(project_id, workspace_id, drawing_id) == (
        f"projects/{project_id}/workspaces/{workspace_id}/drawings/{drawing_id}.png"
    )
    assert run_artifact_path(project_id, run_id, "stage_2", "page-scan.json") == (
        f"projects/{project_id}/runs/{run_id}/stage-2/page-scan.json"
    )
    with pytest.raises(ValueError):
        project_source_pdf_path("not-a-uuid")
    with pytest.raises(ValueError):
        run_artifact_path(project_id, run_id, "../escape", "payload.json")


def test_supabase_event_repository_uses_atomic_server_sequence() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=7)

        client = SupabaseClient(
            base_url="http://supabase.local",
            service_role_key="secret-test-key",
            transport=httpx.MockTransport(handler),
        )
        repository = SupabaseEventRepository(client)
        event = AgentEvent(
            agent_run_id=str(uuid4()),
            seq=0,
            event_type=EventType.RUN_CREATED,
        )
        saved = await repository.append(event)

        assert saved.seq == 7
        assert requests[0].url.path.endswith("/rest/v1/rpc/append_agent_event")
        payload = json.loads(requests[0].content)
        assert payload["target_run_id"] == event.agent_run_id
        assert requests[0].headers["authorization"] == "Bearer secret-test-key"

    asyncio.run(run())


def test_supabase_queue_claim_and_acknowledge() -> None:
    async def run() -> None:
        run_id = str(uuid4())
        methods: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            methods.append(request.method)
            if request.url.path.endswith("/rpc/claim_agent_run"):
                return httpx.Response(200, json=run_id)
            if request.method == "DELETE":
                return httpx.Response(204)
            return httpx.Response(201, json=[])

        client = SupabaseClient(
            base_url="http://supabase.local",
            service_role_key="secret-test-key",
            transport=httpx.MockTransport(handler),
        )
        queue = SupabaseRunQueue(client, worker_id="worker-1")
        assert await queue.dequeue() == run_id
        await queue.acknowledge(run_id)
        assert methods == ["POST", "DELETE"]

    asyncio.run(run())


def test_supabase_error_does_not_expose_response_or_service_key() -> None:
    async def run() -> None:
        client = SupabaseClient(
            base_url="http://supabase.local",
            service_role_key="top-secret-service-key",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    500,
                    text="database error includes top-secret-service-key and private row",
                )
            ),
        )
        with pytest.raises(AgentServiceError) as captured:
            await client.select("projects")
        rendered = str(captured.value)
        assert "top-secret-service-key" not in rendered
        assert "private row" not in rendered
        assert "HTTP 500" in captured.value.message

    asyncio.run(run())
