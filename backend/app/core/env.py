from __future__ import annotations

import os
import re
from pathlib import Path


def load_env_files(paths: list[Path] | None = None) -> None:
    """Load .env files without overriding real environment variables."""

    values: dict[str, str] = {}
    for path in paths or default_env_paths():
        if path.is_file():
            values.update(parse_env_file(path))

    for key, value in values.items():
        os.environ.setdefault(key, value)


def default_env_paths() -> list[Path]:
    backend_dir = Path(__file__).resolve().parents[2]
    project_dir = backend_dir.parent
    return [project_dir / ".env", backend_dir / ".env"]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not _VALID_ENV_KEY.fullmatch(key):
            continue
        values[key] = _clean_env_value(value)
    return values


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        quote = value[0]
        unquoted = value[1:-1]
        if quote == '"':
            unquoted = unquoted.replace("\\n", "\n").replace("\\t", "\t")
        return unquoted

    comment_index = value.find(" #")
    if comment_index >= 0:
        value = value[:comment_index].rstrip()
    return value


_VALID_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
