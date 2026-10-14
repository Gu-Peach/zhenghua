from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

from src.domain.models.improvement import AcceptedFeedback, Diagnosis
from src.harness.model_gateway import ModelGateway, ModelRequest


class ImprovementDiagnoserAgent:
    def __init__(self, *, gateway: ModelGateway, prompt_path: Path) -> None:
        self._gateway = gateway
        self._prompt = prompt_path.read_text(encoding="utf-8")
        # output_model validates locally; it does not send the contract to the provider.
        # Generate the prompt contract from the same model to avoid field/enum drift.
        self._prompt += "\nOutput JSON Schema:\n" + json.dumps(
            Diagnosis.model_json_schema(), ensure_ascii=False
        )

    async def diagnose(self, feedback: AcceptedFeedback) -> Diagnosis:
        content: list[dict[str, Any]] = [{"type": "text", "text": feedback.model_dump_json()}]
        paths: set[Path] = set()
        for artifact in feedback.context.get("artifacts", []):
            bundle = artifact.get("bundle", {})
            requests = bundle.get("page_scan_requests", []) + bundle.get("cross_page_requests", [])
            if artifact.get("request"):
                requests.append(artifact["request"])
            for request in requests:
                page = request.get("page") or request.get("target_page") or {}
                if page.get("image_path"):
                    paths.add(Path(page["image_path"]))
        root = feedback.context.get("profile_root")
        if root:
            images = await asyncio.to_thread(lambda: sorted(Path(root).rglob("*.png")))
            paths.update(images[:2])
            feedback.context["visual_coverage"] = {
                "fewshot_total": len(images),
                "fewshot_included": min(2, len(images)),
            }
        for path in sorted(paths):
            if not path.is_file() or path.is_symlink():
                continue
            from src.agent.extraction_agent.infrastructure.zh_vlm_stages import _prepare_few_shot_image

            data, media_type = await asyncio.to_thread(_prepare_few_shot_image, path, max_side=1600)
            content.append({"type": "text", "text": f"Evidence image: {path.name}"})
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{base64.b64encode(data).decode()}",
                        "detail": "auto",
                    },
                }
            )
        content[0]["text"] = json.dumps(feedback.model_dump(mode="json"), ensure_ascii=False)
        response = await self._gateway.invoke(
            ModelRequest(
                agent_name="improvement_diagnoser",
                run_id=f"improvement:{feedback.feedback_id}",
                output_model=Diagnosis,
                messages=[
                    {"role": "system", "content": self._prompt},
                    {"role": "user", "content": content},
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
