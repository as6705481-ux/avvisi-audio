from flask import Flask, render_template, request, redirect, url_for, flash, session, current_app
from db import get_public_client, get_service_client, get_supabase
from datetime import datetime, timedelta
from collections import defaultdict
import calendar
import pytz
from uuid import uuid4, UUID

ALLOWED_ITEM_TYPES = {"rentable", "consumable", "service", "bundle"}
USER_ROLES         = {"admin","sales","ops","finance"}
QUOTE_PREFIX       = "AVV"
QUOTE_CURRENCY     = "HNL"
VALID_STATUSES     = {"draft","sent","accepted","declined","expired","cancelled","converted"}

TZ_DEFAULT = "America/Tegucigalpa"

RES_STATUS_FIRM = "firm"

# AUTENTIFICACION GOOGLE: https://cjnzkhlzltzntviigpvk.supabase.co/auth/v1/callback
app = Flask(__name__)
app.secret_key = "cambia-esto"  # req. para flash mensajes

tz = pytz.timezone("America/Tegucigalpa")

def teg(dt: datetime) -> datetime:
    """Convierte naive a Tegucigalpa tz-aware."""
    if dt.tzinfo is None:
        return tz.localize(dt)
    return dt.astimezone(tz)

def parse_uuid(v: str | None) -> str | None:
    if not v:
        return None
    try:
        return str(UUID(v))
    except Exception:
        return None

def gen_quote_number(sb, prefix=QUOTE_PREFIX):
    """Genera correlativo tipo AVV-YYYY-#### consultando el mayor existente del año."""
    year = datetime.now().year
    # Busca el mayor existente de este año
    like_prefix = f"{prefix}-{year}-"
    res = sb.table("quotations") \
            .select("quote_number") \
            .ilike("quote_number", like_prefix + "%") \
            .order("quote_number", desc=True) \
            .limit(1).execute()
    last = (res.data or [{}])[0].get("quote_number")
    n = 1
    if last:
        try:
            n = int(last.split("-")[-1]) + 1
        except Exception:
            n = 1
    return f"{prefix}-{year}-{n:04d}"

def money(x):  # seguridad para None/float
    try:
        return round(float(x or 0), 2)
    except Exception:
        return 0.0

def recompute_totals(sb, quotation_id):
    """Recalcula subtotales, impuestos y total de la cotización, y actualiza la cabecera."""
    # Traer líneas
    lines = sb.table("quotation_items").select(
        "id, quantity, unit_price, discount_pct, tax_rate"
    ).eq("quotation_id", quotation_id).execute().data or []

    subtotal = discount_total = tax_total = total = 0.0

    for ln in lines:
        qty   = float(ln["quantity"] or 0)
        price = float(ln["unit_price"] or 0)
        disc  = float(ln["discount_pct"] or 0)
        tax   = float(ln["tax_rate"] or 0)

        line_gross = qty * price                       # antes de descuento
        line_disc  = line_gross * (disc/100.0)
        line_base  = line_gross - line_disc
        line_tax   = line_base * (tax/100.0)
        line_total = line_base + line_tax

        # Actualiza la línea (snapshot)
        sb.table("quotation_items").update({
            "line_subtotal": round(line_base,2),
            "line_tax": round(line_tax,2),
            "line_total": round(line_total,2),
        }).eq("id", ln["id"]).execute()

        subtotal       += line_base
        discount_total += line_disc
        tax_total      += line_tax
        total          += line_total

    sb.table("quotations").update({
        "subtotal": round(subtotal,2),
        "discount_total": round(discount_total,2),
        "tax_total": round(tax_total,2),
        "total": round(total,2),
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", quotation_id).execute()

@app.context_processor
def inject_user():
    u = {}
    try:
        if session.get("user_id"):
            sb = get_service_client()
            prof = sb.table("profiles").select("id, full_name").eq("id", session["user_id"]).single().execute()
            if prof.data:
                u = {"id": prof.data["id"], "name": prof.data.get("full_name") or "Usuario"}
    except Exception:
        pass
    if not u:
        u = {"id": "", "name": "Usuario"}  # invitado
    return dict(user=u)
def login_required(f):
    from functools import wraps
    def wrapper(*args, **kwargs):
        if not session.get("access_token") or not session.get("user_id"):
            flash("Inicia sesión para continuar.", "error")
            return redirect(url_for("login_get"))
        return f(*args, **kwargs)
    return wraps(f)(wrapper)

# ! RUTAS BÁSICAS DE AUTENTICACIÓN (USANDO ANON KEY) !
# - Registro (sign_up)
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/catalogo-coorporativos")
def catalogo_coporativos():
    return render_template("catalogo-coorporativos.html")

@app.route("/catalogo-social")
def ctalogo_social():
    return render_template("catalogo-social.html")

@app.route("/catalogo-btl")
def ctalogo_btl():
    return render_template("catalogo-btl.html")

@app.get("/login")
def login_get():
    return render_template("auth_login.html")

@app.post("/login")
def login_post():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Correo y contraseña son requeridos", "error")
        return redirect(url_for("login_get"))

    sb_pub = get_public_client()   # 🔑 usar ANON KEY para Auth

    try:
        auth_res = sb_pub.auth.sign_in_with_password({"email": email, "password": password})
        # Guarda sesión
        session["access_token"] = auth_res.session.access_token
        session["user_id"] = auth_res.user.id
        flash("Bienvenido 👋", "success")

        # Si quieres que todas las consultas pasen con RLS del usuario:
        get_public_client().postgrest.auth(session["access_token"])

        return redirect(url_for("dashboard"))

    except Exception as e:
        # Muestra el mensaje que viene de GoTrue (útil: 'Email not confirmed', 'Invalid login credentials', etc.)
        msg = getattr(e, "message", None) or str(e)
        # Mensajes típicos y explicación
        if "Email not confirmed" in msg:
            flash("Tu correo no está confirmado. Revisa tu bandeja o reenvía el enlace de verificación.", "error")
        elif "Invalid login credentials" in msg:
            flash("Credenciales inválidas. Verifica correo/contraseña.", "error")
        else:
            flash(f"Error de autenticación: {msg}", "error")
        return redirect(url_for("login_get"))

@app.get("/register")
def register_get():
    return render_template("auth_register.html")

@app.post("/register")
def register_post():
    sb = get_public_client()
    full_name = request.form.get("full_name", "").strip()
    email     = request.form.get("email", "").strip().lower()
    password  = request.form.get("password", "")
    password2 = request.form.get("password2", "")

    # Validaciones simples
    if not full_name or not email or not password:
        flash("Todos los campos son obligatorios.", "error")
        return redirect(url_for("register_get"))
    if password != password2:
        flash("Las contraseñas no coinciden.", "error")
        return redirect(url_for("register_get"))
    if len(password) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "error")
        return redirect(url_for("register_get"))

    # Opcional: define tu URL de redirección post-confirmación en Supabase (Auth → URL config)
    redirect_url = request.host_url.rstrip("/") + "/login"

    try:
        # Alta en Supabase Auth (GoTrue)
        # Guarda full_name en metadatos para que tu trigger handle_new_user() lo copie a profiles
        res = sb.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {"full_name": full_name},
                "email_redirect_to": redirect_url
            }
        })

        # Si el proyecto requiere confirmación de email, aquí normalmente NO hay sesión todavía
        if not res.user:
            flash("Registro creado. Revisa tu correo para confirmar tu cuenta.", "success")
            return redirect(url_for("login_get"))

        # Si la confirmación está desactivada, tendrás user/session ya; puedes loguear:
        if res.session and res.session.access_token:
            session["access_token"] = res.session.access_token
            session["user_id"]      = res.user.id
            flash("Cuenta creada y sesión iniciada.", "success")
            return redirect(url_for("items"))

        # Caso estándar: creado pero debe confirmar el correo
        flash("Cuenta creada. Revisa tu correo para confirmar e iniciar sesión.", "success")
        return redirect(url_for("login_get"))

    except Exception as e:
        msg = getattr(e, "message", None) or str(e)
        # Mensajes habituales de GoTrue
        if "User already registered" in msg or "already registered" in msg:
            flash("Este correo ya está registrado.", "error")
        elif "weak password" in msg.lower():
            flash("Contraseña débil. Usa al menos 8 caracteres con números y letras.", "error")
        else:
            flash(f"Error al registrar: {msg}", "error")
        return redirect(url_for("register_get"))

# ==================== ---------------------- =========================
@app.get("/dashboard")
@login_required
def dashboard():
    """
    Dashboard simple:
    - User: perfil (para mostrar nombre)
    - Ingresos por mes: suma de 'total' de quotations últimos 6 meses
    - Top productos: suma de 'quantity' por 'custom_name' en quotation_items últimos 6 meses
    """
    sb_service = get_service_client()

    # 1) Usuario (perfil)
    user = {"id": session.get("user_id"), "name": "Usuario"}
    try:
        prof = sb_service.table("profiles").select("full_name").eq("id", session["user_id"]).single().execute()
        if prof.data and prof.data.get("full_name"):
            user["name"] = prof.data["full_name"]
    except Exception:
        pass  # tolerante a fallos

    # Rango: últimos 6 meses
    today = datetime.utcnow().date().replace(day=1)
    six_months_ago = (today.replace(day=1) - timedelta(days=1)).replace(day=1)  # 1ro del mes pasado
    # Queremos incluir el mes actual y 5 previos
    months_labels = []
    pivot = today
    for i in range(6):
        label = f"{calendar.month_abbr[pivot.month]} {pivot.year}"  # p.ej. 'Oct 2025'
        months_labels.insert(0, label)
        # retrocede 1 mes
        prev_last_day = pivot - timedelta(days=1)
        pivot = prev_last_day.replace(day=1)

    # 2) Ingresos por mes (sumamos total de quotations por created_at)
    try:
        q_res = sb_service.table("quotations") \
            .select("id,total,created_at,status") \
            .gte("created_at", six_months_ago.isoformat()) \
            .execute()
        # Agrega por (YYYY-MM)
        totals_by_yyyymm = defaultdict(float)
        for row in (q_res.data or []):
            if not row.get("created_at"): 
                continue
            dt = datetime.fromisoformat(row["created_at"].replace("Z","+00:00"))
            key = f"{dt.year:04d}-{dt.month:02d}"
            totals_by_yyyymm[key] += float(row.get("total") or 0.0)

        # mapea al orden de labels (que ya construimos)
        def yyyymm(label):
            mon_abbr, year = label.split()
            m = list(calendar.month_abbr).index(mon_abbr)
            return f"{int(year):04d}-{m:02d}"

        incomes = [round(totals_by_yyyymm.get(yyyymm(lbl), 0.0), 2) for lbl in months_labels]
    except Exception:
        months_labels = months_labels or []
        incomes = [0]*len(months_labels)

    # 3) Top productos (por líneas de cotización)
    try:
        qi_res = sb_service.table("quotation_items") \
            .select("custom_name,quantity,created_at") \
            .gte("created_at", six_months_ago.isoformat()) \
            .limit(5000) \
            .execute()
        qty_by_name = defaultdict(float)
        for row in (qi_res.data or []):
            name = row.get("custom_name") or "Sin nombre"
            qty_by_name[name] += float(row.get("quantity") or 0.0)
        # Top 6
        top = sorted(qty_by_name.items(), key=lambda kv: kv[1], reverse=True)[:6]
        product_names = [k for k, _ in top] or ["—"]
        product_quantities = [round(v, 2) for _, v in top] or [0]
    except Exception:
        product_names = ["—"]
        product_quantities = [0]

    return render_template(
        "dashboard.html",
        user               = user,
        months             = months_labels,
        incomes            = incomes,
        product_names      = product_names,
        product_quantities = product_quantities
    )

# ------------------------------------------------------------------
@app.get("/items")
def items():
    sb = get_service_client()  # o get_public_client() + RLS
    # Items base
    res = sb.table("items").select(
        "id, sku, name, description, item_type, unit, default_rate, tax_rate,active, created_at", "supplier_id"
    ).order("sku").limit(200).execute()
    items = res.data or []

    # Stock simple (si usas inventory_balances)
    bal = sb.table("inventory_balances").select("item_id, on_hand").execute().data or []
    by_id = {b["item_id"]: b["on_hand"] for b in bal}
    for it in items:
        it["on_hand"] = by_id.get(it["id"])

    # Si manejas proveedores y nombre:
    suppliers = sb.table("suppliers").select("id, name").execute().data or []
    name_by_id = {s["id"]: s["name"] for s in suppliers}
    
    for it in items:
        it["supplier_name"] = name_by_id.get(it.get("supplier_id"))

    return render_template("items.html", products=items)

@app.route("/products/add", methods=["GET", "POST"], endpoint="product_add")
def product_add():
    sb = get_service_client()

    # --- Fuentes para selects (GET y POST fallido) ---
    try:
        suppliers = sb.table("suppliers").select("id,name,email").order("name").execute().data or []
    except Exception:
        suppliers = []

    try:
        # categorías distintas existentes en items.category
        rows = sb.table("items").select("category").not_.is_("category", "null").execute().data or []
        categories = sorted({r["category"] for r in rows if r.get("category")})
    except Exception:
        categories = []

    if request.method == "GET":
        return render_template("product_add.html", suppliers=suppliers, categories=categories)

    # --------- POST ----------
    name        = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    item_type   = (request.form.get("item_type") or "").strip()
    unit        = (request.form.get("unit") or "unit").strip()
    sku         = (request.form.get("sku") or "").strip()
    active      = True if request.form.get("active") == "1" else False

    # proveedor y categoría
    supplier_id  = (request.form.get("supplier_id") or "").strip() or None  # <select name="supplier_id">
    category     = (request.form.get("category") or "").strip()
    new_category = (request.form.get("new_category") or "").strip()
    if new_category:
        category = new_category
    if not category:
        category = None

    # tags opcionales (coma-separados en un input texto)
    tags_raw  = (request.form.get("tags") or "").strip()
    tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None

    # numéricos
    try:
        default_rate = float(request.form.get("default_rate") or 0.0)
    except ValueError:
        default_rate = 0.0

    try:
        tax_rate = float(request.form.get("tax_rate") or 0.0)
    except ValueError:
        tax_rate = 0.0

    # stock inicial (solo para consumibles)
    try:
        stock = int(float(request.form.get("stock") or 0))
    except ValueError:
        stock = 0

    # activos (si es rentable)
    try:
        asset_count = int(request.form.get("asset_count") or 0)
    except ValueError:
        asset_count = 0
    serial_prefix = (request.form.get("serial_prefix") or "").strip() or "SER"

    # Validaciones mínimas
    if not name:
        flash("El nombre es obligatorio.", "error")
        return render_template("product_add.html", suppliers=suppliers, categories=categories)

    if item_type not in ALLOWED_ITEM_TYPES:
        flash("Tipo de ítem inválido.", "error")
        return render_template("product_add.html", suppliers=suppliers, categories=categories)

    if not (0 <= tax_rate <= 100):
        flash("El impuesto debe estar entre 0 y 100.", "error")
        return render_template("product_add.html", suppliers=suppliers, categories=categories)

    # SKU auto si no viene
    if not sku:
        sku = f"ITM-{str(uuid4())[:8].upper()}"

    # --- Inserción de item (y devolvemos id) ---
    try:
        resp = sb.table("items").insert({
            "sku": sku,
            "name": name,
            "description": description,
            "item_type": item_type,
            "unit": unit,
            "default_rate": default_rate,
            "tax_rate": tax_rate,
            "active": active,
            "supplier_id": supplier_id,   # FK a suppliers.id (uuid o None)
            "category": category,         # text o None
            "tags": tags_list             # text[] o None
        }, returning="representation"  # <-- necesario en v2 para devolver la fila
        ).execute()

        item_id = resp.data[0]["id"]    # <-- la fila insertada viene en una lista

    except Exception as e:
        flash(f"No se pudo crear el producto: {getattr(e,'message',str(e))}", "error")
        return render_template("product_add.html", suppliers=suppliers, categories=categories)

    # --- Stock: sólo si consumible ---
    if item_type == "consumable":
        try:
            sb.table("inventory_balances").insert({
                "item_id": item_id,           # <-- ojo: item_id (no product_id)
                "on_hand": max(0, stock),
                "min_level": 0
            }).execute()
        except Exception:
            # si la tabla no existe / RLS lo bloquea, no romper el flujo
            pass

    # --- Activos seriados: sólo si rentable ---
    if item_type == "rentable" and asset_count > 0:
        try:
            assets = []
            for i in range(1, asset_count + 1):
                serial_no = f"{serial_prefix}-{sku}-{i:03d}"
                assets.append({"item_id": item_id, "serial_no": serial_no, "active": True})
            if assets:
                sb.table("assets").insert(assets).execute()
        except Exception:
            pass

    flash("Producto creado correctamente.", "success")
    return redirect(url_for("items"))

@app.route("/products/<product_id>/edit", methods=["GET", "POST"], endpoint="product_edit")
def product_edit(product_id):
    sb = get_service_client()

    # Cargar datos base
    try:
        item = sb.table("items").select(
            "id, sku, name, description, item_type, unit, default_rate, tax_rate, "
            "active, supplier_id, category, tags, created_at"
        ).eq("id", product_id).single().execute().data
        if not item:
            flash("Producto no encontrado.", "error")
            return redirect(url_for("items"))
    except Exception as e:
        flash(f"No se pudo cargar el producto: {getattr(e,'message',str(e))}", "error")
        return redirect(url_for("items"))

    # Stock actual (si existe)
    on_hand = None
    try:
        bal = sb.table("inventory_balances").select("on_hand").eq("item_id", item["id"]).single().execute().data
        
        if bal:
            on_hand = bal.get("on_hand")

    except Exception:
        print("no stock")
        pass

    # Suppliers
    suppliers = []
    try:
        suppliers = sb.table("suppliers").select("id,name,email").order("name").execute().data or []
    except Exception:
        suppliers = []

    # Categorías existentes (distintas)
    categories = []
    try:
        rows       = sb.table("items").select("category").not_.is_("category", "null").execute().data or []
        categories = sorted({r["category"] for r in rows if r.get("category")})
    except Exception:
        categories = []

    if request.method == "GET":
        return render_template(
            "product_edit.html",
            product    = item,
            on_hand    = on_hand,
            suppliers  = suppliers,
            categories = categories
        )

    # --- POST: guardar cambios ---
    name        = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    sku         = (request.form.get("sku") or "").strip()
    unit        = (request.form.get("unit") or "unit").strip()
    item_type   = (request.form.get("item_type") or "").strip()
    active      = True if request.form.get("active") == "1" else False

    # números
    try:
        default_rate = float(request.form.get("default_rate") or 0.0)
    except ValueError:
        default_rate = 0.0
    try:
        tax_rate = float(request.form.get("tax_rate") or 0.0)
    except ValueError:
        tax_rate = 0.0

    # proveedor
    supplier_id = parse_uuid(request.form.get("supplier_id") or "")  # puede ser None
    print("supplier_id:", supplier_id)
    # categoría
    category = (request.form.get("category") or "").strip()
    new_category = (request.form.get("new_category") or "").strip()
    if new_category:
        category = new_category  # prioriza nueva

    # tags
    tags_raw = (request.form.get("tags") or "").strip()
    tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None

    # validaciones mínimas
    if not name:
        flash("El nombre es obligatorio.", "error")
        return redirect(url_for("product_edit", product_id = product_id))
    if item_type not in {"consumable", "rentable", "service", "bundle"}:
        flash("Tipo de ítem inválido.", "error")
        return redirect(url_for("product_edit", product_id = product_id))
    if not (0 <= tax_rate <= 100):
        flash("El impuesto debe estar entre 0 y 100.", "error")
        return redirect(url_for("product_edit", product_id = product_id))

    # actualizar item
    payload = {
        "sku": sku or None,
        "name": name,
        "description": description,
        "item_type": item_type,
        "unit": unit or "unit",
        "default_rate": default_rate,
        "tax_rate": tax_rate,
        "active": active,
        "supplier_id": supplier_id,
        "category": category or None,
        "tags": tags_list if tags_list else None,
    }

    try:
        sb.table("items").update(payload).eq("id", item["id"]).execute()
    except Exception as e:
        flash(f"No se pudo actualizar el producto: {getattr(e,'message',str(e))}", "error")
        return redirect(url_for("product_edit", product_id = product_id))

    # stock (solo consumible): upsert en inventory_balances
    if item_type == "consumable":
        try:
            stock_val = request.form.get("stock")
            stock_int = int(float(stock_val)) if stock_val is not None and stock_val != "" else None

            if stock_int is not None:
                # UPSERT manual (update si existe; si no, insert)
                if on_hand is None:
                    sb.table("bundle_items").insert({
                        "item_id": item["id"],
                        "on_hand": max(0, stock_int),
                        "min_level": 0
                    }).execute()
                else:
                    sb.table("inventory_balances").update({
                        "on_hand": max(0, stock_int)
                    }).eq("product_id", item["id"]).execute()
        except Exception as e:
            flash(f"Producto actualizado, pero el stock no pudo guardarse: {getattr(e,'message',str(e))}", "warning")
            return redirect(url_for("product_edit", product_id = product_id))
    else:
        # Si cambió a no-consumible, puedes optar por eliminar su balance:
        # try:
        #     sb.table("inventory_balances").delete().eq("product_id", item["id"]).execute()
        # except Exception:
        #     pass
        pass

    flash("Cambios guardados correctamente.", "success")
    return redirect(url_for("items"))

@app.post("/products/<product_id>/delete", endpoint="product_delete")
def product_delete(product_id):
    sb = get_service_client()

    # 1) Traer el item para saber tipo y existencia
    try:
        res = sb.table("items").select("id, name, item_type").eq("id", product_id).single().execute()
        item = res.data
        if not item:
            flash("El producto no existe.", "error")
            return redirect(url_for("items"))
    except Exception as e:
        flash(f"No se pudo cargar el producto: {getattr(e,'message', str(e))}", "error")
        return redirect(url_for("items"))

    # 2) Validar dependencias que BLOQUEAN
    # 2.1) ¿Es componente en algún bundle? (bundle_items.item_id = product_id)
    try:
        comp_count = sb.table("bundle_items").select("bundle_id", count="exact").eq("item_id", product_id).execute().count or 0
        if comp_count > 0:
            flash(f"No se puede eliminar: este producto es componente de {comp_count} bundle(s). "
                  "Quita el componente de esos bundles primero.", "error")
            return redirect(url_for("items"))
    except Exception:
        # si falla el conteo, preferimos prevenir
        flash("No se pudo verificar si el producto pertenece a bundles. Intenta más tarde.", "error")
        return redirect(url_for("items"))

    # 2.2) ¿Tiene reservas activas? (reservations.item_id = product_id)
    try:
        rsv_count = sb.table("reservations").select("id", count="exact").eq("item_id", product_id).execute().count or 0
        if rsv_count > 0:
            flash(f"No se puede eliminar: hay {rsv_count} reserva(s) asociada(s) a este producto. "
                  "Libera o elimina esas reservas primero.", "error")
            return redirect(url_for("items"))
    except Exception:
        flash("No se pudo verificar reservas del producto. Intenta más tarde.", "error")
        return redirect(url_for("items"))

    # 3) Si el ítem es un BUNDLE, borra sus líneas de composición (bundle_id = product_id)
    if item["item_type"] == "bundle":
        try:
            sb.table("bundle_items").delete().eq("bundle_id", product_id).execute()
        except Exception as e:
            flash(f"No se pudo limpiar la composición del bundle: {getattr(e,'message', str(e))}", "error")
            return redirect(url_for("items"))

    # 4) Borrar el ítem (assets e inventory_balances se irán por cascade; quotation_items hará SET NULL)
    try:
        sb.table("items").delete().eq("id", product_id).execute()
        flash(f"Producto '{item['name']}' eliminado correctamente.", "success")
    except Exception as e:
        flash(f"No se pudo eliminar el producto: {getattr(e,'message', str(e))}", "error")

    return redirect(url_for("items"))

@app.post("/products/<product_id>/status", endpoint="product_set_status")
def product_set_status(product_id):
    sb = get_service_client()
    action = (request.args.get("action") or "").lower()  # 'activate' | 'deactivate'
    new_val = True if action == "activate" else False
    try:
        sb.table("items").update({"active": new_val}).eq("id", product_id).execute()
        flash(f"Producto {'activado' if new_val else 'desactivado'}.", "success")
    except Exception as e:
        flash(f"No se pudo actualizar estado: {getattr(e,'message',str(e))}", "error")
    return redirect(url_for("items"))


# =========================
# LISTAR
# =========================
@app.get("/suppliers", endpoint="suppliers")
def suppliers_list():
    sb = get_service_client()
    res = sb.table("suppliers").select(
        "id,name,email,phone,address,active,created_at"
    ).order("name").execute()
    suppliers = res.data or []
    return render_template("suppliers.html", suppliers=suppliers)


# =========================
# CREAR
# =========================
@app.route("/suppliers/add", methods=["GET", "POST"], endpoint="supplier_add")
def supplier_add():
    sb = get_service_client()

    if request.method == "GET":
        return render_template("supplier_add.html")

    # POST
    name  = (request.form.get("name")  or "").strip()
    email = (request.form.get("email") or "").strip() or None
    phone = (request.form.get("phone") or "").strip() or None
    tax_id = (request.form.get("tax_id") or "").strip() or None
    notes = (request.form.get("notes") or "").strip() or None
    active = True if request.form.get("active") == "1" else False

    # Dirección (jsonb)
    address = {
        "street":  (request.form.get("street")  or "").strip(),
        "city":    (request.form.get("city")    or "").strip(),
        "state":   (request.form.get("state")   or "").strip(),
        "zip":     (request.form.get("zip")     or "").strip(),
        "country": (request.form.get("country") or "").strip(),
    }

    print(name, email, phone, tax_id, notes, active, address)
    # Si todo viene vacío, guarda None
    if not any(address.values()):
        address = None

    if not name:
        flash("El nombre es obligatorio.", "error")
        return render_template("supplier_add.html")
    
    try:
        resp = sb.table("suppliers")\
             .insert({
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "tax_id": tax_id,
                    "address": address,
                    "notes": notes,
                    "active": active
                }, returning="representation")\
                        .execute()

        rows = getattr(resp, "data", None) or []
        if not rows:
            # Si RLS/regex/único fallan, a veces viene error aquí
            raise RuntimeError(f"Insert sin data. Detalle: {getattr(resp,'error',None)}")

        new_id = rows[0].get("id")
        flash("Proveedor creado correctamente.", "success")
        return redirect(url_for("suppliers"))

    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f"No se pudo crear el proveedor: {str(e)}", "error")
        return render_template("supplier_add.html")



# =========================
# EDITAR
# =========================
@app.route("/suppliers/<supplier_id>/edit", methods=["GET", "POST"], endpoint="supplier_edit")
def supplier_edit(supplier_id):
    sb = get_service_client()

    # Cargar proveedor
    try:
        row = sb.table("suppliers").select(
            "id,name,email,phone,tax_id,address,notes,active,created_at"
        ).eq("id", supplier_id).single().execute().data
        if not row:
            flash("Proveedor no encontrado.", "error")
            return redirect(url_for("suppliers"))
    except Exception as e:
        flash(f"No se pudo cargar el proveedor: {getattr(e,'message',str(e))}", "error")
        return redirect(url_for("suppliers"))

    if request.method == "GET":
        return render_template("supplier_edit.html", supplier=row)

    # POST
    name   = (request.form.get("name")  or "").strip()
    email  = (request.form.get("email") or "").strip() or None
    phone  = (request.form.get("phone") or "").strip() or None
    tax_id = (request.form.get("tax_id") or "").strip() or None
    notes  = (request.form.get("notes") or "").strip() or None
    active = True if request.form.get("active") == "1" else False

    address = {
        "street":  (request.form.get("street")  or "").strip(),
        "city":    (request.form.get("city")    or "").strip(),
        "state":   (request.form.get("state")   or "").strip(),
        "zip":     (request.form.get("zip")     or "").strip(),
        "country": (request.form.get("country") or "").strip(),
    }
    if not any(address.values()):
        address = None

    if not name:
        flash("El nombre es obligatorio.", "error")
        return render_template("supplier_edit.html", supplier=row)

    try:
        sb.table("suppliers").update({
            "name": name,
            "email": email,
            "phone": phone,
            "tax_id": tax_id,
            "address": address,
            "notes": notes,
            "active": active
        }).eq("id", supplier_id).execute()
        flash("Proveedor actualizado.", "success")
        return redirect(url_for("suppliers"))
    except Exception as e:
        flash(f"No se pudo actualizar: {getattr(e,'message',str(e))}", "error")
        return render_template("supplier_edit.html", supplier=row)

# =========================
# ACTIVAR / DESACTIVAR
# =========================
@app.post("/suppliers/<supplier_id>/deactivate", endpoint="supplier_deactivate")
def supplier_deactivate(supplier_id):
    sb = get_service_client()
    try:
        sb.table("suppliers").update({"active": False}).eq("id", supplier_id).execute()
        flash("Proveedor desactivado.", "success")
    except Exception as e:
        flash(f"No se pudo desactivar: {getattr(e,'message',str(e))}", "error")
    return redirect(url_for("suppliers"))

@app.post("/suppliers/<supplier_id>/activate", endpoint="supplier_activate")
def supplier_activate(supplier_id):
    sb = get_service_client()
    try:
        sb.table("suppliers").update({"active": True}).eq("id", supplier_id).execute()
        flash("Proveedor activado.", "success")
    except Exception as e:
        flash(f"No se pudo activar: {getattr(e,'message',str(e))}", "error")
    return redirect(url_for("suppliers"))


# =========================
# BORRAR
# =========================
@app.post("/suppliers/<supplier_id>/delete", endpoint="delete_supplier")
def supplier_delete(supplier_id):
    sb = get_service_client()

    # (Seguridad) bloquear si hay items asociados
    try:
        cnt = sb.table("items").select("id", count="exact").eq("supplier_id", supplier_id).execute().count or 0
        if cnt > 0:
            print(f"No se puede eliminar: hay {cnt} item(s) asociados a este proveedor. Reasigna o elimina esos items primero.", "error")
            return redirect(url_for("suppliers"))
    except Exception:
        pass  # si falla el conteo, preferimos no borrar

    try:
        sb.table("suppliers").delete().eq("id", supplier_id).execute()
        flash("Proveedor eliminado.", "success")
    except Exception as e:
        flash(f"No se pudo eliminar: {getattr(e,'message',str(e))}", "error")
    return redirect(url_for("suppliers"))

# =========================
# LISTAR CLIENTES
# =========================
@app.get("/clients", endpoint="clients")
def clients_list():
    sb = get_service_client()
    res = sb.table("clients").select(
        "id,name,tax_id,email,phone,billing_address,organization_id,is_eventual,created_at,updated_at"
    ).order("name").execute()
    clients = (res.data or [])

    # (Opcional) cargar contacto primario por cliente para mostrar en la tabla
    primary = {}
    try:
        crows = (
            sb.table("contacts")
              .select("id,client_id,name,email,phone,is_primary")
              .eq("is_primary", True)
              .execute()
              .data or []
        )
        for c in crows:
            primary[c["client_id"]] = c
    except Exception:
        pass

    return render_template("clients.html", clients=clients, primary=primary)

# =========================
# CREAR CLIENTE
# =========================
@app.route("/clients/add", methods=["GET", "POST"], endpoint="client_add")
def client_add():
    sb = get_service_client()

    if request.method == "GET":
        return render_template("client_add.html")

    # POST
    name            = (request.form.get("name") or "").strip()
    tax_id          = (request.form.get("tax_id") or "").strip() or None
    email           = (request.form.get("email") or "").strip() or None
    phone           = (request.form.get("phone") or "").strip() or None
    organization_id = (request.form.get("organization_id") or "").strip() or None
    is_eventual     = True if request.form.get("is_eventual") == "1" else False

    # Dirección (jsonb)
    billing_address = {
        "street":  (request.form.get("street")  or "").strip(),
        "city":    (request.form.get("city")    or "").strip(),
        "state":   (request.form.get("state")   or "").strip(),
        "zip":     (request.form.get("zip")     or "").strip(),
        "country": (request.form.get("country") or "").strip(),
    }
    if not any(billing_address.values()):
        billing_address = None

    if not name:
        flash("El nombre del cliente es obligatorio.", "error")
        return render_template("client_add.html")

    # Si marcaron 'is_eventual', puedes garantizar existencia única del eventual:
    # (opcional; si quieres estricto, valida que no exista otro is_eventual=true)
    try:
        ins = (
            sb.table("clients")
              .insert({
                  "name": name,
                  "tax_id": tax_id,
                  "email": email,
                  "phone": phone,
                  "billing_address": billing_address,
                  "organization_id": organization_id,
                  "is_eventual": is_eventual
              })
              .select("id")
              .single()
              .execute()
        )
        flash("Cliente creado correctamente.", "success")
        return redirect(url_for("clients"))
    except Exception as e:
        msg = getattr(e, "message", str(e))
        if "clients_tax_id_uniq" in msg:
            flash("El RTN/Tax ID ya existe para otro cliente.", "error")
        elif "clients_email_chk" in msg:
            flash("El correo no tiene un formato válido.", "error")
        elif "clients_phone_chk" in msg:
            flash("El teléfono no tiene un formato válido.", "error")
        else:
            flash(f"No se pudo crear el cliente: {msg}", "error")
        return render_template("client_add.html")

# =========================
# EDITAR CLIENTE
# =========================
@app.route("/clients/<client_id>/edit", methods=["GET", "POST"], endpoint="client_edit")
def client_edit(client_id):
    sb = get_service_client()

    # Cargar cliente
    try:
        row = (
            sb.table("clients")
              .select("id,name,tax_id,email,phone,billing_address,organization_id,is_eventual,created_at,updated_at")
              .eq("id", client_id).single().execute().data
        )
        if not row:
            flash("Cliente no encontrado.", "error")
            return redirect(url_for("clients"))
    except Exception as e:
        flash(f"No se pudo cargar el cliente: {getattr(e,'message',str(e))}", "error")
        return redirect(url_for("clients"))

    if request.method == "GET":
        return render_template("client_edit.html", client=row)

    # POST
    name            = (request.form.get("name") or "").strip()
    tax_id          = (request.form.get("tax_id") or "").strip() or None
    email           = (request.form.get("email") or "").strip() or None
    phone           = (request.form.get("phone") or "").strip() or None
    organization_id = (request.form.get("organization_id") or "").strip() or None
    is_eventual     = True if request.form.get("is_eventual") == "1" else False

    billing_address = {
        "street":  (request.form.get("street")  or "").strip(),
        "city":    (request.form.get("city")    or "").strip(),
        "state":   (request.form.get("state")   or "").strip(),
        "zip":     (request.form.get("zip")     or "").strip(),
        "country": (request.form.get("country") or "").strip(),
    }
    if not any(billing_address.values()):
        billing_address = None

    if not name:
        flash("El nombre del cliente es obligatorio.", "error")
        return render_template("client_edit.html", client=row)

    try:
        sb.table("clients").update({
            "name": name,
            "tax_id": tax_id,
            "email": email,
            "phone": phone,
            "billing_address": billing_address,
            "organization_id": organization_id,
            "is_eventual": is_eventual
        }).eq("id", client_id).execute()

        flash("Cliente actualizado.", "success")
        return redirect(url_for("clients"))
    except Exception as e:
        msg = getattr(e, "message", str(e))
        if "clients_tax_id_uniq" in msg:
            flash("El RTN/Tax ID ya existe para otro cliente.", "error")
        elif "clients_email_chk" in msg:
            flash("El correo no tiene un formato válido.", "error")
        elif "clients_phone_chk" in msg:
            flash("El teléfono no tiene un formato válido.", "error")
        else:
            flash(f"No se pudo actualizar: {msg}", "error")
        return render_template("client_edit.html", client=row)

# =========================
# BORRAR CLIENTE (bloquea si hay dependencias con RESTRICT)
# =========================
@app.post("/clients/<client_id>/delete", endpoint="client_delete")
def client_delete(client_id):
    sb = get_service_client()

    # Bloquear si hay eventos
    try:
        ev_count = sb.table("events").select("id", count="exact").eq("client_id", client_id).execute().count or 0
        if ev_count > 0:
            flash(f"No se puede eliminar: hay {ev_count} evento(s) asociados a este cliente.", "error")
            return redirect(url_for("clients"))
    except Exception:
        pass

    # Bloquear si hay cotizaciones
    try:
        q_count = sb.table("quotations").select("id", count="exact").eq("client_id", client_id).execute().count or 0
        if q_count > 0:
            flash(f"No se puede eliminar: hay {q_count} cotización(es) asociadas a este cliente.", "error")
            return redirect(url_for("clients"))
    except Exception:
        pass

    # Contacts se borran por cascade, así que no bloquean
    try:
        sb.table("clients").delete().eq("id", client_id).execute()
        flash("Cliente eliminado.", "success")
    except Exception as e:
        flash(f"No se pudo eliminar: {getattr(e,'message',str(e))}", "error")

    return redirect(url_for("clients"))

# ---------- LISTAR ----------
@app.get("/users", endpoint="users")
def users_list():
    sb = get_service_client()

    # 1) perfiles
    prof = (
        sb.table("profiles")
          .select("id, full_name, phone, role, active, created_at, updated_at")
          .order("created_at")
          .execute()
    ).data or []

    # 2) emails desde auth (listado admin)
    email_by_id = {}
    try:
        # per_page alto para evitar paginar (ajusta si tienes >1k)
        lu = sb.auth.admin.list_users({"per_page": 1000})
        for u in lu.users:
            email_by_id[u.id] = u.email
    except Exception:
        pass

    # 3) fusionar
    users = []
    for p in prof:
        users.append({
            **p,
            "email": email_by_id.get(p["id"], None)
        })

    return render_template("users.html", users=users)

# ---------- CREAR ----------
@app.route("/users/add", methods=["GET","POST"], endpoint="user_add")
def user_add():
    sb = get_service_client()

    if request.method == "GET":
        return render_template("user_add.html", roles=sorted(USER_ROLES))

    full_name = (request.form.get("full_name") or "").strip()
    email     = (request.form.get("email") or "").strip()
    phone     = (request.form.get("phone") or "").strip()
    role      = (request.form.get("role") or "sales").strip()
    password  = request.form.get("password") or ""
    active    = True if request.form.get("active") == "1" else False

    if not email or not password:
        flash("Correo y contraseña son obligatorios.", "error")
        return render_template("user_add.html", roles=sorted(USER_ROLES))

    if role not in USER_ROLES:
        flash("Rol inválido.", "error")
        return render_template("user_add.html", roles=sorted(USER_ROLES))

    try:
        # 1) crear en auth.users
        created = sb.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name, "phone": phone}
        })
        uid = created.user.id

        # 2) actualizar profile (el trigger ya pudo crear uno)
        sb.table("profiles").upsert({
            "id": uid,
            "full_name": full_name,
            "phone": phone,
            "role": role,
            "active": active,
            "updated_at": datetime.utcnow().isoformat()
        }).execute()

        flash("Usuario creado.", "success")
        return redirect(url_for("users"))

    except Exception as e:
        flash(f"No se pudo crear el usuario: {getattr(e,'message',str(e))}", "error")
        return render_template("user_add.html", roles=sorted(USER_ROLES))

# ---------- EDITAR ----------
@app.route("/users/<user_id>/edit", methods=["GET","POST"], endpoint="user_edit")
def user_edit(user_id):
    sb = get_service_client()

    # cargar profile
    try:
        p = sb.table("profiles").select(
            "id, full_name, phone, role, active, created_at, updated_at"
        ).eq("id", user_id).single().execute().data
        if not p:
            flash("Perfil no encontrado.", "error")
            return redirect(url_for("users"))
    except Exception as e:
        flash(f"No se pudo cargar el perfil: {getattr(e,'message',str(e))}", "error")
        return redirect(url_for("users"))

    # cargar email desde auth
    email = None
    try:
        u = sb.auth.admin.get_user_by_id(user_id)
        email = getattr(u.user, "email", None)
    except Exception:
        pass

    if request.method == "GET":
        return render_template("user_edit.html", user={**p, "email": email}, roles=sorted(USER_ROLES))

    # POST
    full_name = (request.form.get("full_name") or "").strip()
    new_email = (request.form.get("email") or "").strip()
    phone     = (request.form.get("phone") or "").strip()
    role      = (request.form.get("role") or "").strip()
    active    = True if request.form.get("active") == "1" else False

    new_password = request.form.get("new_password") or ""   # opcional

    if role not in USER_ROLES:
        flash("Rol inválido.", "error")
        return render_template("user_edit.html", user={**p, "email": email}, roles=sorted(USER_ROLES))

    try:
        # 1) actualizar profile
        sb.table("profiles").update({
            "full_name": full_name or None,
            "phone": phone or None,
            "role": role,
            "active": active,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()

        # 2) actualizar email/contraseña si cambiaron
        upd_payload = {}
        if new_email and new_email != email:
            upd_payload["email"] = new_email
            upd_payload["email_confirm"] = True
        if new_password:
            upd_payload["password"] = new_password
        if upd_payload:
            sb.auth.admin.update_user_by_id(user_id, upd_payload)

        flash("Usuario actualizado.", "success")
        return redirect(url_for("users"))
    except Exception as e:
        flash(f"No se pudo actualizar: {getattr(e,'message',str(e))}", "error")
        return render_template("user_edit.html", user={**p, "email": email}, roles=sorted(USER_ROLES))

# ---------- ACTIVAR / DESACTIVAR (perfil) ----------
@app.post("/users/<user_id>/deactivate", endpoint="user_deactivate")
def user_deactivate(user_id):
    sb = get_service_client()
    try:
        sb.table("profiles").update({"active": False, "updated_at": datetime.utcnow().isoformat()}).eq("id", user_id).execute()
        flash("Usuario desactivado (perfil).", "success")
    except Exception as e:
        flash(f"No se pudo desactivar: {getattr(e,'message',str(e))}", "error")
    return redirect(url_for("users"))

@app.post("/users/<user_id>/activate", endpoint="user_activate")
def user_activate(user_id):
    sb = get_service_client()
    try:
        sb.table("profiles").update({"active": True, "updated_at": datetime.utcnow().isoformat()}).eq("id", user_id).execute()
        flash("Usuario activado (perfil).", "success")
    except Exception as e:
        flash(f"No se pudo activar: {getattr(e,'message',str(e))}", "error")
    return redirect(url_for("users"))

# (Opcional) también podrías "banear" vía auth si quieres bloquear login a nivel de auth.
# En versiones recientes existe ban_duration; si no, puedes usar app_metadata/claims.


# ---------- ELIMINAR ----------
@app.post("/users/<user_id>/delete", endpoint="user_delete")
def user_delete(user_id):
    sb = get_service_client()
    try:
        # Eliminar en auth elimina el profile por FK ON DELETE CASCADE
        sb.auth.admin.delete_user(user_id)
        flash("Usuario eliminado.", "success")
    except Exception as e:
        flash(f"No se pudo eliminar: {getattr(e,'message',str(e))}", "error")
    return redirect(url_for("users"))

@app.get("/quotations", endpoint="quotations")
def quotations_list():
    sb = get_service_client()
    rows = sb.table("quotations").select(
        "id, quote_number, client_id, contact_id, event_id, owner_id, currency, status, total, created_at, valid_until"
    ).order("created_at", desc=True).limit(500).execute().data or []

    # Carga nombres auxiliares (clientes / contactos / eventos / owner)
    # (Opcional) puedes hacer joins en SQL, aquí lo hago simple con dict
    names = {"clients":{}, "contacts":{}, "events":{}, "profiles":{}}
    try:
        cli = sb.table("clients").select("id,name").execute().data or []
        con = sb.table("contacts").select("id,name").execute().data or []
        ev  = sb.table("events").select("id,name").execute().data or []
        own = sb.table("profiles").select("id,full_name").execute().data or []
        names["clients"]  = {x["id"]: x["name"] for x in cli}
        names["contacts"] = {x["id"]: x["name"] for x in con}
        names["events"]   = {x["id"]: x["name"] for x in ev}
        names["profiles"] = {x["id"]: x["full_name"] for x in own}
    except Exception:
        pass

    return render_template("quotations.html", quotations=rows, names=names)

@app.route("/quotations/add", methods=["GET","POST"], endpoint="quotation_add")
def quotation_add():
    sb = get_service_client()

    # Catálogos
    clients  = sb.table("clients").select("id,name").order("name").execute().data or []
    contacts = sb.table("contacts").select("id,client_id,name").order("name").execute().data or []
    events   = sb.table("events").select("id,name,client_id,start_at,end_at").order("start_at", desc=True).limit(200).execute().data or []
    owners   = sb.table("profiles").select("id,full_name").order("full_name").execute().data or []
    items    = sb.table("items").select("id,sku,name,item_type,unit,default_rate,tax_rate").eq("active", True).order("name").execute().data or []

    if request.method == "GET":
        return render_template(
            "quotation_add.html",
            clients=clients, contacts=contacts, events=events, owners=owners,
            items=items, default_currency=QUOTE_CURRENCY
        )

    # ------- POST: cabecera -------
    client_id  = (request.form.get("client_id")  or "").strip()
    contact_id = (request.form.get("contact_id") or "").strip() or None
    event_id   = (request.form.get("event_id")   or "").strip() or None
    owner_id   = (request.form.get("owner_id")   or "").strip()
    currency   = (request.form.get("currency")   or QUOTE_CURRENCY).strip()[:3].upper()

    try:
        exchange = float(request.form.get("exchange_rate") or 1.0)
    except Exception:
        exchange = 1.0

    valid_u   = (request.form.get("valid_until") or "").strip() or None
    notes_int = (request.form.get("notes_internal") or "").strip() or None
    notes_cli = (request.form.get("notes_client") or "").strip() or None
    terms     = (request.form.get("terms") or "").strip() or None
    try:
        deposit = float(request.form.get("deposit_due") or 0.0)
    except Exception:
        deposit = 0.0

    if not client_id or not owner_id:
        flash("Cliente y Propietario son obligatorios.", "error")
        return render_template(
            "quotation_add.html",
            clients=clients, contacts=contacts, events=events, owners=owners,
            items=items, default_currency=QUOTE_CURRENCY
        )

    # Generar número
    quote_no = gen_quote_number(sb)

    try:
        # 1) Crear cabecera
        resp = sb.table("quotations").insert({
            "quote_number": quote_no,
            "client_id": client_id,
            "contact_id": contact_id,
            "event_id": event_id,
            "owner_id": owner_id,
            "currency": currency,
            "exchange_rate": exchange,
            "status": "draft",
            "valid_until": valid_u,
            "notes_internal": notes_int,
            "notes_client": notes_cli,
            "terms": terms,
            "deposit_due": deposit,
            "subtotal": 0.0, "discount_total": 0.0, "tax_total": 0.0, "total": 0.0
        }, returning="representation").execute()

        qid = resp.data[0]["id"]

        # 2) Primera revisión
        sb.table("quotation_revisions").insert({
            "quotation_id": qid, "version": 1, "created_by": owner_id, "comment": "Creación de cotización"
        }).execute()

        # 3) Estado inicial en historial
        sb.table("quotation_status_history").insert({
            "quotation_id": qid, "old_status": None, "new_status": "draft",
            "changed_by": owner_id, "note": "Creada en borrador"
        }).execute()

        # ------- POST: líneas (productos) -------
        # Arrays del formulario
        item_ids       = request.form.getlist("item_id[]")
        quantities     = request.form.getlist("quantity[]")
        discounts      = request.form.getlist("discount_pct[]")
        sections       = request.form.getlist("section[]")
        line_descs     = request.form.getlist("line_description[]")
        unit_prices    = request.form.getlist("unit_price[]")  # NUEVO
        tax_rates      = request.form.getlist("tax_rate[]")     # NUEVO

        # Normaliza filas válidas (usa None para precio/impuesto vacíos → snapshot)
        raw_rows = []
        for idx, iid in enumerate(item_ids):
            iid = (iid or "").strip()
            if not iid:
                continue

            # cantidad
            try:
                qty = float(quantities[idx]) if idx < len(quantities) and quantities[idx] not in (None, "") else 1.0
            except Exception:
                qty = 1.0
            if qty <= 0:
                continue

            # descuento
            try:
                disc = float(discounts[idx]) if idx < len(discounts) and discounts[idx] not in (None, "") else 0.0
            except Exception:
                disc = 0.0
            if disc < 0:
                disc = 0.0

            # precio custom (puede venir vacío → None)
            up_val = unit_prices[idx] if idx < len(unit_prices) else ""
            try:
                up_custom = float(up_val) if str(up_val).strip() != "" else None
            except Exception:
                up_custom = None
            if up_custom is not None and up_custom < 0:
                flash("El precio no puede ser negativo. Se usará el precio del ítem.", "warning")
                up_custom = None

            # impuesto custom (puede venir vacío → None)
            tr_val = tax_rates[idx] if idx < len(tax_rates) else ""
            try:
                tr_custom = float(tr_val) if str(tr_val).strip() != "" else None
            except Exception:
                tr_custom = None
            if tr_custom is not None:
                if tr_custom < 0 or tr_custom > 100:
                    flash("El impuesto debe estar entre 0 y 100. Se usará el impuesto del ítem.", "warning")
                    tr_custom = None

            sect = (sections[idx] if idx < len(sections) else "") or ""
            desc = (line_descs[idx] if idx < len(line_descs) else "") or ""

            raw_rows.append({
                "item_id": iid,
                "qty": qty,
                "disc": disc,
                "sect": (sect.strip() or None),
                "desc": (desc.strip() or None),
                "unit_price": up_custom,   # puede ser None → snapshot
                "tax_rate": tr_custom      # puede ser None → snapshot
            })

        if raw_rows:
            # Snapshot de ítems
            unique_ids = sorted({r["item_id"] for r in raw_rows})
            meta = {}
            if unique_ids:
                meta_rows = (
                    sb.table("items")
                      .select("id,name,item_type,unit,default_rate,tax_rate")
                      .in_("id", unique_ids).execute().data or []
                )
                meta = {m["id"]: m for m in meta_rows}

            # Inserción batch con mezcla (custom o snapshot)
            to_insert = []
            sort_order = 1
            for r in raw_rows:
                it = meta.get(r["item_id"])
                if not it:
                    continue

                unit_price = r["unit_price"] if r["unit_price"] is not None else float(it["default_rate"])
                tax_rate   = r["tax_rate"]   if r["tax_rate"]   is not None else float(it["tax_rate"])

                to_insert.append({
                    "quotation_id": qid,
                    "item_id": r["item_id"],
                    "custom_name": it["name"],
                    "description": r["desc"],
                    "section": r["sect"],
                    "item_type": it["item_type"],
                    "quantity": r["qty"],
                    "unit": it.get("unit") or "unit",
                    "unit_price": unit_price,     # ← usa custom si vino
                    "discount_pct": r["disc"],
                    "tax_rate": tax_rate,         # ← usa custom si vino
                    "sort_order": sort_order
                })
                sort_order += 1

            if to_insert:
                sb.table("quotation_items").insert(to_insert).execute()
                # Recalcular totales de cabecera
                recompute_totals(sb, qid)

        flash(f"Cotización {quote_no} creada.", "success")
        return redirect(url_for("quotation_edit", quotation_id=qid))

    except Exception as e:
        flash(f"No se pudo crear: {getattr(e,'message',str(e))}", "error")
        return render_template(
            "quotation_add.html",
            clients=clients, contacts=contacts, events=events, owners=owners,
            items=items, default_currency=QUOTE_CURRENCY
        )

@app.route("/quotations/<quotation_id>/edit", methods=["GET","POST"], endpoint="quotation_edit")
def quotation_edit(quotation_id):
    sb = get_service_client()

    # Cargar cabecera
    q = sb.table("quotations").select("*").eq("id", quotation_id).single().execute().data
    if not q:
        flash("Cotización no encontrada.", "error")
        return redirect(url_for("quotations"))

    # Catálogos
    clients  = sb.table("clients").select("id,name").order("name").execute().data or []
    contacts = sb.table("contacts").select("id,client_id,name").order("name").execute().data or []
    events   = sb.table("events").select("id,name,client_id,start_at,end_at").order("start_at", desc=True).limit(200).execute().data or []
    owners   = sb.table("profiles").select("id,full_name").order("full_name").execute().data or []
    items    = sb.table("items").select("id,sku,name,item_type,default_rate,tax_rate,active").eq("active", True).order("name").execute().data or []
    
    # Líneas
    lines = sb.table("quotation_items").select(
        "id, item_id, custom_name, description, section, item_type, quantity, unit, unit_price, discount_pct, tax_rate, line_subtotal, line_tax, line_total, sort_order"
    ).eq("quotation_id", quotation_id).order("sort_order").execute().data or []

    print("--------------------------00 bandera    -------------------------")
    print(q)
    if request.method == "GET":
        return render_template(
            "quotation_edit.html",
            q         = q,
            lines     = lines,
            clients   = clients,
            contacts  = contacts,
            events    = events,
            owners    = owners,
            items     = items
        )
    
    print("--------------------------0 bandera    -------------------------")
    # POST (update cabecera o agregar línea)
    if request.form.get("action") == "add_line":
        # Agregar línea rápida desde selector
        item_id = (request.form.get("item_id") or "").strip()
        qty     = float(request.form.get("quantity") or 1)
        disc    = float(request.form.get("discount_pct") or 0.0)
        section = (request.form.get("section") or "").strip() or None
        desc    = (request.form.get("line_description") or "").strip() or None

        if not item_id:
            flash("Selecciona un ítem.", "error")
            return redirect(url_for("quotation_edit", quotation_id=quotation_id))

        it = sb.table("items").select("id,name,item_type,unit,default_rate,tax_rate").eq("id", item_id).single().execute().data
        if not it:
            flash("Ítem no válido.", "error")
            return redirect(url_for("quotation_edit", quotation_id=quotation_id))

        sb.table("quotation_items").insert({
            "quotation_id": quotation_id,
            "item_id": item_id,
            "custom_name": it["name"],
            "description": desc,
            "section": section,
            "item_type": it["item_type"],
            "quantity": qty,
            "unit": it.get("unit") or "unit",
            "unit_price": it["default_rate"],
            "discount_pct": disc,
            "tax_rate": it["tax_rate"],
            "sort_order": (len(lines) + 1)
        }).execute()

        # Recalcular totales
        recompute_totals(sb, quotation_id)
        flash("Línea agregada.", "success")
        return redirect(url_for("quotation_edit", quotation_id=quotation_id))

    print("--------------------------primera bandera    -------------------------")
    # Actualizar cabecera
    upd = {
        "client_id":  (request.form.get("client_id")  or "").strip() or q["client_id"],
        "contact_id": (request.form.get("contact_id") or "").strip() or None,
        "event_id":   (request.form.get("event_id")   or "").strip() or None,
        "owner_id":   (request.form.get("owner_id")   or q["owner_id"]).strip(),
        "currency":   (request.form.get("currency")   or q["currency"]).strip()[:3].upper(),
        "exchange_rate": float(request.form.get("exchange_rate") or q["exchange_rate"] or 1.0),
        "valid_until": (request.form.get("valid_until") or None),
        "notes_internal": (request.form.get("notes_internal") or None),
        "notes_client":   (request.form.get("notes_client") or None),
        "terms":          (request.form.get("terms") or None),
        "deposit_due":    float(request.form.get("deposit_due") or q["deposit_due"] or 0.0),
        "updated_at": datetime.utcnow().isoformat()
    }

    print(upd)
    try:
        sb.table("quotations").update(upd).eq("id", quotation_id).execute()
        flash("Cabecera actualizada.", "success")
    except Exception as e:
        flash(f"No se pudo actualizar: {getattr(e,'message',str(e))}", "error")

    return redirect(url_for("quotation_edit", quotation_id=quotation_id))

@app.post("/quotations/<quotation_id>/lines/<line_id>/update", endpoint="quotation_line_update")
def quotation_line_update(quotation_id, line_id):
    sb = get_service_client()
    # Campos editables en línea
    qty   = float(request.form.get("quantity") or 1)
    price = float(request.form.get("unit_price") or 0)
    disc  = float(request.form.get("discount_pct") or 0)
    tax   = float(request.form.get("tax_rate") or 0)
    name  = (request.form.get("custom_name") or "").strip() or None
    desc  = (request.form.get("description") or "").strip() or None
    unit  = (request.form.get("unit") or "unit").strip()
    sect  = (request.form.get("section") or "").strip() or None

    try:
        sb.table("quotation_items").update({
            "custom_name": name,
            "description": desc,
            "section": sect,
            "quantity": qty,
            "unit": unit,
            "unit_price": price,
            "discount_pct": disc,
            "tax_rate": tax
        }).eq("id", line_id).eq("quotation_id", quotation_id).execute()

        recompute_totals(sb, quotation_id)
        flash("Línea actualizada.", "success")
    except Exception as e:
        flash(f"No se pudo actualizar la línea: {getattr(e,'message',str(e))}", "error")

    return redirect(url_for("quotation_edit", quotation_id=quotation_id))

@app.post("/quotations/<quotation_id>/lines/<line_id>/delete", endpoint="quotation_line_delete")
def quotation_line_delete(quotation_id, line_id):
    sb = get_service_client()
    try:
        sb.table("quotation_items").delete().eq("id", line_id).eq("quotation_id", quotation_id).execute()
        recompute_totals(sb, quotation_id)
        flash("Línea eliminada.", "success")
    except Exception as e:
        flash(f"No se pudo eliminar la línea: {getattr(e,'message',str(e))}", "error")

    return redirect(url_for("quotation_edit", quotation_id=quotation_id))

@app.post("/quotations/<quotation_id>/status", endpoint="quotation_set_status")
def quotation_set_status(quotation_id):
    sb = get_service_client()
    target = (request.form.get("status") or "").strip()
    actor  = (request.form.get("actor_id") or "").strip()  # el usuario que opera el cambio

    if target not in VALID_STATUSES:
        flash("Estado inválido.", "error")
        return redirect(url_for("quotation_edit", quotation_id=quotation_id))

    q = sb.table("quotations").select("id,status").eq("id", quotation_id).single().execute().data
    if not q:
        flash("Cotización no encontrada.", "error")
        return redirect(url_for("quotations"))

    old = q["status"]
    # Reglas simples de transición (ajústalas a tu flujo)
    allowed = {
        "draft": {"sent","cancelled"},
        "sent": {"accepted","declined","expired","cancelled"},
        "accepted": {"converted","cancelled"},
        "declined": set(),
        "expired": set(),
        "cancelled": set(),
        "converted": set()
    }
    if target not in allowed.get(old, set()):
        flash(f"No se puede pasar de {old} a {target}.", "error")
        return redirect(url_for("quotation_edit", quotation_id=quotation_id))

    # Campos de marca de tiempo según estado
    time_updates = {}
    now_iso = datetime.utcnow().isoformat()
    if target == "sent":
        time_updates["sent_at"] = now_iso
    if target == "accepted":
        time_updates["accepted_at"] = now_iso

    try:
        # 1) actualizar estado
        sb.table("quotations").update({
            "status": target,
            "updated_at": now_iso,
            **time_updates
        }).eq("id", quotation_id).execute()

        # 2) historial
        sb.table("quotation_status_history").insert({
            "quotation_id": quotation_id,
            "old_status": old,
            "new_status": target,
            "changed_by": actor or None,
            "note": request.form.get("note") or None
        }).execute()

        flash(f"Estado cambiado a {target}.", "success")
    except Exception as e:
        flash(f"No se pudo cambiar estado: {getattr(e,'message',str(e))}", "error")

    return redirect(url_for("quotation_edit", quotation_id=quotation_id))

@app.post("/quotations/<quotation_id>/delete", endpoint="quotation_delete")
def quotation_delete(quotation_id):
    sb = get_service_client()
    q = sb.table("quotations").select("status, quote_number").eq("id", quotation_id).single().execute().data
    if not q:
        flash("Cotización no encontrada.", "error")
        return redirect(url_for("quotations"))

    if q["status"] not in {"draft","cancelled"}:
        flash("Sólo se pueden eliminar cotizaciones en borrador o canceladas.", "error")
        return redirect(url_for("quotation_edit", quotation_id=quotation_id))

    try:
        # items y revisiones caen por ON DELETE CASCADE
        sb.table("quotations").delete().eq("id", quotation_id).execute()
        flash(f"Cotización {q['quote_number']} eliminada.", "success")
    except Exception as e:
        flash(f"No se pudo eliminar: {getattr(e,'message',str(e))}", "error")

    return redirect(url_for("quotations"))

# contacts_routes.py
from flask import render_template, request, redirect, url_for, flash
from datetime import datetime

@app.route("/contacts", methods=["GET"], endpoint="contacts")
def contacts():
    sb = get_service_client()

    # Catálogo de clientes para filtro y nombres
    clients = sb.table("clients").select("id,name").order("name").execute().data or []
    client_map = {c["id"]: c["name"] for c in clients}

    q        = (request.args.get("q") or "").strip()
    client_f = (request.args.get("client_id") or "").strip()

    qry = sb.table("contacts").select("id,client_id,name,email,phone,role,is_primary,created_at").order("created_at", desc=True)
    if q:
        # búsqueda simple por nombre/email/phone
        qry = qry.or_(f"name.ilike.%{q}%,email.ilike.%{q}%,phone.ilike.%{q}%")
    if client_f:
        qry = qry.eq("client_id", client_f)

    contacts = qry.execute().data or []

    # Enriquecer con nombre del cliente
    for c in contacts:
        c["client_name"] = client_map.get(c["client_id"], "—")

    return render_template("contacts_list.html", contacts=contacts, clients=clients, q=q, client_id=client_f)


@app.route("/contacts/add", methods=["GET","POST"], endpoint="contact_add")
def contact_add():
    sb = get_service_client()
    clients = sb.table("clients").select("id,name").order("name").execute().data or []

    if request.method == "GET":
        return render_template("contact_add.html", clients=clients)

    client_id = (request.form.get("client_id") or "").strip()
    name      = (request.form.get("name") or "").strip()
    email     = (request.form.get("email") or "").strip() or None
    phone     = (request.form.get("phone") or "").strip() or None
    role      = (request.form.get("role") or "").strip() or None
    is_primary = True if request.form.get("is_primary") == "1" else False

    if not client_id or not name:
        flash("Cliente y Nombre son obligatorios.", "error")
        return render_template("contact_add.html", clients=clients)

    try:
        # Si viene como principal, limpiar otros del mismo cliente
        if is_primary:
            sb.table("contacts").update({"is_primary": False}).eq("client_id", client_id).eq("is_primary", True).execute()

        sb.table("contacts").insert({
            "client_id": client_id,
            "name": name,
            "email": email,
            "phone": phone,
            "role": role,
            "is_primary": is_primary
        }).execute()

        flash("Contacto creado correctamente.", "success")
        return redirect(url_for("contacts"))

    except Exception as e:
        # Puede romper por unique (client_id,email) o validaciones de email/phone
        flash(f"No se pudo crear el contacto: {getattr(e,'message',str(e))}", "error")
        return render_template("contact_add.html", clients=clients)


@app.route("/contacts/<contact_id>/edit", methods=["GET","POST"], endpoint="contact_edit")
def contact_edit(contact_id):
    sb = get_service_client()
    clients = sb.table("clients").select("id,name").order("name").execute().data or []

    # leer contacto
    c = sb.table("contacts").select("*").eq("id", contact_id).single().execute().data
    if not c:
        flash("Contacto no encontrado.", "error")
        return redirect(url_for("contacts"))

    if request.method == "GET":
        return render_template("contact_edit.html", contact=c, clients=clients)

    # POST
    client_id = (request.form.get("client_id") or "").strip()
    name      = (request.form.get("name") or "").strip()
    email     = (request.form.get("email") or "").strip() or None
    phone     = (request.form.get("phone") or "").strip() or None
    role      = (request.form.get("role") or "").strip() or None
    is_primary = True if request.form.get("is_primary") == "1" else False

    if not client_id or not name:
        flash("Cliente y Nombre son obligatorios.", "error")
        return render_template("contact_edit.html", contact=c, clients=clients)

    try:
        if is_primary:
            # Asegurar único principal por cliente
            sb.table("contacts").update({"is_primary": False}).eq("client_id", client_id).eq("is_primary", True).neq("id", contact_id).execute()

        sb.table("contacts").update({
            "client_id": client_id,
            "name": name,
            "email": email,
            "phone": phone,
            "role": role,
            "is_primary": is_primary
        }).eq("id", contact_id).execute()

        flash("Contacto actualizado.", "success")
        return redirect(url_for("contacts"))

    except Exception as e:
        flash(f"No se pudo actualizar: {getattr(e,'message',str(e))}", "error")
        return render_template("contact_edit.html", contact=c, clients=clients)


@app.post("/contacts/<contact_id>/delete")
def contact_delete(contact_id):
    sb = get_service_client()
    try:
        sb.table("contacts").delete().eq("id", contact_id).execute()
        flash("Contacto eliminado.", "success")
    except Exception as e:
        flash(f"No se pudo eliminar: {getattr(e,'message',str(e))}", "error")
    return redirect(url_for("contacts"))

@app.post("/contacts/<contact_id>/set_primary")
def contact_set_primary(contact_id):
    sb = get_service_client()
    # obtener client_id del contacto
    c = sb.table("contacts").select("id,client_id").eq("id", contact_id).single().execute().data
    if not c:
        flash("Contacto no encontrado.", "error")
        return redirect(url_for("contacts"))
    client_id = c["client_id"]

    try:
        sb.table("contacts").update({"is_primary": False}).eq("client_id", client_id).eq("is_primary", True).execute()
        sb.table("contacts").update({"is_primary": True}).eq("id", contact_id).execute()
        flash("Contacto marcado como principal.", "success")
    except Exception as e:
        flash(f"No se pudo marcar como principal: {getattr(e,'message',str(e))}", "error")

    return redirect(url_for("contacts"))

def _parse_dt_local(s: str, tzname: str = TZ_DEFAULT):
    """
    Convierte 'YYYY-MM-DDTHH:MM' (input type=datetime-local) a ISO 8601 UTC.
    Si viene vacío, retorna None.
    """
    if not s:
        return None
    # asume naive local time, conviértelo a UTC ISO
    try:
        # '2025-10-26T18:30'
        naive = datetime.strptime(s, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    tz = pytz.timezone(tzname)
    aware_local = tz.localize(naive)
    aware_utc = aware_local.astimezone(pytz.UTC)
    return aware_utc.isoformat()

def _fmt_dt_local(iso_dt: str, tzname: str = TZ_DEFAULT):
    """
    Para precargar el <input type=datetime-local> en edición.
    Recibe ISO (UTC) y lo convierte a 'YYYY-MM-DDTHH:MM' en tz local.
    """
    if not iso_dt:
        return ""
    tz = pytz.timezone(tzname)
    try:
        # Supabase suele devolver con 'Z' → fromisoformat no siempre soporta 'Z'
        dt = datetime.fromisoformat(iso_dt.replace("Z", "+00:00"))
    except Exception:
        return ""
    local = dt.astimezone(tz)
    return local.strftime("%Y-%m-%dT%H:%M")

@app.route("/events", methods=["GET"], endpoint="events")
def events():
    sb = get_service_client()
    clients  = sb.table("clients").select("id,name").order("name").execute().data or []
    contacts = sb.table("contacts").select("id,client_id,name").order("name").execute().data or []

    client_id = (request.args.get("client_id") or "").strip()
    q         = (request.args.get("q") or "").strip()

    qry = (sb.table("events")
             .select("id,name,client_id,contact_id,venue,start_at,end_at,timezone,created_at")
             .order("start_at", desc=True))

    if client_id:
        qry = qry.eq("client_id", client_id)
    if q:
        # búsqueda simple por nombre/venue
        qry = qry.or_(f"name.ilike.%{q}%,venue.ilike.%{q}%")

    rows = qry.execute().data or []

    # Enriquecer: nombres de cliente y contacto
    client_map  = {c["id"]: c["name"] for c in clients}
    contact_map = {}
    if rows:
        # Trae contactos de los clientes visibles (para nombre rápido)
        cids = sorted({r["client_id"] for r in rows})
        contact_rows = sb.table("contacts").select("id,name").in_("id", [r["contact_id"] for r in rows if r.get("contact_id")]).execute().data or []
        contact_map = {c["id"]: c["name"] for c in contact_rows}

    for r in rows:
        r["client_name"]  = client_map.get(r["client_id"], "—")
        r["contact_name"] = contact_map.get(r.get("contact_id")) if r.get("contact_id") else "—"

    return render_template("events_list.html",
                           events=rows, clients=clients, contacts=contacts,
                           client_id=client_id, q=q)

@app.route("/events/add", methods=["GET","POST"], endpoint="event_add")
def event_add():
    sb = get_service_client()
    clients  = sb.table("clients").select("id,name").order("name").execute().data or []
    contacts = sb.table("contacts").select("id,client_id,name").order("name").execute().data or []
    owners   = sb.table("profiles").select("id,full_name").order("full_name").execute().data or []

    if request.method == "GET":
        return render_template("event_add.html",
                               clients=clients, contacts=contacts, owners=owners,
                               tz_default=TZ_DEFAULT)

    name      = (request.form.get("name") or "").strip()
    client_id = (request.form.get("client_id") or "").strip()
    contact_id= (request.form.get("contact_id") or "").strip() or None
    venue     = (request.form.get("venue") or "").strip() or None
    tzname    = (request.form.get("timezone") or TZ_DEFAULT).strip() or TZ_DEFAULT
    created_by= (request.form.get("created_by") or "").strip() or None

    start_local = (request.form.get("start_at") or "").strip()  # 'YYYY-MM-DDTHH:MM'
    end_local   = (request.form.get("end_at") or "").strip()

    build_local = (request.form.get("build_start_at") or "").strip()
    strike_local= (request.form.get("strike_end_at") or "").strip()

    if not name or not client_id or not start_local or not end_local:
        flash("Nombre, Cliente, Inicio y Fin son obligatorios.", "error")
        return render_template("event_add.html",
                               clients=clients, contacts=contacts, owners=owners,
                               tz_default=TZ_DEFAULT)

    # Validación: contacto pertenece al cliente (si viene)
    if contact_id:
        count = (sb.table("contacts").select("id", count="exact")
                 .eq("id", contact_id).eq("client_id", client_id)
                 .execute().count or 0)
        if count == 0:
            flash("El contacto no pertenece al cliente seleccionado.", "error")
            return render_template("event_add.html",
                                   clients=clients, contacts=contacts, owners=owners,
                                   tz_default=TZ_DEFAULT)

    start_iso  = _parse_dt_local(start_local, tzname)
    end_iso    = _parse_dt_local(end_local, tzname)
    build_iso  = _parse_dt_local(build_local, tzname) if build_local else None
    strike_iso = _parse_dt_local(strike_local, tzname) if strike_local else None

    if not start_iso or not end_iso:
        flash("Fechas inválidas.", "error")
        return render_template("event_add.html",
                               clients=clients, contacts=contacts, owners=owners,
                               tz_default=TZ_DEFAULT)

    if end_iso <= start_iso:
        flash("La fecha/hora de fin debe ser mayor al inicio.", "error")
        return render_template("event_add.html",
                               clients=clients, contacts=contacts, owners=owners,
                               tz_default=TZ_DEFAULT)

    try:
        sb.table("events").insert({
            "name": name,
            "client_id": client_id,
            "contact_id": contact_id,
            "venue": venue,
            "start_at": start_iso,
            "end_at": end_iso,
            "timezone": tzname,
            "notes": (request.form.get("notes") or "").strip() or None,
            "created_by": created_by or None,
            "build_start_at": build_iso,
            "strike_end_at": strike_iso
        }).execute()

        flash("Evento creado correctamente.", "success")
        return redirect(url_for("events"))

    except Exception as e:
        flash(f"No se pudo crear el evento: {getattr(e,'message',str(e))}", "error")
        return render_template("event_add.html",
                               clients=clients, contacts=contacts, owners=owners,
                               tz_default=TZ_DEFAULT)

@app.route("/events/<event_id>/edit", methods=["GET","POST"], endpoint="event_edit")
def event_edit(event_id):
    sb = get_service_client()
    clients  = sb.table("clients").select("id,name").order("name").execute().data or []
    contacts = sb.table("contacts").select("id,client_id,name").order("name").execute().data or []
    owners   = sb.table("profiles").select("id,full_name").order("full_name").execute().data or []

    ev = sb.table("events").select("*").eq("id", event_id).single().execute().data
    if not ev:
        flash("Evento no encontrado.", "error")
        return redirect(url_for("events"))

    if request.method == "GET":
        # Pre-formatear datetime-local
        start_local  = _fmt_dt_local(ev.get("start_at"),  ev.get("timezone") or TZ_DEFAULT)
        end_local    = _fmt_dt_local(ev.get("end_at"),    ev.get("timezone") or TZ_DEFAULT)
        build_local  = _fmt_dt_local(ev.get("build_start_at"), ev.get("timezone") or TZ_DEFAULT) if ev.get("build_start_at") else ""
        strike_local = _fmt_dt_local(ev.get("strike_end_at"),  ev.get("timezone") or TZ_DEFAULT) if ev.get("strike_end_at") else ""

        return render_template("event_edit.html",
                               event=ev, clients=clients, contacts=contacts, owners=owners,
                               start_local=start_local, end_local=end_local,
                               build_local=build_local, strike_local=strike_local,
                               tz_default=(ev.get("timezone") or TZ_DEFAULT))

    # POST
    name      = (request.form.get("name") or "").strip()
    client_id = (request.form.get("client_id") or "").strip()
    contact_id= (request.form.get("contact_id") or "").strip() or None
    venue     = (request.form.get("venue") or "").strip() or None
    tzname    = (request.form.get("timezone") or TZ_DEFAULT).strip() or TZ_DEFAULT

    start_local = (request.form.get("start_at") or "").strip()
    end_local   = (request.form.get("end_at") or "").strip()
    build_local = (request.form.get("build_start_at") or "").strip()
    strike_local= (request.form.get("strike_end_at") or "").strip()

    if not name or not client_id or not start_local or not end_local:
        flash("Nombre, Cliente, Inicio y Fin son obligatorios.", "error")
        return redirect(url_for("event_edit", event_id=event_id))

    if contact_id:
        count = (sb.table("contacts").select("id", count="exact")
                 .eq("id", contact_id).eq("client_id", client_id)
                 .execute().count or 0)
        if count == 0:
            flash("El contacto no pertenece al cliente seleccionado.", "error")
            return redirect(url_for("event_edit", event_id=event_id))

    start_iso  = _parse_dt_local(start_local, tzname)
    end_iso    = _parse_dt_local(end_local, tzname)
    build_iso  = _parse_dt_local(build_local, tzname) if build_local else None
    strike_iso = _parse_dt_local(strike_local, tzname) if strike_local else None

    if not start_iso or not end_iso or end_iso <= start_iso:
        flash("Rango de fechas inválido.", "error")
        return redirect(url_for("event_edit", event_id=event_id))

    try:
        sb.table("events").update({
            "name": name,
            "client_id": client_id,
            "contact_id": contact_id,
            "venue": venue,
            "start_at": start_iso,
            "end_at": end_iso,
            "timezone": tzname,
            "notes": (request.form.get("notes") or "").strip() or None,
            "build_start_at": build_iso,
            "strike_end_at": strike_iso
        }).eq("id", event_id).execute()

        flash("Evento actualizado.", "success")
        return redirect(url_for("events"))

    except Exception as e:
        flash(f"No se pudo actualizar: {getattr(e,'message',str(e))}", "error")
        return redirect(url_for("event_edit", event_id=event_id))

@app.post("/events/<event_id>/delete")
def event_delete(event_id):
    sb = get_service_client()
    try:
        sb.table("events").delete().eq("id", event_id).execute()
        flash("Evento eliminado.", "success")
    except Exception as e:
        flash(f"No se pudo eliminar: {getattr(e,'message',str(e))}", "error")
    return redirect(url_for("events"))

def _parse_dt_local(s: str, tzname: str = TZ_DEFAULT):
    if not s:
        return None
    try:
        naive = datetime.strptime(s, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    tz = pytz.timezone(tzname)
    aware_local = tz.localize(naive)
    return aware_local.astimezone(pytz.UTC).isoformat()

@app.route("/quotations/<quotation_id>/event/new",
           methods=["GET","POST"],
           endpoint="quote_event_new")
def quote_event_new(quotation_id):
    sb = get_service_client()

    # Traer cotización con lo necesario
    q = (sb.table("quotations")
            .select("id,quote_number,client_id,contact_id,event_id")
            .eq("id", quotation_id).single().execute().data)
    if not q:
        flash("Cotización no encontrada.", "error")
        return redirect(url_for("quotations"))

    # Si ya tiene evento, redirige a editar
    if q.get("event_id"):
        flash("La cotización ya tiene un evento vinculado.", "info")
        return redirect(url_for("event_edit", event_id=q["event_id"]))

    # Catálogos limitados al cliente de la cotización
    # Cliente
    client = (sb.table("clients").select("id,name")
                 .eq("id", q["client_id"]).single().execute().data)
    if not client:
        flash("Cliente de la cotización no existe.", "error")
        return redirect(url_for("quotation_edit", quotation_id=quotation_id))

    # Contactos SOLO de este cliente
    contacts = (sb.table("contacts")
                  .select("id,client_id,name")
                  .eq("client_id", q["client_id"])
                  .order("is_primary", desc=True)
                  .order("name")
                  .execute().data or [])

    # Owners para “creado por”
    owners = (sb.table("profiles")
                .select("id,full_name")
                .order("full_name")
                .execute().data or [])

    if request.method == "GET":
        # Sugerencias
        suggested_name = f"Evento — {q['quote_number']}"
        return render_template(
            "event_from_quote.html",
            quotation=q,
            client=client,
            contacts=contacts,
            owners=owners,
            suggested_name=suggested_name,
            tz_default=TZ_DEFAULT
        )

    # POST — crear evento y vincular a la cotización
    name       = (request.form.get("name") or "").strip()
    contact_id = (request.form.get("contact_id") or "").strip() or None
    venue      = (request.form.get("venue") or "").strip() or None
    tzname     = (request.form.get("timezone") or TZ_DEFAULT).strip() or TZ_DEFAULT
    created_by = (request.form.get("created_by") or "").strip() or None

    start_local = (request.form.get("start_at") or "").strip()
    end_local   = (request.form.get("end_at") or "").strip()
    build_local = (request.form.get("build_start_at") or "").strip()
    strike_local= (request.form.get("strike_end_at") or "").strip()

    if not name or not start_local or not end_local:
        flash("Nombre, Inicio y Fin son obligatorios.", "error")
        return redirect(url_for("quote_event_new", quotation_id=quotation_id))

    # Valida que el contacto (si viene) sea del cliente de la cotización
    if contact_id:
        cnt = (sb.table("contacts").select("id", count="exact")
                 .eq("id", contact_id).eq("client_id", q["client_id"])
                 .execute().count or 0)
        if cnt == 0:
            flash("El contacto seleccionado no pertenece al cliente de la cotización.", "error")
            return redirect(url_for("quote_event_new", quotation_id=quotation_id))

    start_iso  = _parse_dt_local(start_local, tzname)
    end_iso    = _parse_dt_local(end_local, tzname)
    build_iso  = _parse_dt_local(build_local, tzname) if build_local else None
    strike_iso = _parse_dt_local(strike_local, tzname) if strike_local else None

    if not start_iso or not end_iso or end_iso <= start_iso:
        flash("Rango de fechas inválido.", "error")
        return redirect(url_for("quote_event_new", quotation_id=quotation_id))

    try:
        # Crear evento
        ins = (sb.table("events").insert({
            "name": name,
            "client_id": q["client_id"],
            "contact_id": contact_id,
            "venue": venue,
            "start_at": start_iso,
            "end_at": end_iso,
            "timezone": tzname,
            "created_by": created_by or None,
            "notes": (request.form.get("notes") or "").strip() or None,
            "build_start_at": build_iso,
            "strike_end_at": strike_iso
        }).select("id").single().execute())
        event_id = ins.data["id"]

        # Vincular en la cotización
        sb.table("quotations").update({"event_id": event_id}).eq("id", quotation_id).execute()

        flash("Evento creado y vinculado a la cotización.", "success")
        # Regresa a editar la cotización (o a editar el evento si prefieres)
        return redirect(url_for("quotation_edit", quotation_id=quotation_id))

    except Exception as e:
        flash(f"No se pudo crear el evento: {getattr(e,'message',str(e))}", "error")
        return redirect(url_for("quote_event_new", quotation_id=quotation_id))

def _now_utc_iso():
    return datetime.now(TZ_DEFAULT.utc).isoformat()

def _fetch_quote_core(sb, quotation_id):
    """Trae cabecera + evento (fechas) y valida precondiciones básicas."""
    q = (sb.table("quotations")
           .select("id,quote_number,status,event_id,client_id")
           .eq("id", quotation_id).single().execute().data)
    if not q:
        raise ValueError("Cotización no encontrada.")

    if q["status"] == "accepted":
        raise ValueError("La cotización ya está aceptada.")

    if not q.get("event_id"):
        raise ValueError("La cotización no tiene evento vinculado.")

    ev = (sb.table("events")
            .select("id,name,start_at,end_at,timezone")
            .eq("id", q["event_id"]).single().execute().data)
    if not ev:
        raise ValueError("El evento vinculado no existe.")

    # Fechas válidas
    start_at = ev.get("start_at")
    end_at   = ev.get("end_at")
    if not start_at or not end_at:
        raise ValueError("El evento no tiene fechas de inicio/fin válidas.")
    return q, ev

def _fetch_quote_lines_with_items(sb, quotation_id):
    """Trae líneas con snapshot y metadatos del ítem."""
    rows = (sb.table("quotation_items")
              .select("id, item_id, item_type, quantity, unit, unit_price, tax_rate, discount_pct, start_at, end_at, section")
              .eq("quotation_id", quotation_id)
              .order("sort_order").execute().data or [])
    if not rows:
        raise ValueError("La cotización no tiene líneas.")
    # Map items meta
    item_ids = sorted({r["item_id"] for r in rows if r.get("item_id")})
    meta = {}
    if item_ids:
        meta_rows = (sb.table("items")
                       .select("id,item_type,default_rate,tax_rate,unit,active,rentable_capacity")
                       .in_("id", item_ids).execute().data or [])
        meta = {m["id"]: m for m in meta_rows}
    return rows, meta

def _expand_bundle_components(sb, bundle_ids):
    """
    Retorna dict bundle_id -> lista de componentes [{item_id, quantity}]
    Solo usa public.bundle_items. No trae metadatos del ítem componente.
    """
    if not bundle_ids:
        return {}
    comps = (sb.table("bundle_items")
               .select("bundle_id,item_id,quantity")
               .in_("bundle_id", sorted(bundle_ids)).execute().data or [])
    out = {}
    for c in comps:
        out.setdefault(c["bundle_id"], []).append({"item_id": c["item_id"], "quantity": float(c["quantity"])})
    return out

def _compute_item_capacity(sb, item_id, fallback_assets=True):
    """
    Capacidad (=unidades disponibles en paralelo) para ítems rentables.
    Usa items.rentable_capacity si está definido; si es nulo, cuenta assets activos.
    """
    it = (sb.table("items").select("rentable_capacity").eq("id", item_id).single().execute().data)
    cap = it.get("rentable_capacity") if it else None
    if cap is not None:
        try:
            return int(cap)
        except Exception:
            pass
    if not fallback_assets:
        return 0
    # contar assets activos
    cnt = (sb.table("assets").select("id", count="exact").eq("item_id", item_id).eq("active", True).execute().count) or 0
    return int(cnt)

def _sum_overlapping_reserved(sb, item_id, start_iso, end_iso):
    """
    Suma de quantity ya reservada en traslapes para item_id, considerando estados (tentative, firm).
    Usa period overlap: [start, end).
    """
    # Filtra traslapes en el servidor (Supabase) con operadores de rango
    # Como no podemos usar operadores PG nativos en REST igualitos, hacemos filtro aproximado:
    # overlap si NOT( end <= start_new OR start >= end_new )
    rows = (sb.table("reservations")
              .select("id,quantity,start_at,end_at,status")
              .eq("item_id", item_id)
              .in_("status", ["tentative","firm"])
              .lte("end_at", end_iso)  # <= end_new (aprox)
              .gte("start_at", start_iso)  # >= start_new (aprox)
              .execute().data or [])
    # Lo anterior es una aproximación; opcionalmente traer por ventana y filtrar en app:
    total = 0
    for r in rows:
        s = r.get("start_at"); e = r.get("end_at")
        if not s or not e:
            continue
        # Chequeo exacto en app: overlap si s < end_new y e > start_new (con [start,end) semicl.)
        if s < end_iso and e > start_iso:
            total += int(r.get("quantity") or 0)
    return total

def _build_needed_reservations(sb, q_lines, items_meta, event, quotation_id):
    """
    Convierte líneas en 'necesidades de reserva' por item rentable:
      - Si la línea trae start/end, usa esos; de lo contrario, usa las fechas del evento.
      - Para bundles, multiplica las cantidades por sus componentes rentables.
    """
    start_ev = event["start_at"]; end_ev = event["end_at"]
    # 1) agrupar necesidades
    needs = []  # [{item_id, quantity, start_at, end_at}]
    bundles = [r for r in q_lines if r["item_type"] == "bundle"]
    bundle_ids = [r["item_id"] for r in bundles if r.get("item_id")]
    bundle_map = _expand_bundle_components(sb, bundle_ids)

    for r in q_lines:
        # define ventana de tiempo de reserva para la línea
        s = r.get("start_at") or start_ev
        e = r.get("end_at")   or end_ev
        if not s or not e or e <= s:
            # ignora líneas con ventanas inválidas
            continue

        if r["item_type"] == "rentable":
            needs.append({
                "item_id": r["item_id"],
                "quantity": int(round(float(r["quantity"]))),
                "start_at": s, "end_at": e
            })
        elif r["item_type"] == "bundle":
            # expandir componentes
            comps = bundle_map.get(r["item_id"], [])
            qty_parent = float(r["quantity"])
            for c in comps:
                comp_id = c["item_id"]
                comp_qty = float(c["quantity"]) * qty_parent
                meta = items_meta.get(comp_id)
                if not meta:
                    continue
                if meta.get("item_type") != "rentable":
                    continue
                needs.append({
                    "item_id": comp_id,
                    "quantity": int(round(comp_qty)),
                    "start_at": s, "end_at": e
                })
        else:
            # consumable / service no generan reserva
            pass

    # 2) consolidar por (item_id, ventana exacta). Si quisieras, puedes consolidar por item_id ignorando ventana.
    compact = {}
    for n in needs:
        key = (n["item_id"], n["start_at"], n["end_at"])
        compact.setdefault(key, 0)
        compact[key] += int(n["quantity"])
    out = []
    for (item_id, s, e), q in compact.items():
        out.append({"item_id": item_id, "quantity": q, "start_at": s, "end_at": e, "quotation_id": quotation_id, "event_id": event["id"]})
    return out

def _check_availability_or_raise(sb, reservations_needed):
    """
    Para cada (item_id, ventana), compara:
      capacidad >= (ya reservado en traslape + solicitado)
    Lanza ValueError con detalle si no hay capacidad.
    """
    # precargar capacidades por item
    item_ids = sorted({r["item_id"] for r in reservations_needed})
    capacities = {iid: _compute_item_capacity(sb, iid) for iid in item_ids}

    shortages = []
    for r in reservations_needed:
        item_id = r["item_id"]
        cap = capacities.get(item_id, 0)
        already = _sum_overlapping_reserved(sb, item_id, r["start_at"], r["end_at"])
        need = int(r["quantity"])
        if need + already > cap:
            shortages.append({
                "item_id": item_id,
                "capacity": cap,
                "already": already,
                "request": need,
                "start_at": r["start_at"],
                "end_at": r["end_at"]
            })

    if shortages:
        # construye mensaje claro
        lines = []
        for s in shortages:
            lines.append(
                f"- Item {s['item_id']} sin capacidad: cap={s['capacity']} reservado={s['already']} requerido={s['request']} ({s['start_at']} → {s['end_at']})"
            )
        msg = "No hay capacidad suficiente para algunos ítems rentables:\n" + "\n".join(lines)
        raise ValueError(msg)

def _create_reservations(sb, reservations_needed):
    """Borra reservas previas de la cotización y crea nuevas (status='firm')."""
    qid = reservations_needed[0]["quotation_id"]
    sb.table("reservations").delete().eq("quotation_id", qid).execute()
    payload = []
    for r in reservations_needed:
        payload.append({
            "item_id": r["item_id"],
            "quotation_id": r["quotation_id"],
            "event_id": r["event_id"],
            "start_at": r["start_at"],
            "end_at": r["end_at"],
            "quantity": int(r["quantity"]),
            "status": RES_STATUS_FIRM
        })
    if payload:
        sb.table("reservations").insert(payload).execute()

def _accept_quote(sb, qid, user_id=None):
    """Actualiza estado e historial."""
    sb.table("quotations").update({
        "status": "accepted",
        "accepted_at": _now_utc_iso()
    }).eq("id", qid).execute()
    sb.table("quotation_status_history").insert({
        "quotation_id": qid, "old_status": "draft", "new_status": "accepted",
        "changed_by": user_id, "note": "Aceptada y reservas generadas"
    }).execute()

@app.post("/quotations/<quotation_id>/accept")
def quotation_accept(quotation_id):
    sb = get_service_client()
    try:
        q, ev = _fetch_quote_core(sb, quotation_id)
        lines, meta = _fetch_quote_lines_with_items(sb, quotation_id)

        # Construye necesidades (rentables y bundles rentables)
        needs = _build_needed_reservations(sb, lines, meta, ev, quotation_id)
        if not needs:
            raise ValueError("No hay líneas rentables (o válidas) para reservar.")

        # Chequea capacidad previa a insertar
        _check_availability_or_raise(sb, needs)

        # Crea reservas (reemplaza las existentes de esta cotización)
        _create_reservations(sb, needs)

        # Acepta la cotización
        # (si tienes auth de usuario, pasa su id aquí para el historial)
        _accept_quote(sb, quotation_id, user_id=None)

        flash("Cotización aceptada y reservas creadas (estado: firm).", "success")
        return redirect(url_for("quotation_edit", quotation_id=quotation_id))

    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("quotation_edit", quotation_id=quotation_id))
    except Exception as e:
        flash(f"Error al aceptar y reservar: {getattr(e,'message',str(e))}", "error")
        return redirect(url_for("quotation_edit", quotation_id=quotation_id))

if __name__ == "__main__":
    app.run(debug=True)
