"""Select the user's ignored extraction copy only inside a local test CLI process."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = "src.agent.extraction_agent"


def test_extraction_root(repository_root: Path = ROOT) -> Path:
    """Require an existing copy; never regenerate it or fall back to production."""
    target = (repository_root / "agent_test/extraction_agent").resolve()
    if not (target / "__init__.py").is_file() or not (target / "profiles").is_dir():
        raise FileNotFoundError(
            f"Local test extraction copy is missing: {target}. "
            "Copy services/agent/src/agent/extraction_agent there before running the local CLI."
        )
    return target


def activate_test_extraction(repository_root: Path = ROOT) -> Path:
    """Resolve absolute imports to the copy before any extraction module is loaded."""
    target = test_extraction_root(repository_root)
    for name, module in tuple(sys.modules.items()):
        if name == PACKAGE or name.startswith(PACKAGE + "."):
            origin = getattr(module, "__file__", None)
            if origin is None or not Path(origin).resolve().is_relative_to(target):
                raise RuntimeError(
                    f"Extraction module {name} is already loaded outside {target}; "
                    "start a fresh local CLI process to avoid mixing test and production code."
                )
    source_root = str((repository_root / "services/agent").resolve())
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    parent = importlib.import_module("src.agent")
    preferred = str(target.parent)
    parent.__path__ = [preferred, *(path for path in parent.__path__ if path != preferred)]
    importlib.invalidate_caches()
    importlib.import_module(PACKAGE)
    assert_test_extraction_loaded(repository_root)
    return target


def assert_test_extraction_loaded(repository_root: Path = ROOT) -> None:
    """Reject paid execution through an imported helper using the production implementation."""
    target = test_extraction_root(repository_root)
    loaded = loaded_extraction_root()
    if loaded != target:
        raise RuntimeError(f"Local extraction must run from {target}, currently loaded: {loaded}")


def loaded_extraction_root() -> Path:
    """Expose the actual imported implementation for local run diagnostics."""
    module = sys.modules.get(PACKAGE)
    origin = getattr(module, "__file__", None)
    if origin is None:
        raise RuntimeError("Extraction implementation has not been selected")
    return Path(origin).resolve().parent
