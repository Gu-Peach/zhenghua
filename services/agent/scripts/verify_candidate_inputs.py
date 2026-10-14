"""Explicit read-only candidate/dataset preflight; never executes models or releases."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.candidate_evaluation import CandidateEvaluationExecutor
from src.domain.enums import RunType
from src.main import create_app


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-id", required=True)
    args = parser.parse_args()
    app = create_app()
    candidate = await app.state.candidate_repository.get(args.candidate_id)
    executor = app.state.agent_worker._executors[RunType.PROFILE_EVALUATION]
    if not isinstance(executor, CandidateEvaluationExecutor):
        raise ValueError("Candidate evaluator is unavailable.")
    base, proposed = await executor._roots(candidate)
    cases = await executor._dataset(candidate, base)
    print(
        json.dumps(
            {
                "candidate_id": args.candidate_id,
                "candidate_checksum": proposed.profile.checksum,
                "cases": len(cases),
                "coverage": [{"kind": c.kind.value, "stage": c.stage.value} for c in cases],
                "model_calls": 0,
                "database_writes": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
