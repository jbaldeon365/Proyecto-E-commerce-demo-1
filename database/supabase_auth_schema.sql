-- ============================================================
-- Autenticacion y perfiles para V1
-- Proyecto ecommerce Falabella
-- ============================================================

create table if not exists perfiles (
  id uuid primary key references auth.users(id) on delete cascade,
  nombre text not null,
  email text not null,
  rol text not null default 'cliente' check (rol in ('cliente', 'admin')),
  created_at timestamptz not null default now()
);

create index if not exists idx_perfiles_rol on perfiles (rol);

grant usage on schema public to anon, authenticated;
revoke update on table perfiles from anon, authenticated;
grant select, insert on table perfiles to authenticated;

alter table perfiles enable row level security;

drop policy if exists "perfiles_select_demo" on perfiles;
drop policy if exists "perfiles_insert_demo" on perfiles;
drop policy if exists "perfiles_update_demo" on perfiles;

create policy "perfiles_select_demo"
on perfiles
for select
to authenticated
using (auth.uid() = id);

create policy "perfiles_insert_demo"
on perfiles
for insert
to authenticated
with check (auth.uid() = id and rol = 'cliente');

-- Para convertir un usuario en administrador, primero crea la cuenta
-- desde la app y luego ejecuta una sentencia como esta en SQL Editor:
--
-- update perfiles
-- set rol = 'admin'
-- where email = 'admin@correo.com';
