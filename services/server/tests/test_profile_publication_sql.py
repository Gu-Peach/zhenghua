"""Opt-in SQL integration in disposable databases, never the running business database."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[3]
CONTAINER = ""
pytestmark = pytest.mark.skipif(
    os.environ.get("PROFILE_PUBLICATION_SQL_TEST") != "1",
    reason="explicit disposable SQL integration only",
)


def sql(database: str, statement: str) -> str:
    assert database == "postgres" or re.fullmatch(
        r"profile_publish_test_[a-f0-9]{32}", database
    )
    assert re.fullmatch(r"codex-profile-sql-[a-f0-9]{32}", CONTAINER)
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER,
            "psql",
            "-U",
            "postgres",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
        ],
        input=statement,
        capture_output=True,
        encoding="utf-8",
        timeout=25,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


@pytest.fixture(scope="module", autouse=True)
def isolated_cluster():
    global CONTAINER
    CONTAINER = "codex-profile-sql-" + uuid4().hex
    image = "public.ecr.aws/supabase/postgres:17.6.1.106"
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "--label",
            "codex.task=profile-wizard-sql",
            "--network",
            "none",
            "--user",
            "postgres",
            "--tmpfs",
            "/tmp:rw,mode=1777",
            "--entrypoint",
            "/bin/sh",
            image,
            "-c",
            "initdb -D /tmp/profile-data -A trust -U postgres >/tmp/init.log && exec postgres -D /tmp/profile-data -c shared_preload_libraries='' -c listen_addresses=''",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    try:
        for _ in range(20):
            result = subprocess.run(
                ["docker", "exec", CONTAINER, "pg_isready", "-U", "postgres"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                break
            time.sleep(0.5)
        else:
            logs = subprocess.run(
                ["docker", "logs", CONTAINER], capture_output=True, text=True, check=False
            )
            raise AssertionError(logs.stdout + logs.stderr)
        sql(
            "postgres",
            "create role anon; create role authenticated; create role service_role bypassrls;",
        )
        yield
    finally:
        assert re.fullmatch(r"codex-profile-sql-[a-f0-9]{32}", CONTAINER)
        label = subprocess.check_output(
            [
                "docker",
                "inspect",
                "--format",
                '{{index .Config.Labels "codex.task"}}',
                CONTAINER,
            ],
            text=True,
        ).strip()
        assert label == "profile-wizard-sql"
        subprocess.run(
            ["docker", "rm", "-f", CONTAINER],
            capture_output=True,
            check=True,
            timeout=20,
        )


@pytest.mark.parametrize("legacy", [False, True])
def test_publication_migration_empty_and_legacy_snapshot(legacy):
    database = "profile_publish_test_" + uuid4().hex
    sql("postgres", f'create database "{database}";')
    try:
        sql(
            database,
            """
          create schema auth;
          create table auth.users(id uuid primary key);
          create function auth.uid() returns uuid language sql as
            'select nullif(current_setting(''request.jwt.claim.sub'',true),'''')::uuid';
          grant usage on schema auth to authenticated;
          insert into auth.users values ('00000000-0000-0000-0000-000000000011'),('00000000-0000-0000-0000-000000000012');
        """,
        )
        sql(
            database,
            (
                ROOT
                / "supabase/migrations/20261014000000_create_simple_extraction_business_tables.sql"
            ).read_text(encoding="utf-8"),
        )
        if legacy:
            sql(
                database,
                "insert into extraction_profiles(profile_key,profile_version,display_name,checksum,resource_ref,created_by) values('legacy','1.0.0','Legacy','sha256:'||repeat('0',64),'local://legacy/profile.json','00000000-0000-0000-0000-000000000011');",
            )
        sql(
            database,
            (
                ROOT
                / "supabase/migrations/20261017010000_profile_wizard_publication.sql"
            ).read_text(encoding="utf-8"),
        )
        sql(
            database,
            """
          do $$ declare actor uuid := '00000000-0000-0000-0000-000000000011';
          other_actor uuid := '00000000-0000-0000-0000-000000000012';
          ref text := 'storage://project-assets/profiles/'||actor||'/sample/1.0.0/'||repeat('a',64)||'.zip';
          first jsonb; second jsonb;
          begin
            first := public.publish_extraction_profile(actor,'sample','1.0.0','样例','sha256:'||repeat('a',64),ref);
            second := public.publish_extraction_profile(actor,'sample','1.0.0','样例','sha256:'||repeat('a',64),ref);
            assert first->>'id'=second->>'id';
            assert (select count(*) from extraction_profiles where profile_key='sample')=1;
            begin
              perform public.publish_extraction_profile(other_actor,'sample','1.0.1','跨用户','sha256:'||repeat('b',64),
                'storage://project-assets/profiles/'||other_actor||'/sample/1.0.1/'||repeat('b',64)||'.zip');
              raise exception 'Cross-owner publication unexpectedly succeeded';
            exception when sqlstate 'PT403' then null; end;
            begin
              perform public.publish_extraction_profile(actor,'sample','1.0.0','改内容','sha256:'||repeat('b',64),
                'storage://project-assets/profiles/'||actor||'/sample/1.0.0/'||repeat('b',64)||'.zip');
              raise exception 'Version overwrite unexpectedly succeeded';
            exception when sqlstate 'PT409' then null; end;
            begin
              update extraction_profiles set display_name='覆盖' where profile_key='sample';
              raise exception 'Published resource unexpectedly mutable';
            exception when sqlstate 'PT409' then null; end;
          end $$;
          set role authenticated;
          select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000011',false);
          do $$ begin
            begin
              perform public.publish_extraction_profile('00000000-0000-0000-0000-000000000011','unauthorized','1.0.0','不应发布','sha256:'||repeat('a',64),'bad');
              raise exception 'Browser role called trusted RPC';
            exception when insufficient_privilege then null; end;
            begin
              insert into extraction_profiles(profile_key,profile_version,display_name,checksum,resource_ref,created_by)
              values('bypass','1.0.0','越权','sha256:'||repeat('a',64),'storage://bad','00000000-0000-0000-0000-000000000011');
              raise exception 'Browser bypassed publication';
            exception when sqlstate 'PT403' then null; end;
          end $$;
          reset role;
        """,
        )
        if legacy:
            assert (
                sql(
                    database,
                    "select resource_ref from extraction_profiles where profile_key='legacy';",
                ).strip()
                == "local://legacy/profile.json"
            )
    finally:
        # Only this test's freshly generated, verified database name can be dropped.
        sql("postgres", f'drop database "{database}";')
