
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
-- Excepciones: Pago pendiente, Observado, Revision administrativa, Cancelado
-- ============================================================

create table if not exists pedidos (
  id uuid primary key default gen_random_uuid(),
  codigo text not null unique,
  cliente_id uuid not null references clientes(id) on delete restrict,
  total numeric(12, 2) not null check (total >= 0),
  estado text not null default 'Pendiente'
    check (
      estado in (
        'Pendiente',
        'Procesando',
        'Enviado',
        'Entregado',
        'Pago pendiente',
        'Observado',
        'Revision administrativa',
        'Cancelado'
      )
    ),
  metodo_pago text not null default 'Tarjeta',
  estado_pago text not null default 'Aprobado'
    check (estado_pago in ('Aprobado', 'Rechazado')),
  codigo_pago text,
  fecha_pago timestamptz,
  requiere_revision boolean not null default false,
  motivo_revision text,
  actualizado_por text not null default 'sistema',
  fecha_actualizacion_estado timestamptz not null default now(),
  fecha_pedido timestamptz not null default now()
);

alter table pedidos add column if not exists metodo_pago text not null default 'Tarjeta';
alter table pedidos add column if not exists estado_pago text not null default 'Aprobado';
alter table pedidos add column if not exists codigo_pago text;
alter table pedidos add column if not exists fecha_pago timestamptz;
alter table pedidos add column if not exists requiere_revision boolean not null default false;
alter table pedidos add column if not exists motivo_revision text;
alter table pedidos add column if not exists actualizado_por text not null default 'sistema';
alter table pedidos add column if not exists fecha_actualizacion_estado timestamptz not null default now();

do $$
begin
  alter table pedidos drop constraint if exists pedidos_estado_check;
  alter table pedidos
  add constraint pedidos_estado_check
  check (
    estado in (
      'Pendiente',
      'Procesando',
      'Enviado',
      'Entregado',
      'Pago pendiente',
      'Observado',
      'Revision administrativa',
      'Cancelado'
    )
  );

  if not exists (
    select 1
    from pg_constraint
    where conname = 'pedidos_estado_pago_check'
  ) then
    alter table pedidos
    add constraint pedidos_estado_pago_check
    check (estado_pago in ('Aprobado', 'Rechazado'));
  end if;
end $$;

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
-- Tabla: pagos_simulados
-- Registra intentos de pago de la pasarela simulada.
-- Los pagos rechazados no generan pedido, pero quedan como metrica.
-- ============================================================

create table if not exists pagos_simulados (
  id uuid primary key default gen_random_uuid(),
  pedido_id uuid references pedidos(id) on delete set null,
  cliente_email text not null,
  metodo_pago text not null,
  estado_pago text not null check (estado_pago in ('Aprobado', 'Rechazado')),
  codigo_pago text not null unique,
  monto numeric(12, 2) not null check (monto >= 0),
  fecha_pago timestamptz not null default now()
);

-- ============================================================
-- Indices para mejorar busquedas y filtros administrativos.
-- ============================================================

create index if not exists idx_pedidos_codigo on pedidos (codigo);
create index if not exists idx_pedidos_estado on pedidos (estado);
create index if not exists idx_pedidos_estado_pago on pedidos (estado_pago);
create index if not exists idx_pedidos_revision on pedidos (requiere_revision);
create index if not exists idx_pedidos_fecha_estado on pedidos (fecha_actualizacion_estado);
create index if not exists idx_detalle_pedido_id on detalle_pedidos (pedido_id);
create index if not exists idx_perfiles_rol on perfiles (rol);
create index if not exists idx_pagos_estado_pago on pagos_simulados (estado_pago);
create index if not exists idx_pagos_metodo_pago on pagos_simulados (metodo_pago);

-- ============================================================
-- Permisos para usar Supabase desde Streamlit con anon/public key
-- ============================================================


grant usage on schema public to anon, authenticated;
revoke update on perfiles from anon, authenticated;
grant select, insert on perfiles to authenticated;
grant select, insert, update on clientes to anon, authenticated;
grant select, insert, update on pedidos to anon, authenticated;
grant select, insert, update on detalle_pedidos to anon, authenticated;
grant select, insert on pagos_simulados to anon, authenticated;

-- ============================================================
-- Funcion: procesar_pedidos_automaticos
-- Simula una tarea cloud programada. Avanza pedidos normales y
-- deja excepciones para revision administrativa.
-- ============================================================

create or replace function procesar_pedidos_automaticos()
returns table (actualizados int, observados int)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_actualizados int := 0;
  v_observados int := 0;
  v_count int := 0;
begin
  update pedidos
  set
    estado = 'Pago pendiente',
    requiere_revision = true,
    motivo_revision = 'Pago rechazado o pendiente. Requiere revision administrativa.',
    actualizado_por = 'edge_function',
    fecha_actualizacion_estado = now()
  where estado in ('Pendiente', 'Procesando')
    and estado_pago <> 'Aprobado';

  get diagnostics v_observados = row_count;

  update pedidos
  set
    estado = 'Procesando',
    actualizado_por = 'edge_function',
    fecha_actualizacion_estado = now()
  where estado = 'Pendiente'
    and estado_pago = 'Aprobado'
    and requiere_revision = false
    and fecha_actualizacion_estado <= now() - interval '1 minute';

  get diagnostics v_count = row_count;
  v_actualizados := v_count;

  update pedidos
  set
    estado = 'Enviado',
    actualizado_por = 'edge_function',
    fecha_actualizacion_estado = now()
  where estado = 'Procesando'
    and estado_pago = 'Aprobado'
    and requiere_revision = false
    and fecha_actualizacion_estado <= now() - interval '5 minutes';

  get diagnostics v_count = row_count;
  v_actualizados := v_actualizados + v_count;

  update pedidos
  set
    estado = 'Entregado',
    actualizado_por = 'edge_function',
    fecha_actualizacion_estado = now()
  where estado = 'Enviado'
    and estado_pago = 'Aprobado'
    and requiere_revision = false
    and fecha_actualizacion_estado <= now() - interval '10 minutes';

  get diagnostics v_count = row_count;
  v_actualizados := v_actualizados + v_count;

  return query select v_actualizados, v_observados;
end;
$$;

grant execute on function procesar_pedidos_automaticos() to anon, authenticated;

alter table perfiles enable row level security;
alter table clientes enable row level security;
alter table pedidos enable row level security;
alter table detalle_pedidos enable row level security;
alter table pagos_simulados enable row level security;

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

drop policy if exists "pagos_select_demo" on pagos_simulados;
drop policy if exists "pagos_insert_demo" on pagos_simulados;

create policy "pagos_select_demo"
on pagos_simulados for select
to anon, authenticated
using (true);

create policy "pagos_insert_demo"
on pagos_simulados for insert
to anon, authenticated
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

insert into pedidos (
  id,
  codigo,
  cliente_id,
  total,
  estado,
  metodo_pago,
  estado_pago,
  codigo_pago,
  fecha_pago,
  requiere_revision,
  motivo_revision,
  actualizado_por,
  fecha_actualizacion_estado,
  fecha_pedido
)
values
  (
    '22222222-2222-2222-2222-222222222222',
    'FAL-DEMO-0001',
    '11111111-1111-1111-1111-111111111111',
    2679.80,
    'Pendiente',
    'Tarjeta',
    'Aprobado',
    'PAY-DEMO-0001',
    now(),
    false,
    null,
    'sistema',
    now(),
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
