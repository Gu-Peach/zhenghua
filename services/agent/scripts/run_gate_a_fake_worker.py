"""Isolated process worker for Gate A tests only; it cannot select a real VLM."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.agent.extraction_agent.application.extraction_run_executor import FullExtractionRunExecutor
from src.application.run_control import RunControlService
from src.application.worker import AgentWorker
from src.config import AgentSettings
from src.domain.enums import RunType
from src.infrastructure.project_assets import (
    SupabaseProjectAssetStore,
    SupabaseSourceDocumentProvider,
)
from src.infrastructure.supabase_client import SupabaseClient
from src.infrastructure.supabase_repositories import (
    SupabaseArtifactRepository,
    SupabaseEventRepository,
    SupabaseProposalRepository,
    SupabaseRunQueue,
    SupabaseRunRepository,
)
from src.infrastructure.supabase_result_data import SupabaseResultDataRepository
from src.infrastructure.supabase_stage_repository import SupabaseStageRepository
from src.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/agent/tests/integration"))
from test_gate_a_real_supabase import FakeStages, InjectedCrash  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--crash", default="")
    args = parser.parse_args()
    settings = replace(AgentSettings.from_env(), default_model="fake-gate-a")
    if settings.supabase_url != "http://127.0.0.1:54321":
        raise ValueError("Only the local test stack is allowed.")
    client = SupabaseClient(
        base_url=settings.supabase_url, service_role_key=settings.supabase_service_role_key or ""
    )
    registry = ProfileRegistry(
        profile_root=settings.profile_root, workspace_root=ROOT, allow_legacy_references=True
    )
    registry.load_all()
    runs, events = SupabaseRunRepository(client), SupabaseEventRepository(client)
    artifacts, proposals = SupabaseArtifactRepository(client), SupabaseProposalRepository(client)
    queue = SupabaseRunQueue(client)
    control = RunControlService(runs=runs, events=events, artifacts=artifacts, queue=queue)
    stages = SupabaseStageRepository(client, lease_seconds=5 if args.crash else 300)
    result_data = SupabaseResultDataRepository(
        client, profiles=registry, drawing_cache_root=args.runtime / "drawings"
    )
    worker = AgentWorker(
        runs=runs,
        queue=queue,
        publisher=control.publisher,
        artifacts=artifacts,
        proposals=proposals,
        result_data=result_data,
        durable_stages=stages,
    )
    worker.register(
        RunType.FULL_EXTRACTION,
        FullExtractionRunExecutor(
            settings=settings,
            profiles=registry,
            documents=SupabaseSourceDocumentProvider(client, cache_root=args.runtime / "sources"),
            artifacts=artifacts,
            publisher=control.publisher,
            runtime_root=args.runtime,
            project_assets=SupabaseProjectAssetStore(client),
            durable_stages=stages,
        ),
    )
    lease = await stages.claim()
    if not lease or lease.run_id != args.run_id:
        raise ValueError("Unexpected test queue item; do not run acceptance in parallel.")
    fake = FakeStages(args.crash)
    exit_code = 0
    with patch(
        "src.agent.extraction_agent.application.page_workflow_extraction.build_extraction_stage_dispatcher",
        return_value=fake,
    ):
        try:
            await worker._run_durable(lease)
        except InjectedCrash:
            exit_code = 42
    print(json.dumps({"calls": fake.calls, "crashed": exit_code == 42}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
