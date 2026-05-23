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
    └── supabase_schema.sql
```

## Instalacion

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Configurar Supabase

1. Crea un proyecto en Supabase.
2. Abre el SQL Editor.
3. Ejecuta el contenido de `database/supabase_schema.sql`.
4. Copia `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml`.
5. Completa:

```toml
[supabase]
url = "https://TU-PROYECTO.supabase.co"
key = "TU_SUPABASE_ANON_KEY"
```

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
