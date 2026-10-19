"""Apply only this additive migration to the named local project; never run a data-edit RPC."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTAINER = "supabase_db_zhenghua_test"
VERSION = "20261018020000"
MIGRATIONS = {
    VERSION: "explain_connection_edits",
    "20261018030000": "connection_delete_no_snapshot",
    "20261018040000": "swap_endpoints_keep_origin",
    "20261018050000": "explain_rescan",
    "20261019010000": "rescan_scope_replacement",
}


def command(arguments: list[str], content: str | None = None) -> str:
    result = subprocess.run(
        arguments,
        input=content,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout


def sql(content: str) -> str:
    return command(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER,
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
        ],
        content,
    )


def fingerprints() -> str:
    return sql("""select jsonb_build_object(
      'profiles',(select md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' order by id),'')) from public.extraction_profiles t),
      'projects',(select md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' order by id),'')) from public.extraction_projects t),
      'rows',(select md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' order by id),'')) from public.extraction_connection_rows t));""").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration", choices=tuple(MIGRATIONS), default=VERSION)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the additive schema and record migration history atomically",
    )
    args = parser.parse_args()
    version = args.migration
    name = MIGRATIONS[version]
    migration = ROOT / f"supabase/migrations/{version}_{name}.sql"
    project = command(
        [
            "docker",
            "inspect",
            "--format",
            '{{index .Config.Labels "com.supabase.cli.project"}}',
            CONTAINER,
        ]
    ).strip()
    if project != "zhenghua_test":
        raise RuntimeError("Container project label mismatch; refusing schema change")
    source = migration.read_text(encoding="utf-8")
    existing = sql(
        f"select coalesce(array_to_string(statements,''),'') from supabase_migrations.schema_migrations where version='{version}';"
    )
    if existing.strip() and existing.strip() != source.strip():
        raise RuntimeError("Applied migration content differs from the local file")
    if not existing.strip() and not args.apply:
        print(
            json.dumps(
                {
                    "migration": version,
                    "applied": False,
                    "action": "Run with --apply to install this migration only",
                }
            )
        )
        return
    before = fingerprints()
    directory = (
        ROOT
        / ".runtime/migrations"
        / (version + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    )
    directory.mkdir(parents=True, exist_ok=False)
    if not existing.strip():
        backup = command(
            [
                "docker",
                "exec",
                CONTAINER,
                "pg_dump",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "--schema-only",
                "--schema=public",
            ]
        )
        (directory / "before-schema.sql").write_text(backup, encoding="utf-8")
        quoted = "'" + source.replace("'", "''") + "'"
        body = "\n".join(
            line
            for line in source.splitlines()
            if line.strip().lower() not in {"begin;", "commit;"}
        )
        sql(
            "begin;\n"
            + body
            + f"\ninsert into supabase_migrations.schema_migrations(version,name,statements) values('{version}','{name}',array[{quoted}]);\ncommit;"
        )
    verified = (
        sql(
            "select to_regclass('public.connection_edit_proposals') is not null and to_regprocedure('public.prepare_explain_connection_edit(jsonb)') is not null and to_regprocedure('public.decide_explain_connection_edit(jsonb)') is not null;"
        ).strip()
        == "t"
    )
    if version == "20261018030000":
        verified = (
            verified
            and sql(
                "select position('No deleted business-row snapshots' in pg_get_functiondef('public.manage_extraction_connection(jsonb)'::regprocedure))>0;"
            ).strip()
            == "t"
        )
    if version == "20261018040000":
        verified = (
            verified
            and sql(
                "select position('EDIT_ORIGIN_CHANGE_FORBIDDEN_REGENERATE' in pg_get_functiondef('public.decide_explain_connection_edit(jsonb)'::regprocedure))>0;"
            ).strip()
            == "t"
        )
    if version == "20261018050000":
        verified = (
            verified
            and sql(
                "select to_regclass('public.connection_rescan_runs') is not null and to_regclass('public.connection_rescan_assets') is not null and to_regprocedure('public.enqueue_connection_rescan(jsonb)') is not null and to_regprocedure('public.claim_connection_rescan(text)') is not null and to_regprocedure('public.decide_connection_rescan(jsonb)') is not null;"
            ).strip()
            == "t"
        )
    if version == "20261019010000":
        verified = (
            verified
            and sql(
                "select to_regprocedure('public.decide_connection_rescan_patch(jsonb)') is not null and to_regprocedure('public.rescan_replacement_contract()') is not null and rescan_replacement_contract()=1 and position('Deletion preview must equal' in pg_get_functiondef('public.decide_connection_rescan(jsonb)'::regprocedure))>0;"
            ).strip()
            == "t"
        )
    result = {
        "migration": version,
        "applied": verified,
        "already_applied": bool(existing.strip()),
        "business_rows_unchanged": before == fingerprints(),
        "checksum": hashlib.sha256(source.encode()).hexdigest(),
    }
    (directory / "receipt.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
