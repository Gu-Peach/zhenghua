"""Explicit local model invocation; no server, extraction job or data writes."""

from __future__ import annotations

import argparse
import asyncio
from time import perf_counter
from uuid import UUID, uuid4

from src.config import AgentSettings
from src.domain.errors import AgentServiceError

from .factory import create_explain_agent
from .models import ConnectionQuery, ExplainActor, ExplainContext, ExplainError, ExplainTurn


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only row/page Explain Agent with retrieval tools")
    parser.add_argument("--project-id", type=UUID, required=True)
    parser.add_argument("--connection-id", type=UUID)
    parser.add_argument("--drawing-page")
    parser.add_argument("--pdf-page-number", type=int)
    parser.add_argument("--target-drawing-page")
    parser.add_argument("--principle-number")
    parser.add_argument("--start-terminal")
    parser.add_argument("--end-terminal")
    parser.add_argument("--workspace-code")
    parser.add_argument(
        "--actor-id", type=UUID, required=True, help="Trusted local caller's existing owner UUID"
    )
    parser.add_argument("--batch-id")
    parser.add_argument("--record-version", type=int)
    parser.add_argument("--question", default="请解释这一行的端子连接和信息来源。")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--allow-real-model", action="store_true")
    args = parser.parse_args()
    if not args.allow_real_model:
        parser.error("Real model calls require --allow-real-model; no database/model request was made.")
    filters = {
        key: getattr(args, key)
        for key in (
            "drawing_page",
            "pdf_page_number",
            "target_drawing_page",
            "principle_number",
            "start_terminal",
            "end_terminal",
            "workspace_code",
        )
        if getattr(args, key) is not None
    }
    if bool(args.connection_id) == bool(filters):
        parser.error("Provide either --connection-id or exact query filters.")

    async def run() -> None:
        settings = AgentSettings.from_env()
        agent = create_explain_agent(settings)
        actor = ExplainActor(user_id=args.actor_id)
        conversation = uuid4()
        question = args.question
        while question:
            started = perf_counter()
            result = await agent.ask(
                ExplainTurn(
                    project_id=args.project_id,
                    connection_id=args.connection_id,
                    query=ConnectionQuery(**filters) if filters else None,
                    conversation_id=conversation,
                    batch_id=args.batch_id,
                    record_version=args.record_version,
                    message=question,
                ),
                actor,
            )
            print(result.answer)
            context = result.context
            batch = context.row.batch_id if isinstance(context, ExplainContext) else context.batch_id
            print(f"model={settings.default_model}; duration={perf_counter() - started:.2f}s; batch={batch}")
            if not args.interactive:
                return
            question = (await asyncio.to_thread(input, "追问（空行退出）：")).strip()

    try:
        asyncio.run(run())
    except (ExplainError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    except AgentServiceError:
        parser.exit(1, "Data/model service unavailable; no business records were changed.\n")


if __name__ == "__main__":
    main()
