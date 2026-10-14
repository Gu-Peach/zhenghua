from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_retries: int = 2
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 15.0

    def delay_for(self, retry_index: int) -> float:
        if retry_index < 0:
            raise ValueError("retry_index must be non-negative.")
        return float(min(self.max_backoff_seconds, self.initial_backoff_seconds * (2**retry_index)))


def is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429} or status_code >= 500
