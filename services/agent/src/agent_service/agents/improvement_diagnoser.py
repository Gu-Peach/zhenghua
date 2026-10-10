from __future__ import annotations

from pathlib import Path

from ..domain.models.improvement import AcceptedFeedback, Diagnosis
from ..harness.model_gateway import ModelGateway, ModelRequest


class ImprovementDiagnoserAgent:
    def __init__(self, *, gateway: ModelGateway, prompt_path: Path) -> None:
        self._gateway = gateway
        self._prompt = prompt_path.read_text(encoding="utf-8")

    async def diagnose(self, feedback: AcceptedFeedback) -> Diagnosis:
        response = await self._gateway.invoke(
            ModelRequest(
                agent_name="improvement_diagnoser",
                run_id=f"improvement:{feedback.feedback_id}",
                output_model=Diagnosis,
                messages=[
                    {"role": "system", "content": self._prompt},
                    {"role": "user", "content": feedback.model_dump(mode="json")},
                ],
                metadata={
                    "feedback_id": feedback.feedback_id,
                    "profile": feedback.profile.model_dump(mode="json"),
                },
            )
        )
        if not isinstance(response.parsed, Diagnosis):
            raise TypeError("Improvement diagnoser returned an unexpected result.")
        return response.parsed
