grant usage on schema public to anon, authenticated;

revoke update on table perfiles from anon, authenticated;
grant select, insert on table perfiles to authenticated;
grant select, insert, update on table clientes to anon, authenticated;
grant select, insert, update on table pedidos to anon, authenticated;
grant select, insert, update on table detalle_pedidos to anon, authenticated;
grant select, insert on table pagos_simulados to anon, authenticated;
grant execute on function procesar_pedidos_automaticos() to anon, authenticated;

alter table perfiles enable row level security;
alter table clientes enable row level security;
alter table pedidos enable row level security;
alter table detalle_pedidos enable row level security;
alter table pagos_simulados enable row level security;

-- ============================================================
-- Perfiles
-- ============================================================

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

-- ============================================================
-- Clientes
-- ============================================================

drop policy if exists "clientes_select_demo" on clientes;
drop policy if exists "clientes_insert_demo" on clientes;
drop policy if exists "clientes_update_demo" on clientes;

create policy "clientes_select_demo"
on clientes
for select
to anon, authenticated
using (true);

create policy "clientes_insert_demo"
on clientes
for insert
to anon, authenticated
with check (true);

create policy "clientes_update_demo"
on clientes
for update
to anon, authenticated
using (true)
with check (true);

-- ============================================================
-- Pedidos
-- ============================================================

drop policy if exists "pedidos_select_demo" on pedidos;
drop policy if exists "pedidos_insert_demo" on pedidos;
drop policy if exists "pedidos_update_demo" on pedidos;

create policy "pedidos_select_demo"
on pedidos
for select
to anon, authenticated
using (true);

create policy "pedidos_insert_demo"
on pedidos
for insert
to anon, authenticated
with check (true);

create policy "pedidos_update_demo"
on pedidos
for update
to anon, authenticated
using (true)
with check (true);

-- ============================================================
-- Detalle de pedidos
-- ============================================================

drop policy if exists "detalle_select_demo" on detalle_pedidos;
drop policy if exists "detalle_insert_demo" on detalle_pedidos;
drop policy if exists "detalle_update_demo" on detalle_pedidos;

create policy "detalle_select_demo"
on detalle_pedidos
for select
to anon, authenticated
using (true);

create policy "detalle_insert_demo"
on detalle_pedidos
for insert
to anon, authenticated
with check (true);

create policy "detalle_update_demo"
on detalle_pedidos
for update
to anon, authenticated
using (true)
with check (true);

-- ============================================================
-- Pagos simulados
-- ============================================================

drop policy if exists "pagos_select_demo" on pagos_simulados;
drop policy if exists "pagos_insert_demo" on pagos_simulados;

create policy "pagos_select_demo"
on pagos_simulados
for select
to anon, authenticated
using (true);

create policy "pagos_insert_demo"
on pagos_simulados
for insert
to anon, authenticated
with check (true);
