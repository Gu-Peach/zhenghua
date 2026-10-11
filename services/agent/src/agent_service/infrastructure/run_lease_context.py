"""Task-local fencing token, never shared between workers or HTTP requests."""
from contextvars import ContextVar

from ..domain.models.stage_persistence import RunLease

current_run_lease: ContextVar[RunLease | None] = ContextVar("current_run_lease", default=None)
