-- Add structured terminal positions without changing the three-table boundary.
-- Rollback: stop coordinate writers, then remove these columns/constraints/triggers
-- in a new migration. Dropping columns discards stored coordinates.
begin;
alter table public.extraction_connection_rows
  add column start_terminal_coordinates jsonb,
  add column end_terminal_coordinates jsonb;

create function public.is_extraction_terminal_coordinates(value jsonb) returns boolean
language plpgsql immutable strict set search_path = public, pg_temp as $$
begin
  if jsonb_typeof(value) <> 'object' then return false; end if;
  if not (value ?& array['x','y','pdf_page_number'])
     or value - array['x','y','pdf_page_number'] <> '{}'::jsonb then
    return false;
  end if;
  if jsonb_typeof(value->'x') <> 'number'
     or jsonb_typeof(value->'y') <> 'number'
     or jsonb_typeof(value->'pdf_page_number') <> 'number' then
    return false;
  end if;
  return (value->>'x')::numeric between 0 and 1
    and (value->>'y')::numeric between 0 and 1
    and (value->>'pdf_page_number')::numeric >= 1
    and (value->>'pdf_page_number')::numeric = trunc((value->>'pdf_page_number')::numeric);
end;
$$;
revoke all on function public.is_extraction_terminal_coordinates(jsonb) from public,anon;
grant execute on function public.is_extraction_terminal_coordinates(jsonb) to authenticated,service_role;

alter table public.extraction_connection_rows
  add constraint extraction_start_coordinates_valid check (
    start_terminal_coordinates is null or public.is_extraction_terminal_coordinates(start_terminal_coordinates)),
  add constraint extraction_end_coordinates_valid check (
    end_terminal_coordinates is null or public.is_extraction_terminal_coordinates(end_terminal_coordinates));

comment on column public.extraction_connection_rows.start_terminal_coordinates is
  '起点端子中心：{x,y,pdf_page_number}。x/y为完整页左上起算0～1归一化坐标，页号为本坐标PDF物理页；未知NULL。';
comment on column public.extraction_connection_rows.end_terminal_coordinates is
  '终点端子中心：{x,y,pdf_page_number}。跨页时独立保留所属PDF物理页，不能用业务页号或来源页替代；未知NULL。';

create function public.clear_stale_extraction_coordinates() returns trigger
language plpgsql set search_path = public, pg_temp as $$
begin
  if (new.start_terminal is distinct from old.start_terminal
      or new.source_pdf_page_number is distinct from old.source_pdf_page_number)
     and new.start_terminal_coordinates is not distinct from old.start_terminal_coordinates then
    new.start_terminal_coordinates := null;
  end if;
  if (new.end_terminal is distinct from old.end_terminal
      or new.target_pdf_page_number is distinct from old.target_pdf_page_number
      or new.source_pdf_page_number is distinct from old.source_pdf_page_number)
     and new.end_terminal_coordinates is not distinct from old.end_terminal_coordinates then
    new.end_terminal_coordinates := null;
  end if;
  return new;
end;
$$;
revoke all on function public.clear_stale_extraction_coordinates() from public,anon;
grant execute on function public.clear_stale_extraction_coordinates() to authenticated,service_role;
create trigger extraction_rows_clear_stale_coordinates before update on public.extraction_connection_rows
  for each row execute function public.clear_stale_extraction_coordinates();

notify pgrst, 'reload schema';
commit;
