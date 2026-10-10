from __future__ import annotations

import re
from collections import defaultdict

from ..domain.models.improvement import AcceptedFeedback, Diagnosis, FailureSignature


class ImprovementIntake:
    def validate(self, feedback: AcceptedFeedback) -> None:
        if not feedback.accepted:
            raise ValueError("Only accepted feedback can enter improvement intake.")
        if not feedback.evidence_ids or not feedback.stage_artifact_ids or not feedback.trace_ids:
            raise ValueError("Improvement feedback requires evidence, stage artifacts, and traces.")

    def signature(self, feedback: AcceptedFeedback, diagnosis: Diagnosis) -> FailureSignature:
        self.validate(feedback)
        pattern_source = " ".join(sorted(str(key) for key in feedback.after))
        pattern = re.sub(r"[^a-z0-9_.:-]+", "-", pattern_source.lower()).strip("-") or "generic"
        return FailureSignature(
            profile_key=feedback.profile.key,
            profile_version=feedback.profile.version,
            affected_stage=diagnosis.affected_stage[0],
            category=diagnosis.category,
            pattern=pattern,
            model_name=feedback.model_name,
            prompt_checksum=feedback.prompt_checksum,
        )

    def candidate_groups(
        self,
        items: list[tuple[AcceptedFeedback, Diagnosis]],
        *,
        minimum_count: int = 2,
    ) -> list[list[tuple[AcceptedFeedback, Diagnosis]]]:
        grouped: dict[str, list[tuple[AcceptedFeedback, Diagnosis]]] = defaultdict(list)
        for feedback, diagnosis in items:
            signature = self.signature(feedback, diagnosis)
            grouped[signature.key].append((feedback, diagnosis))
        return [
            group
            for group in grouped.values()
            if len(group) >= minimum_count or any(item.severity in {"high", "critical"} for item, _ in group)
        ]
