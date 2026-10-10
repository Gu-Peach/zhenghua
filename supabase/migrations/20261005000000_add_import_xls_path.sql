alter table public.wiring_tables
  add column if not exists import_xls_path text;

alter table public.wiring_tables
  add column if not exists import_xlsx_path text;
