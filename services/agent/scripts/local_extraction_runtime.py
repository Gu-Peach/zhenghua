"""Select test or formal extraction sources only inside a local CLI process."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Literal, cast

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = "src.agent.extraction_agent"
AgentSource = Literal["test", "formal"]


def add_agent_source_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent-source", choices=["test", "formal"], default="test",
        help="Local code and Profile source: test=agent_test (default), formal=services/agent/src",
    )


def agent_source_from_cli() -> AgentSource:
    """Choose code before extraction imports; the main parser still validates all arguments."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    add_agent_source_argument(parser)
    args, _ = parser.parse_known_args()
    return cast(AgentSource, args.agent_source)


def formal_extraction_root(repository_root: Path = ROOT) -> Path:
    target = (repository_root / "services/agent/src/agent/extraction_agent").resolve()
    if not (target / "__init__.py").is_file() or not (target / "profiles").is_dir():
        raise FileNotFoundError(f"Formal local extraction source is missing: {target}")
    return target


def extraction_root(source: AgentSource, repository_root: Path = ROOT) -> Path:
    if source == "test":
        return test_extraction_root(repository_root)
    if source == "formal":
        return formal_extraction_root(repository_root)
    raise ValueError(f"Unknown local Agent source: {source}")


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
    return activate_extraction("test", repository_root)


def activate_extraction(source: AgentSource, repository_root: Path = ROOT) -> Path:
    """Resolve absolute imports to the selected source before extraction modules load."""
    target = extraction_root(source, repository_root)
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
    assert_extraction_loaded(source, repository_root)
    return target


def assert_test_extraction_loaded(repository_root: Path = ROOT) -> None:
    assert_extraction_loaded("test", repository_root)


def assert_extraction_loaded(source: AgentSource, repository_root: Path = ROOT) -> None:
    """Require code to match the explicitly selected local source before paid execution."""
    target = extraction_root(source, repository_root)
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
