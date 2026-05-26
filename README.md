# Falabella Cloud Order Manager

Aplicacion web en Streamlit para simular una plataforma de comercio electronico escalable en la nube, orientada a la gestion de pedidos.

## Modulos incluidos

- Catalogo de productos desde MongoDB, con datos flexibles por categoria.
- Carrito de compras con agregar, quitar, subtotal, total y confirmacion.
- Registro de pedidos con codigo, cliente, productos, cantidades, total, fecha y estado.
- Panel administrativo para buscar, filtrar, ver detalle y actualizar estados.
- Dashboard con pedidos, ventas simuladas, productos mas vendidos y categorias.

## Tecnologias

- Streamlit: interfaz web.
- MongoDB: catalogo de productos.
- Supabase: clientes, pedidos y detalle de pedidos.
- Redis: carrito temporal por usuario.
- Docker: contenedor de ejecucion de la app.
- Railway: despliegue cloud del contenedor.
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

## Ejecutar con Docker

Construir la imagen:

```bash
docker build -t falabella-order-manager .
```

Ejecutar el contenedor:

```bash
docker run --env-file .env -p 8501:8501 falabella-order-manager
```

Ejemplo de `.env` local:

```text
MONGODB_URI=mongodb+srv://USUARIO:CLAVE@cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_DATABASE=falabella_ecommerce
MONGODB_COLLECTION=productos
SUPABASE_URL=https://TU-PROYECTO.supabase.co
SUPABASE_KEY=TU_SUPABASE_ANON_O_PUBLISHABLE_KEY
REDIS_URL=redis://default:CLAVE@HOST:PUERTO
```

No subas `.env` a GitHub.

## Desplegar en Railway con Docker

1. Sube estos archivos a GitHub:

```text
Dockerfile
.dockerignore
railway.json
requirements.txt
app.py
database/
```

2. En Railway crea un proyecto:

```text
New Project > Deploy from GitHub repo
```

3. Selecciona el repositorio y la rama:

```text
v1
```

4. Railway detectara el `Dockerfile` y construira el contenedor.

5. En el servicio de la app, entra a `Variables` y agrega:

```text
MONGODB_URI
MONGODB_DATABASE
MONGODB_COLLECTION
SUPABASE_URL
SUPABASE_KEY
REDIS_URL
```

6. Para Redis en Railway:

```text
New > Database > Redis
```

Luego vincula o copia `REDIS_URL` al servicio de la app.

7. En MongoDB Atlas, permite conexiones desde Railway. Para pruebas:

```text
0.0.0.0/0
```

8. Ejecuta el deploy. La app usara el puerto dinamico `PORT` que Railway asigna automaticamente.

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

## Configurar Redis para carrito temporal

Redis es opcional. Si no se configura, el carrito se guarda solo en la sesion activa de Streamlit.
Si configuras Redis, el carrito se conserva por usuario aunque recargue la pagina o vuelva a iniciar sesion.

### En Railway

1. Crea o abre tu proyecto en Railway.
2. Agrega un servicio Redis desde `New > Database > Redis`.
3. Copia la variable generada por Railway:

```text
REDIS_URL
```

4. En el servicio de la app Streamlit, agrega estas variables:

```text
REDIS_URL
MONGODB_URI
MONGODB_DATABASE
MONGODB_COLLECTION
SUPABASE_URL
SUPABASE_KEY
```

5. Despliega nuevamente la app.

### En local o Streamlit Cloud

Tambien puedes configurar Redis en `.streamlit/secrets.toml`:

```toml
[redis]
url = "redis://default:CLAVE@HOST:PUERTO"
```

La app guarda el carrito con una clave por usuario:

```text
cart:<id_usuario_supabase>
```

El carrito expira despues de 24 horas.

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
    D --> E[Confirma la compra]
    E --> F[Se genera un pedido]
    F --> G[El pedido se almacena en Supabase]
    C --> H[Catalogo consultado desde MongoDB]
    G --> I[Area administrativa revisa el pedido]
    I --> J[Se actualiza el estado del pedido]
    J --> K[Dashboard muestra reportes y metricas]
```
