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
ROLES = ["cliente", "admin"]

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
    url = url.rstrip("/")
    if url.endswith("/rest/v1"):
        url = url.removesuffix("/rest/v1")
    return url, key


def has_supabase_config() -> bool:
    url, key = get_supabase_config()
    return bool(url and key)


def supabase_key_type() -> str:
    _, key = get_supabase_config()
    lowered = key.lower()
    if not key:
        return "missing"
    if "service_role" in lowered or lowered.startswith("sb_secret_"):
        return "secret"
    if lowered.startswith("sb_publishable_") or "anon" in lowered:
        return "public"
    return "unknown"


def render_security_notices() -> None:
    key_type = supabase_key_type()
    if key_type == "secret":
        st.warning(
            "Supabase esta usando una secret/service key. Para una V1 segura, usa anon/public key "
            "con politicas RLS y guarda la secret key solo en entornos privados."
        )
    elif key_type == "unknown":
        st.info(
            "No se pudo identificar el tipo de key de Supabase. Verifica que sea anon/public/publishable "
            "para evitar exponer credenciales administrativas."
        )


def supabase_headers(prefer_return: bool = False) -> dict[str, str]:
    _, key = get_supabase_config()
    token = st.session_state.get("access_token") or key
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {token}",
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
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:300] if response.text else str(exc)
        raise RuntimeError(
            f"Supabase rechazo la solicitud a la tabla '{table}'. "
            f"Codigo HTTP: {response.status_code}. Detalle: {detail}"
        ) from exc
    if not response.text:
        return []
    return response.json()


def supabase_auth_request(endpoint: str, payload: dict) -> dict:
    url, key = get_supabase_config()
    response = requests.post(
        f"{url}/auth/v1/{endpoint}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=12,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:300] if response.text else str(exc)
        raise RuntimeError(f"Supabase Auth rechazo la solicitud. Detalle: {detail}") from exc
    return response.json()


def init_state() -> None:
    st.session_state.setdefault("cart", {})
    st.session_state.setdefault("demo_orders", [])
    st.session_state.setdefault("access_token", "")
    st.session_state.setdefault("current_user", None)
    st.session_state.setdefault("current_profile", None)


def money(value: float) -> str:
    return f"S/ {value:,.2f}"


def product_id(producto: dict) -> str:
    return str(producto.get("_id") or producto.get("id"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_profile() -> dict:
    return st.session_state.get("current_profile") or {}


def current_role() -> str:
    return current_profile().get("rol", "cliente")


def is_authenticated() -> bool:
    return bool(st.session_state.get("access_token") and st.session_state.get("current_user"))


def load_profile(user: dict) -> dict | None:
    user_id = user.get("id")
    if not user_id:
        return None
    perfiles = supabase_request(
        "GET",
        "perfiles",
        params={"select": "*", "id": f"eq.{user_id}", "limit": "1"},
    )
    return perfiles[0] if perfiles else None


def create_profile(user: dict, nombre: str, rol: str = "cliente") -> dict:
    profile = {
        "id": user["id"],
        "nombre": nombre,
        "email": user["email"],
        "rol": rol if rol in ROLES else "cliente",
    }
    result = supabase_request("POST", "perfiles", payload=profile, prefer_return=True)
    return result[0]


def login_user(email: str, password: str) -> None:
    auth = supabase_auth_request(
        "token?grant_type=password",
        {"email": email, "password": password},
    )
    st.session_state.access_token = auth["access_token"]
    st.session_state.current_user = auth["user"]
    profile = load_profile(auth["user"])
    if profile is None:
        profile = create_profile(auth["user"], auth["user"].get("email", "Usuario"))
    st.session_state.current_profile = profile


def register_user(nombre: str, email: str, password: str) -> None:
    auth = supabase_auth_request(
        "signup",
        {"email": email, "password": password, "data": {"nombre": nombre}},
    )
    user = auth.get("user")
    access_token = auth.get("access_token")
    if not user:
        raise RuntimeError("No se recibio el usuario creado desde Supabase Auth.")
    if not access_token:
        raise RuntimeError(
            "Usuario registrado. Revisa si Supabase requiere confirmar el correo antes de iniciar sesion."
        )
    st.session_state.access_token = access_token
    st.session_state.current_user = user
    st.session_state.current_profile = create_profile(user, nombre)


def logout_user() -> None:
    st.session_state.access_token = ""
    st.session_state.current_user = None
    st.session_state.current_profile = None
    st.session_state.cart = {}


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


def load_current_user_orders(orders: list[dict]) -> list[dict]:
    email = current_profile().get("email", "").lower()
    if not email:
        return []
    return [order for order in orders if order["cliente"].get("email", "").lower() == email]


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


def render_auth_page() -> None:
    st.title("Falabella Cloud Order Manager")
    st.caption("Inicia sesion para comprar o administrar pedidos.")

    if not has_supabase_config():
        st.error("Configura Supabase en secrets para usar autenticacion.")
        return

    tab_login, tab_register = st.tabs(["Iniciar sesion", "Crear cuenta"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Correo electronico", key="login_email")
            password = st.text_input("Contrasena", type="password", key="login_password")
            submitted = st.form_submit_button("Entrar")
        if submitted:
            if not email or not password:
                st.error("Ingresa correo y contrasena.")
                return
            try:
                login_user(email, password)
                st.success("Sesion iniciada.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo iniciar sesion. {exc}")

    with tab_register:
        with st.form("register_form"):
            nombre = st.text_input("Nombre completo")
            email = st.text_input("Correo electronico")
            password = st.text_input("Contrasena", type="password")
            submitted = st.form_submit_button("Crear cuenta cliente")
        if submitted:
            if not nombre or not email or not password:
                st.error("Completa nombre, correo y contrasena.")
                return
            if len(password) < 6:
                st.error("La contrasena debe tener al menos 6 caracteres.")
                return
            try:
                register_user(nombre, email, password)
                st.success("Cuenta creada.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear la cuenta. {exc}")


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
        profile = current_profile()
        nombre = st.text_input("Nombre completo", value=profile.get("nombre", ""))
        email = st.text_input("Correo electronico", value=profile.get("email", ""))
        telefono = st.text_input("Telefono")
        direccion = st.text_area("Direccion de entrega")
        submitted = st.form_submit_button("Confirmar compra")

    if submitted:
        if not nombre or not email:
            st.error("Ingresa nombre y correo para generar el pedido.")
            return
        try:
            codigo = create_order(
                {"nombre": nombre, "email": email, "telefono": telefono, "direccion": direccion},
                items,
            )
            st.success(f"Pedido generado correctamente: {codigo}")
            st.rerun()
        except Exception as exc:
            st.error("No se pudo guardar el pedido en Supabase.")
            st.info(
                "Revisa que hayas ejecutado el SQL completo, incluyendo permisos y politicas RLS. "
                f"Detalle tecnico: {exc}"
            )


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


def render_my_orders(orders: list[dict]) -> None:
    st.subheader("Mis pedidos")
    user_orders = load_current_user_orders(orders)

    if not user_orders:
        st.info("Aun no tienes pedidos registrados con tu correo.")
        return

    for order in user_orders:
        with st.expander(f"{order['codigo']} - {order['estado']}"):
            st.write(f"Fecha: {order['fecha_pedido']}")
            st.write(f"Total: **{money(order['total'])}**")
            detalle = pd.DataFrame(order["items"])
            if not detalle.empty:
                detalle["precio"] = detalle["precio"].map(money)
                detalle["subtotal"] = detalle["subtotal"].map(money)
                st.dataframe(
                    detalle[["nombre", "categoria", "precio", "cantidad", "subtotal"]],
                    use_container_width=True,
                )


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
    render_security_notices()

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

    if not is_authenticated():
        render_auth_page()
        return

    productos, product_source = load_products()
    orders, order_source = load_orders()
    render_header(product_source, order_source)
    render_security_notices()

    profile = current_profile()
    role = current_role()
    st.sidebar.write(f"Usuario: **{profile.get('nombre', 'Usuario')}**")
    st.sidebar.write(f"Rol: **{role}**")
    if st.sidebar.button("Cerrar sesion"):
        logout_user()
        st.rerun()

    if role == "admin":
        pages = ["Pedidos administrativos", "Dashboard", "Configuracion"]
    else:
        pages = ["Catalogo", "Carrito", "Mis pedidos"]

    page = st.sidebar.radio(
        "Modulos del sistema",
        pages,
    )
    st.sidebar.divider()
    st.sidebar.write(f"Productos en catalogo: **{len(productos)}**")
    st.sidebar.write(f"Items en carrito: **{sum(st.session_state.cart.values())}**")
    st.sidebar.write(f"Pedidos registrados: **{len(orders)}**")

    if page == "Catalogo":
        render_catalog(productos)
    elif page == "Carrito":
        render_cart(productos)
    elif page == "Mis pedidos":
        render_my_orders(orders)
    elif page == "Pedidos administrativos":
        render_admin(orders)
    elif page == "Dashboard":
        render_dashboard(orders)
    else:
        render_data_tools(product_source)


if __name__ == "__main__":
    main()
