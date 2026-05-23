from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
import requests
import streamlit as st

try:
    from pymongo import MongoClient
except Exception:  # pragma: no cover
    MongoClient = None

ESTADOS = ["Pendiente", "Procesando", "Enviado", "Entregado"]

PRODUCTOS_DEMO = [
    {
        "_id": "PROD-001",
        "nombre": "Laptop Lenovo IdeaPad 15",
        "categoria": "Tecnologia",
        "precio": 2499.90,
        "stock": 12,
        "imagen": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=900&q=80",
        "descripcion": "Laptop de 15 pulgadas para estudio, oficina y productividad diaria.",
        "caracteristicas": {
            "marca": "Lenovo",
            "procesador": "Intel Core i5",
            "memoria": "16 GB RAM",
            "almacenamiento": "512 GB SSD",
        },
    },
    {
        "_id": "PROD-002",
        "nombre": "Smart TV Samsung 55 4K",
        "categoria": "Electrodomesticos",
        "precio": 1899.00,
        "stock": 8,
        "imagen": "https://images.unsplash.com/photo-1593784991095-a205069470b6?auto=format&fit=crop&w=900&q=80",
        "descripcion": "Televisor 4K con aplicaciones integradas y alto contraste.",
        "caracteristicas": {
            "marca": "Samsung",
            "tamano": "55 pulgadas",
            "resolucion": "4K UHD",
            "garantia": "12 meses",
        },
    },
    {
        "_id": "PROD-003",
        "nombre": "Zapatillas Urbanas Hombre",
        "categoria": "Moda",
        "precio": 179.90,
        "stock": 25,
        "imagen": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=900&q=80",
        "descripcion": "Zapatillas comodas para uso diario con suela antideslizante.",
        "caracteristicas": {
            "talla": "40-44",
            "color": "Negro",
            "material": "Textil y sintetico",
        },
    },
    {
        "_id": "PROD-004",
        "nombre": "Refrigeradora No Frost 300L",
        "categoria": "Electrodomesticos",
        "precio": 1399.50,
        "stock": 6,
        "imagen": "https://images.unsplash.com/photo-1584568694244-14fbdf83bd30?auto=format&fit=crop&w=900&q=80",
        "descripcion": "Refrigeradora de bajo consumo con tecnologia No Frost.",
        "caracteristicas": {
            "capacidad": "300 litros",
            "consumo": "Clase A",
            "garantia": "24 meses",
        },
    },
    {
        "_id": "PROD-005",
        "nombre": "Audifonos Bluetooth Sony",
        "categoria": "Tecnologia",
        "precio": 349.90,
        "stock": 18,
        "imagen": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=900&q=80",
        "descripcion": "Audifonos inalambricos con cancelacion de ruido y bateria prolongada.",
        "caracteristicas": {"marca": "Sony", "conexion": "Bluetooth", "bateria": "30 horas"},
    },
    {
        "_id": "PROD-006",
        "nombre": "Casaca Impermeable Mujer",
        "categoria": "Moda",
        "precio": 229.90,
        "stock": 15,
        "imagen": "https://images.unsplash.com/photo-1544022613-e87ca75a784a?auto=format&fit=crop&w=900&q=80",
        "descripcion": "Casaca ligera resistente al agua para temporada fria.",
        "caracteristicas": {"talla": "S-M-L", "color": "Azul", "material": "Poliester"},
    },
]


def get_secret(section: str, key: str, env_key: str, default: str = "") -> str:
    try:
        return st.secrets.get(section, {}).get(key, os.getenv(env_key, default))
    except Exception:
        return os.getenv(env_key, default)


@st.cache_resource(show_spinner=False)
def get_mongo_collection():
    uri = get_secret("mongodb", "uri", "MONGODB_URI")
    database = get_secret("mongodb", "database", "MONGODB_DATABASE", "falabella_ecommerce")
    collection = get_secret("mongodb", "collection", "MONGODB_COLLECTION", "productos")

    if not uri or MongoClient is None:
        return None

    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    client.admin.command("ping")
    return client[database][collection]


def get_supabase_config() -> tuple[str, str]:
    url = get_secret("supabase", "url", "SUPABASE_URL")
    key = get_secret("supabase", "key", "SUPABASE_KEY")
    return url.rstrip("/"), key


def has_supabase_config() -> bool:
    url, key = get_supabase_config()
    return bool(url and key)


def supabase_headers(prefer_return: bool = False) -> dict[str, str]:
    _, key = get_supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer_return:
        headers["Prefer"] = "return=representation"
    return headers


def supabase_request(
    method: str,
    table: str,
    *,
    params: dict | None = None,
    payload: dict | list[dict] | None = None,
    prefer_return: bool = False,
) -> list[dict]:
    url, _ = get_supabase_config()
    response = requests.request(
        method,
        f"{url}/rest/v1/{table}",
        headers=supabase_headers(prefer_return=prefer_return),
        params=params,
        json=payload,
        timeout=12,
    )
    response.raise_for_status()
    if not response.text:
        return []
    return response.json()


def init_state() -> None:
    st.session_state.setdefault("cart", {})
    st.session_state.setdefault("demo_orders", [])


def money(value: float) -> str:
    return f"S/ {value:,.2f}"


def product_id(producto: dict) -> str:
    return str(producto.get("_id") or producto.get("id"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_products() -> tuple[list[dict], str]:
    try:
        collection = get_mongo_collection()
        if collection is None:
            return PRODUCTOS_DEMO, "demo"
        productos = list(collection.find({}).sort("nombre", 1))
        if not productos:
            return PRODUCTOS_DEMO, "demo"
        return productos, "mongodb"
    except Exception as exc:
        st.warning(f"No se pudo conectar a MongoDB. Usando catalogo demo. Detalle: {exc}")
        return PRODUCTOS_DEMO, "demo"


def add_to_cart(pid: str, quantity: int) -> None:
    current = st.session_state.cart.get(pid, 0)
    st.session_state.cart[pid] = current + quantity
    st.toast("Producto agregado al carrito")


def remove_from_cart(pid: str) -> None:
    st.session_state.cart.pop(pid, None)


def cart_items(productos: list[dict]) -> list[dict]:
    by_id = {product_id(producto): producto for producto in productos}
    items = []
    for pid, quantity in st.session_state.cart.items():
        producto = by_id.get(pid)
        if not producto:
            continue
        precio = float(producto["precio"])
        items.append(
            {
                "producto_id": pid,
                "nombre": producto["nombre"],
                "categoria": producto["categoria"],
                "precio": precio,
                "cantidad": quantity,
                "subtotal": precio * quantity,
            }
        )
    return items


def cart_total(items: list[dict]) -> float:
    return sum(item["subtotal"] for item in items)


def create_order(cliente: dict, items: list[dict]) -> str:
    codigo = f"FAL-{datetime.now().strftime('%Y%m%d')}-{str(uuid4())[:8].upper()}"
    total = cart_total(items)

    if not has_supabase_config():
        st.session_state.demo_orders.append(
            {
                "id": str(uuid4()),
                "codigo": codigo,
                "cliente": cliente,
                "items": items,
                "total": total,
                "estado": "Pendiente",
                "fecha_pedido": now_iso(),
            }
        )
        st.session_state.cart = {}
        return codigo

    cliente_res = supabase_request(
        "POST",
        "clientes",
        payload={
            "nombre": cliente["nombre"],
            "email": cliente["email"],
            "telefono": cliente.get("telefono", ""),
            "direccion": cliente.get("direccion", ""),
        },
        prefer_return=True,
    )
    cliente_id = cliente_res[0]["id"]

    pedido_res = supabase_request(
        "POST",
        "pedidos",
        payload={"codigo": codigo, "cliente_id": cliente_id, "total": total, "estado": "Pendiente"},
        prefer_return=True,
    )
    pedido_id = pedido_res[0]["id"]

    detalle = [
        {
            "pedido_id": pedido_id,
            "producto_id": item["producto_id"],
            "producto_nombre": item["nombre"],
            "categoria": item["categoria"],
            "precio": item["precio"],
            "cantidad": item["cantidad"],
            "subtotal": item["subtotal"],
        }
        for item in items
    ]
    supabase_request("POST", "detalle_pedidos", payload=detalle)
    st.session_state.cart = {}
    return codigo


def load_orders() -> tuple[list[dict], str]:
    if not has_supabase_config():
        return st.session_state.demo_orders, "demo"

    pedidos = supabase_request(
        "GET",
        "pedidos",
        params={
            "select": "id,codigo,total,estado,fecha_pedido,clientes(nombre,email,telefono,direccion)",
            "order": "fecha_pedido.desc",
        },
    )
    detalles = supabase_request("GET", "detalle_pedidos", params={"select": "*"})

    detalles_por_pedido: dict[str, list[dict]] = {}
    for item in detalles:
        detalles_por_pedido.setdefault(item["pedido_id"], []).append(
            {
                "producto_id": item["producto_id"],
                "nombre": item["producto_nombre"],
                "categoria": item["categoria"],
                "precio": float(item["precio"]),
                "cantidad": item["cantidad"],
                "subtotal": float(item["subtotal"]),
            }
        )

    orders = []
    for pedido in pedidos:
        cliente = pedido.get("clientes") or {}
        orders.append(
            {
                "id": pedido["id"],
                "codigo": pedido["codigo"],
                "cliente": cliente,
                "items": detalles_por_pedido.get(pedido["id"], []),
                "total": float(pedido["total"]),
                "estado": pedido["estado"],
                "fecha_pedido": pedido["fecha_pedido"],
            }
        )
    return orders, "supabase"


def update_order_status(order_id: str, estado: str) -> None:
    if not has_supabase_config():
        for order in st.session_state.demo_orders:
            if order["id"] == order_id:
                order["estado"] = estado
                return
    else:
        supabase_request(
            "PATCH",
            "pedidos",
            params={"id": f"eq.{order_id}"},
            payload={"estado": estado},
        )


def seed_mongodb() -> None:
    collection = get_mongo_collection()
    if collection is None:
        st.error("Configura MongoDB primero para cargar los productos semilla.")
        return
    for producto in PRODUCTOS_DEMO:
        collection.replace_one({"_id": producto["_id"]}, producto, upsert=True)
    st.success("Catalogo semilla cargado en MongoDB.")


def render_header(product_source: str, order_source: str) -> None:
    st.title("Falabella Cloud Order Manager")
    st.caption("Plataforma ecommerce escalable orientada a catalogo, carrito y gestion de pedidos.")

    cols = st.columns(3)
    cols[0].metric("Catalogo", "MongoDB" if product_source == "mongodb" else "Demo")
    cols[1].metric("Pedidos", "Supabase" if order_source == "supabase" else "Demo")
    cols[2].metric("Estado operativo", "Listo")


def render_catalog(productos: list[dict]) -> None:
    st.subheader("Catalogo de productos")

    categorias = ["Todas"] + sorted({producto["categoria"] for producto in productos})
    categoria = st.selectbox("Filtrar por categoria", categorias)
    busqueda = st.text_input("Buscar producto", placeholder="Laptop, zapatillas, TV...")

    filtrados = productos
    if categoria != "Todas":
        filtrados = [producto for producto in filtrados if producto["categoria"] == categoria]
    if busqueda:
        filtrados = [
            producto
            for producto in filtrados
            if busqueda.lower() in producto["nombre"].lower()
            or busqueda.lower() in producto["descripcion"].lower()
        ]

    for index in range(0, len(filtrados), 3):
        row = st.columns(3)
        for col, producto in zip(row, filtrados[index : index + 3]):
            with col:
                st.image(producto["imagen"], use_container_width=True)
                st.markdown(f"**{producto['nombre']}**")
                st.caption(f"{producto['categoria']} | Stock: {producto['stock']}")
                st.write(producto["descripcion"])
                st.write(f"**{money(float(producto['precio']))}**")

                with st.expander("Caracteristicas"):
                    st.json(producto.get("caracteristicas", {}), expanded=False)

                qty = st.number_input(
                    "Cantidad",
                    min_value=1,
                    max_value=max(1, int(producto["stock"])),
                    value=1,
                    key=f"qty_{product_id(producto)}",
                )
                if st.button("Agregar al carrito", key=f"add_{product_id(producto)}"):
                    add_to_cart(product_id(producto), qty)


def render_cart(productos: list[dict]) -> None:
    st.subheader("Carrito de compras")
    items = cart_items(productos)

    if not items:
        st.info("El carrito esta vacio. Agrega productos desde el catalogo.")
        return

    df = pd.DataFrame(items)
    df["precio"] = df["precio"].map(money)
    df["subtotal"] = df["subtotal"].map(money)
    st.dataframe(df[["nombre", "categoria", "precio", "cantidad", "subtotal"]], use_container_width=True)

    for item in items:
        if st.button(f"Quitar {item['nombre']}", key=f"remove_{item['producto_id']}"):
            remove_from_cart(item["producto_id"])
            st.rerun()

    st.metric("Total", money(cart_total(items)))

    with st.form("checkout_form"):
        st.markdown("**Datos del cliente**")
        nombre = st.text_input("Nombre completo")
        email = st.text_input("Correo electronico")
        telefono = st.text_input("Telefono")
        direccion = st.text_area("Direccion de entrega")
        submitted = st.form_submit_button("Confirmar compra")

    if submitted:
        if not nombre or not email:
            st.error("Ingresa nombre y correo para generar el pedido.")
            return
        codigo = create_order(
            {"nombre": nombre, "email": email, "telefono": telefono, "direccion": direccion},
            items,
        )
        st.success(f"Pedido generado correctamente: {codigo}")
        st.rerun()


def render_admin(orders: list[dict]) -> None:
    st.subheader("Administracion de pedidos")

    if not orders:
        st.info("Aun no hay pedidos registrados.")
        return

    search = st.text_input("Buscar por codigo de pedido")
    status = st.selectbox("Filtrar por estado", ["Todos"] + ESTADOS)

    filtered = orders
    if search:
        filtered = [order for order in filtered if search.upper() in order["codigo"].upper()]
    if status != "Todos":
        filtered = [order for order in filtered if order["estado"] == status]

    table = [
        {
            "codigo": order["codigo"],
            "cliente": order["cliente"].get("nombre", ""),
            "estado": order["estado"],
            "total": money(order["total"]),
            "fecha_pedido": order["fecha_pedido"],
        }
        for order in filtered
    ]
    st.dataframe(pd.DataFrame(table), use_container_width=True)

    for order in filtered:
        with st.expander(f"{order['codigo']} - {order['estado']}"):
            st.write(f"Cliente: **{order['cliente'].get('nombre', '')}**")
            st.write(f"Email: {order['cliente'].get('email', '')}")
            st.write(f"Total: **{money(order['total'])}**")

            detalle = pd.DataFrame(order["items"])
            if not detalle.empty:
                detalle["precio"] = detalle["precio"].map(money)
                detalle["subtotal"] = detalle["subtotal"].map(money)
                st.dataframe(
                    detalle[["nombre", "categoria", "precio", "cantidad", "subtotal"]],
                    use_container_width=True,
                )

            nuevo_estado = st.selectbox(
                "Actualizar estado",
                ESTADOS,
                index=ESTADOS.index(order["estado"]),
                key=f"estado_{order['id']}",
            )
            if st.button("Guardar estado", key=f"save_{order['id']}"):
                update_order_status(order["id"], nuevo_estado)
                st.success("Estado actualizado.")
                st.rerun()


def render_dashboard(orders: list[dict]) -> None:
    st.subheader("Dashboard")

    total_orders = len(orders)
    pending = sum(1 for order in orders if order["estado"] == "Pendiente")
    delivered = sum(1 for order in orders if order["estado"] == "Entregado")
    sales = sum(order["total"] for order in orders)

    cols = st.columns(4)
    cols[0].metric("Total de pedidos", total_orders)
    cols[1].metric("Pedidos pendientes", pending)
    cols[2].metric("Pedidos entregados", delivered)
    cols[3].metric("Ventas totales", money(sales))

    items = [item for order in orders for item in order["items"]]
    if not items:
        st.info("Genera pedidos para visualizar metricas por producto y categoria.")
        return

    df = pd.DataFrame(items)
    top_products = df.groupby("nombre", as_index=False)["cantidad"].sum().sort_values("cantidad", ascending=False)
    by_category = df.groupby("categoria", as_index=False)["subtotal"].sum().sort_values("subtotal", ascending=False)

    left, right = st.columns(2)
    with left:
        st.markdown("**Productos mas vendidos**")
        st.bar_chart(top_products.set_index("nombre"))
    with right:
        st.markdown("**Ventas por categoria**")
        st.bar_chart(by_category.set_index("categoria"))


def render_data_tools(product_source: str) -> None:
    st.subheader("Configuracion y carga inicial")
    st.write("Usa esta seccion para preparar datos de demostracion y validar conexiones.")

    col1, col2 = st.columns(2)
    with col1:
        st.info("MongoDB almacena el catalogo flexible de productos.")
        if st.button("Cargar productos semilla en MongoDB"):
            seed_mongodb()
    with col2:
        st.info("Supabase almacena clientes, pedidos y detalle de pedidos.")
        st.code("database/supabase_schema.sql", language="text")

    if product_source == "demo":
        st.warning("El catalogo esta usando datos demo porque MongoDB no esta configurado o no tiene productos.")


def main() -> None:
    st.set_page_config(page_title="Falabella Order Manager", page_icon="🛒", layout="wide")
    init_state()

    productos, product_source = load_products()
    orders, order_source = load_orders()
    render_header(product_source, order_source)

    page = st.sidebar.radio(
        "Modulos del sistema",
        ["Catalogo", "Carrito", "Pedidos administrativos", "Dashboard", "Configuracion"],
    )
    st.sidebar.divider()
    st.sidebar.write(f"Productos en catalogo: **{len(productos)}**")
    st.sidebar.write(f"Items en carrito: **{sum(st.session_state.cart.values())}**")
    st.sidebar.write(f"Pedidos registrados: **{len(orders)}**")

    if page == "Catalogo":
        render_catalog(productos)
    elif page == "Carrito":
        render_cart(productos)
    elif page == "Pedidos administrativos":
        render_admin(orders)
    elif page == "Dashboard":
        render_dashboard(orders)
    else:
        render_data_tools(product_source)


if __name__ == "__main__":
    main()
