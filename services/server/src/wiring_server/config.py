from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    service_key: str
    agent_url: str = "http://127.0.0.1:8100"
    agent_token: str = ""
    web_origin: str = "http://localhost:5174"
    max_pdf_bytes: int = 200 * 1024 * 1024
    database_url: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        root = Path(__file__).resolve().parents[4]
        values: dict[str, str] = {}
        # Only infrastructure credentials are shared; Agent/model configuration stays separate.
        for path in (root / "services/agent/.env", root / "services/server/.env"):
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        key, raw_value = line.split("=", 1)
                        values[key.strip()] = raw_value.strip().strip("\"'")

        def value(*keys: str, default: str = "") -> str:
            for key in keys:
                found = os.environ.get(key) or values.get(key)
                if found:
                    return found
            return default

        return cls(
            supabase_url=value("SERVER_SUPABASE_URL", "SUPABASE_URL").rstrip("/"),
            service_key=value(
                "SERVER_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY"
            ),
            agent_url=value("SERVER_AGENT_URL", default="http://127.0.0.1:8100").rstrip(
                "/"
            ),
            agent_token=value("AGENT_INTERNAL_TOKEN"),
            web_origin=value("SERVER_WEB_ORIGIN", default="http://localhost:5174"),
            database_url=value("SERVER_DATABASE_URL"),
        )
