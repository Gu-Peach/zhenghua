from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = AGENT_ROOT.parents[1]
SOURCE_ROOT = AGENT_ROOT / "src"
for path in (str(SOURCE_ROOT), str(REPOSITORY_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from agent_service.agents.profile_router import ProfileRouterAgent  # noqa: E402
from agent_service.application.profile_assignment import ProfileAssignmentService  # noqa: E402
from agent_service.config import AgentSettings  # noqa: E402
from agent_service.graphs.profile_detection import (  # noqa: E402
    ProfileDetectionRuntime,
    run_profile_detection,
)
from agent_service.harness.model_gateway import OpenAICompatibleModelGateway  # noqa: E402
from agent_service.harness.retry import RetryPolicy  # noqa: E402
from agent_service.profiles import ProfileRegistry  # noqa: E402
from agent_service.tools.pdf_first_page import PdfFirstPageRenderer  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the M4 Profile Router against PDF physical page 1.",
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--run-id", default="profile-detection-manual")
    parser.add_argument("--project-id", default="manual-project")
    parser.add_argument("--base-url", default=os.getenv("AGENT_MODEL_BASE_URL"))
    parser.add_argument("--api-key", default=os.getenv("AGENT_MODEL_API_KEY"))
    parser.add_argument("--model", default=os.getenv("AGENT_DEFAULT_MODEL"))
    parser.add_argument("--confirm-profile", choices=["zh", "abb"])
    parser.add_argument("--confirmed-by", default="manual-tester")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    if not args.base_url or not args.model:
        raise SystemExit(
            "Missing model configuration. Set AGENT_MODEL_BASE_URL and AGENT_DEFAULT_MODEL "
            "or pass --base-url and --model."
        )
    settings = AgentSettings.from_env()
    registry = ProfileRegistry(
        profile_root=settings.profile_root,
        workspace_root=settings.workspace_root,
        allow_legacy_references=True,
    )
    registry.load_all()
    gateway = OpenAICompatibleModelGateway(
        base_url=args.base_url,
        api_key=args.api_key,
        default_model=args.model,
        timeout_seconds=settings.model_timeout_seconds,
        retry_policy=RetryPolicy(max_retries=settings.model_max_retries),
    )
    runtime = ProfileDetectionRuntime(
        renderer=PdfFirstPageRenderer(
            dpi=settings.profile_detection_dpi,
            max_pdf_bytes=settings.profile_max_pdf_bytes,
        ),
        router=ProfileRouterAgent(
            gateway=gateway,
            registry=registry,
            prompt_path=AGENT_ROOT / "prompts" / "profile_router.md",
            auto_select_threshold=settings.profile_auto_select_threshold,
        ),
    )
    result = await run_profile_detection(
        runtime=runtime,
        run_id=args.run_id,
        project_id=args.project_id,
        pdf_path=args.pdf,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    assignment_service = ProfileAssignmentService(registry)
    if result.assigned_profile is not None:
        assignment = assignment_service.from_automatic_detection(result)
        print("\nAssigned ProfileBinding:")
        print(json.dumps(assignment.model_dump(mode="json"), ensure_ascii=False, indent=2))
    elif args.confirm_profile:
        assignment = assignment_service.confirm(
            result,
            profile_key=args.confirm_profile,
            confirmed_by=args.confirmed_by,
        )
        print("\nConfirmed ProfileBinding:")
        print(json.dumps(assignment.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
