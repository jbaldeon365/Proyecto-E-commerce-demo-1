from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

try:
    from pymongo import MongoClient
except Exception:  # pragma: no cover
    MongoClient = None

try:
    import redis
except Exception:  # pragma: no cover
    redis = None

ESTADOS_OPERATIVOS = ["Pendiente", "Procesando", "Enviado", "Entregado"]
ESTADOS_EXCEPCION = ["Pago pendiente", "Observado", "Revision administrativa", "Cancelado"]
ESTADOS = ESTADOS_OPERATIVOS + ESTADOS_EXCEPCION
ESTADOS_ADMINISTRATIVOS = ["Revision administrativa"]
ROLES = ["cliente", "admin"]
METODOS_PAGO = ["Tarjeta", "Yape"]
ESTADOS_PAGO = ["Aprobado", "Rechazado"]
CATALOG_CACHE_KEY = "catalogo:productos"
CATALOG_CACHE_TTL_SECONDS = 300
LIMA_TZ = ZoneInfo("America/Lima")
MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
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


def get_redis_url() -> str:
    return get_secret("redis", "url", "REDIS_URL")


@st.cache_resource(show_spinner=False)
def get_redis_client():
    url = get_redis_url()
    if not url or redis is None:
        return None

    try:
        client = redis.from_url(url, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


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
    st.session_state.setdefault("access_token", "")
    st.session_state.setdefault("current_user", None)
    st.session_state.setdefault("current_profile", None)
    st.session_state.setdefault("cart_loaded_from_redis", False)
    st.session_state.setdefault("show_payment_gateway", False)
    st.session_state.setdefault("payment_step", 1)
    st.session_state.setdefault("checkout_customer", {})
    st.session_state.setdefault("checkout_items", [])
    st.session_state.setdefault("payment_method", METODOS_PAGO[0])
    st.session_state.setdefault("payment_details", {})
    st.session_state.setdefault("simulate_payment_rejection", False)
    st.session_state.setdefault("checkout_step", "cart")
    st.session_state.setdefault("show_order_confirmation", False)
    st.session_state.setdefault("order_confirmation", {})
    st.session_state.setdefault("status_notifications", [])
    st.session_state.setdefault("order_status_snapshot", {})


def money(value: float) -> str:
    return f"S/ {value:,.2f}"


def humanize_key(key: str) -> str:
    return key.replace("_", " ").capitalize()


def product_id(producto: dict) -> str:
    return str(producto.get("_id") or producto.get("id"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_lima_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(LIMA_TZ).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return value


def format_lima_date_friendly(value: str) -> str:
    if not value:
        return ""
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        lima = parsed.astimezone(LIMA_TZ)
        return f"{lima.day} de {MESES_ES[lima.month - 1]}"
    except Exception:
        return value


def order_status_icon(estado: str) -> str:
    return {
        "Pendiente": "\U0001f7e1",
        "Procesando": "\U0001f535",
        "Enviado": "\U0001f69a",
        "Entregado": "\u2705",
        "Cancelado": "\u274c",
        "Pago pendiente": "\u23f3",
        "Observado": "\u26a0\ufe0f",
        "Revision administrativa": "\U0001f50d",
    }.get(estado, "\U0001f4cb")


def order_status_message(order: dict) -> str:
    estado = order["estado"]
    if estado == "Pendiente":
        return "Tu pedido esta siendo preparado."
    if estado == "Procesando":
        return "Tu pedido esta en proceso de despacho."
    if estado == "Enviado":
        return "Tu pedido esta en camino."
    if estado == "Entregado":
        fecha = format_lima_date_friendly(order.get("fecha_actualizacion_estado", ""))
        return f"Entregado el {fecha}." if fecha else "Pedido entregado."
    if estado == "Cancelado":
        return "Este pedido fue cancelado."
    if order.get("motivo_revision"):
        return order["motivo_revision"]
    return "Tu pedido requiere revision administrativa."


def order_progress_index(estado: str) -> int:
    if estado in ESTADOS_OPERATIVOS:
        return ESTADOS_OPERATIVOS.index(estado)
    return 0


def render_order_progress(estado: str) -> None:
    if estado not in ESTADOS_OPERATIVOS:
        st.warning("Este pedido esta fuera del flujo automatico y requiere revision administrativa.")
        return

    current = order_progress_index(estado)
    progress = (current + 1) / len(ESTADOS_OPERATIVOS)
    st.progress(progress)
    cols = st.columns(len(ESTADOS_OPERATIVOS))
    for idx, step in enumerate(ESTADOS_OPERATIVOS):
        marker = "✓" if idx <= current else "○"
        cols[idx].caption(f"{marker} {step}")


def current_profile() -> dict:
    return st.session_state.get("current_profile") or {}


def current_role() -> str:
    return current_profile().get("rol", "cliente")


def is_authenticated() -> bool:
    return bool(st.session_state.get("access_token") and st.session_state.get("current_user"))


def current_user_id() -> str:
    user = st.session_state.get("current_user") or {}
    return user.get("id", "")


def current_email() -> str:
    return current_profile().get("email", "").strip().lower()


def redis_cart_key() -> str:
    user_id = current_user_id()
    return f"cart:{user_id}" if user_id else ""


def redis_order_status_key() -> str:
    user_id = current_user_id()
    return f"orders:last-status:{user_id}" if user_id else ""


def load_cart_from_redis() -> None:
    if st.session_state.get("cart_loaded_from_redis"):
        return

    client = get_redis_client()
    key = redis_cart_key()
    if client is None or not key:
        st.session_state.cart_loaded_from_redis = True
        return

    raw_cart = client.get(key)
    try:
        raw_cart = client.get(key)
        if raw_cart:
            cart = json.loads(raw_cart)
            st.session_state.cart = {str(pid): int(quantity) for pid, quantity in cart.items()}
    except (TypeError, ValueError):
        st.session_state.cart = {}
    except Exception:
        pass

    st.session_state.cart_loaded_from_redis = True


def save_cart_to_redis() -> None:
    client = get_redis_client()
    key = redis_cart_key()
    if client is None or not key:
        return

    try:
        if st.session_state.cart:
            client.set(key, json.dumps(st.session_state.cart), ex=60 * 60 * 24)
        else:
            client.delete(key)
    except Exception:
        pass


def clear_cart_from_redis() -> None:
    client = get_redis_client()
    key = redis_cart_key()
    if client is not None and key:
        try:
            client.delete(key)
        except Exception:
            pass


def load_order_status_snapshot() -> dict:
    client = get_redis_client()
    key = redis_order_status_key()
    if client is not None and key:
        try:
            raw_snapshot = client.get(key)
            return json.loads(raw_snapshot) if raw_snapshot else {}
        except Exception:
            return {}
    return st.session_state.get("order_status_snapshot", {})


def save_order_status_snapshot(snapshot: dict) -> None:
    client = get_redis_client()
    key = redis_order_status_key()
    if client is not None and key:
        try:
            client.set(key, json.dumps(snapshot), ex=60 * 60 * 24 * 30)
            return
        except Exception:
            pass
    st.session_state.order_status_snapshot = snapshot


def notify_order_status_changes(orders: list[dict]) -> None:
    if current_role() != "cliente":
        return

    user_orders = load_current_user_orders(orders)
    current_snapshot = {order["codigo"]: order["estado"] for order in user_orders}
    previous_snapshot = load_order_status_snapshot()

    notifications = []
    for order in user_orders:
        codigo = order["codigo"]
        previous_status = previous_snapshot.get(codigo)
        current_status = order["estado"]
        if previous_status and previous_status != current_status:
            first_item = (order.get("items") or [{}])[0]
            product_code = first_item.get("producto_id", "")
            product_label = f" - Producto {product_code}" if product_code else ""
            notifications.append(
                f"Pedido {codigo}{product_label}: {previous_status} -> {current_status}"
            )

    save_order_status_snapshot(current_snapshot)
    st.session_state.status_notifications = notifications

    for notification in notifications:
        st.toast(notification)


def normalize_product(producto: dict) -> dict:
    normalized = dict(producto)
    normalized["_id"] = str(normalized.get("_id") or normalized.get("id"))
    return normalized


def load_catalog_from_redis() -> list[dict] | None:
    client = get_redis_client()
    if client is None:
        return None
    try:
        raw_catalog = client.get(CATALOG_CACHE_KEY)
        if not raw_catalog:
            return None
        catalog = json.loads(raw_catalog)
        productos = [normalize_product(producto) for producto in catalog]
        if is_legacy_catalog_cache(productos):
            client.delete(CATALOG_CACHE_KEY)
            return None
        return productos
    except Exception:
        return None


def save_catalog_to_redis(productos: list[dict]) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        normalized = [normalize_product(producto) for producto in productos]
        client.set(CATALOG_CACHE_KEY, json.dumps(normalized), ex=CATALOG_CACHE_TTL_SECONDS)
    except Exception:
        pass


def is_legacy_catalog_cache(productos: list[dict]) -> bool:
    legacy_names = {
        "Laptop Lenovo IdeaPad 15",
        "Smart TV Samsung 55 4K",
        "Zapatillas Urbanas Hombre",
        "Refrigeradora No Frost 300L",
        "Audifonos Bluetooth Sony",
        "Casaca Impermeable Mujer",
    }
    names = {str(producto.get("nombre", "")) for producto in productos}
    return bool(names & legacy_names)


def invalidate_catalog_cache() -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(CATALOG_CACHE_KEY)
    except Exception:
        pass


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


def update_current_profile_name(nombre: str) -> None:
    user_id = current_user_id()
    if not user_id:
        return
    supabase_request(
        "PATCH",
        "perfiles",
        params={"id": f"eq.{user_id}"},
        payload={"nombre": nombre.strip(), "updated_at": now_iso()},
    )
    profile = current_profile().copy()
    profile["nombre"] = nombre.strip()
    st.session_state.current_profile = profile


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
    st.session_state.cart_loaded_from_redis = False
    load_cart_from_redis()


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
    st.session_state.cart_loaded_from_redis = False
    load_cart_from_redis()


def logout_user() -> None:
    save_cart_to_redis()
    st.session_state.access_token = ""
    st.session_state.current_user = None
    st.session_state.current_profile = None
    st.session_state.cart = {}
    st.session_state.cart_loaded_from_redis = False


def load_products() -> tuple[list[dict], str]:
    try:
        cached_products = load_catalog_from_redis()
        if cached_products:
            return cached_products, "redis"

        collection = get_mongo_collection()
        if collection is None:
            st.error("No se pudo conectar a MongoDB. Configura el catalogo en MongoDB Atlas.")
            return [], "sin_conexion"
        productos = [normalize_product(producto) for producto in collection.find({}).sort("nombre", 1)]
        if not productos:
            st.warning("No hay productos registrados en MongoDB Atlas.")
            return [], "mongodb_vacio"
        save_catalog_to_redis(productos)
        return productos, "mongodb"
    except Exception as exc:
        st.error(f"No se pudo cargar el catalogo desde MongoDB Atlas. Detalle: {exc}")
        return [], "sin_conexion"


def add_to_cart(pid: str, quantity: int) -> None:
    current = st.session_state.cart.get(pid, 0)
    st.session_state.cart[pid] = current + quantity
    save_cart_to_redis()
    st.toast("Producto agregado al carrito")


def set_cart_quantity(pid: str, quantity: int) -> None:
    if quantity <= 0:
        st.session_state.cart.pop(pid, None)
    else:
        st.session_state.cart[pid] = quantity
    save_cart_to_redis()


def remove_from_cart(pid: str) -> None:
    st.session_state.cart.pop(pid, None)
    save_cart_to_redis()


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
                "imagen": producto.get("imagen", ""),
                "stock": int(producto.get("stock", 0)),
            }
        )
    return items


def cart_total(items: list[dict]) -> float:
    return sum(item["subtotal"] for item in items)


def simulate_payment(metodo_pago: str, estado_pago: str) -> dict:
    status = estado_pago if estado_pago in ESTADOS_PAGO else "Aprobado"
    return {
        "metodo_pago": metodo_pago if metodo_pago in METODOS_PAGO else "Tarjeta",
        "estado_pago": status,
        "codigo_pago": f"PAY-{str(uuid4())[:8].upper()}",
        "fecha_pago": now_iso(),
    }


def reset_payment_gateway() -> None:
    st.session_state.show_payment_gateway = False
    st.session_state.payment_step = 1
    st.session_state.checkout_customer = {}
    st.session_state.checkout_items = []
    st.session_state.payment_method = METODOS_PAGO[0]
    st.session_state.payment_details = {}
    st.session_state.simulate_payment_rejection = False
    st.session_state.checkout_step = "cart"


def close_order_confirmation() -> None:
    st.session_state.show_order_confirmation = False
    st.session_state.order_confirmation = {}
    st.session_state.checkout_step = "cart"


def mask_card_number(card_number: str) -> str:
    digits = "".join(char for char in card_number if char.isdigit())
    if len(digits) < 4:
        return "****"
    return f"**** **** **** {digits[-4:]}"


def validate_payment_details(method: str, details: dict) -> list[str]:
    errors = []

    if method == "Tarjeta":
        card_number = "".join(char for char in details.get("card_number", "") if char.isdigit())
        cvv = "".join(char for char in details.get("cvv", "") if char.isdigit())
        if not details.get("card_holder"):
            errors.append("Ingresa el nombre del titular de la tarjeta.")
        if len(card_number) < 13 or len(card_number) > 19:
            errors.append("Ingresa un numero de tarjeta valido.")
        if not details.get("expiry"):
            errors.append("Ingresa la fecha de vencimiento.")
        if len(cvv) not in [3, 4]:
            errors.append("Ingresa un CVV valido.")
        if not details.get("document"):
            errors.append("Ingresa el documento del titular.")
    elif method == "Yape":
        phone = "".join(char for char in details.get("phone", "") if char.isdigit())
        approval_code = "".join(char for char in details.get("approval_code", "") if char.isdigit())
        if len(phone) != 9:
            errors.append("Ingresa un numero de celular Yape de 9 digitos.")
        if len(approval_code) < 6:
            errors.append("Ingresa el numero de aprobacion de Yape.")
    else:
        errors.append("Selecciona un metodo de pago valido.")

    return errors


def payment_gateway_content() -> None:
    items = st.session_state.get("checkout_items", [])
    customer = st.session_state.get("checkout_customer", {})
    total = cart_total(items)
    step = st.session_state.get("payment_step", 1)

    st.metric("Monto total a pagar", money(total))
    st.caption("Pasarela simulada para validar el flujo de checkout antes de generar el pedido.")

    if step == 1:
        st.markdown("**Paso 1 de 3: selecciona el metodo de pago**")
        if st.session_state.payment_method not in METODOS_PAGO:
            st.session_state.payment_method = METODOS_PAGO[0]
        method = st.radio(
            "Metodo de pago",
            METODOS_PAGO,
            index=METODOS_PAGO.index(st.session_state.payment_method),
            horizontal=True,
        )
        st.session_state.payment_method = method

        col1, col2 = st.columns(2)
        if col1.button("Cancelar", use_container_width=True):
            reset_payment_gateway()
            st.rerun()
        if col2.button("Siguiente", type="primary", use_container_width=True):
            st.session_state.payment_step = 2
            st.rerun()

    elif step == 2:
        method = st.session_state.payment_method
        details = st.session_state.payment_details
        st.markdown(f"**Paso 2 de 3: datos de pago - {method}**")

        if method == "Tarjeta":
            details["card_holder"] = st.text_input(
                "Titular de la tarjeta",
                value=details.get("card_holder", customer.get("nombre", "")),
            )
            details["card_number"] = st.text_input(
                "Numero de tarjeta",
                value=details.get("card_number", ""),
                placeholder="4111 1111 1111 1111",
            )
            col_a, col_b = st.columns(2)
            details["expiry"] = col_a.text_input(
                "Vencimiento",
                value=details.get("expiry", ""),
                placeholder="MM/AA",
            )
            details["cvv"] = col_b.text_input(
                "CVV",
                value=details.get("cvv", ""),
                type="password",
            )
            details["document"] = st.text_input(
                "Documento del titular",
                value=details.get("document", ""),
                placeholder="DNI o CE",
            )
            details["installments"] = st.selectbox(
                "Cuotas",
                ["1 cuota", "3 cuotas", "6 cuotas", "12 cuotas"],
                index=["1 cuota", "3 cuotas", "6 cuotas", "12 cuotas"].index(
                    details.get("installments", "1 cuota")
                ),
            )
        else:
            details["phone"] = st.text_input(
                "Numero de celular Yape",
                value=details.get("phone", ""),
                placeholder="999888777",
            )
            details["approval_code"] = st.text_input(
                "Numero de aprobacion",
                value=details.get("approval_code", ""),
                placeholder="123456",
            )

        st.session_state.payment_details = details

        col1, col2 = st.columns(2)
        if col1.button("Atras", use_container_width=True):
            st.session_state.payment_step = 1
            st.rerun()
        if col2.button("Siguiente", type="primary", use_container_width=True):
            errors = validate_payment_details(method, details)
            if errors:
                for error in errors:
                    st.error(error)
            else:
                st.session_state.payment_step = 3
                st.rerun()

    else:
        method = st.session_state.payment_method
        details = st.session_state.payment_details
        st.markdown("**Paso 3 de 3: confirma la operacion**")
        st.write(f"Cliente: **{customer.get('nombre', '')}**")
        st.write(f"Correo: {customer.get('email', '')}")
        st.write(f"Metodo: **{method}**")
        if method == "Tarjeta":
            st.write(f"Tarjeta: {mask_card_number(details.get('card_number', ''))}")
            st.write(f"Cuotas: {details.get('installments', '1 cuota')}")
        else:
            st.write(f"Celular Yape: {details.get('phone', '')}")
            st.write(f"Nro. aprobacion: {details.get('approval_code', '')}")

        st.session_state.simulate_payment_rejection = st.checkbox(
            "Simular rechazo de la pasarela para pruebas",
            value=st.session_state.simulate_payment_rejection,
        )

        col1, col2 = st.columns(2)
        if col1.button("Atras", use_container_width=True):
            st.session_state.payment_step = 2
            st.rerun()
        if col2.button("Confirmar pago", type="primary", use_container_width=True):
            status = "Rechazado" if st.session_state.simulate_payment_rejection else "Aprobado"
            payment = simulate_payment(method, status)
            try:
                codigo = create_order(customer, items, payment)
                st.session_state.order_confirmation = {
                    "codigo": codigo,
                    "cliente": customer,
                    "items": items,
                    "payment": payment,
                    "total": total,
                    "estado_inicial": "Pendiente",
                }
                reset_payment_gateway()
                st.session_state.show_order_confirmation = True
                st.rerun()
            except Exception as exc:
                st.error("No se pudo completar la compra.")
                st.info(f"Detalle tecnico: {exc}")


def order_confirmation_content() -> None:
    confirmation = st.session_state.get("order_confirmation", {})
    if not confirmation:
        close_order_confirmation()
        st.rerun()

    customer = confirmation.get("cliente", {})
    items = confirmation.get("items", [])
    payment = confirmation.get("payment", {})

    st.success("Pago aprobado y pedido generado correctamente.")
    st.metric("Codigo de pedido", confirmation.get("codigo", ""))
    st.write(f"Cliente: **{customer.get('nombre', '')}**")
    st.write(f"Correo: {customer.get('email', '')}")
    st.write(f"Metodo de pago: **{payment.get('metodo_pago', '')}**")
    st.write(f"Codigo de pago: {payment.get('codigo_pago', '')}")
    st.write(f"Fecha de pago: {format_lima_datetime(payment.get('fecha_pago', ''))}")
    st.write(f"Estado inicial: **{confirmation.get('estado_inicial', 'Pendiente')}**")
    st.write(f"Total: **{money(float(confirmation.get('total', 0)))}**")

    detalle = pd.DataFrame(items)
    if not detalle.empty:
        detalle["precio"] = detalle["precio"].map(money)
        detalle["subtotal"] = detalle["subtotal"].map(money)
        st.dataframe(
            detalle[["nombre", "categoria", "precio", "cantidad", "subtotal"]],
            use_container_width=True,
            hide_index=True,
        )

    if st.button("Continuar", type="primary", use_container_width=True):
        close_order_confirmation()
        st.rerun()


def render_order_confirmation() -> None:
    dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if dialog:
        dialog("Comprobante de pedido")(order_confirmation_content)()
    else:
        with st.container(border=True):
            order_confirmation_content()


def render_payment_gateway() -> None:
    dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if dialog:
        dialog("Pasarela de pago simulada")(payment_gateway_content)()
    else:
        with st.container(border=True):
            payment_gateway_content()


def record_payment_attempt(cliente: dict, payment: dict, amount: float, pedido_id: str | None = None) -> None:
    if not has_supabase_config():
        return

    try:
        supabase_request(
            "POST",
            "pagos_simulados",
            payload={
                "pedido_id": pedido_id,
                "cliente_email": cliente.get("email", ""),
                "metodo_pago": payment["metodo_pago"],
                "estado_pago": payment["estado_pago"],
                "codigo_pago": payment["codigo_pago"],
                "monto": amount,
                "fecha_pago": payment["fecha_pago"],
            },
        )
    except Exception:
        pass


def validate_cart_stock(items: list[dict]) -> list[str]:
    collection = get_mongo_collection()
    errors = []

    if collection is None:
        return errors

    for item in items:
        producto = collection.find_one({"_id": item["producto_id"]}, {"stock": 1, "nombre": 1})
        if not producto:
            errors.append(f"{item['nombre']} ya no esta disponible en el catalogo.")
            continue
        available = int(producto.get("stock", 0))
        requested = int(item["cantidad"])
        if requested > available:
            errors.append(
                f"{item['nombre']}: solicitaste {requested}, pero solo hay {available} disponible(s)."
            )

    return errors


def get_or_save_customer(cliente: dict) -> str:
    email = cliente["email"].strip().lower()
    payload = {
        "nombre": cliente["nombre"].strip(),
        "email": email,
        "telefono": cliente.get("telefono", "").strip(),
        "direccion": cliente.get("direccion", "").strip(),
        "updated_at": now_iso(),
    }
    existing = supabase_request(
        "GET",
        "clientes",
        params={"select": "id", "email": f"eq.{email}", "limit": 1},
    )
    if existing:
        cliente_id = existing[0]["id"]
        supabase_request(
            "PATCH",
            "clientes",
            params={"id": f"eq.{cliente_id}"},
            payload=payload,
        )
        return cliente_id

    cliente_res = supabase_request(
        "POST",
        "clientes",
        payload=payload,
        prefer_return=True,
    )
    return cliente_res[0]["id"]


def load_customer_by_email(email: str) -> dict:
    normalized_email = email.strip().lower()
    if not normalized_email or not has_supabase_config():
        return {}
    clientes = supabase_request(
        "GET",
        "clientes",
        params={"select": "*", "email": f"eq.{normalized_email}", "limit": 1},
    )
    return clientes[0] if clientes else {}


def save_current_customer_profile(nombre: str, telefono: str, direccion: str) -> None:
    email = current_email()
    if not email:
        raise RuntimeError("No se encontro el correo del usuario autenticado.")
    get_or_save_customer(
        {
            "nombre": nombre,
            "email": email,
            "telefono": telefono,
            "direccion": direccion,
        }
    )


def discount_stock(items: list[dict]) -> None:
    collection = get_mongo_collection()
    if collection is None:
        return

    updated_items = []
    try:
        for item in items:
            result = collection.update_one(
                {"_id": item["producto_id"], "stock": {"$gte": int(item["cantidad"])}},
                {"$inc": {"stock": -int(item["cantidad"])}},
            )
            if result.modified_count != 1:
                raise RuntimeError(f"No se pudo descontar stock de {item['nombre']}.")
            updated_items.append(item)
    except Exception:
        for item in updated_items:
            collection.update_one(
                {"_id": item["producto_id"]},
                {"$inc": {"stock": int(item["cantidad"])}},
            )
        raise
    invalidate_catalog_cache()


def clean_cart_by_stock(productos: list[dict]) -> list[str]:
    by_id = {product_id(producto): producto for producto in productos}
    warnings = []
    changed = False

    for pid, quantity in list(st.session_state.cart.items()):
        producto = by_id.get(pid)
        if not producto:
            st.session_state.cart.pop(pid, None)
            warnings.append("Se retiro un producto que ya no existe en el catalogo.")
            changed = True
            continue

        stock = int(producto.get("stock", 0))
        if stock <= 0:
            st.session_state.cart.pop(pid, None)
            warnings.append(f"{producto['nombre']} se retiro del carrito porque no tiene stock.")
            changed = True
        elif quantity > stock:
            st.session_state.cart[pid] = stock
            warnings.append(f"{producto['nombre']} se ajusto a {stock} unidad(es) por stock disponible.")
            changed = True

    if changed:
        save_cart_to_redis()

    return warnings


def create_order(cliente: dict, items: list[dict], payment: dict) -> str:
    codigo = f"FAL-{datetime.now().strftime('%Y%m%d')}-{str(uuid4())[:8].upper()}"
    total = cart_total(items)
    if payment.get("estado_pago") != "Aprobado":
        record_payment_attempt(cliente, payment, total)
        raise RuntimeError("El pago fue rechazado por la pasarela simulada. No se genero el pedido.")
    stock_errors = validate_cart_stock(items)
    if stock_errors:
        raise RuntimeError(" ".join(stock_errors))

    if not has_supabase_config():
        raise RuntimeError("Configura Supabase para registrar pedidos.")

    cliente_id = get_or_save_customer(cliente)

    pedido_res = supabase_request(
        "POST",
        "pedidos",
        payload={
            "codigo": codigo,
            "cliente_id": cliente_id,
            "total": total,
            "estado": "Pendiente",
            "metodo_pago": payment["metodo_pago"],
            "estado_pago": payment["estado_pago"],
            "codigo_pago": payment["codigo_pago"],
            "fecha_pago": payment["fecha_pago"],
            "requiere_revision": False,
            "motivo_revision": "",
            "actualizado_por": "sistema",
            "fecha_actualizacion_estado": now_iso(),
        },
        prefer_return=True,
    )
    pedido_id = pedido_res[0]["id"]
    record_payment_attempt(cliente, payment, total, pedido_id)

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
    discount_stock(items)
    st.session_state.cart = {}
    clear_cart_from_redis()
    return codigo


def load_orders() -> tuple[list[dict], str]:
    if not has_supabase_config():
        return [], "sin_conexion"

    pedidos = supabase_request(
        "GET",
        "pedidos",
        params={
            "select": (
                "id,codigo,total,estado,metodo_pago,estado_pago,codigo_pago,fecha_pago,"
                "requiere_revision,motivo_revision,actualizado_por,fecha_actualizacion_estado,"
                "fecha_pedido,clientes(nombre,email,telefono,direccion)"
            ),
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
                "metodo_pago": pedido.get("metodo_pago", "Tarjeta"),
                "estado_pago": pedido.get("estado_pago", "Aprobado"),
                "codigo_pago": pedido.get("codigo_pago", ""),
                "fecha_pago": pedido.get("fecha_pago", ""),
                "requiere_revision": bool(pedido.get("requiere_revision", False)),
                "motivo_revision": pedido.get("motivo_revision", ""),
                "actualizado_por": pedido.get("actualizado_por", ""),
                "fecha_actualizacion_estado": pedido.get("fecha_actualizacion_estado", ""),
                "fecha_pedido": pedido["fecha_pedido"],
            }
        )
    return orders, "supabase"


def load_current_user_orders(orders: list[dict]) -> list[dict]:
    email = current_profile().get("email", "").lower()
    if not email:
        return []
    return [order for order in orders if order["cliente"].get("email", "").lower() == email]


def load_payment_attempts() -> list[dict]:
    if not has_supabase_config():
        return []
    try:
        return supabase_request(
            "GET",
            "pagos_simulados",
            params={"select": "*", "order": "fecha_pago.desc"},
        )
    except Exception:
        return []


def update_order_status(order_id: str, estado: str, motivo_revision: str = "") -> None:
    requires_review = estado in ESTADOS_EXCEPCION and estado != "Cancelado"
    if not has_supabase_config():
        raise RuntimeError("Configura Supabase para actualizar pedidos.")
    supabase_request(
        "PATCH",
        "pedidos",
        params={"id": f"eq.{order_id}"},
        payload={
            "estado": estado,
            "requiere_revision": requires_review,
            "motivo_revision": motivo_revision,
            "actualizado_por": "admin",
            "fecha_actualizacion_estado": now_iso(),
        },
    )


def render_header() -> None:
    st.title("Gestor de pedidos - Falabella Cloud")
    st.caption("Plataforma ecommerce escalable orientada a catalogo, carrito y gestion de pedidos.")


def render_auth_page() -> None:
    st.title("Gestor de pedidos - Falabella Cloud")
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
    if not productos:
        st.info("No hay productos disponibles. Revisa MongoDB Atlas y limpia el cache de Redis si corresponde.")
        return

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
                stock = int(producto.get("stock", 0))
                st.image(producto["imagen"], use_container_width=True)
                st.markdown(f"**{producto['nombre']}**")
                st.caption(f"{producto['categoria']} | Stock: {stock}")
                st.write(producto["descripcion"])
                st.write(f"**{money(float(producto['precio']))}**")

                with st.expander("Caracteristicas"):
                    caracteristicas = producto.get("caracteristicas", {})
                    if caracteristicas:
                        for key, value in caracteristicas.items():
                            st.write(f"**{humanize_key(str(key))}:** {value}")
                    else:
                        st.write("Sin caracteristicas adicionales.")

                if stock <= 0:
                    st.warning("Sin stock disponible")
                    st.button("Agregar al carrito", key=f"add_{product_id(producto)}", disabled=True)
                else:
                    qty = st.number_input(
                        "Cantidad",
                        min_value=1,
                        max_value=stock,
                        value=1,
                        key=f"qty_{product_id(producto)}",
                    )
                    already_in_cart = st.session_state.cart.get(product_id(producto), 0)
                    remaining = stock - already_in_cart
                    disabled = remaining <= 0
                    if st.button(
                        "Agregar al carrito",
                        key=f"add_{product_id(producto)}",
                        disabled=disabled,
                    ):
                        if qty > remaining:
                            st.error(f"Solo puedes agregar {remaining} unidad(es) mas de este producto.")
                        else:
                            add_to_cart(product_id(producto), qty)
                    if disabled:
                        st.caption("Ya agregaste todo el stock disponible al carrito.")


def render_cart(productos: list[dict]) -> None:
    st.subheader("Carrito de compras")
    for warning in clean_cart_by_stock(productos):
        st.warning(warning)

    items = cart_items(productos)

    if not items:
        st.session_state.checkout_step = "cart"
        st.info("El carrito esta vacio. Agrega productos desde el catalogo.")
        return

    if st.session_state.checkout_step == "cart":
        st.caption("Revisa tus productos antes de continuar con los datos de entrega y pago.")

        for item in items:
            with st.container(border=True):
                col_img, col_info, col_price, col_qty, col_subtotal, col_remove = st.columns(
                    [1.1, 3.2, 1.4, 1.8, 1.4, 0.5]
                )

                with col_img:
                    if item.get("imagen"):
                        st.image(item["imagen"], width=90)

                with col_info:
                    st.markdown(f"**{item['nombre']}**")
                    st.caption(item["categoria"])
                    if item["stock"] <= 3:
                        st.caption("Ultimas unidades")

                with col_price:
                    st.caption("Precio")
                    st.write(money(item["precio"]))

                with col_qty:
                    st.caption("Cantidad")
                    minus, qty_col, plus = st.columns([1, 1, 1])
                    if minus.button("-", key=f"minus_{item['producto_id']}", use_container_width=True):
                        set_cart_quantity(item["producto_id"], item["cantidad"] - 1)
                        st.rerun()
                    qty_col.write(f"**{item['cantidad']}**")
                    if plus.button(
                        "+",
                        key=f"plus_{item['producto_id']}",
                        use_container_width=True,
                        disabled=item["cantidad"] >= item["stock"],
                    ):
                        set_cart_quantity(item["producto_id"], item["cantidad"] + 1)
                        st.rerun()
                    st.caption(f"Max {item['stock']} unidades")

                with col_subtotal:
                    st.caption("Subtotal")
                    st.write(f"**{money(item['subtotal'])}**")

                with col_remove:
                    if st.button("X", key=f"remove_{item['producto_id']}", help="Quitar producto"):
                        remove_from_cart(item["producto_id"])
                        st.rerun()

        subtotal = cart_total(items)
        st.divider()
        summary_cols = st.columns([2, 1])
        with summary_cols[1]:
            st.markdown("**Resumen de compra**")
            st.write(f"Subtotal: **{money(subtotal)}**")
            st.write("Envio: **S/ 0.00**")
            st.write(f"Total: **{money(subtotal)}**")
            if st.button("Siguiente", type="primary", use_container_width=True):
                st.session_state.checkout_step = "customer"
                st.rerun()

    else:
        st.markdown("**Datos de entrega**")
        st.caption("Completa los datos del cliente antes de pasar a la pasarela de pago.")
        profile = current_profile()
        customer_profile = load_customer_by_email(profile.get("email", ""))
        with st.form("checkout_customer_form"):
            nombre = st.text_input("Nombre completo", value=customer_profile.get("nombre") or profile.get("nombre", ""))
            email = st.text_input("Correo electronico", value=profile.get("email", ""), disabled=True)
            telefono = st.text_input("Telefono", value=customer_profile.get("telefono", ""))
            direccion = st.text_area("Direccion de entrega", value=customer_profile.get("direccion", ""))
            col_back, col_pay = st.columns(2)
            back = col_back.form_submit_button("Volver al carrito", use_container_width=True)
            submitted = col_pay.form_submit_button("Pagar", type="primary", use_container_width=True)

        if back:
            st.session_state.checkout_step = "cart"
            st.rerun()

        if submitted:
            email = profile.get("email", "")
            if not nombre or not email:
                st.error("Ingresa nombre y correo para generar el pedido.")
                return
            st.session_state.checkout_customer = {
                "nombre": nombre,
                "email": email,
                "telefono": telefono,
                "direccion": direccion,
            }
            st.session_state.checkout_items = items
            st.session_state.payment_step = 1
            st.session_state.payment_details = {}
            st.session_state.simulate_payment_rejection = False
            st.session_state.show_payment_gateway = True
            st.rerun()

    if st.session_state.get("show_payment_gateway"):
        render_payment_gateway()
    if st.session_state.get("show_order_confirmation"):
        render_order_confirmation()


def render_admin(orders: list[dict]) -> None:
    st.subheader("Administracion de pedidos")
    st.caption(
        "El flujo normal puede avanzar automaticamente; el administrador revisa excepciones, "
        "pedidos observados y casos que requieren criterio humano."
    )

    if not orders:
        st.info("Aun no hay pedidos registrados.")
        return

    st.markdown("**Filtros de busqueda**")
    col1, col2, col3 = st.columns(3)
    search = col1.text_input("Buscar codigo o cliente", placeholder="FAL-..., nombre o correo")
    status = col2.selectbox("Estado del pedido", ["Todos"] + ESTADOS)
    payment_status = col3.selectbox("Estado de pago", ["Todos"] + ESTADOS_PAGO)

    col4, col5, col6 = st.columns(3)
    payment_methods = sorted({order.get("metodo_pago", "Tarjeta") for order in orders})
    payment_method = col4.selectbox("Metodo de pago", ["Todos"] + payment_methods)
    clientes = sorted(
        {
            order["cliente"].get("nombre", "").strip()
            for order in orders
            if order["cliente"].get("nombre", "").strip()
        }
    )
    cliente_filter = col5.selectbox("Cliente", ["Todos"] + clientes)
    limit = col6.selectbox("Mostrar", [10, 25, 50, 100, "Todos"], index=1)

    filtered = orders
    if search:
        query = search.lower()
        filtered = [
            order
            for order in filtered
            if query in order["codigo"].lower()
            or query in order["cliente"].get("nombre", "").lower()
            or query in order["cliente"].get("email", "").lower()
        ]
    if status != "Todos":
        filtered = [order for order in filtered if order["estado"] == status]
    if payment_status != "Todos":
        filtered = [order for order in filtered if order.get("estado_pago", "Aprobado") == payment_status]
    if payment_method != "Todos":
        filtered = [order for order in filtered if order.get("metodo_pago", "Tarjeta") == payment_method]
    if cliente_filter != "Todos":
        filtered = [order for order in filtered if order["cliente"].get("nombre", "") == cliente_filter]

    filtered = sorted(filtered, key=lambda order: order.get("fecha_pedido", ""), reverse=True)
    visible_orders = filtered if limit == "Todos" else filtered[: int(limit)]

    summary = st.columns(4)
    summary[0].metric("Pedidos encontrados", len(filtered))
    summary[1].metric("Pendientes", sum(1 for order in filtered if order["estado"] == "Pendiente"))
    summary[2].metric("En revision", sum(1 for order in filtered if order.get("requiere_revision")))
    summary[3].metric("Total filtrado", money(sum(order["total"] for order in filtered)))

    table = [
        {
            "codigo": order["codigo"],
            "cliente": order["cliente"].get("nombre", ""),
            "email": order["cliente"].get("email", ""),
            "estado": order["estado"],
            "pago": order.get("estado_pago", "Aprobado"),
            "metodo_pago": order.get("metodo_pago", "Tarjeta"),
            "revision": "Si" if order.get("requiere_revision") else "No",
            "total": money(order["total"]),
            "fecha_lima": format_lima_datetime(order["fecha_pedido"]),
        }
        for order in visible_orders
    ]
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

    if len(filtered) > len(visible_orders):
        st.caption(f"Mostrando {len(visible_orders)} de {len(filtered)} pedidos filtrados.")

    if not search.strip():
        st.info("Ingresa un codigo de pedido, nombre o correo para ver el detalle y actualizar su estado.")
        return

    st.markdown("**Detalle y actualizacion de estado**")
    if not filtered:
        st.info("No hay pedidos que coincidan con los filtros seleccionados.")
        return

    options = {
        f"{order['codigo']} | {order['cliente'].get('nombre', '')} | {order['estado']} | {format_lima_datetime(order['fecha_pedido'])}": order
        for order in filtered
    }
    selected_label = st.selectbox("Seleccionar pedido", list(options.keys()))
    selected_orders = [options[selected_label]] if selected_label else []

    for order in selected_orders:
        with st.expander(f"{order['codigo']} - {order['estado']}"):
            st.write(f"Cliente: **{order['cliente'].get('nombre', '')}**")
            st.write(f"Email: {order['cliente'].get('email', '')}")
            st.write(f"Fecha Lima: {format_lima_datetime(order['fecha_pedido'])}")
            st.write(f"Total: **{money(order['total'])}**")
            st.write(
                f"Pago: **{order.get('estado_pago', 'Aprobado')}** "
                f"({order.get('metodo_pago', 'Tarjeta')})"
            )
            if order.get("codigo_pago"):
                st.caption(f"Codigo de pago: {order['codigo_pago']}")
            if order.get("requiere_revision") or order.get("motivo_revision"):
                st.warning(order.get("motivo_revision") or "Pedido marcado para revision administrativa.")

            detalle = pd.DataFrame(order["items"])
            if not detalle.empty:
                detalle["precio"] = detalle["precio"].map(money)
                detalle["subtotal"] = detalle["subtotal"].map(money)
                st.dataframe(
                    detalle[["nombre", "categoria", "precio", "cantidad", "subtotal"]],
                    use_container_width=True,
                )

            nuevo_estado = ESTADOS_ADMINISTRATIVOS[0]
            st.write(f"Accion administrativa: **{nuevo_estado}**")
            motivo_revision = st.text_area(
                "Motivo u observacion administrativa",
                value=order.get("motivo_revision", ""),
                key=f"motivo_{order['id']}",
            )
            if st.button("Guardar estado", key=f"save_{order['id']}"):
                if not motivo_revision.strip():
                    st.error("Ingresa una observacion para registrar la excepcion administrativa.")
                    return
                update_order_status(order["id"], nuevo_estado, motivo_revision)
                st.success("Estado actualizado.")
                st.rerun()


def render_my_orders(orders: list[dict], productos: list[dict]) -> None:
    st.subheader("Mis pedidos")
    user_orders = load_current_user_orders(orders)

    if not user_orders:
        st.info("Aun no tienes pedidos registrados con tu correo.")
        return

    busqueda = st.text_input("Buscar por N° de pedido", placeholder="FAL-20260605...")

    filtered = user_orders
    if busqueda:
        query = busqueda.lower()
        filtered = [o for o in filtered if query in o["codigo"].lower()]

    if not filtered:
        st.info("No se encontraron pedidos con ese numero.")
        return

    st.caption(f"{len(filtered)} pedido(s)")

    img_map = {product_id(p): p.get("imagen", "") for p in productos}

    for order in filtered:
        with st.container(border=True):
            col_date, col_total = st.columns([4, 1])
            with col_date:
                st.markdown(f"**{format_lima_date_friendly(order['fecha_pedido'])}**")
            with col_total:
                st.markdown(
                    f"<p style='text-align:right'><b>{money(order['total'])}</b></p>",
                    unsafe_allow_html=True,
                )

            st.markdown(f"Pedido N° **{order['codigo']}**")

            icon = order_status_icon(order["estado"])
            message = order_status_message(order)
            st.markdown(f"{icon} **{order['estado']}**")
            st.caption(message)
            render_order_progress(order["estado"])

            st.divider()
            items = order.get("items", [])
            for item in items[:3]:
                col_img, col_info, col_qty = st.columns([0.8, 4, 1])
                with col_img:
                    img = img_map.get(item["producto_id"], "")
                    if img:
                        st.image(img, width=55)
                with col_info:
                    st.markdown(f"**{item['nombre']}**")
                    st.caption(f"{item['categoria']} \u00b7 {money(item['precio'])}")
                with col_qty:
                    st.caption(f"x{item['cantidad']}")

            remaining = len(items) - 3
            if remaining > 0:
                st.caption(f"+{remaining} producto(s) mas")

            st.divider()
            pago_icon = "\u2705" if order.get("estado_pago") == "Aprobado" else "\u274c"
            st.caption(
                f"Pago: {pago_icon} {order.get('estado_pago', 'Aprobado')} \u00b7 "
                f"{order.get('metodo_pago', 'Tarjeta')}"
            )

            with st.expander("Revisar detalle"):
                st.write(f"**Fecha completa:** {format_lima_datetime(order['fecha_pedido'])}")
                st.write(f"**Metodo de pago:** {order.get('metodo_pago', 'Tarjeta')}")
                st.write(f"**Estado de pago:** {order.get('estado_pago', 'Aprobado')}")
                if order.get("codigo_pago"):
                    st.write(f"**Codigo de pago:** {order['codigo_pago']}")
                if order.get("fecha_pago"):
                    st.write(f"**Fecha de pago:** {format_lima_datetime(order['fecha_pago'])}")
                detalle = pd.DataFrame(items)
                if not detalle.empty:
                    detalle["precio"] = detalle["precio"].map(money)
                    detalle["subtotal"] = detalle["subtotal"].map(money)
                    st.dataframe(
                        detalle[["nombre", "categoria", "precio", "cantidad", "subtotal"]],
                        use_container_width=True,
                        hide_index=True,
                    )


def render_customer_profile() -> None:
    st.subheader("Mi perfil")
    st.caption("Administra tus datos de contacto y entrega. El correo se mantiene como identificador de la cuenta.")

    profile = current_profile()
    email = profile.get("email", "")
    customer_profile = load_customer_by_email(email)

    with st.form("customer_profile_form"):
        nombre = st.text_input("Nombre completo", value=customer_profile.get("nombre") or profile.get("nombre", ""))
        st.text_input("Correo electronico", value=email, disabled=True)
        telefono = st.text_input("Telefono", value=customer_profile.get("telefono", ""))
        direccion = st.text_area("Direccion principal de entrega", value=customer_profile.get("direccion", ""))
        submitted = st.form_submit_button("Guardar perfil", type="primary")

    if submitted:
        if not nombre.strip():
            st.error("Ingresa tu nombre completo.")
            return
        if telefono and not telefono.strip().isdigit():
            st.error("El telefono debe contener solo numeros.")
            return
        try:
            update_current_profile_name(nombre)
            save_current_customer_profile(nombre, telefono, direccion)
            st.success("Perfil actualizado correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo actualizar el perfil. {exc}")

def render_dashboard(orders: list[dict], productos: list[dict], payments: list[dict]) -> None:
    st.subheader("Dashboard")

    total_orders = len(orders)
    pending = sum(1 for order in orders if order["estado"] == "Pendiente")
    processing = sum(1 for order in orders if order["estado"] == "Procesando")
    shipped = sum(1 for order in orders if order["estado"] == "Enviado")
    delivered = sum(1 for order in orders if order["estado"] == "Entregado")
    cancelled = sum(1 for order in orders if order["estado"] == "Cancelado")
    review_orders = sum(1 for order in orders if order.get("requiere_revision"))
    billable_orders = [order for order in orders if order["estado"] != "Cancelado"]
    sales = sum(order["total"] for order in billable_orders)
    avg_ticket = sales / len(billable_orders) if billable_orders else 0
    approved_payments = sum(1 for payment in payments if payment.get("estado_pago") == "Aprobado")
    rejected_payments = sum(1 for payment in payments if payment.get("estado_pago") == "Rechazado")
    total_payments = approved_payments + rejected_payments
    approval_rate = (approved_payments / total_payments * 100) if total_payments else 0
    low_stock = sum(1 for producto in productos if int(producto.get("stock", 0)) <= 5)

    st.markdown("**Resumen operativo**")
    cols = st.columns(4)
    cols[0].metric("Total de pedidos", total_orders)
    cols[1].metric("Ventas totales", money(sales))
    cols[2].metric("Ticket promedio", money(avg_ticket))
    cols[3].metric("Tasa de aprobacion", f"{approval_rate:.0f}%")

    cols = st.columns(4)
    cols[0].metric("Pendientes", pending)
    cols[1].metric("En proceso", processing)
    cols[2].metric("Enviados", shipped)
    cols[3].metric("Entregados", delivered)

    cols = st.columns(4)
    cols[0].metric("Pedidos en revision", review_orders)
    cols[1].metric("Pedidos cancelados", cancelled)
    cols[2].metric("Pagos rechazados", rejected_payments)
    cols[3].metric("Productos bajo stock", low_stock)

    if orders:
        st.divider()
        st.markdown("**Graficas operativas**")
        status_df = pd.DataFrame(orders)
        if "metodo_pago" not in status_df.columns:
            status_df["metodo_pago"] = "Tarjeta"

        left, right = st.columns(2)
        with left:
            st.markdown("Pedidos por estado")
            by_status = status_df.groupby("estado", as_index=False)["id"].count()
            by_status.columns = ["Estado", "Cantidad"]
            st.bar_chart(by_status.set_index("Estado"))
        with right:
            st.markdown("Pagos por metodo")
            payment_df = pd.DataFrame(payments) if payments else status_df
            if "metodo_pago" in payment_df.columns and "id" in payment_df.columns:
                by_payment = payment_df.groupby("metodo_pago", as_index=False)["id"].count()
                by_payment.columns = ["Metodo", "Cantidad"]
                st.bar_chart(by_payment.set_index("Metodo"))

        try:
            dates_df = status_df.copy()
            dates_df["fecha"] = pd.to_datetime(
                dates_df["fecha_pedido"].str.replace("Z", "+00:00", regex=False),
                utc=True,
                errors="coerce",
            ).dt.date
            daily = dates_df.groupby("fecha", as_index=False).agg(
                pedidos=("id", "count"),
                ventas=("total", "sum"),
            )
            daily = daily.sort_values("fecha")

            left, right = st.columns(2)
            with left:
                st.markdown("Pedidos por dia")
                st.line_chart(daily.set_index("fecha")["pedidos"])
            with right:
                st.markdown("Ventas por dia")
                st.line_chart(daily.set_index("fecha")["ventas"])
        except Exception:
            pass

    items = [item for order in orders for item in order["items"]]
    if items:
        st.divider()
        st.markdown("**Productos y categorias**")
        df = pd.DataFrame(items)
        top_products = df.groupby("nombre", as_index=False)["cantidad"].sum().sort_values("cantidad", ascending=False)
        by_category = df.groupby("categoria", as_index=False)["subtotal"].sum().sort_values("subtotal", ascending=False)

        left, right = st.columns(2)
        with left:
            st.markdown("Productos mas vendidos")
            st.bar_chart(top_products.set_index("nombre"))
        with right:
            st.markdown("Ventas por categoria")
            st.bar_chart(by_category.set_index("categoria"))

    if orders:
        st.divider()
        st.markdown("**Top clientes**")
        clientes_data = []
        for order in orders:
            cliente = order.get("cliente", {})
            nombre = cliente.get("nombre", "Sin nombre")
            email = cliente.get("email", "")
            if nombre and email:
                clientes_data.append({"cliente": nombre, "email": email, "total": order["total"]})
        if clientes_data:
            clientes_df = pd.DataFrame(clientes_data)
            top_clientes = (
                clientes_df.groupby(["cliente", "email"], as_index=False)
                .agg(pedidos=("total", "count"), total_compras=("total", "sum"))
                .sort_values("total_compras", ascending=False)
                .head(10)
            )
            top_clientes["total_compras"] = top_clientes["total_compras"].map(money)
            st.dataframe(top_clientes, use_container_width=True, hide_index=True)

    low_stock_products = [
        {
            "producto": producto["nombre"],
            "categoria": producto["categoria"],
            "stock": int(producto.get("stock", 0)),
            "precio": money(float(producto["precio"])),
        }
        for producto in productos
        if int(producto.get("stock", 0)) <= 5
    ]
    if low_stock_products:
        st.divider()
        st.markdown("**Productos con stock bajo** (5 o menos unidades)")
        st.dataframe(pd.DataFrame(low_stock_products), use_container_width=True, hide_index=True)

    if orders:
        st.divider()
        st.markdown("**Exportar datos**")
        export_data = [
            {
                "codigo": order["codigo"],
                "cliente": order["cliente"].get("nombre", ""),
                "email": order["cliente"].get("email", ""),
                "estado": order["estado"],
                "estado_pago": order.get("estado_pago", ""),
                "metodo_pago": order.get("metodo_pago", ""),
                "total": order["total"],
                "fecha_pedido": format_lima_datetime(order["fecha_pedido"]),
                "requiere_revision": "Si" if order.get("requiere_revision") else "No",
            }
            for order in orders
        ]
        export_df = pd.DataFrame(export_data)
        csv = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Descargar pedidos en CSV",
            data=csv,
            file_name="pedidos_falabella.csv",
            mime="text/csv",
        )

    if not items and not orders:
        st.info("Genera pedidos para visualizar metricas por producto y categoria.")


def render_data_tools(product_source: str, order_source: str) -> None:
    st.subheader("Configuracion del sistema")
    st.write("Estado actual de las conexiones principales de la plataforma.")
    render_security_notices()

    redis_source = "Redis" if get_redis_client() is not None else "Sesion local"
    catalog_label = {
        "mongodb": "MongoDB",
        "redis": "Redis cache",
        "sin_conexion": "Sin conexion",
        "mongodb_vacio": "MongoDB vacio",
    }.get(product_source, product_source)
    cols = st.columns(4)
    cols[0].metric("Catalogo", catalog_label)
    cols[1].metric("Pedidos", "Supabase" if order_source == "supabase" else "Sin conexion")
    cols[2].metric("Carrito temporal", redis_source)
    cols[3].metric("Estado operativo", "Listo")

    if product_source in {"sin_conexion", "mongodb_vacio"}:
        st.warning("El catalogo no esta disponible. Revisa MongoDB Atlas y la coleccion configurada.")
    if product_source == "redis":
        st.info("El catalogo se esta leyendo desde Redis. MongoDB Atlas se mantiene como fuente oficial.")
    if order_source != "supabase":
        st.warning("Los pedidos no estan disponibles. Revisa la conexion de Supabase.")
    if redis_source != "Redis":
        st.info("Redis no esta configurado. El carrito se conserva solo en la sesion activa.")


def main() -> None:
    st.set_page_config(page_title="Falabella Order Manager", page_icon="🛒", layout="wide")
    init_state()

    if not is_authenticated():
        render_auth_page()
        return

    load_cart_from_redis()

    productos, product_source = load_products()
    orders, order_source = load_orders()
    payments = load_payment_attempts()
    render_header()
    render_security_notices()

    profile = current_profile()
    role = current_role()
    if role == "cliente":
        notify_order_status_changes(orders)

    st.sidebar.write(f"Usuario: **{profile.get('nombre', 'Usuario')}**")
    st.sidebar.write(f"Rol: **{role}**")
    if st.sidebar.button("Cerrar sesion"):
        logout_user()
        st.rerun()

    if role == "admin":
        pages = ["Pedidos administrativos", "Dashboard", "Configuracion"]
    else:
        pages = ["Catalogo", "Carrito", "Mis pedidos", "Mi perfil"]

    page = st.sidebar.radio(
        "Modulos del sistema",
        pages,
    )
    st.sidebar.divider()
    st.sidebar.write(f"Productos en catalogo: **{len(productos)}**")
    st.sidebar.write(f"Items en carrito: **{sum(st.session_state.cart.values())}**")
    st.sidebar.write(f"Pedidos registrados: **{len(orders)}**")

    if role == "cliente" and st.session_state.get("status_notifications"):
        with st.container(border=True):
            st.markdown("**Notificaciones de pedidos**")
            for notification in st.session_state.status_notifications:
                st.info(notification)

    if page == "Catalogo":
        render_catalog(productos)
    elif page == "Carrito":
        render_cart(productos)
    elif page == "Mis pedidos":
        render_my_orders(orders, productos)
    elif page == "Mi perfil":
        render_customer_profile()
    elif page == "Pedidos administrativos":
        render_admin(orders)
    elif page == "Dashboard":
        render_dashboard(orders, productos, payments)
    else:
        render_data_tools(product_source, order_source)


if __name__ == "__main__":
    main()
