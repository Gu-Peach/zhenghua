from __future__ import annotations

import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = AGENT_ROOT.parents[1]
SOURCE_ROOT = AGENT_ROOT / "src"

for path in (str(SOURCE_ROOT), str(REPOSITORY_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
