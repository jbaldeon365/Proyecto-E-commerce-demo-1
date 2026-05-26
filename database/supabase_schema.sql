
-- ============================================================
-- Tabla: perfiles
-- Complementa Supabase Auth con datos de rol para la app.
-- El usuario y contrasena se gestionan en auth.users.
-- ============================================================

create table if not exists perfiles (
  id uuid primary key references auth.users(id) on delete cascade,
  nombre text not null,
  email text not null,
  rol text not null default 'cliente' check (rol in ('cliente', 'admin')),
  created_at timestamptz not null default now()
);

-- ============================================================
-- Tabla: clientes
-- Guarda los datos principales del cliente que realiza la compra.
-- ============================================================

create table if not exists clientes (
  id uuid primary key default gen_random_uuid(),
  nombre text not null,
  email text not null,
  telefono text,
  direccion text,
  created_at timestamptz not null default now()
);

-- ============================================================
-- Tabla: pedidos
-- Guarda la cabecera del pedido y su estado dentro del flujo.
-- Estados permitidos:
-- Pendiente -> Procesando -> Enviado -> Entregado
-- ============================================================

create table if not exists pedidos (
  id uuid primary key default gen_random_uuid(),
  codigo text not null unique,
  cliente_id uuid not null references clientes(id) on delete restrict,
  total numeric(12, 2) not null check (total >= 0),
  estado text not null default 'Pendiente'
    check (estado in ('Pendiente', 'Procesando', 'Enviado', 'Entregado')),
  fecha_pedido timestamptz not null default now()
);

-- ============================================================
-- Tabla: detalle_pedidos
-- Guarda los productos comprados en cada pedido.
-- ============================================================

create table if not exists detalle_pedidos (
  id uuid primary key default gen_random_uuid(),
  pedido_id uuid not null references pedidos(id) on delete cascade,
  producto_id text not null,
  producto_nombre text not null,
  categoria text not null,
  precio numeric(12, 2) not null check (precio >= 0),
  cantidad int not null check (cantidad > 0),
  subtotal numeric(12, 2) not null check (subtotal >= 0),
  unique (pedido_id, producto_id)
);

-- ============================================================
-- Indices para mejorar busquedas y filtros administrativos.
-- ============================================================

create index if not exists idx_pedidos_codigo on pedidos (codigo);
create index if not exists idx_pedidos_estado on pedidos (estado);
create index if not exists idx_detalle_pedido_id on detalle_pedidos (pedido_id);
create index if not exists idx_perfiles_rol on perfiles (rol);

-- ============================================================
-- Permisos para usar Supabase desde Streamlit con anon/public key
-- ============================================================


grant usage on schema public to anon, authenticated;
revoke update on perfiles from anon, authenticated;
grant select, insert on perfiles to authenticated;
grant select, insert, update on clientes to anon, authenticated;
grant select, insert, update on pedidos to anon, authenticated;
grant select, insert, update on detalle_pedidos to anon, authenticated;

alter table perfiles enable row level security;
alter table clientes enable row level security;
alter table pedidos enable row level security;
alter table detalle_pedidos enable row level security;

drop policy if exists "perfiles_select_demo" on perfiles;
drop policy if exists "perfiles_insert_demo" on perfiles;
drop policy if exists "perfiles_update_demo" on perfiles;

create policy "perfiles_select_demo"
on perfiles for select
to authenticated
using (auth.uid() = id);

create policy "perfiles_insert_demo"
on perfiles for insert
to authenticated
with check (auth.uid() = id and rol = 'cliente');

drop policy if exists "clientes_select_demo" on clientes;
drop policy if exists "clientes_insert_demo" on clientes;
drop policy if exists "clientes_update_demo" on clientes;

create policy "clientes_select_demo"
on clientes for select
to anon, authenticated
using (true);

create policy "clientes_insert_demo"
on clientes for insert
to anon, authenticated
with check (true);

create policy "clientes_update_demo"
on clientes for update
to anon, authenticated
using (true)
with check (true);

drop policy if exists "pedidos_select_demo" on pedidos;
drop policy if exists "pedidos_insert_demo" on pedidos;
drop policy if exists "pedidos_update_demo" on pedidos;

create policy "pedidos_select_demo"
on pedidos for select
to anon, authenticated
using (true);

create policy "pedidos_insert_demo"
on pedidos for insert
to anon, authenticated
with check (true);

create policy "pedidos_update_demo"
on pedidos for update
to anon, authenticated
using (true)
with check (true);

drop policy if exists "detalle_select_demo" on detalle_pedidos;
drop policy if exists "detalle_insert_demo" on detalle_pedidos;
drop policy if exists "detalle_update_demo" on detalle_pedidos;

create policy "detalle_select_demo"
on detalle_pedidos for select
to anon, authenticated
using (true);

create policy "detalle_insert_demo"
on detalle_pedidos for insert
to anon, authenticated
with check (true);

create policy "detalle_update_demo"
on detalle_pedidos for update
to anon, authenticated
using (true)
with check (true);

-- ============================================================
-- Datos de prueba opcionales
-- ============================================================

insert into clientes (id, nombre, email, telefono, direccion)
values
  (
    '11111111-1111-1111-1111-111111111111',
    'Cliente Demo',
    'cliente.demo@correo.com',
    '999999999',
    'Av. Demo 123, Lima'
  )
on conflict (id) do nothing;

insert into pedidos (id, codigo, cliente_id, total, estado, fecha_pedido)
values
  (
    '22222222-2222-2222-2222-222222222222',
    'FAL-DEMO-0001',
    '11111111-1111-1111-1111-111111111111',
    2679.80,
    'Pendiente',
    now()
  )
on conflict (codigo) do nothing;

insert into detalle_pedidos (
  pedido_id,
  producto_id,
  producto_nombre,
  categoria,
  precio,
  cantidad,
  subtotal
)
values
  (
    '22222222-2222-2222-2222-222222222222',
    'PROD-001',
    'Laptop Lenovo IdeaPad 15',
    'Tecnologia',
    2499.90,
    1,
    2499.90
  ),
  (
    '22222222-2222-2222-2222-222222222222',
    'PROD-003',
    'Zapatillas Urbanas Hombre',
    'Moda',
    179.90,
    1,
    179.90
  )
on conflict do nothing;
