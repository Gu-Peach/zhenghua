from __future__ import annotations

import asyncio
import base64
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import httpx

from agent_service.domain.enums import EventType, RunType, ScopeType
from agent_service.domain.errors import AgentServiceError
from agent_service.domain.models.proposals import ProposalValidation, ResultProposal
from agent_service.domain.models.runs import (
    AgentEvent,
    CreateRunRequest,
    ModelRef,
    ProfileRef,
    RunScope,
)
from agent_service.infrastructure.project_assets import (
    SupabaseProjectAssetStore,
    SupabaseSourceDocumentProvider,
)
from agent_service.infrastructure.storage_paths import project_source_pdf_path
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.infrastructure.supabase_repositories import (
    SupabaseArtifactRepository,
    SupabaseCheckpointStore,
    SupabaseEventRepository,
    SupabaseProposalRepository,
    SupabaseRunQueue,
    SupabaseRunRepository,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def main() -> int:
    base_url = os.environ.get("AGENT_SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("AGENT_SUPABASE_SERVICE_ROLE_KEY", "")
    anon_key = os.environ.get("AGENT_SUPABASE_ANON_KEY", "")
    bucket = os.environ.get("AGENT_SUPABASE_STORAGE_BUCKET", "project-assets")
    if not base_url or not service_key:
        raise RuntimeError("AGENT_SUPABASE_URL and AGENT_SUPABASE_SERVICE_ROLE_KEY are required.")
    if bucket != "project-assets":
        raise RuntimeError(
            "Production foundation verification requires the private 'project-assets' bucket; "
            "do not point it at the legacy public 'images' bucket."
        )

    client = SupabaseClient(base_url=base_url, service_role_key=service_key)
    project_id = str(uuid4())
    document_id = str(uuid4())
    auth_user_id: str | None = None
    uploaded_paths: list[str] = []
    smoke_email = f"agent-smoke-{uuid4().hex}@example.invalid"
    smoke_password = f"Smoke-{uuid4().hex}!"
    async with httpx.AsyncClient(timeout=30.0) as http:
        auth_response = await http.post(
            f"{base_url}/auth/v1/admin/users",
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            json={
                "email": smoke_email,
                "password": smoke_password,
                "email_confirm": True,
            },
        )
        auth_response.raise_for_status()
        auth_user_id = str(auth_response.json()["id"])

    try:
        await client.insert(
            "projects",
            {
                "id": project_id,
                "owner_id": auth_user_id,
                "name": "Agent Supabase smoke test",
                "standard_profile": "zh",
                "status": "processing",
            },
        )
        asset_store = SupabaseProjectAssetStore(client, bucket=bucket)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_pdf = root / "input.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n")
            await asset_store.upload_source_pdf(
                project_id=project_id,
                document_id=document_id,
                original_filename="input.pdf",
                pdf_path=source_pdf,
            )
            uploaded_paths.append(project_source_pdf_path(project_id))

            provider = SupabaseSourceDocumentProvider(client, cache_root=root / "cache")
            downloaded = await provider.get(document_id, project_id)
            assert downloaded.local_path.read_bytes() == source_pdf.read_bytes()

            output_dir = root / "run-output"
            image = output_dir / "pages" / "002.C" / "1.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_1X1)
            index = output_dir / "agent" / "drawing_index.json"
            index.parent.mkdir(parents=True)
            index.write_text(
                '{"pages":[{"pdf_page":1,"function":"002.C","internal_page":1}]}',
                encoding="utf-8",
            )

            request = CreateRunRequest(
                run_type=RunType.FULL_EXTRACTION,
                project_id=project_id,
                source_document_id=document_id,
                requested_by=auth_user_id,
                profile_hint="zh",
                expected_result_version=0,
                scope=RunScope(type=ScopeType.PROJECT, id=project_id),
            )
            runs = SupabaseRunRepository(client)
            run = await runs.create(request, f"smoke-{uuid4()}")
            published = await asset_store.publish_extraction_pages(run, output_dir)
            assert published.workspace_count == 1
            assert published.drawing_count == 1
            uploaded_paths.extend(published.object_paths)

            workspace = (
                await client.select(
                    "workspaces",
                    params={"project_id": f"eq.{project_id}", "limit": "1"},
                )
            )[0]
            drawing = (
                await client.select(
                    "drawings",
                    params={"project_id": f"eq.{project_id}", "limit": "1"},
                )
            )[0]
            result_version = (
                await client.insert(
                    "result_versions",
                    {
                        "project_id": project_id,
                        "version": 1,
                        "agent_run_id": run.agent_run_id,
                        "status": "draft",
                        "created_by": auth_user_id,
                    },
                )
            )[0]
            allocated_units = await asyncio.gather(
                *[
                    client.insert(
                        "wiring_units",
                        {
                            "project_id": project_id,
                            "result_version_id": result_version["id"],
                            "workspace_id": workspace["id"],
                            "drawing_id": drawing["id"],
                            "terminal_strip": f"X{index + 1}",
                        },
                    )
                    for index in range(8)
                ]
            )
            assert sorted(int(rows[0]["wire_number"]) for rows in allocated_units) == list(range(1000, 1008))

            queue = SupabaseRunQueue(client, worker_id="smoke-worker", lease_seconds=30)
            await queue.enqueue(run.agent_run_id)
            assert await queue.dequeue() == run.agent_run_id
            await queue.acknowledge(run.agent_run_id)

            events = SupabaseEventRepository(client)
            saved_events = await asyncio.gather(
                *[
                    events.append(
                        AgentEvent(
                            agent_run_id=run.agent_run_id,
                            seq=0,
                            event_type=EventType.ITEM_COMPLETED,
                            message=f"event-{index}",
                        )
                    )
                    for index in range(5)
                ]
            )
            assert sorted(event.seq for event in saved_events) == list(range(5))

            artifacts = SupabaseArtifactRepository(client)
            artifact_id = f"{run.agent_run_id}:smoke"
            await artifacts.put(
                artifact_id,
                {
                    "artifact_id": artifact_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": "smoke",
                    "storage_bucket": bucket,
                    "storage_path": published.object_paths[0],
                },
            )
            assert (await artifacts.get(artifact_id) or {}).get("kind") == "smoke"

            checkpoints = SupabaseCheckpointStore(client)
            checkpoint_key = f"{run.agent_run_id}:graph:node:item"
            assert await checkpoints.save(checkpoint_key, {"step": 1}) == 1
            assert await checkpoints.save(checkpoint_key, {"step": 2}, expected_revision=1) == 2
            try:
                await checkpoints.save(checkpoint_key, {"step": 3}, expected_revision=1)
            except AgentServiceError:
                pass
            else:
                raise AssertionError("Stale checkpoint revision was accepted.")

            proposal = ResultProposal(
                agent_run_id=run.agent_run_id,
                project_id=project_id,
                base_result_version=0,
                profile=ProfileRef(key="zh", version="1.0.0"),
                model=ModelRef(name="smoke-model"),
                scope=run.scope,
                validation=ProposalValidation(schema_valid=True, business_rules_valid=True),
            )
            proposals = SupabaseProposalRepository(client)
            await proposals.submit(proposal)
            assert await proposals.get(proposal.proposal_id) == proposal

            private_url = f"{base_url}/storage/v1/object/public/{bucket}/{published.object_paths[0]}"
            async with httpx.AsyncClient(timeout=30.0) as http:
                anonymous = await http.get(private_url)
            assert anonymous.status_code != 200
            signed_url = await client.create_signed_url(
                bucket=bucket,
                object_path=published.object_paths[0],
                expires_in=60,
            )
            async with httpx.AsyncClient(timeout=30.0) as http:
                signed = await http.get(signed_url)
            assert signed.status_code == 200

            if anon_key:
                async with httpx.AsyncClient(timeout=30.0) as http:
                    login = await http.post(
                        f"{base_url}/auth/v1/token",
                        params={"grant_type": "password"},
                        headers={"apikey": anon_key},
                        json={"email": smoke_email, "password": smoke_password},
                    )
                    login.raise_for_status()
                    owner_token = login.json()["access_token"]
                    anonymous_rows = await http.get(
                        f"{base_url}/rest/v1/projects",
                        params={"id": f"eq.{project_id}", "select": "id"},
                        headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}"},
                    )
                    owner_rows = await http.get(
                        f"{base_url}/rest/v1/projects",
                        params={"id": f"eq.{project_id}", "select": "id"},
                        headers={"apikey": anon_key, "Authorization": f"Bearer {owner_token}"},
                    )
                assert anonymous_rows.status_code in {200, 401}
                owner_rows.raise_for_status()
                if anonymous_rows.status_code == 200:
                    assert anonymous_rows.json() == []
                assert owner_rows.json() == [{"id": project_id}]

        print(
            "Supabase production foundation verified: "
            f"project={project_id}, events=5, workspaces=1, drawings=1, "
            f"wire_numbers=1000..1007, bucket={bucket}"
        )
        return 0
    finally:
        await client.remove_objects(bucket=bucket, object_paths=uploaded_paths)
        await client.delete("projects", filters={"id": f"eq.{project_id}"})
        if auth_user_id is not None:
            async with httpx.AsyncClient(timeout=30.0) as http:
                await http.delete(
                    f"{base_url}/auth/v1/admin/users/{auth_user_id}",
                    headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
                )


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"Supabase production verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
