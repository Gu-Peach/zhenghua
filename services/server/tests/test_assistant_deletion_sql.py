"""Opt-in deletion/GC migration checks in a disposable, network-isolated Postgres."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from test_profile_publication_sql import (
    isolated_cluster as isolated_cluster,  # noqa: PLC0414
)
from test_profile_publication_sql import sql

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(
    os.environ.get("ASSISTANT_SQL_TEST") != "1", reason="opt-in disposable database"
)
OWNER = "00000000-0000-0000-0000-000000000011"
OTHER = "00000000-0000-0000-0000-000000000012"


@pytest.mark.parametrize("legacy", [False, True])
def test_delete_migration_ownership_busy_cascade_gc_and_domain_isolation(legacy):
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
            create table extraction_projects(id uuid primary key, owner_id uuid);
            create table business_results(id integer primary key, value text);
            insert into business_results values (1,'原线表'),(2,'独立重扫任务');
        """,
        )
        sql(
            database,
            (ROOT / "supabase/migrations/20261019020000_main_assistant.sql").read_text(
                encoding="utf-8"
            ),
        )
        conversation, other_conversation, turn, action, attachment = map(
            str, (uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
        )
        seed = f"""
            insert into assistant_conversations(id,owner_id,title) values
              ('{conversation}','{OWNER}','待删除历史'),('{other_conversation}','{OTHER}','其他用户');
            insert into assistant_turns(id,conversation_id,owner_id,request_hash,request,tool_token_hash,status)
              values ('{turn}','{conversation}','{OWNER}','hash','{{}}','token','completed');
            insert into assistant_actions(id,conversation_id,turn_id,owner_id,tool_name)
              values ('{action}','{conversation}','{turn}','{OWNER}','start_rescan');
            insert into assistant_attachments(id,conversation_id,owner_id,filename,mime_type,role,checksum,storage_path,uploaded)
              values ('{attachment}','{conversation}','{OWNER}','image.png','image/png','detail','checksum',
              'assistant/{OWNER}/{conversation}/{attachment}/checksum',true);
        """
        if legacy:
            sql(database, seed)
        sql(
            database,
            (
                ROOT
                / "supabase/migrations/20261019050000_assistant_conversation_deletion.sql"
            ).read_text(encoding="utf-8"),
        )
        if not legacy:
            sql(database, seed)
        assert (
            sql(database, "select count(*) from assistant_conversations;").strip()
            == "2"
        )
        for statement in (
            f"select assistant_delete_conversation('{OTHER}','{conversation}');",
            f"set role authenticated; select assistant_delete_conversation('{OWNER}','{conversation}');",
            "set role authenticated; select count(*) from assistant_asset_gc;",
            "set role anon; select count(*) from assistant_asset_gc;",
        ):
            with pytest.raises(AssertionError):
                sql(database, statement)
        # Both active turns and in-flight uploads are protected; expired turns remain deletable.
        sql(
            database,
            f"update assistant_turns set status='running',lease_until=now()+interval '1 minute' where id='{turn}';",
        )
        with pytest.raises(AssertionError):
            sql(
                database,
                f"select assistant_delete_conversation('{OWNER}','{conversation}');",
            )
        sql(
            database,
            f"update assistant_turns set lease_until=now()-interval '1 minute' where id='{turn}'; update assistant_attachments set uploaded=false where id='{attachment}';",
        )
        with pytest.raises(AssertionError):
            sql(
                database,
                f"select assistant_delete_conversation('{OWNER}','{conversation}');",
            )
        # A malformed legacy path fails the queue constraint and rolls back the entire deletion.
        sql(
            database,
            f"update assistant_attachments set uploaded=true,storage_path='projects/foreign/original.pdf' where id='{attachment}';",
        )
        with pytest.raises(AssertionError):
            sql(
                database,
                f"select assistant_delete_conversation('{OWNER}','{conversation}');",
            )
        assert (
            sql(database, "select count(*) from assistant_conversations;").strip()
            == "2"
        )
        sql(
            database,
            f"update assistant_attachments set storage_path='assistant/{OWNER}/{conversation}/{attachment}/checksum' where id='{attachment}';",
        )
        assert (
            sql(
                database,
                f"set role service_role; select assistant_delete_conversation('{OWNER}','{conversation}');",
            )
            .strip()
            .endswith("\nt")
        )
        assert (
            sql(
                database,
                f"select assistant_delete_conversation('{OWNER}','{conversation}');",
            ).strip()
            == "t"
        )
        for table in ("assistant_turns", "assistant_actions", "assistant_attachments"):
            assert sql(database, f"select count(*) from {table};").strip() == "0"
        assert (
            sql(database, "select count(*) from assistant_conversations;").strip()
            == "1"
        )
        assert (
            sql(
                database,
                f"select count(*) from assistant_asset_gc where owner_id='{OWNER}' and conversation_id='{conversation}';",
            ).strip()
            == "1"
        )
        assert sql(database, "select count(*) from business_results;").strip() == "2"
        assert (
            sql(
                database,
                "select relrowsecurity from pg_class where relname='assistant_asset_gc';",
            ).strip()
            == "t"
        )
        with pytest.raises(AssertionError):
            sql(
                database,
                f"select assistant_begin_turn('{OWNER}','{conversation}','{turn}','{{}}','hash','new-token');",
            )
    finally:
        sql("postgres", f'drop database "{database}";')
