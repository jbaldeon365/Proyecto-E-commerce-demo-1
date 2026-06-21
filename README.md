# Falabella Cloud Order Manager

Aplicacion web en Streamlit para una plataforma de comercio electronico escalable en la nube, orientada a la gestion de pedidos.

## Modulos incluidos

- Catalogo de productos desde MongoDB, con busqueda, filtros y tarjetas de producto redisenadas.
- Carrito de compras con agregar, quitar, cambiar cantidad, subtotal, total y confirmacion.
- Pasarela de pago simulada antes de generar el pedido.
- Comprobante final de pedido despues del pago aprobado.
- Registro de pedidos con codigo, cliente unico por correo, productos, cantidades, total, fecha y estado.
- Panel administrativo con tabla seleccionable, filtros, detalle del pedido y registro de revision administrativa.
- Perfil del cliente para mantener nombre, telefono y direccion principal.
- Mis pedidos con progreso de estado, detalle de compra y notificaciones de cambios por popup.
- Dashboard separado por secciones: resumen ejecutivo, pedidos, pagos, catalogo, clientes, inventario y exportacion CSV.
- Validaciones de entradas para cliente, perfil, direccion, pago y observaciones administrativas.

## Tecnologias

- Streamlit: interfaz web.
- MongoDB Atlas: catalogo de productos y stock.
- Supabase Auth: autenticacion con correo y contrasena.
- Supabase PostgreSQL: clientes, perfiles, pedidos, detalle de pedidos y pagos simulados.
- Supabase pg_cron: procesamiento automatico de estados de pedidos.
- Upstash Redis: carrito temporal por usuario, cache temporal de catalogo y snapshot de notificaciones.
- Pandas: tablas, metricas y exportacion CSV.

## Estructura

```text
.
|-- app.py
|-- requirements.txt
|-- README.md
|-- .gitignore
|-- .streamlit/
|   `-- secrets.toml.example
`-- database/
    |-- supabase_cron_job.sql
    |-- supabase_schema.sql
    |-- supabase_rls_policies.sql
    `-- supabase_auth_schema.sql
```

## Instalacion local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue en Streamlit Cloud

1. Sube el proyecto a GitHub.
2. En Streamlit Cloud selecciona el repositorio y la rama `v1`.
3. Usa `app.py` como archivo principal.
4. En `App settings > Secrets`, configura MongoDB, Supabase y Upstash Redis.

## Configurar Supabase

1. Crea un proyecto en Supabase.
2. Abre el SQL Editor.
3. Ejecuta el contenido de `database/supabase_schema.sql`.
4. Ejecuta el contenido de `database/supabase_auth_schema.sql`.
5. Si necesitas separar politicas RLS, ejecuta tambien `database/supabase_rls_policies.sql`.
6. Copia `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml` para uso local.
7. Completa:

```toml
[supabase]
url = "https://TU-PROYECTO.supabase.co"
key = "TU_SUPABASE_ANON_O_PUBLISHABLE_KEY"
```

Para una version segura, usa una key anon/public/publishable con politicas RLS.
No subas `.streamlit/secrets.toml` a GitHub.

## Autenticacion y roles

La app usa Supabase Auth para login con correo y contrasena.

1. En Supabase, entra a `Authentication > Providers`.
2. Activa el proveedor `Email`.
3. Para pruebas academicas, puedes desactivar la confirmacion obligatoria de correo.
4. Crea una cuenta desde la app.
5. Para convertir esa cuenta en administrador, ejecuta:

```sql
update perfiles
set rol = 'admin'
where email = 'admin@correo.com';
```

Los usuarios nuevos se crean como `cliente`. El admin puede ver el panel administrativo,
dashboard y configuracion; el cliente puede comprar, mantener su perfil y consultar sus pedidos.

## Automatizacion de pedidos con Supabase

La app incluye una funcion SQL llamada `procesar_pedidos_automaticos()` y un cron job de Supabase
configurado en `database/supabase_cron_job.sql`.

El flujo normal avanza sin intervencion manual:

```text
Pendiente -> Procesando -> Enviado -> Entregado
```

Los casos con problemas quedan fuera del flujo automatico:

```text
Pago pendiente
Observado
Revision administrativa
Cancelado
```

### Cron automatico en Supabase

1. Entra a `SQL Editor`.
2. Ejecuta `database/supabase_schema.sql`.
3. Ejecuta `database/supabase_cron_job.sql`.
4. Verifica que el job quedo creado con:

```sql
select jobid, jobname, schedule, command, active
from cron.job
where jobname = 'procesar-pedidos-automaticos';
```

El cron ejecuta cada 1 minuto:

```text
procesar_pedidos_automaticos()
```

El panel administrativo queda enfocado en consultar pedidos y resolver excepciones. En la interfaz
administrativa se selecciona una fila de la tabla de pedidos y el detalle aparece debajo para revisar
productos, datos de pago y registrar `Revision administrativa` cuando se requiera intervencion humana.

## Configurar MongoDB Atlas

1. Crea un cluster en MongoDB Atlas.
2. Crea o selecciona la base de datos `falabella_ecommerce`.
3. Crea la coleccion `productos`.
4. Carga productos reales directamente en MongoDB Atlas.
5. En `.streamlit/secrets.toml` o en Streamlit Cloud Secrets, completa:

```toml
[mongodb]
uri = "mongodb+srv://USUARIO:CLAVE@cluster.mongodb.net/?retryWrites=true&w=majority"
database = "falabella_ecommerce"
collection = "productos"
```

MongoDB Atlas es la fuente oficial del catalogo y stock. Si cambias productos y Redis tenia cache anterior,
elimina la clave `catalogo:productos` en Upstash.

## Configurar Upstash Redis

Upstash Redis es recomendado para mantener el carrito temporal por usuario, cachear el catalogo y guardar
el snapshot usado para notificar cambios de estado.

1. Crea una cuenta en Upstash.
2. Crea una base de datos Redis.
3. Copia la URL de conexion Redis. Puede tener formato `redis://` o `rediss://`.
4. En Streamlit Cloud, abre `App settings > Secrets`.
5. Agrega:

```toml
[redis]
url = "rediss://default:CLAVE@HOST:PUERTO"
```

La app usa estas claves:

```text
cart:<id_usuario_supabase>
orders:last-status:<id_usuario_supabase>
catalogo:productos
```

El carrito expira despues de 24 horas. El cache del catalogo expira despues de 5 minutos.

## Flujo de compra

1. El cliente inicia sesion.
2. Visualiza el catalogo con productos desde MongoDB o cache Redis.
3. Agrega productos al carrito.
4. Completa datos de entrega.
5. Selecciona metodo de pago simulado: `Tarjeta` o `Yape`.
6. Confirma el pago.
7. Si el pago es aprobado, se genera el pedido en Supabase.
8. Se descuenta stock en MongoDB.
9. Se muestra el comprobante final en popup.
10. Supabase pg_cron procesa el avance de estados.
11. El cliente ve cambios mediante notificaciones popup y en `Mis pedidos`.

## Interfaz actual

- La barra lateral muestra la marca `FALABELLA`, un saludo al usuario y los modulos disponibles segun su rol.
- La vista cliente muestra el catalogo con tarjetas de producto del mismo tamano, filtros y busqueda.
- Las notificaciones de cambios de estado se muestran como popups mediante `st.toast()`.
- El administrador selecciona pedidos directamente desde la tabla para abrir el detalle debajo.
- El administrador solo registra `Revision administrativa`; los estados normales avanzan mediante `pg_cron`.
- El dashboard organiza indicadores por secciones empresariales y permite exportar pedidos a CSV.

## Flujo del sistema

```mermaid
flowchart TD
    A[Cliente] --> B[Ingresa a la plataforma ecommerce]
    B --> C[Visualiza productos disponibles]
    C --> D[Agrega productos al carrito]
    D --> R[Carrito temporal en Upstash Redis]
    D --> E[Pasarela de pago simulada]
    E -->|Pago aprobado| F[Se genera un pedido]
    E -->|Pago rechazado| P[Se registra intento de pago]
    F --> G[El pedido se almacena en Supabase PostgreSQL]
    C --> H[Catalogo consultado desde Redis o MongoDB]
    H --> M[MongoDB Atlas como fuente oficial]
    G --> A1[Supabase pg_cron procesa pedidos normales]
    A1 -->|Sin observaciones| J[Estado avanza automaticamente]
    A1 -->|Con problemas| I[Area administrativa revisa excepciones]
    I --> J
    J --> K[Dashboard muestra reportes y metricas]
```
