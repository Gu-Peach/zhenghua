"""Disposable PostgreSQL empty/legacy migration verification, no VLM or real user data."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
CONTAINER = "supabase_db_zhenghua_test"


def command(*args: str, sql: str | None = None) -> str:
    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, *args],
        input=sql,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    return result.stdout


def execute(database: str, sql: str) -> str:
    if not re.fullmatch(r"gate_a_(empty|legacy)_[a-f0-9]{32}", database):
        raise ValueError("Refusing a non-disposable database target.")
    return command("psql", "-U", "postgres", "-d", database, "-v", "ON_ERROR_STOP=1", "-At", sql=sql)


def main() -> None:
    if os.getenv("AGENT_TEST_REAL_SUPABASE") != "true":
        raise SystemExit("Set AGENT_TEST_REAL_SUPABASE=true for disposable database verification.")
    migrations = sorted((ROOT / "supabase/migrations").glob("*.sql"))
    for scenario in ("empty", "legacy"):
        database = f"gate_a_{scenario}_{uuid4().hex}"
        command("createdb", "-U", "postgres", database)
        try:
            execute(
                database,
                (ROOT / "services/agent/tests/assets/gate_a_supabase_schema_fixture.sql").read_text(
                    encoding="utf-8"
                ),
            )
            seeded = False
            for migration in migrations:
                if scenario == "legacy" and not seeded and migration.name.startswith("20261010"):
                    execute(
                        database,
                        "insert into public.wiring_tables(job_id,group_id,source_filename,title,records) "
                        "values('gate-a-synthetic','legacy','synthetic.pdf','synthetic legacy',"
                        '\'[ {"line_number":"synthetic-keep"} ]\'::jsonb);',
                    )
                    seeded = True
                execute(database, "begin;\n" + migration.read_text(encoding="utf-8") + "\ncommit;")
            if seeded:
                assert (
                    execute(
                        database,
                        "select records->0->>'line_number' from public.wiring_tables "
                        "where job_id='gate-a-synthetic';",
                    ).strip()
                    == "synthetic-keep"
                )
            checks = execute(
                database,
                "select count(*) from pg_proc where pronamespace='public'::regnamespace "
                "and proname='gate_a_finalize';",
            )
            assert checks.strip() == "1"
            if any(path.name.startswith("20261011000000") for path in migrations):
                execute(database, (ROOT / "services/agent/tests/assets/gate_b_atomic_creation.sql")
                        .read_text(encoding="utf-8"))
            print(f"PASS {scenario}: {len(migrations)} ordered migrations; legacy data preserved")
        finally:
            # Only the exact UUID database created by this iteration can be removed.
            assert re.fullmatch(r"gate_a_(empty|legacy)_[a-f0-9]{32}", database)
            command("dropdb", "-U", "postgres", database)


if __name__ == "__main__":
    main()
