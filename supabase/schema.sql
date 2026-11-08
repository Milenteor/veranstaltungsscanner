-- Veranstaltungsscanner Steiermark: Datenbank
-- Einmal komplett im Supabase SQL Editor ausführen (Projekt in Region EU, z. B. Frankfurt).
-- Danach unten bei "Mitglieder" die eigenen Mail-Adressen eintragen.

-- ---------------------------------------------------------------- Mitglieder
create table if not exists public.members (
  email      text primary key,
  admin      boolean not null default false,
  note       text,
  created_at timestamptz not null default now()
);
alter table public.members enable row level security;
-- Niemand liest die Liste über die App; Pflege nur im Supabase-Dashboard.

create or replace function public.is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members m where lower(m.email) = lower(coalesce(auth.jwt()->>'email','')));
$$;
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members m where lower(m.email) = lower(coalesce(auth.jwt()->>'email','')) and m.admin);
$$;
grant execute on function public.is_member() to authenticated;
grant execute on function public.is_admin() to authenticated;

-- ---------------------------------------------------------------- Dokumente
-- Ein Dokument je Pfad, gleiche Pfade wie im Claude-Artefakt:
--   data/users/<uid>/<doc>   privat, nur die Person selbst
--   runs/..., config/..., linkinfo/...   alle Mitglieder lesen, nur Admins schreiben
--   linkq/..., log/..., invites/..., team/...   alle Mitglieder lesen und schreiben
create table if not exists public.docs (
  path       text primary key check (path ~ '^[A-Za-z0-9_.~:@+-]{1,200}(/[A-Za-z0-9_.~:@+-]{1,200}){1,14}$'),
  col        text generated always as (regexp_replace(path, '/[^/]+$', '')) stored,
  ts         text generated always as (data->>'ts') stored,
  data       jsonb not null,
  owner      uuid default auth.uid(),
  updated_at timestamptz not null default now()
);
create index if not exists docs_col_idx on public.docs (col);
create index if not exists docs_col_ts_idx on public.docs (col, ts desc);

create or replace function public.vs_can_read(p text) returns boolean
language sql stable as $$
  select case
    when split_part(p,'/',1) = 'data' then split_part(p,'/',2) = 'users' and split_part(p,'/',3) = auth.uid()::text
    when split_part(p,'/',1) in ('runs','config','linkinfo','linkq','log','invites','team') then public.is_member()
    else false end;
$$;
create or replace function public.vs_can_write(p text) returns boolean
language sql stable as $$
  select case
    when split_part(p,'/',1) = 'data' then split_part(p,'/',2) = 'users' and split_part(p,'/',3) = auth.uid()::text and public.is_member()
    when split_part(p,'/',1) in ('runs','config','linkinfo') then public.is_admin()
    when split_part(p,'/',1) in ('linkq','log','invites','team') then public.is_member()
    else false end;
$$;

alter table public.docs enable row level security;
drop policy if exists docs_select on public.docs;
drop policy if exists docs_insert on public.docs;
drop policy if exists docs_update on public.docs;
drop policy if exists docs_delete on public.docs;
create policy docs_select on public.docs for select to authenticated using (public.vs_can_read(path));
create policy docs_insert on public.docs for insert to authenticated with check (public.vs_can_write(path));
create policy docs_update on public.docs for update to authenticated using (public.vs_can_write(path)) with check (public.vs_can_write(path));
create policy docs_delete on public.docs for delete to authenticated using (public.vs_can_write(path));

create or replace function public.docs_touch() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end; $$;
drop trigger if exists docs_touch on public.docs;
create trigger docs_touch before update on public.docs for each row execute function public.docs_touch();

-- Live-Aktualisierung für Einladungen und Team-Termine
do $$ begin
  alter publication supabase_realtime add table public.docs;
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------- KI-Fragen: Tageslimit
create table if not exists public.ask_log (
  id      bigserial primary key,
  uid     uuid not null,
  kind    text not null,
  at      timestamptz not null default now()
);
create index if not exists ask_log_uid_at on public.ask_log (uid, at desc);
alter table public.ask_log enable row level security;
-- Nur die Edge Functions (Service-Schlüssel) schreiben und lesen hier.

-- ---------------------------------------------------------------- Mitglieder eintragen
-- Eigene Adresse als Admin (ändern!):
-- insert into public.members (email, admin) values ('du@beispiel.at', true) on conflict (email) do update set admin = excluded.admin;
-- Weitere Personen:
-- insert into public.members (email) values ('kollegin@beispiel.at') on conflict do nothing;
