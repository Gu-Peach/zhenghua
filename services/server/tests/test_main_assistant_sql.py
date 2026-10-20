"""Disposable Postgres integration; never targets the business database."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from test_profile_publication_sql import isolated_cluster as isolated_cluster, sql

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(
    os.environ.get("ASSISTANT_SQL_TEST") != "1", reason="opt-in disposable database"
)
OWNER = "00000000-0000-0000-0000-000000000011"
OTHER = "00000000-0000-0000-0000-000000000012"


@pytest.mark.parametrize("legacy", [False, True])
def test_assistant_migration_rls_replay_and_leases(legacy):
    database = "profile_publish_test_" + uuid4().hex
    sql("postgres", f'create database "{database}";')
    try:
        sql(
            database,
            f"""
          create schema auth;
          create table auth.users(id uuid primary key);
          create function auth.uid() returns uuid language sql as
            'select nullif(current_setting(''request.jwt.claim.sub'',true),'''')::uuid';
          grant usage on schema auth to authenticated;
          insert into auth.users values ('{OWNER}'),('{OTHER}');
          create table public.extraction_projects(id uuid primary key, owner_id uuid, name text);
        """,
        )
        project, conversation, turn = map(str, (uuid4(), uuid4(), uuid4()))
        if legacy:
            sql(
                database,
                f"insert into extraction_projects values('{project}','{OWNER}','原有项目');",
            )
        sql(
            database,
            (ROOT / "supabase/migrations/20261019020000_main_assistant.sql").read_text(
                encoding="utf-8"
            ),
        )
        sql(
            database,
            f"insert into assistant_conversations(id,owner_id,title) values('{conversation}','{OWNER}','跨项目对话');",
        )
        assert (
            sql(
                database,
                f"set role authenticated; set request.jwt.claim.sub='{OTHER}'; select count(*) from assistant_conversations;",
            )
            .strip()
            .endswith("0")
        )
        assert (
            sql(
                database,
                f"set role authenticated; set request.jwt.claim.sub='{OWNER}'; select count(*) from assistant_conversations;",
            )
            .strip()
            .endswith("1")
        )
        for statement in [
            f"set role authenticated; insert into assistant_conversations(id,owner_id,title) values('{uuid4()}','{OTHER}','越权');",
            f"select assistant_begin_turn('{OTHER}','{conversation}','{turn}','{{}}','body','token');",
            f"set role authenticated; select assistant_begin_turn('{OWNER}','{conversation}','{turn}','{{}}','body','token');",
        ]:
            with pytest.raises(AssertionError):
                sql(database, statement)
        begin = f"select assistant_begin_turn('{OWNER}','{conversation}','{turn}','{{}}','body','token')->>'status';"
        assert sql(database, begin).strip() == "running"
        with pytest.raises(AssertionError):
            sql(database, begin)
        sql(
            database,
            f"update assistant_turns set lease_until=now()-interval '1 minute' where id='{turn}';",
        )
        assert (
            sql(database, begin.replace("'token'", "'new-token'")).strip() == "running"
        )
        finish = f"select assistant_finish_turn('{OWNER}','{turn}','new-token','completed','[]','已处理',null,'{{}}')->>'status';"
        with pytest.raises(AssertionError):
            sql(database, finish.replace("new-token", "token"))
        assert sql(database, finish).strip() == "completed"
        assert sql(database, begin).strip() == "completed"
        with pytest.raises(AssertionError):
            sql(database, begin.replace("'body'", "'changed'"))
        for table in ("assistant_turns", "assistant_actions", "assistant_attachments"):
            assert (
                sql(
                    database,
                    f"select relrowsecurity from pg_class where relname='{table}';",
                ).strip()
                == "t"
            )
        assert sql(database, "select count(*) from extraction_projects;").strip() == (
            "1" if legacy else "0"
        )
    finally:
        sql("postgres", f'drop database "{database}";')
