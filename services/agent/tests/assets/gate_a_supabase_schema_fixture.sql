-- Supabase prerequisite schemas for disposable migration-only databases.
-- This is not an Auth/Storage implementation; HTTP tests use the real stack.
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create schema auth;
create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid
$$;
create function auth.role() returns text language sql stable as $$
  select nullif(current_setting('request.jwt.claim.role',true),'')
$$;
create schema storage;
create table storage.buckets(id text primary key,name text,public boolean,
  file_size_limit bigint,allowed_mime_types text[]);
create table storage.objects(id uuid primary key default gen_random_uuid(),bucket_id text,name text);
create function storage.foldername(name text) returns text[] language sql immutable as $$
  select string_to_array(name,'/')
$$;
grant usage on schema public,auth,storage to anon,authenticated,service_role;
