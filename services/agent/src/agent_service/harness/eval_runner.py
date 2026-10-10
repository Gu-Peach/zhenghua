from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from ..domain.enums import EvalCaseKind
from ..domain.models.improvement import (
    EvalCaseResult,
    EvalMetrics,
    EvalReport,
    ImprovementCase,
)

EvalExecutor = Callable[[ImprovementCase], Awaitable[EvalCaseResult]]


class EvalRunner:
    """Provider-neutral baseline/candidate runner with deterministic field metrics."""

    async def compare(
        self,
        *,
        candidate_id: str,
        cases: list[ImprovementCase],
        baseline_executor: EvalExecutor,
        candidate_executor: EvalExecutor,
    ) -> EvalReport:
        if not cases:
            raise ValueError("Evaluation requires at least one case.")
        baseline_results = [await baseline_executor(case) for case in cases]
        candidate_results = [await candidate_executor(case) for case in cases]
        self._validate_case_alignment(cases, baseline_results, candidate_results)
        return EvalReport(
            candidate_id=candidate_id,
            baseline=self.metrics(baseline_results),
            candidate=self.metrics(candidate_results),
            baseline_results=baseline_results,
            candidate_results=candidate_results,
        )

    @classmethod
    def metrics(cls, results: list[EvalCaseResult]) -> EvalMetrics:
        if not results:
            return EvalMetrics(
                total_cases=0,
                passed_cases=0,
                target_pass_rate=0.0,
                protected_regressions=0,
                negative_hallucinations=0,
                schema_valid_rate=0.0,
                field_precision=0.0,
                field_recall=0.0,
                total_cost=0.0,
                p95_duration_seconds=0.0,
            )
        passed = [item for item in results if cls._passes(item)]
        targets = [item for item in results if item.kind == EvalCaseKind.TARGET]
        protected = [item for item in results if item.kind == EvalCaseKind.PROTECTED]
        negatives = [item for item in results if item.kind == EvalCaseKind.NEGATIVE]
        true_positive = 0
        predicted = 0
        expected = 0
        for item in results:
            expected_fields = _leaf_fields(item.expected)
            actual_fields = _leaf_fields(item.actual)
            expected += len(expected_fields)
            predicted += len(actual_fields)
            true_positive += sum(
                1 for key, value in actual_fields.items() if expected_fields.get(key) == value
            )
        durations = sorted(item.duration_seconds for item in results)
        p95_index = max(0, math.ceil(len(durations) * 0.95) - 1)
        return EvalMetrics(
            total_cases=len(results),
            passed_cases=len(passed),
            target_pass_rate=(
                sum(1 for item in targets if cls._passes(item)) / len(targets) if targets else 1.0
            ),
            protected_regressions=sum(1 for item in protected if not cls._passes(item)),
            negative_hallucinations=sum(
                1 for item in negatives if _has_content(item.actual) and not _has_content(item.expected)
            ),
            schema_valid_rate=sum(1 for item in results if item.schema_valid) / len(results),
            field_precision=true_positive / predicted if predicted else 1.0,
            field_recall=true_positive / expected if expected else 1.0,
            total_cost=sum(item.cost for item in results),
            p95_duration_seconds=durations[p95_index],
        )

    @staticmethod
    def _passes(result: EvalCaseResult) -> bool:
        return result.error is None and result.schema_valid and result.expected == result.actual

    @staticmethod
    def _validate_case_alignment(
        cases: list[ImprovementCase],
        baseline: list[EvalCaseResult],
        candidate: list[EvalCaseResult],
    ) -> None:
        expected_ids = [item.case_id for item in cases]
        if [item.case_id for item in baseline] != expected_ids:
            raise ValueError("Baseline results do not align with the evaluation dataset.")
        if [item.case_id for item in candidate] != expected_ids:
            raise ValueError("Candidate results do not align with the evaluation dataset.")


class InMemoryEvalRepository:
    def __init__(self) -> None:
        self._reports: dict[str, EvalReport] = {}
        self._lock = asyncio.Lock()

    async def put(self, report: EvalReport) -> None:
        async with self._lock:
            self._reports[report.eval_run_id] = report.model_copy(deep=True)

    async def get(self, eval_run_id: str) -> EvalReport:
        async with self._lock:
            report = self._reports.get(eval_run_id)
        if report is None:
            raise KeyError(eval_run_id)
        return report.model_copy(deep=True)


def _leaf_fields(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_leaf_fields(item, child))
        return result
    if isinstance(value, list):
        result = {}
        for index, item in enumerate(value):
            child = f"{prefix}[{index}]"
            result.update(_leaf_fields(item, child))
        return result
    return {prefix: value}


def _has_content(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return True
