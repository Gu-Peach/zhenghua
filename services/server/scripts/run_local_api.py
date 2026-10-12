"""Explicit local Supabase transaction setup; no credentials are saved or printed."""

import argparse
import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/server/src"))
from wiring_server.config import Settings
from wiring_server.local_supabase import local_dsn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supabase-container", required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    settings = replace(
        Settings.from_env(), database_url=local_dsn(args.supabase_container)
    )
    spec = importlib.util.spec_from_file_location(
        "local_business_api", ROOT / "apps/api/src/main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    uvicorn.run(module.create_app(settings), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
