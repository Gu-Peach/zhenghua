from __future__ import annotations

from pathlib import Path

from ..domain.models.improvement import (
    AcceptedFeedback,
    Diagnosis,
    ProfilePatchModelOutput,
)
from ..harness.model_gateway import ModelGateway, ModelRequest


class ProfilePatchBuilderAgent:
    def __init__(self, *, gateway: ModelGateway, prompt_path: Path) -> None:
        self._gateway = gateway
        self._prompt = prompt_path.read_text(encoding="utf-8")

    async def build(
        self,
        *,
        feedback: list[AcceptedFeedback],
        diagnoses: list[Diagnosis],
    ) -> ProfilePatchModelOutput:
        response = await self._gateway.invoke(
            ModelRequest(
                agent_name="profile_patch_builder",
                run_id=f"candidate:{feedback[0].profile.key}:{feedback[0].profile.version}",
                output_model=ProfilePatchModelOutput,
                messages=[
                    {"role": "system", "content": self._prompt},
                    {
                        "role": "user",
                        "content": {
                            "feedback": [item.model_dump(mode="json") for item in feedback],
                            "diagnoses": [item.model_dump(mode="json") for item in diagnoses],
                        },
                    },
                ],
            )
        )
        if not isinstance(response.parsed, ProfilePatchModelOutput):
            raise TypeError("Profile patch builder returned an unexpected result.")
        return response.parsed
