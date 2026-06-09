# blueprints/items/service.py
from __future__ import annotations

import uuid

from extensions.supabase import get_service_client
from utils.money import money_float
from utils.validators import is_valid_item_type


def list_items():
    sb = get_service_client()

    # 1) items + supplier (esto ya te funciona)
    items = (
        sb.table("items")
          .select("*, suppliers(id,name)")
          .order("created_at", desc=True)
          .execute()
    ).data or []

    if not items:
        return []

    # 2) solo consumables necesitan inventory_balances
    consumable_ids = [it["id"] for it in items if it.get("item_type") == "consumable"]

    bal_by_item = {}
    if consumable_ids:
        balances = (
            sb.table("inventory_balances")
              .select("item_id,on_hand")
              .in_("item_id", consumable_ids)
              .execute()
        ).data or []
        bal_by_item = {b["item_id"]: b for b in balances}

    # 3) attach “stocked_info” consistente
    for it in items:
        t = (it.get("item_type") or "").lower()

        if t == "consumable":
            it["stock_on_hand"] = (bal_by_item.get(it["id"]) or {}).get("on_hand", 0)
        elif t == "rentable":
            it["stock_on_hand"] = it.get("rentable_capacity", 0)
        else:
            it["stock_on_hand"] = None  # service/bundle

    return items


def list_suppliers():
    sb = get_service_client()
    res = sb.table("suppliers").select("*").order("created_at", desc=True).execute()
    return res.data or []


def list_categories():
    sb = get_service_client()
    rows = sb.table("items").select("category").not_.is_("category", "null").execute().data or []
    categories = sorted({r["category"] for r in rows if r.get("category")})
    return categories


def list_stocked_items(item_id: str):
    sb = get_service_client()
    res = (
            sb.table("inventory_balances")
            .select("*")
            .eq("item_id", item_id)
            .order("updated_at", desc=True)
            .execute()
        )
    return res.data[0] or []


def get_item(item_id: str):
    sb = get_service_client()
    res = sb.table("items").select("*").eq("id", item_id).single().execute()
    return res.data


def create_item(form: dict):
    sku           = (form.get("sku") or "").strip()
    if not sku:
        sku = f"ITM-{uuid.uuid4().hex[:8].upper()}"
    item_type     = (form.get("item_type") or "").strip()
    stock         = int(float(form.get("stock") or 0))
    rentable_capacity = int(float(form.get("asset_count") or 0))
    # serial_prefix = (form.get("serial_prefix") or "").strip() or "SER"
    tags_raw      = (form.get("tags") or "").strip()
    tags_list    = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None
    new_category = (form.get("new_category") or "").strip()
    category     = (form.get("category") or "").strip()

    if new_category:
        category = new_category

    if not is_valid_item_type(item_type):
        raise ValueError("Tipo inválido. Use: rentable/consumable/service/bundle")

    payload = {
        "sku": sku,
        "name": (form.get("name") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "item_type": item_type,
        "unit": (form.get("unit") or "EA").strip(),
        "default_rate": money_float(form.get("default_rate")),
        "low_rate": money_float(form.get("low_rate")),
        "supplier_id": (form.get("supplier_id") or "").strip(),
        "category": category,
        "tags": tags_list,
        "rentable_capacity": rentable_capacity,
        "active": bool(form.get("active")),
    }

    sb = get_service_client()
    res = sb.table("items").insert(payload).execute()

    item_id = res.data[0]["id"]

    # --- Stock: sólo si consumible ---
    if item_type == "consumable":
        create_inventory_balance(item_id, stock)

    return (res.data or [None])[0]


def update_item(item_id: str, form: dict):
    item_type     = (form.get("item_type") or "").strip()
    # asset_count   = int(form.get("asset_count") or 0)
    # serial_prefix = (form.get("serial_prefix") or "").strip() or "SER"
    tags_raw      = (form.get("tags") or "").strip()
    tags_list    = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None
    category = (form.get("category") or "").strip()
    new_category = (form.get("new_category") or "").strip()

    # stock inputs
    stock             = int(float(form.get("stock") or 0))  # consumable
    rentable_capacity = int(float(form.get("rentable_capacity") or 0))  # rentable

    if new_category:
        category = new_category

    if item_type and not is_valid_item_type(item_type):
        raise ValueError("Tipo inválido. Use: rentable/consumable/service/bundle")
    
    payload = {
        "name": (form.get("name") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "item_type": item_type,
        "unit": (form.get("unit") or "EA").strip(),
        "default_rate": money_float(form.get("default_rate")),
        "low_rate": money_float(form.get("low_rate")),
        "supplier_id": (form.get("supplier_id") or "").strip(),
        "category": category,
        "tags": tags_list,
        "active": bool(form.get("active")),
    }

    sb = get_service_client()
    res = sb.table("items").update(payload).eq("id", item_id).execute()

    # ✅ actualizar stock SIN duplicar
    if item_type == "consumable":
        upsert_inventory_balance(item_id, stock)

    if item_type == "rentable":
        update_rentable_capacity(item_id, rentable_capacity)
    
    return (res.data or [None])[0]


def create_inventory_balance(item_id: str, stock: int):
    """
    Crea un registro de inventory_balances para items consumibles.
    Si la tabla no existe o RLS lo bloquea, no rompe el flujo.
    """
    try:
        sb = get_service_client()
        sb.table("inventory_balances").insert({
            "item_id": item_id,
            "on_hand": max(0, stock),
            "min_level": 0
        }).execute()
        return True
    except Exception:
        return False


# def create_serial_assets(item_id: str, sku: str, asset_count: int, serial_prefix: str = "SER"):
#     """
#     Crea activos seriados para items rentables.
#     Genera serial_no con formato: {serial_prefix}-{sku}-{número:03d}
#     Si falla, no rompe el flujo.
#     """
#     if asset_count <= 0:
#         return False
    
#     try:
#         assets = []
#         for i in range(1, asset_count + 1):
#             serial_no = f"{serial_prefix}-{sku}-{i:03d}"
#             assets.append({"item_id": item_id, "serial_no": serial_no, "active": True})
        
#         if assets:
#             sb = get_service_client()
#             sb.table("assets").insert(assets).execute()
#         return True
#     except Exception:
#         return False


def upsert_inventory_balance(item_id: str, on_hand: int) -> bool:
    """Consumibles: setea on_hand. Si no existe fila, la crea."""
    try:
        sb = get_service_client()
        on_hand = max(0, int(on_hand))

        # 1) intentar update
        upd = (
            sb.table("inventory_balances")
            .update({"on_hand": on_hand})
            .eq("item_id", item_id)
            .execute()
        )
        if upd.data:  # actualizó algo
            return True

        # 2) si no había fila, insertar
        sb.table("inventory_balances").insert({
            "item_id": item_id,
            "on_hand": on_hand,
            "min_level": 0
        }).execute()
        return True
    except Exception:
        return False
    

def update_rentable_capacity(item_id: str, capacity: int) -> bool:
    """Rentables: setea rentable_capacity en items."""
    try:
        sb = get_service_client()
        capacity = max(0, int(capacity))
        sb.table("items").update({"rentable_capacity": capacity}).eq("id", item_id).execute()
        return True
    except Exception:
        return False



def set_item_status(item_id: str, is_active: bool):
    """
    Actualiza estado del item.
    Soporta schemas con columna 'active' (viejo) o 'is_active' (nuevo).
    Intenta primero 'active' y si falla, intenta 'is_active'.
    """
    sb = get_service_client()

    # 1) Intento estilo viejo: active
    try:
        sb.table("items").update({"active": bool(is_active)}).eq("id", item_id).execute()
        return True
    except Exception:
        pass

    # 2) Intento estilo nuevo: is_active
    sb.table("items").update({"is_active": bool(is_active)}).eq("id", item_id).execute()
    return True


def delete_item(item_id: str):
    sb = get_service_client()
    sb.table("items").delete().eq("id", item_id).execute()
    return True
