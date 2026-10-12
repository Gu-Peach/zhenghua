"""Explicit local development helper; no DSN is persisted or logged."""

import json
import subprocess
from urllib.parse import quote


def local_dsn(container: str) -> str:
    if not container.startswith("supabase_db_") or any(
        char.isspace() for char in container
    ):
        raise ValueError("Explicit local Supabase DB container is required")
    values = json.loads(
        subprocess.check_output(
            ["docker", "inspect", container, "--format", "{{json .Config.Env}}"],
            text=True,
        )
    )
    env = dict(item.split("=", 1) for item in values if "=" in item)
    port = (
        subprocess.check_output(["docker", "port", container, "5432/tcp"], text=True)
        .strip()
        .splitlines()[0]
        .rsplit(":", 1)[1]
    )
    return f"postgresql://{quote(env.get('POSTGRES_USER', 'postgres'), safe='')}:{quote(env['POSTGRES_PASSWORD'], safe='')}@127.0.0.1:{port}/{env.get('POSTGRES_DB', 'postgres')}"
