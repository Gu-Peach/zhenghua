from __future__ import annotations

import json
from pathlib import Path

from src.domain.models.improvement import EvalReport, EvaluationJudgement
from src.harness.model_gateway import ModelGateway, ModelRequest


class EvaluationJudgeAgent:
    def __init__(self, *, gateway: ModelGateway, prompt_path: Path) -> None:
        self._gateway = gateway
        self._prompt = prompt_path.read_text(encoding="utf-8")
        self._prompt += "\nOutput JSON Schema:\n" + json.dumps(
            EvaluationJudgement.model_json_schema(), ensure_ascii=False
        )

    async def judge(self, report: EvalReport) -> EvaluationJudgement:
        response = await self._gateway.invoke(
            ModelRequest(
                agent_name="evaluation_judge",
                run_id=report.eval_run_id,
                output_model=EvaluationJudgement,
                messages=[
                    {"role": "system", "content": self._prompt},
                    {"role": "user", "content": report.model_dump(mode="json")},
                ],
                metadata={"candidate_id": report.candidate_id},
            )
        )
        if not isinstance(response.parsed, EvaluationJudgement):
            raise TypeError("Evaluation judge returned an unexpected result.")
        return response.parsed
