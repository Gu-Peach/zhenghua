# Local Supabase setup

The repository currently contains the migration SQL but does not rely on a
generated `config.toml`. For the already-running local Supabase instance, open
the Studio URL printed by `supabase start`, open SQL Editor, and run:

```text
migrations/20260918000000_create_wiring_tables.sql
```

If this directory is later initialized as a complete Supabase CLI project, the
same migration can be applied with:

```powershell
supabase db reset
```

Or paste `migrations/20260918000000_create_wiring_tables.sql` into Studio's
SQL Editor.

The schema contains one business table, `public.wiring_tables`. Each row is a
線表批次 and stores its extracted records as JSONB. Storage files are uploaded
to the public `images` bucket with this layout:

```text
images/
  <job_id>/
    source/<original.pdf>
    pages/page_001.png
    groups/wire-table-001/pages/page_001.png
    groups/wire-table-001/records.json
    groups/wire-table-001/wiring-table.xlsx
    agent/merge_decisions.json
```

Use the local Supabase URL and keys printed by `supabase start`:

```env
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_STORAGE_BUCKET=images
SUPABASE_ENABLED=true
```

Only the backend receives `SUPABASE_SERVICE_ROLE_KEY`. The frontend receives
the publishable/anon key and has read-only access through RLS.
