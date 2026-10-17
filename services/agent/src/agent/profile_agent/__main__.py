"""Local independent developer entry; model calls require --allow-real-model."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from .factory import create_profile_agent
from .models import DraftCreate, ProfileActor, ProfileTurn
from .validation import validate_draft


async def run() -> None:
    parser = argparse.ArgumentParser(description="独立Profile Agent；只修改本地隔离草稿，不正式发布")
    parser.add_argument("--actor", type=UUID, required=True, help="本地开发身份；生产接口必须由鉴权宿主提供")
    parser.add_argument("--state-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--key", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--source-profile")
    create.add_argument("--source-version")
    create.add_argument("--draft-id", type=UUID, default=None)
    for name in (
        "show",
        "validate",
        "audit",
        "read",
        "attach",
        "ask",
        "confirm",
        "confirm-expected",
        "export",
    ):
        command = commands.add_parser(name)
        command.add_argument("draft", type=UUID)
        if name in {"attach", "ask", "confirm", "confirm-expected", "export"}:
            command.add_argument("--revision", type=int, required=True)
        if name == "read":
            command.add_argument("--file", required=True)
            command.add_argument("--offset", type=int, default=0)
        elif name == "attach":
            command.add_argument("--image", type=Path, required=True)
        elif name == "ask":
            command.add_argument("--message", required=True)
            command.add_argument("--edit", action="store_true", help="本轮明确要求修改草稿")
            command.add_argument("--allow-real-model", action="store_true", required=True)
            command.add_argument("--observations", type=Path, help="用户提供的实际输出/期望对照JSON数组")
            command.add_argument("--turn-id", type=UUID, default=None)
        elif name == "confirm":
            command.add_argument("--proposal", type=UUID, required=True)
            decision = command.add_mutually_exclusive_group(required=True)
            decision.add_argument("--accept", action="store_true")
            decision.add_argument("--reject", action="store_true")
        elif name == "confirm-expected":
            command.add_argument(
                "--checksums", type=Path, required=True, help="已人工查看的Expected路径到checksum映射JSON"
            )
    args = parser.parse_args()
    agent = create_profile_agent(state_root=args.state_root)
    actor = ProfileActor(user_id=args.actor)
    result: Any
    if args.command == "create":
        result = await agent.create(
            DraftCreate(
                draft_id=args.draft_id or uuid4(),
                key=args.key,
                display_name=args.name,
                source_profile=args.source_profile,
                source_version=args.source_version,
            ),
            actor,
        )
    elif args.command == "show":
        result = agent.store.get(args.draft, actor)
    elif args.command == "read":
        result = agent.store.read(args.draft, actor, args.file, args.offset)
    elif args.command == "attach":
        result = agent.store.attach(
            args.draft, actor, args.revision, uuid4(), args.image.name, args.image.read_bytes()
        )
    elif args.command == "ask":
        observations = json.loads(args.observations.read_text(encoding="utf-8")) if args.observations else []
        result = await agent.ask(
            args.draft,
            ProfileTurn(
                turn_id=args.turn_id or uuid4(),
                message=args.message,
                intent="edit" if args.edit else "discuss",
                expected_revision=args.revision,
                observations=observations,
            ),
            actor,
        )
    elif args.command == "confirm":
        result = await agent.confirm(args.draft, args.proposal, args.revision, args.accept, actor)
    elif args.command == "confirm-expected":
        result = agent.store.confirm_expected(
            args.draft, actor, args.revision, json.loads(args.checksums.read_text(encoding="utf-8"))
        )
    elif args.command == "audit":
        result = agent.store.audit(args.draft, actor)
    elif args.command == "validate":
        root, meta = agent.store.root_for(args.draft, actor)
        result = validate_draft(root, meta)
    else:
        result = await agent.export(args.draft, args.revision, actor)
    value = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
