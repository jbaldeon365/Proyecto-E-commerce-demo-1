# Falabella Cloud Order Manager

Aplicacion web en Streamlit para simular una plataforma de comercio electronico escalable en la nube, orientada a la gestion de pedidos.

## Modulos incluidos

- Catalogo de productos desde MongoDB, con datos flexibles por categoria.
- Carrito de compras con agregar, quitar, subtotal, total y confirmacion.
- Pasarela de pago simulada antes de generar el pedido.
- Registro de pedidos con codigo, cliente, productos, cantidades, total, fecha y estado.
- Panel administrativo para buscar, filtrar, ver detalle y actualizar estados.
- Dashboard con pedidos, ventas simuladas, pagos, productos mas vendidos, bajo stock y categorias.

## Tecnologias

- Streamlit: interfaz web.
- MongoDB: catalogo de productos.
- Supabase: clientes, pedidos y detalle de pedidos.
- Upstash Redis: carrito temporal por usuario y cache temporal del catalogo.
- Pandas: tablas y metricas.

## Estructura

```text
.
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example
└── database/
    ├── productos_mongodb_seed.json
    ├── supabase_schema.sql
    ├── supabase_rls_policies.sql
    └── supabase_auth_schema.sql
```

## Instalacion

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
4. Copia `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml`.
5. Completa:

```toml
[supabase]
url = "https://TU-PROYECTO.supabase.co"
key = "TU_SUPABASE_ANON_O_PUBLISHABLE_KEY"
```

Para una version 1 segura, usa una key anon/public/publishable con politicas RLS.
No subas `.streamlit/secrets.toml` a GitHub y evita usar una secret/service key en apps publicas.

## Configurar autenticacion

La app usa Supabase Auth para login con correo y contrasena.

1. En Supabase, entra a `Authentication > Providers`.
2. Activa el proveedor `Email`.
3. Para pruebas academicas, puedes desactivar la confirmacion obligatoria de correo.
4. En `SQL Editor`, ejecuta:

```text
database/supabase_auth_schema.sql
```

5. Crea una cuenta desde la app.
6. Para convertir esa cuenta en administrador, ejecuta en Supabase:

```sql
update perfiles
set rol = 'admin'
where email = 'admin@correo.com';
```

Los usuarios nuevos se crean como `cliente`. El admin puede ver el panel administrativo,
dashboard y configuracion; el cliente puede comprar y consultar sus pedidos.

## Configurar MongoDB

1. Crea un cluster en MongoDB Atlas.
2. Copia la cadena de conexion.
3. En `.streamlit/secrets.toml`, completa:

```toml
[mongodb]
uri = "mongodb+srv://USUARIO:CLAVE@cluster.mongodb.net/?retryWrites=true&w=majority"
database = "falabella_ecommerce"
collection = "productos"
```

4. En la app, entra al modulo `Configuracion` y pulsa `Cargar productos semilla en MongoDB`.

Tambien puedes importar manualmente `database/productos_mongodb_seed.json` en MongoDB Compass o Atlas.

## Configurar Upstash Redis

Upstash Redis es opcional, pero recomendado para mantener el carrito temporal por usuario y cachear el catalogo en la nube.
Si no se configura, el carrito se guarda solo en la sesion activa de Streamlit.
Si se configura, el carrito se conserva aunque el usuario recargue la pagina o vuelva a iniciar sesion.

### En Upstash

1. Crea una cuenta en Upstash.
2. Crea una base de datos Redis.
3. Copia la URL de conexion Redis. Puede tener formato `redis://` o `rediss://`.
4. En Streamlit Cloud, abre `App settings > Secrets`.
5. Agrega:

```toml
[redis]
url = "rediss://default:CLAVE@HOST:PUERTO"
```

Tambien puedes configurarlo localmente en `.streamlit/secrets.toml` con el mismo formato.

La app usa Redis para dos propositos:

- Carrito temporal por usuario autenticado.
- Cache temporal del catalogo consultado desde MongoDB Atlas.

MongoDB Atlas se mantiene como fuente oficial del catalogo y stock. Redis solo guarda una copia temporal
para reducir consultas repetitivas. Cuando se descuenta stock o se recarga el catalogo semilla, la app
invalida el cache para volver a sincronizar datos desde MongoDB.

La app guarda el carrito con una clave por usuario de Supabase:

```text
cart:<id_usuario_supabase>
```

El carrito expira despues de 24 horas. El cache del catalogo expira despues de 5 minutos.

## Pasarela de pago simulada

Antes de generar un pedido, el cliente selecciona un metodo de pago y el resultado simulado:

- Tarjeta
- Yape
- Pago contra entrega

El pago puede ser `Aprobado` o `Rechazado`. Si el pago es aprobado, el sistema genera el pedido en
Supabase y descuenta stock en MongoDB Atlas. Si el pago es rechazado, no se genera pedido, pero el
intento queda registrado en `pagos_simulados` para que el dashboard muestre metricas de pagos.

## Modo demo

La aplicacion funciona aunque no configures credenciales. En ese caso:

- El catalogo usa productos demo definidos en `app.py`.
- Los pedidos se guardan solo en memoria de la sesion de Streamlit.

Este modo sirve para presentar el flujo, probar el carrito y validar la experiencia antes de conectar la nube.

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
    F --> G[El pedido se almacena en Supabase]
    C --> H[Catalogo consultado desde Redis o MongoDB]
    H --> M[MongoDB Atlas como fuente oficial]
    G --> I[Area administrativa revisa el pedido]
    I --> J[Se actualiza el estado del pedido]
    J --> K[Dashboard muestra reportes y metricas]
```
