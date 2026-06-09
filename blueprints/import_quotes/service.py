"""
service.py – Lógica de negocio del módulo de importación de cotizaciones históricas.

Patrón de insert Supabase-py correcto para esta versión:
    res = sb.table("...").insert({...}).execute()
    new_id = (res.data or [{}])[0]["id"]      ← NO usar .select().single() después de insert
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from flask import session

from extensions.supabase import get_service_client
from blueprints.quotations.service import recompute_totals, gen_quote_number

CLIENT_EVENTUAL  = "Cliente Eventual"
CONTACT_EVENTUAL = "Contacto Eventual"
EVENT_EVENTUAL   = "Evento Eventual"
SUPPLIER_NAME    = "Avvisi Audiovisuales"


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────────────────────
# Clasificación automática de ítems importados
# ─────────────────────────────────────────────────────────────────────────────

_RENTABLE_KW = (
    "equipo", "consola", "mezcladora", "bocina", "speaker", "pantalla",
    "proyector", "reflector", "truss", "tarima", "camara",
    "monitor", "amplificador", "subwoofer", "procesador", "generador",
    "canon", "cannon", "follow spot", "followspot", "par64", "par38",
    "scanner", "moving head", "moving", "beam", "wash", "fog",
    "hazer", "haze", "cable", "rack", "patch",
    # catálogo Avvisi
    "microfono", "parlante", "escenario", "porteria", "sm58", "luces",
)
_SERVICE_KW = (
    "tecnico", "operador", "chofer", "instalacion",
    "transporte", "flete", "produccion", "direccion",
    "coordinacion", "diseno", "servicio", "montaje", "desmontaje",
    "logistica", "traslado", "viatico",
    # personal y servicios Avvisi
    "animador", "host", "edecan", "promotora", "staff", "cantante",
    "show", "personaje", "camarin", "camerino", "santa", "globo",
    "silla", "mesa", "hotel", "alimentacion", "saco", "duende", "elfo",
)
# Iluminación va ANTES de Audio para capturar "Consola de Luces" correctamente
_CATEGORY_MAP = (
    ("Iluminación",  ("consola de luces", "consola dmx", "luces", "par led",
                      "reflector", "strobo", "dmx", "iluminaci",
                      "moving head", "beam", "wash", "follow", "canon", "foco")),
    ("Audio",        ("consola de audio", "audio", "sonido", "microfono", "bocina",
                      "speaker", "amplificador", "mezcladora", "subwoofer",
                      "xlr", "parlante", "pa ", "monitor de escenario",
                      "sm58", "diadema", "barra")),
    ("Video",        ("video", "pantalla", "proyector", "led wall", "camara",
                      "hdmi", "switcher", "scaler", "videowall", "totem")),
    ("Estructuras",  ("truss", "estructura", "andamio", "tarima", "rigging",
                      "malla", "escenario", "porteria")),
    ("Personal",     ("tecnico", "operador", "chofer", "asistente",
                      "personal", "staff", "animador", "host", "edecan",
                      "promotora", "cantante", "personaje", "santa",
                      "duende", "elfo")),
    ("Transporte",   ("transporte", "flete", "traslado", "logistica",
                      "viatico", "montaje, desmontaje")),
    ("Generadores",  ("generador", "planta electrica", "centro de carga")),
    ("Producción",   ("produccion", "direccion", "coordinacion", "diseno",
                      "montaje", "desmontaje", "show")),
)


def _no_acc(s: str) -> str:
    """Elimina acentos para comparación case-insensitive sin acentos."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _classify_item(name: str) -> tuple[str, str]:
    """Devuelve (item_type, category) inferidos del nombre normalizado."""
    nla = _no_acc(name.lower())   # sin acentos para matching consistente

    item_type = "service"
    for kw in _RENTABLE_KW:
        if kw in nla:
            item_type = "rentable"
            break

    category = "General"
    for cat, keywords in _CATEGORY_MAP:
        if any(_no_acc(kw) in nla for kw in keywords):
            category = cat
            break

    return item_type, category


# ─────────────────────────────────────────────────────────────────────────────
# Homologación / Normalización de nombres de productos
# ─────────────────────────────────────────────────────────────────────────────

# Tabla: (nombre_canónico, [regex sobre lowercase-sin-acentos])  — primer match gana
_HOMOLOG: list[tuple[str, list[str]]] = [
    # Micrófonos
    ("Micrófono Inalámbrico Shure SM58",
        [r"sm58", r"inalambrico.*shure", r"shure.*inalambrico",
         r"microfono.*inalambrico", r"inalambrico.*microfono"]),
    ("Micrófono de Diadema",                    [r"diadema"]),
    # Consolas
    ("Consola de Luces DMX",
        [r"consola.*luces", r"consola.*luz", r"consola.*dmx"]),
    ("Consola de Audio",
        [r"consola.*audio", r"consola de sonido"]),
    # Audio / Parlantes
    ("Sistema de Audio Tipo Barra",
        [r"parlante.*barra", r"barra.*parlante", r"audio.*barra",
         r"barra.*audio", r"audio de barra", r"audio.*corporativo"]),
    ("Sistema de Audio Profesional",
        [r"audio profesional", r"audio.*grande", r"audio para evento"]),
    # Iluminación
    ("Luces Robóticas",                         [r"luces roboticas", r"moving head", r"robotica"]),
    ("Luces LED",                               [r"^luces led\b", r"\bpar led\b"]),
    ("Iluminación General",                     [r"^iluminacion$", r"^iluminacion\s"]),
    # Video
    ("Tótem de Pantalla LED",                   [r"totem.*led", r"totem.*pantalla"]),
    # Personal
    ("Animador / Host de Evento",               [r"\banimador\b", r"\bhost\b"]),
    ("Edecán",                                  [r"\bedecan\b"]),
    ("Promotora",                               [r"\bpromotora\b"]),
    ("Personal de Staff",                       [r"personal.*staff", r"\bstaff\b"]),
    ("Santa Claus",                             [r"\bsanta\b"]),
    ("Personajes Navideños (Grinch / Sra. Claus)", [r"grinch", r"senora claus"]),
    ("Personajes Mickey y Minnie",              [r"mickey", r"minnie"]),
    ("Duendes para Evento",                     [r"duendecita", r"\bduende\b", r"\belfo\b"]),
    ("Show Musical",                            [r"show musical"]),
    ("Cantante",                                [r"\bcantante\b"]),
    # Transporte / Logística
    ("Transporte Ida y Regreso",                [r"transporte.*ida", r"ida.*regreso"]),
    ("Montaje, Desmontaje y Transporte",        [r"montaje.*desmontaje", r"desmontaje.*montaje"]),
    ("Transporte de Activos y Montaje",         [r"transporte.*activo", r"transporte.*montaje"]),
    # Varios
    ("Centro de Carga",                         [r"centro de carga"]),
    ("Camarín de Lona",                         [r"camerino", r"camarin"]),
    ("Portaglobos",                             [r"portaglobo"]),
    ("Globos Publicitarios",                    [r"\bglobo"]),
    ("Sillas Tiffany",                          [r"tiffany"]),
    ("Silla Blanca",                            [r"silla blanca", r"silla.*santa"]),
    ("Mesas con Faldón",                        [r"mesa.*faldon"]),
    ("Estructura de Entrada",                   [r"estructura.*entrada"]),
    ("Sacos con Dulces Navideños",              [r"saco.*dulce"]),
    ("Hotel",                                   [r"^hotel$"]),
    ("Alimentación",                            [r"^alimentacion"]),
]

_DIM_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*(?:metros?|mts?\.?)?"
)


def _fmt_dim(m: re.Match) -> str:
    return f"{m.group(1).replace(',','.')}x{m.group(2).replace(',','.')}"


def _normalize_item_name(name: str) -> str:
    """
    Convierte un nombre de producto importado a su forma canónica:
    homologa variaciones de ortografía, acentos, marcas y dimensiones.
    """
    raw = name.strip()
    if not raw:
        return raw
    nl  = raw.lower()
    nla = _no_acc(nl)

    # ── Tarima (preserva dimensiones y color) ─────────────────────────────────
    if "tarima" in nla:
        dim   = _DIM_RE.search(raw)
        col   = re.search(r"\b(blanco|negro|blanca|negra)\b", nl)
        forma = re.search(r"forma\s+de?\s*t\b|en\s+t\b|\bforma\s+t\b|\ben\s+forma\s+de?\s*t\b", nl)
        parts = ["Tarima"]
        if dim:
            parts.append(f"{_fmt_dim(dim)} metros")
        if forma:
            parts.append("en Forma de T")
        if col:
            parts.append(f"en {col.group(1).capitalize()}")
        return " ".join(parts)

    # ── Truss / Portería (preserva dimensiones y color) ───────────────────────
    if "truss" in nla:
        dim  = _DIM_RE.search(raw)
        col  = re.search(r"\b(blanco|negro|blanca|negra)\b", nl)
        base = "Portería de Truss" if re.search(r"porteria|porterias", nla) else "Truss de Aluminio"
        parts = [base]
        if dim:
            parts.append(f"{_fmt_dim(dim)} metros")
        if col:
            parts.append(f"en {col.group(1).capitalize()}")
        return " ".join(parts)

    # ── Pantalla LED (preserva dimensiones y resolución) ──────────────────────
    if "pantalla" in nla and re.search(r"led|video|p\s?\d|alta", nla):
        dim  = _DIM_RE.search(raw)
        res  = re.search(r"\bP\s?(\d+(?:\.\d+)?)\b", raw, re.IGNORECASE)
        parts = ["Pantalla LED"]
        if dim:
            parts.append(f"{_fmt_dim(dim)} metros")
        if res:
            parts.append(f"P{res.group(1)}")
        return " ".join(parts)

    # ── Escenario (preserva dimensiones) ──────────────────────────────────────
    if "escenario" in nla:
        dim = _DIM_RE.search(raw)
        parts = ["Escenario"]
        if dim:
            parts.append(f"{_fmt_dim(dim)} metros")
        return " ".join(parts)

    # ── Tabla de homologación ──────────────────────────────────────────────────
    for canonical, patterns in _HOMOLOG:
        for pat in patterns:
            if re.search(pat, nla):
                return canonical

    # ── Fallback: Title Case del nombre original ───────────────────────────────
    return raw.title()


def _get_or_create_supplier(sb, name: str) -> str | None:
    """Devuelve el id del proveedor con ese nombre; lo crea si no existe."""
    try:
        rows = sb.table("suppliers").select("id").eq("name", name).limit(1).execute().data or []
        if rows:
            return rows[0]["id"]
        res = sb.table("suppliers").insert({"name": name}).execute()
        return ((res.data or [{}])[0]).get("id")
    except Exception as exc:
        print(f"[import] proveedor '{name}': {exc}")
        return None


def _find_or_create_catalog_item(
    sb, name: str, price: float, supplier_id: str | None
) -> str | None:
    """
    Busca un ítem en el catálogo por nombre (case-insensitive).
    Si no existe, lo crea con clasificación automática.
    Retorna el id del ítem o None si falla.
    """
    try:
        rows = (
            sb.table("items")
            .select("id")
            .ilike("name", name)
            .limit(1)
            .execute()
            .data or []
        )
        if rows:
            return rows[0]["id"]

        item_type, category = _classify_item(name)
        # Unidad por defecto según tipo
        unit = "EA" if item_type == "rentable" else "EVT"
        payload = {
            "name":         name,
            "description":  "Importado desde archivo histórico.",
            "item_type":    item_type,
            "category":     category,
            "unit":         unit,
            "default_rate": price if price > 0 else None,
            "active":       True,
        }
        if supplier_id:
            payload["supplier_id"] = supplier_id

        res = sb.table("items").insert(payload).execute()
        new_id = ((res.data or [{}])[0]).get("id")
        print(f"[import] ítem creado en catálogo: '{name}' → {new_id}")
        return new_id
    except Exception as exc:
        print(f"[import] catálogo '{name}': {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Catálogos
# ─────────────────────────────────────────────────────────────────────────────

def get_clients_and_profiles() -> tuple[list, list]:
    sb       = get_service_client()
    clients  = sb.table("clients").select("id,name").order("name").execute().data or []
    profiles = sb.table("profiles").select("id,full_name,role").order("full_name").execute().data or []
    return clients, profiles


# ─────────────────────────────────────────────────────────────────────────────
# Sugerencias
# ─────────────────────────────────────────────────────────────────────────────

def suggest_client_id(clients: list, name: str) -> str | None:
    if not name:
        return None
    nl = name.lower().strip()
    for c in clients:
        if (c.get("name") or "").lower().strip() == nl:
            return c["id"]
    for c in clients:
        cn = (c.get("name") or "").lower()
        if nl in cn or cn in nl:
            return c["id"]
    return None


def suggest_owner_id(profiles: list, name: str) -> str | None:
    if not name:
        return None
    nl = name.lower().strip()
    for p in profiles:
        if (p.get("full_name") or "").lower().strip() == nl:
            return p["id"]
    parts = nl.split()
    for p in profiles:
        pn = (p.get("full_name") or "").lower()
        if any(pt in pn for pt in parts if len(pt) > 3):
            return p["id"]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos de find-or-create
# ─────────────────────────────────────────────────────────────────────────────

def _find_or_create_client(sb, name: str) -> str:
    """Devuelve el id del cliente con ese nombre; lo crea si no existe."""
    rows = sb.table("clients").select("id").eq("name", name).limit(1).execute().data or []
    if rows:
        return rows[0]["id"]
    res = sb.table("clients").insert({"name": name}).execute()
    data = (res.data or [{}])[0]
    return data["id"]


def _find_or_create_contact(sb, client_id: str, name: str) -> str | None:
    """Devuelve el id del contacto; lo crea si no existe para ese cliente."""
    try:
        rows = (
            sb.table("contacts")
            .select("id")
            .eq("client_id", client_id)
            .eq("name", name)
            .limit(1)
            .execute()
            .data or []
        )
        if rows:
            return rows[0]["id"]
        res = sb.table("contacts").insert({
            "name":      name,
            "client_id": client_id,
        }).execute()
        return ((res.data or [{}])[0]).get("id")
    except Exception as exc:
        print(f"[import] contacto '{name}': {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Creación principal
# ─────────────────────────────────────────────────────────────────────────────

def create_import(form) -> tuple[str, str]:
    """
    Crea todos los registros a partir del formulario de confirmación de importación.
    Retorna (quote_id, quote_number).
    """
    sb      = get_service_client()

    # ── Responsable ──────────────────────────────────────────────────────────
    owner_id = (form.get("owner_id") or "").strip()
    if not owner_id:
        raise ValueError("Selecciona el responsable de la cotización.")

    # ── Cliente (find-or-create) ──────────────────────────────────────────────
    client_id = (form.get("client_id") or "").strip()
    if not client_id:
        client_name = (form.get("client_name_new") or "").strip() or CLIENT_EVENTUAL
        client_id   = _find_or_create_client(sb, client_name)

    if not client_id:
        raise ValueError("No se pudo crear o encontrar el cliente.")

    # ── Contacto Eventual (find-or-create siempre) ────────────────────────────
    contact_id = _find_or_create_contact(sb, client_id, CONTACT_EVENTUAL)

    # ── ISV ────────────────────────────────────────────────────────────────────
    apply_tax = (form.get("apply_tax") or "yes").lower().strip()
    tax_rate  = 15.0 if apply_tax == "yes" else 0.0

    # ── Evento (find-or-create "Evento Eventual" si no hay datos suficientes) ──
    event_id   = None
    venue      = (form.get("venue") or "").strip()
    event_date = (form.get("event_date") or "").strip()
    event_name = (form.get("event_type") or "").strip() or EVENT_EVENTUAL
    create_ev  = form.get("create_event") == "1"

    if create_ev:
        ev_date = event_date if event_date else _today()
        try:
            ev_payload = {
                "name":       event_name,
                "client_id":  client_id,
                "venue":      venue or "Por definir",
                "start_at":   f"{ev_date}T08:00:00",
                "end_at":     f"{ev_date}T22:00:00",
                "created_by": owner_id,
            }
            ev_res   = sb.table("events").insert(ev_payload).execute()
            event_id = ((ev_res.data or [{}])[0]).get("id")
        except Exception as exc:
            print(f"[import] crear evento: {exc}")

    # ── Fecha emitida ─────────────────────────────────────────────────────────
    date_issued = (form.get("date_issued") or "").strip()

    # ── Vencimiento: 30 días después de la fecha emitida ──────────────────────
    try:
        _base = datetime.strptime(date_issued, "%Y-%m-%d").date() if date_issued else datetime.utcnow().date()
    except ValueError:
        _base = datetime.utcnow().date()
    valid_until_calc = (_base + timedelta(days=30)).isoformat()

    # ── Encabezado de cotización ──────────────────────────────────────────────
    # Usar el número detectado en el archivo; si viene vacío, generar uno automático
    original_qn = (form.get("original_quote_number") or "").strip()
    quote_no    = original_qn if original_qn else gen_quote_number(sb)

    notes_lines = [
        "Importado desde archivo histórico.",
        f"Proveedor: {SUPPLIER_NAME}",
    ]
    if date_issued: notes_lines.append(f"Fecha emitida:  {date_issued}")
    if event_name:  notes_lines.append(f"Tipo de evento: {event_name}")
    if event_date:  notes_lines.append(f"Fecha evento:   {event_date}")
    if venue:       notes_lines.append(f"Lugar:          {venue}")

    q_payload: dict = {
        "quote_number":   quote_no,
        "client_id":      client_id,
        "contact_id":     contact_id,
        "event_id":       event_id,
        "owner_id":       owner_id,
        "currency":       "HNL",
        "exchange_rate":  1.0,
        "status":         "draft",
        "valid_until":    valid_until_calc,
        "tax_rate":       tax_rate,
        "subtotal":       0.0,
        "discount_total": 0.0,
        "tax_total":      0.0,
        "total":          0.0,
        "notes_internal": "\n".join(notes_lines),
    }
    # Preservar la fecha de emisión original del archivo como created_at
    if date_issued:
        q_payload["created_at"] = f"{date_issued}T00:00:00+00:00"

    q_res = (
        sb.table("quotations")
        .insert(q_payload, returning="representation")
        .execute()
    )
    rows     = getattr(q_res, "data", None) or []
    quote_id = rows[0]["id"] if rows else None

    if not quote_id:
        raise RuntimeError("No se obtuvo ID de la cotización creada.")

    # Historial de estado
    try:
        sb.table("quotation_status_history").insert({
            "quotation_id": quote_id,
            "old_status":   None,
            "new_status":   "draft",
            "changed_by":   owner_id,
            "note":         "Importado desde archivo histórico",
        }).execute()
    except Exception:
        pass

    # ── Catálogo: proveedor Avvisi ────────────────────────────────────────────
    avvisi_supplier_id = _get_or_create_supplier(sb, SUPPLIER_NAME)

    # ── Líneas de ítems ───────────────────────────────────────────────────────
    names  = form.getlist("item_name[]")
    qtys   = form.getlist("item_qty[]")
    days_l = form.getlist("item_days[]")
    prices = form.getlist("item_price[]")

    to_insert = []
    for idx, name in enumerate(names):
        name = name.strip()
        if not name:
            continue
        try:
            qty   = float(qtys[idx])  if idx < len(qtys)   else 1.0
            days  = int(float(days_l[idx])) if idx < len(days_l) else 1
            price = float(prices[idx]) if idx < len(prices) else 0.0
        except (ValueError, IndexError):
            continue
        if qty <= 0:
            continue
        # Precio 0 es permitido — el usuario puede corregirlo en la edición
        price = max(price, 0.0)

        # Homologar nombre antes de buscar/crear en catálogo
        name_norm  = _normalize_item_name(name)
        catalog_id = _find_or_create_catalog_item(sb, name_norm, price, avvisi_supplier_id)
        item_type, _ = _classify_item(name_norm)

        to_insert.append({
            "quotation_id": quote_id,
            "item_id":      catalog_id,
            "custom_name":  name_norm,   # nombre canónico en la cotización
            "item_type":    item_type,
            "quantity":     qty,
            "unit":         "unit",
            "days":         max(days, 1),
            "unit_price":   price,
            "discount_pct": 0.0,
            "sort_order":   idx + 1,
        })

    if not to_insert:
        try:
            sb.table("quotations").delete().eq("id", quote_id).execute()
        except Exception:
            pass
        raise ValueError("Agrega al menos un producto antes de importar.")

    items_res = (
        sb.table("quotation_items")
        .insert(to_insert, returning="representation")
        .execute()
    )
    inserted = len(getattr(items_res, "data", None) or [])
    print(f"[import] {inserted} ítems insertados para cotización {quote_id}")

    # ── Recalcular totales ────────────────────────────────────────────────────
    try:
        recompute_totals(sb, quote_id)
    except Exception as exc:
        print(f"[import] recompute_totals: {exc}")

    return quote_id, quote_no
