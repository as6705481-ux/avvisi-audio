# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, redirect, flash, session, url_for, jsonify, send_file, send_from_directory
from models import db, Users, Customers, Products, Quotations, QuotationDetails, Suppliers, escape_latex, ProductComments
from subprocess import run
from sqlalchemy.sql import func
import os
import json
import base64
from pathlib import Path
import mysql.connector
from mysql.connector import Error
from datetime import datetime
from dotenv import load_dotenv
from email.message import EmailMessage
import ssl
import smtplib

app = Flask(__name__)
app.config['SECRET_KEY'] = '24junio98'  # Clave secreta para manejar sesiones
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://admin:24junio98@rdsprueba.cv00e8cgwcmo.us-east-1.rds.amazonaws.com/InventorySystem'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
#dialect://username:password@host:port/database
db.init_app(app)

def getUser():
    return Users.query.get(session['user_id'])

import smtplib
import ssl
from email.message import EmailMessage

def sentemail(details, quotation):
    """
    Envía un correo de alerta cuando se genera una nueva cotización.
    
    Parámetros:
    - customer (dict): Información del cliente (nombre, email, etc.).
    - quotation (dict): Datos de la cotización (ID, fecha, productos, total, etc.).
    """

    # Credenciales del remitente
    email_sender = "galeanoterlyn@gmail.com"
    password = "sqse dqeo pzfu mnci"  
    email_receiver = "ar9829415@gmail.com"  # Puede ser el email del cliente si se requiere

    # Construcción del mensaje
    subject = f"Nueva Cotización Generada - {quotation.customer_id}"
    
    # Formatear el cuerpo del correo
    body_html = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                color: #333;
                background-color: #f9f9f9;
            }}
            .container {{
                background-color: #fff;
                padding: 20px;
                border-radius: 8px;
                max-width: 600px;
                margin: auto;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }}
            h2 {{
                color: #FF7F11;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #FF7F11;
                color: white;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🚀 Nueva Cotización Generada</h2>
            <p><strong>Fecha:</strong> {quotation.quotation_date}</p>
            <p><strong>Cliente:</strong> {Customers.query.get(quotation.customer_id).name}</p>
            <p><strong>ID Cotización:</strong> {quotation.id}</p>
            <p><strong>Ejecutivo:</strong> {Users.query.get(quotation.user_id).name}</p>

            <h3>🛒 Productos Cotizados</h3>
            <table>
                <tr>
                    <th>Producto</th>
                    <th>Cant</th>
                    <th>Días</th>
                    <th>Precio (L)</th>
                    <th>Impuesto (L)</th>
                </tr>
    """

    for detail in details:
        body_html += f"""
                <tr>
                    <td>{detail.product.name}</td>
                    <td>{detail.quantity}</td>
                    <td>{detail.days}</td>
                    <td>{detail.unit_price:.2f}</td>
                    <td>{detail.tax:.2f}</td>
                </tr>
    """

    body_html += f"""
            </table>
            <p style="margin-top: 20px;"><strong>Total Cotización:</strong> L {quotation.total:.2f}</p>
            <p style="font-size: 12px; color: #888;">Este es un mensaje automático, por favor no responder.</p>
        </div>
    </body>
    </html>
    """

    # Crear el mensaje de correo
    em = EmailMessage()
    em["From"] = email_sender
    em["To"] = email_receiver
    em["Subject"] = subject

        # Y luego configurar el email para incluir HTML:
    em.set_content("Este mensaje requiere un cliente compatible con HTML.")
    em.add_alternative(body_html, subtype='html')

    # Configurar conexión segura con SSL
    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(email_sender, password)
            smtp.sendmail(email_sender, email_receiver, em.as_string())
        print("Correo enviado con éxito")
    except Exception as e:
        print(f"Error al enviar el correo: {e}")

@app.context_processor
def inject_user():
    user = Users.query.get(session.get('user_id')) # Obtener usuario autenticado
    return dict(user=user)  # Ahora `user` está en TODAS las plantillas

def conectar_bd():
    try:
        con = mysql.connector.connect(
            host="rdsprueba.cv00e8cgwcmo.us-east-1.rds.amazonaws.com",
            database="AWS AVISSI",
            user="admin",
            password="24junio98",
            port=3306
        )
        if con.is_connected():
            print("Conexión exitosa a la base de datos")
            return con
    except Error as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

def login_required(f):
    #@wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:  # Verifica si el usuario no está en la sesión
            flash("Debes iniciar sesión primero.", "warning")
            return redirect('/home')  # Redirige a la página de inicio de sesión
        return f(*args, **kwargs)
    return decorated_function

# Ruta principal
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
    customers = Customers.query.all()
    products = Products.query.all()
    return render_template('home.html', customers=customers, products=products)

@app.route("/authentic/<int:quotation_id>")
def authentic_quotation(quotation_id):
    quotation = Quotations.query.get(quotation_id)
    
    if not quotation:
        return render_template("not_found.html", quotation_id=quotation_id), 404

    return render_template("authentic.html", quotation=quotation)

@app.route('/authentic')
def authentic():
    return render_template('authentic.html')

@app.route('/option_quotation')
def option_quotation():
    return render_template('option_quotation.html')

@app.route('/info')
def info():
    return render_template('info.html')

# Ruta para registrar un usuario
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form.get('role', 'seller')

        if Users.query.filter_by(email=email).first():
            flash("El correo ya está registrado.", "danger")
            return redirect('/register')

        new_user = Users(name=name, email=email, role=role)
        new_user.password = password  # Usar setter para cifrar
        db.session.add(new_user)
        db.session.commit()

        flash("Usuario registrado exitosamente.", "success")
        return redirect('/login')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = Users.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id

            flash("Inicio de sesión exitoso.", "success")
            
            # Histórico de ingresos mensuales
            historical_data = db.session.query(
                func.date_format(Quotations.created_at, "%Y-%m").label('month'),
                func.sum(Quotations.total).label('total_income')
            ).group_by(func.date_format(Quotations.created_at, "%Y-%m")) \
                .order_by(func.date_format(Quotations.created_at, "%Y-%m")).all()
                
            # Productos más demandados
            top_products = db.session.query(
                Products.name,
                func.sum(QuotationDetails.quantity).label('total_quantity')
            ).join(QuotationDetails, QuotationDetails.product_id == Products.id)\
                .group_by(Products.id)\
                .order_by(func.sum(QuotationDetails.quantity).desc())\
                .limit(5)\
                .all()
                
            months = [row[0] for row in historical_data]
            incomes = [row[1] for row in historical_data]
                
            # Serializar datos para pasarlos al template
            product_names = [row[0] for row in top_products]
            product_quantities = [float(row[1]) for row in top_products]
                
            # Renderizar plantilla con datos
            return render_template(
                'dashboard.html',
                historical_data=historical_data,
                months=json.dumps(months),
                incomes=json.dumps(incomes),
                product_names=json.dumps(product_names),
                product_quantities=json.dumps(product_quantities),
                user = user
            )
            #return redirect('/dashboard')
        else:
            flash("Correo o contraseña incorrectos.", "danger")

    return render_template('home.html')

# Ruta para cerrar sesión
@app.route('/logout')
def logout():
    session.clear()  # Limpia todos los datos almacenados en la sesión
    flash("Has cerrado sesión exitosamente.", "success")
    return render_template('home.html')  # Redirige a la página de inicio de sesión

# Ruta del perfil del usuario
@app.route('/profile/<int:user_id>')
def profile(user_id):
    user = Users.query.get(user_id)
    if not user:
        return "Usuario no encontrado", 404
    return render_template('profile.html', user=user)

# Ruta para gestionar proveedores
@app.route('/suppliers', methods=['GET'])
def list_suppliers():
    suppliers = Suppliers.query.all()
    return render_template('list.html', suppliers=suppliers)

@app.route('/suppliers/edit/<int:id>', methods=['GET', 'POST'])
def edit_supplier(id):
    supplier = Suppliers.query.get_or_404(id)
    if request.method == 'POST':
        supplier.name = request.form['name']
        supplier.email = request.form['email']
        supplier.phone = request.form['phone']
        supplier.address = request.form['address']
        db.session.commit()
        flash('Supplier updated successfully!', 'success')
        return redirect(url_for('list_suppliers'))
    return render_template('edit.html', supplier=supplier)

@app.route('/suppliers/delete/<int:id>', methods=['POST'])
def delete_supplier(id):
    supplier = Suppliers.query.get_or_404(id)
    db.session.delete(supplier)
    db.session.commit()
    flash('Supplier deleted successfully!', 'success')
    return redirect(url_for('list_suppliers'))

@app.route('/suppliers/new', methods=['GET', 'POST'])
def add_supplier():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']

        # Crear un nuevo proveedor
        new_supplier = Suppliers(name=name, email=email, phone=phone, address=address)
        db.session.add(new_supplier)
        db.session.commit()
        flash('Supplier added successfully!', 'success')
        return redirect(url_for('list_suppliers'))

    return render_template('new.html')

# Ruta para mostrar el dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("Debes iniciar sesión primero.", "danger")
        return redirect('/login')

    return render_template('dashboard.html')

# Ruta para gestionar productos
@app.route('/products', methods=['GET', 'POST'])
def list_products():
    suppliers = Suppliers.query.all()

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        unit_price = float(request.form['unit_price'])
        stock = int(request.form['stock'])
        supplier_id = int(request.form.get('supplier_id', '0')) or None
        category = request.form.get('category', 'Otros')
        comments = request.form.get('comments', '')

        product = Products(
            name=name,
            description=description,
            unit_price=unit_price,
            stock=stock,
            supplier_id=supplier_id,
            category=category,
            comments=comments
        )
        db.session.add(product)
        db.session.commit()
        flash("Producto agregado exitosamente.", "success")
        return redirect('/list_products')

    products = Products.query.all()
    return render_template('products.html', products=products, suppliers=suppliers)

# Editar producto
@app.route('/edit/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    suppliers = Suppliers.query.all()
    
    product = Products.query.get_or_404(product_id)

    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.up_price = float(request.form['up_price'])
        product.down_price = float(request.form['down_price'])
        product.stock = int(request.form['stock'])
        product.supplier_id = int(request.form['supplier'])
        db.session.commit()
        return redirect(url_for('list_products'))


    return render_template('edit_product.html', product=product, supplier = Suppliers.query.get(product.supplier_id), suppliers=suppliers )

# Eliminar producto
@app.route('/delete/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    product = Products.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return redirect(url_for('list_products'))

# Agregar nuevo producto
@app.route('/add', methods=['GET', 'POST'])
def add_product():
    suppliers = Suppliers.query.all()
    products = Products.query.all()

    if request.method == 'POST':
        # Obtener el objeto proveedor de la base de datos
        supplier_id = request.form['supplier']
        supplier = Suppliers.query.get(supplier_id)  # Buscar proveedor por ID
        
        # Verificar que el proveedor exista
        if not supplier:
            return "Error: Proveedor no encontrado", 400  

        if request.form['category'] == 'Otros' and request.form['new_category'] != None:
            category = request.form['new_category'] 
            print("categoria correcta ", category)
        else:
            category = request.form['category']

        # Crear el nuevo producto
        new_product = Products(
            name=request.form['name'],
            description=request.form['description'],
            category = category,
            up_price=float(request.form['up_price']),
            down_price=float(request.form['down_price']),
            stock=int(request.form['stock']),
            supplier=supplier  # Asignar el objeto 'supplier' (no el ID)
        )
        db.session.add(new_product)
        db.session.commit()

        return redirect(url_for('list_products'))
    return render_template('add_product.html', suppliers = suppliers, products = products)

@app.route('/customers')
def list_customers():
    customers = Customers.query.all()
    return render_template('customers.html', customers=customers)

@app.route('/edit_customer/<int:id>')
def edit_customer(id):
    customer = Customers.query.get_or_404(id)
    return render_template("edit_customer.html", customer=customer)

@app.route("/quotations")
def quotations():
    quotations = db.session.query(
        Quotations.id,
        Quotations.quotation_date,
        Customers.name.label("customer_name"),
        Quotations.total,
        Quotations.status
    ).join(Customers).all()

    return render_template("quotations.html", quotations=quotations)

def to_dict(model):
    """Convierte un objeto SQLAlchemy en un diccionario, excluyendo campos privados."""
    columns = model.__table__.columns.keys()
    excluded_fields = {'password', '_password'}  # Excluir campos sensibles
    return {col: getattr(model, col) for col in columns if col not in excluded_fields}
@app.route("/edit_quotation/<int:quotation_id>")
def edit_quotation(quotation_id):
    quotation = db.session.query(Quotations).filter_by(id=quotation_id).first()

    if not quotation:
        flash("Cotización no encontrada", "danger")
        return redirect(url_for("quotations"))

    # Convertir el objeto a un diccionario serializable
    quotation_dict = to_dict(quotation)

    # Obtener los detalles de la cotización con los productos
    quotation_details = db.session.query(
        QuotationDetails.id,
        QuotationDetails.product_id,
        Products.id.label("product_id"),
        Products.name.label("product_name"),
        Products.up_price,
        Products.down_price,
        QuotationDetails.quantity,
        QuotationDetails.unit_price,
        QuotationDetails.days,
        QuotationDetails.subtotal
    ).join(Products).filter(QuotationDetails.quotation_id == quotation_id).all()

    # Convertir quotation_details a una lista de diccionarios
    quotation_details_dict = [dict(row._asdict()) for row in quotation_details]

    # Obtener todos los productos, clientes y usuarios (excluyendo contraseñas)
    all_products = [to_dict(product) for product in Products.query.all()]
    all_customers = [to_dict(customer) for customer in Customers.query.all()]
    all_users = [to_dict(user) for user in Users.query.all()]

    # Obtener comentarios de productos
    product_comments = [
        {"product_id": comment.product_id, "comment": comment.comment}
        for comment in db.session.query(ProductComments).filter(ProductComments.quotation_id == quotation_id).all()
    ]

    return render_template("edit_quotation.html",
                           quotation=quotation_dict,
                           quotation_details=quotation_details_dict,
                           all_products=all_products,
                           all_customers=all_customers,
                           all_users=all_users,
                           product_comments=product_comments)

@app.route("/update_quotation/<int:quotation_id>", methods=["POST"])
def update_quotation(quotation_id):
    quotation = Quotations.query.get_or_404(quotation_id)

    # Actualizar los datos principales
    quotation.quotation_date = request.form.get("quotation_date")
    quotation.status         = request.form.get("status")
    quotation.event_location = request.form.get("event_location")
    quotation.event_type     = request.form.get("event_type")
    quotation.customer_id    = int(request.form.get("customer_id"))

    # Eliminar detalles anteriores
    QuotationDetails.query.filter_by(quotation_id=quotation.id).delete()
    ProductComments.query.filter_by(quotation_id=quotation.id).delete()

    total = 0
    tax_rate = 0.15

    # Procesar nuevos productos
    for key in request.form:
        if key.startswith("quantity_"):
            try:
                product_id = int(key.replace("quantity_", ""))
                quantity = int(request.form.get(f"quantity_{product_id}", "1"))
                price = float(request.form.get(f"price_{product_id}", "0"))
                days = int(request.form.get(f"days_{product_id}", "1"))

                product = Products.query.get(product_id)
                if not product:
                    flash(f"Producto ID {product_id} no encontrado.", "warning")
                    continue

                subtotal = price * quantity * days
                apply_tax = QuotationDetails.tax
                
                print(apply_tax)
                print(subtotal)
                tax = subtotal * tax_rate if apply_tax else 0
                total += subtotal + tax

                detail = QuotationDetails(
                    quotation_id=quotation.id,
                    product_id=product_id,
                    quantity=quantity,
                    unit_price=price,
                    days=days,
                    subtotal=subtotal,
                    tax=tax
                )
                db.session.add(detail)

                comment = request.form.get(f"comment_{product_id}", "").strip()
                if comment:
                    product_comment = ProductComments(
                        product_id=product_id,
                        quotation_id=quotation.id,
                        comment=comment
                    )
                    db.session.add(product_comment)

            except ValueError:
                flash("Error en los datos del producto.", "danger")
                continue

    quotation.total = total

    # Guardar cambios en la base de datos
    db.session.commit()
    
    # 🔥 Generar el nuevo PDF actualizado
    details = QuotationDetails.query.filter_by(quotation_id=quotation.id).all()
   
    pdf_file = generate_quotation_pdf(quotation, details)  # Asegúrate que esta función guarda en static/pdf

    if pdf_file:
        # 🔥 Redirigir directamente a descargar el PDF
        return redirect(url_for('download_pdf', filename=f'quotation_{quotation.id}.pdf'))
    else:
        flash("Error al generar el PDF actualizado.", "danger")
        return redirect(url_for('quotations'))
    
# Ruta para agregar un nuevo cliente
@app.route('/customers/new', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']

        new_customer = Customers(name=name, email=email, phone=phone, address=address)

        try:
            db.session.add(new_customer)
            db.session.commit()
            flash('Customer added successfully!', 'success')
            return redirect(url_for('list_customers'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding customer: {e}', 'danger')

    return render_template('add_customer.html')

# Ruta para eliminar un cliente
@app.route('/customers/delete/<int:id>', methods=['POST'])
def delete_customer(id):
    customer = Customers.query.get_or_404(id)
    try:
        db.session.delete(customer)
        db.session.commit()
        flash('Customer deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting customer: {e}', 'danger')
    return redirect(url_for('list_customers'))

@app.route('/orders', methods=['GET', 'POST'])
def orders():
    if request.method == 'POST':
        quotation_id = request.form.get('quotation_id')
        quotation = Quotations.query.get_or_404(quotation_id)

        if request.form.get('action') == 'change_status':
            new_status = request.form.get('new_status')
            quotation.status = new_status
            db.session.commit()
            flash(f"Estado actualizado a '{new_status}'.", "success")

        elif request.form.get('action') == 'assign_user':
            assigned_user_id = request.form.get('assigned_user_id')
            if assigned_user_id:
                quotation.assigned_user_id = int(assigned_user_id)
            else:
                quotation.assigned_user_id = None
            db.session.commit()
            flash("Encargado asignado correctamente.", "success")

        return redirect(url_for('orders'))  # Redirige para evitar re-envío

    # GET request: cargar datos
    quotations = Quotations.query.all()
    users = Users.query.all()
    return render_template("orders.html", quotations=quotations, users=users)

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/users')
def users():
    users = Users.query.all()
    return render_template('users.html', users=users)

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    user = Users.query.get_or_404(user_id)
    if request.method == 'POST':
        user.name = request.form['name']
        user.email = request.form['email']
        user.password = request.form['password']
        user.role = request.form['role']
        user.active = 'active' in request.form
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('edit_user.html', user=user)

@app.route('/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    user = Users.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('users'))

# Ruta para gestionar cotizaciones
@app.route('/create_quotation', methods=['GET', 'POST'])
def create_quotation():
    if 'user_id' not in session:
        flash("Debes iniciar sesión primero.", "danger")
        return redirect('/login')

    if request.method == 'POST':
        customer_id    = request.form.get('customer')
        event_location = request.form.get('event_location')
        event_type     = request.form.get('event_type')
        guest_count    = request.form.get('guest_count')
        quotation_date = request.form.get('quotation_date')
        user_id        = session.get('user_id')
    
        if not customer_id or not event_location or not event_type or not guest_count:
            flash("Por favor completa todos los campos requeridos.", "danger")
            return redirect('/create_quotation')

        # Crear la cotización
        quotation = Quotations(
            customer_id     = int(customer_id),
            user_id         = user_id,
            event_location  = event_location,
            event_type      = event_type,
            guest_count     = int(guest_count),
            quotation_date  = quotation_date,
            total           = 0.0
        )
        db.session.add(quotation)
        db.session.commit()

        total = 0
        tax_rate = 0.15

        # Procesar los productos seleccionados
        for key, value in request.form.items():
            if key.startswith("product_"):
                try:
                    product_id              = int(value)
                    quantity                = int(request.form.get(f"quantity_{product_id}", "1"))
                    days                    = int(request.form.get(f"days_{product_id}", "1"))
                    custom_price_raw        = request.form.get(f"price_{product_id}", "").strip()
                    custom_price_select_raw = request.form.get(f"value_select_{product_id}", "").strip()

                    if int(custom_price_raw) > 0:
                        custom_price_select_raw = custom_price_raw
                        
                    comment = request.form.get(f"comment_{product_id}", "").strip()
                    
                except ValueError:
                    flash("Error al procesar los datos del producto. Verifica los campos ingresados.", "warning")
                    continue

                # Validar producto existente
                product = Products.query.get(product_id)
                if not product:
                    flash(f"Producto con ID {product_id} no encontrado.", "warning")
                    continue

                # Validar precio personalizado o usar el precio base
                try:
                    custom_price = float(custom_price_select_raw) if custom_price_select_raw else product.unit_price
                except ValueError:
                    flash(f"Precio inválido para el producto {product.name}. Usando precio base.", "warning")
                    custom_price = product.unit_price

                apply_tax = request.form.get(f"tax_{product_id}")
                
                # Calcular subtotal e impuesto
                subtotal = custom_price * quantity * days
                tax      = subtotal * tax_rate if apply_tax else 0
                total    += subtotal + tax

                # Crear detalle de cotización
                detail = QuotationDetails(
                    quotation_id    = quotation.id,
                    product_id      = product.id,
                    quantity        = quantity,
                    unit_price      = custom_price,
                    days            = days,
                    subtotal        = subtotal,
                    tax             = tax
                )
                db.session.add(detail)

                # Agregar comentario si existe
                if comment:
                    product_comment = ProductComments(
                        product_id=product.id,
                        quotation_id=quotation.id,
                        comment=comment
                    )
                    db.session.add(product_comment)

        # Actualizar el total de la cotización
        quotation.total = total
        db.session.commit()

        # Generar el PDF
        details  = QuotationDetails.query.filter_by(quotation_id=quotation.id).all()
        pdf_file = generate_quotation_pdf(quotation, details)

        if pdf_file:
            flash("Cotización creada y PDF generado exitosamente.", "success")
            sentemail(details, quotation)
            return redirect(f'/{pdf_file}')
        else:
            flash("Error al generar el PDF.", "danger")
            return redirect('/dashboard')

    # Renderizar la página de creación de cotizaciones
    customers  = Customers.query.all()
    products   = Products.query.all()
    categories = db.session.query(Products.category).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('cotizaciones.html', customers=customers, products=products, categories=categories)

@app.route('/reports', methods=['GET', 'POST'])
def quotation_dashboard():
    if 'user_id' not in session:
        flash("Debes iniciar sesión primero.", "danger")
        return redirect('/login')

    # Obtener todas las cotizaciones y usuarios vendedores
    quotations = Quotations.query.all()
    users = Users.query.filter_by(role='seller').all()

    # Estadísticas de mejores clientes
    top_customers = db.session.query(
        Customers.name,
        func.sum(Quotations.total).label('total_spent')
    ).join(Quotations, Quotations.customer_id == Customers.id) \
        .group_by(Customers.id) \
        .order_by(func.sum(Quotations.total).desc()) \
        .limit(5).all()

    # Estadísticas de mejores usuarios
    top_users = db.session.query(
        Users.name,
        func.count(Quotations.id).label('events_managed'),
        func.sum(Quotations.total).label('total_generated')
    ).join(Quotations, Quotations.user_id == Users.id) \
        .group_by(Users.id) \
        .order_by(func.sum(Quotations.total).desc()) \
        .limit(5).all()

    # Histórico de ingresos mensuales
    historical_data = db.session.query(
        func.date_format(Quotations.created_at, "%Y-%m").label('month'),
        func.sum(Quotations.total).label('total_income')
    ).group_by(func.date_format(Quotations.created_at, "%Y-%m")) \
        .order_by(func.date_format(Quotations.created_at, "%Y-%m")).all()

    # Cotizaciones por estado
    quotations_by_status = db.session.query(
        Quotations.status,
        func.count(Quotations.id).label('count')
    ).group_by(Quotations.status).all()

    # Productos más demandados
    top_products = db.session.query(
        Products.name,
        func.sum(QuotationDetails.quantity).label('total_quantity')
    ).join(QuotationDetails, QuotationDetails.product_id == Products.id)\
        .group_by(Products.id)\
        .order_by(func.sum(QuotationDetails.quantity).desc())\
        .limit(5)\
        .all()

    if request.method == 'POST':
        quotation_id = request.form.get('quotation_id')
        action = request.form.get('action')
        quotation = Quotations.query.get(quotation_id)

        if not quotation:
            flash("Cotización no encontrada.", "danger")
            return redirect(url_for('quotation_dashboard'))

        if action == 'assign_user':
            assigned_user_id = request.form.get('assigned_user_id')
            quotation.assigned_user_id = assigned_user_id
            db.session.commit()
            flash("Encargado asignado correctamente.", "success")

        elif action == 'change_status':
            new_status = request.form.get('new_status')
            if new_status in ['pending', 'approved', 'rejected', 'finalized']:
                quotation.status = new_status
                if new_status == 'finalized':
                    details = QuotationDetails.query.filter_by(quotation_id=quotation.id).all()
                    for detail in details:
                        product = Products.query.get(detail.product_id)
                        if product.stock >= detail.quantity:
                            product.stock -= detail.quantity
                        else:
                            flash(f"Stock insuficiente para {product.name}.", "warning")
                            return redirect(url_for('quotation_dashboard'))

                # Confirmar los cambios en la base de datos
                db.session.commit()
                flash("Estado actualizado correctamente.", "success")
            else:
                flash("Estado no válido.", "danger")

        return redirect(url_for('quotation_dashboard'))

    # Preparar datos para gráficos
    months = [row[0] for row in historical_data]
    incomes = [row[1] for row in historical_data]
    statuses = [row[0].capitalize() for row in quotations_by_status]
    status_counts = [row[1] for row in quotations_by_status]
    customer_names = [row[0] for row in top_customers]
    customer_totals = [row[1] for row in top_customers]
    user_names = [row[0] for row in top_users]
    user_totals = [row[2] for row in top_users]

    # Serializar datos para pasarlos al template
    product_names = [row[0] for row in top_products]
    product_quantities = [float(row[1]) for row in top_products]

    # Renderizar plantilla con datos
    return render_template(
        'dashboard_quotations.html',
        quotations=quotations,
        users=users,
        top_customers=top_customers,
        top_users=top_users,
        historical_data=historical_data,
        quotations_by_status=quotations_by_status,
        months=json.dumps(months),
        incomes=json.dumps(incomes),
        statuses=json.dumps(statuses),
        status_counts=json.dumps(status_counts),
        customer_names=json.dumps(customer_names),
        customer_totals=json.dumps(customer_totals),
        user_names=json.dumps(user_names),
        user_totals=json.dumps(user_totals),
        product_names=json.dumps(product_names),
        product_quantities=json.dumps(product_quantities)
    )

# Función para generar PDFs
def generate_quotation_pdf(quotation, details):
    """
    Genera un PDF para la cotización utilizando LaTeX.
    """
    # Generar el contenido del documento LaTeX

    tex_template = r"""
\documentclass[a4paper,12pt]{article}
\usepackage{url}
\usepackage[utf8]{inputenc}
\usepackage{graphicx}
\usepackage{geometry}
\usepackage{array}
\usepackage{fancyhdr}
\usepackage{pdflscape}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{enumitem}
\usepackage{fontawesome5}
\usepackage{tikz}
\usepackage{svg}
\usepackage{qrcode}
\usepackage{multirow}
\usepackage{siunitx}
\usepackage{colortbl}
\usepackage{multicol}
\usepackage{tabularx}


\definecolor{primary}{HTML}{ff4500}
\geometry{
    landscape,
    top=1.5in,    % Margen superior aumentado
    bottom=1in, % Margen inferior
    left=1in,   % Margen izquierdo
    right=1in   % Margen derecho
}
\setlength{\parindent}{0pt} % Elimina sangría
\setlength{\parskip}{0pt}   % Sin espacio entre párrafos
\renewcommand{\headrulewidth}{0pt} % Elimina la línea debajo del encabezado

% Configuración del encabezado y pie de página
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{
    \includegraphics[width=3cm]{/Users/macbook/Downloads/Telegram Lite/Ultimo/avvisi-python/assets/logo.png}}
\fancyhead[C]{
    \textbf{\Huge Avvisi Audiovisuales} \\
    \vspace*{0.5cm}
    \textbf{\Large \textcolor{primary}{COTIZACIÓN}}
}
\fancyhead[R]{
    \qrcode[height=2cm]{http://127.0.0.1:8000/authentic/""" + f"{ quotation.id }" + r"""}
       
}



% Definir el color azul para el footer y rojo para la franja
\definecolor{footerblue}{HTML}{fc7404}
\definecolor{franjaroja}{RGB}{175, 175, 175}

% Configuración del footer
\fancyfoot[C]{
    \vspace*{0.12cm}
    % Franja roja en la parte inferior
    \begin{tikzpicture}[overlay, remember picture]
        \fill[franjaroja] ([yshift=-1.2cm, xshift=-15cm]current page.south west) rectangle ([yshift=-1.5cm, xshift=15cm]current page.south east);
    \end{tikzpicture}
    % Franja azul más pequeña, sobre la franja roja, con borde superior redondeado
    \begin{tikzpicture}[overlay, remember picture]
        \fill[footerblue, rounded corners=10pt]
        ([yshift=-2.5cm, xshift=-7cm]current page.south west) rectangle
        ([yshift=-0.5cm, xshift=-23cm]current page.south east);
    \end{tikzpicture}
    % Contenido del footer dentro de la franja azul
    \begin{minipage}[b]{\textwidth}
        \vspace*{0.47cm} % Ajuste del contenido dentro de la franja azul
        \hfill % Empuja los íconos a la derecha
        \begin{minipage}[b]{0.8\textwidth}
            \hspace*{2.2cm}\textcolor{white}{\texttt{\href{mailto:avvisiaudio@gmail.com}{\large{\texttt{@avvisi.gmail}}}}}\hspace{0.25cm}\href{https://www.facebook.com/share/ThHZiC2YG1cnBgHd/?mibextid=qi2Omg}{\includegraphics[width=0.5cm]{/Users/macbook/Downloads/Telegram Lite/Ultimo/avvisi-python/assets/facebook.png}}
            \hspace{0.25cm}\href{https://www.instagram.com/avvisiaudio?igsh=MWc5OWZlM3ZtNHZrdA==}{\includegraphics[width=0.5cm]{/Users/macbook/Downloads/Telegram Lite/Ultimo/avvisi-python/assets/instagram.png}}
            \hspace{0.25cm}\href{https://wa.me/50432490824}{\includegraphics[width=0.5cm]{/Users/macbook/Downloads/Telegram Lite/Ultimo/avvisi-python/assets/whatsapp.png}}
            \hspace{0.25cm}\href{https://www.tiktok.com/@avvisiaudio?_t=8q6hsegJ3Sf&_r=1}{\includegraphics[width=0.5cm]{/Users/macbook/Downloads/Telegram Lite/Ultimo/avvisi-python/assets/tiktok.png}}
            \hspace{0.25cm}\textcolor{white}{\texttt{\href{https://avvisiaudio.com/}{\large\texttt{avvisi.com}}}}
        \end{minipage}
    \end{minipage}
}

\begin{document}

\vspace*{1.5cm}
%%%%%%%vamos por aqui%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%
\noindent

\noindent
\textbf{N° Cotización:} 2025-""" + str(quotation.id) + r"""\ \\
\textbf{Nombre del Cliente:} """ + escape_latex(Customers.query.get(quotation.customer_id).name) + r"""\\
\textbf{Lugar de Evento:} """ + escape_latex(quotation.event_location) + r""" \\
\textbf{Tipo de evento:} """ + escape_latex(quotation.event_type) + r""" \\
\textbf{N° de Invitados:} """ + escape_latex(quotation.guest_count) + r"""\\
\textbf{Fecha de Evento:} """ + escape_latex( str(quotation.quotation_date) ) + r"""
\begin{flushright}
\vspace{-3.5cm}
\textbf{Avvisi Audiovisuales}\\
\href{mailto:avvisiaudio@gmail.com}{avvisiaudio@gmail.com} \\
3249-0824 / 9533-8173 \\
\href{https://avvisiaudio.com}{www.avvisiaudio.com} 
\end{flushright}
\vspace{1cm}


\noindent 
\begin{table}[h!]
    \scriptsize
    \centering
    \renewcommand{\arraystretch}{1.3} % Espaciado entre filas
    \begin{tabularx}{\textwidth}{
            l
            c
            X
            l
            l
        }
        \arrayrulecolor{primary}\hline
        \textbf{Cantidad} & \textbf{Días} & \textbf{Descripción} & \textbf{Precio Unitario (L)} & \textbf{Precio Total (L)} \\
        \arrayrulecolor{primary}\hline \hline
"""

    subtotal = 0
    total_tax = 0

    for detail in details:
        tex_template += f"""
        {detail.quantity} & {detail.days} & {{\\raggedright\\arraybackslash {escape_latex(detail.product.name)} }} & {detail.unit_price:,.2f} & {detail.subtotal:,.2f} \\\\
    """

        # Calcular subtotales y totales dinámicamente
        subtotal += detail.subtotal
        total_tax += detail.tax

    print(detail.tax)
    print(total_tax)
    # Total general
    total = subtotal + total_tax

    # Agregar el final de la tabla con los totales
    tex_template += r"""
        \arrayrulecolor{primary}\hline
        & & & \textbf{ISV 15\%:} & """ + f"{total_tax:,.2f}" + r""" \\
        & & & \textbf{Total:} & """ + f"{total:,.2f}" + r"""   \\
        \arrayrulecolor{primary}
    \end{tabularx}
    \label{tab-productos-cotizados}
\end{table}

\vspace{0.4cm}
\noindent\begin{minipage}[t]{0.6\textwidth}
    \textbf{Ejecutivo de Ventas} \\
    \textbf{} """ + escape_latex(Users.query.get(quotation.user_id).name) + r"""\\
    \textbf{} """ + escape_latex(Users.query.get(quotation.user_id).email) + r"""\\
\end{minipage}%

\newpage

\vspace*{1.2cm}

\noindent \textbf{TIEMPO DE MANTENIMIENTO DE OFERTA: 30 DÍAS}

% Lista con menos espacio entre elementos
\begin{enumerate}[itemsep=0.2em]
    \item El uso del equipo dependerá del montaje a realizar según las especificaciones del cliente, tomando en cuenta lugar, número de personas y duración.
    \item La siguiente es una descripción de algunos servicios dentro del presupuesto: presupuesto, personal de staff, presupuesto de operación, impuestos y permisos del montaje.
    \item Los precios en esta cotización están sujetos a cambios según la logística que se maneje por parte de la organización de la actividad. El 50\% del adelanto antes del evento y el 50\% faltante terminado el sound check y el montaje o una cantidad acordada entre las partes.
    \item En caso de que se cancele el evento, se deberá dar un aviso 4 días antes para la devolución del dinero.
    \item Cualquier daño al equipo causado por los invitados o participantes del evento, se reconocerá un porcentaje del valor del mismo según la gravedad del caso.
    \item Si surge alguna consulta, puede comunicarse al \href{tel:+50432490824}{3249-0824} y visitar nuestra página de Facebook \href{https://www.facebook.com/Avvisicorporation/}{Avvisicorporation}.
\end{enumerate}


%\begin{center}
%    \begin{tabular}{c c}
%        \includegraphics[width=0.27\textwidth]{/Users/macbook/Downloads/Telegram Lite/Ultimo/avvisi-python/assets/firma.png} & \hspace*{2cm} 
%        \underline{ \hspace{6cm} }\,\
%    \end{tabular}
%\end{center}

\begin{center}
    \begin{tabular}{c@{\hskip 2cm}c}
        \includegraphics[width=0.27\textwidth]{/Users/macbook/Downloads/Telegram Lite/Ultimo/avvisi-python/assets/firma.png} & \hspace*{2cm} 
         
        \\[-1.95cm] % Ajusta este valor para mover la línea más arriba
        & \underline{ \hspace{6cm} }\,\
    \end{tabular}
\end{center}

\end{document}
"""

    tex_file = f"quotation_{quotation.id}.tex"
    pdf_file = f"quotation_{quotation.id}.pdf"

    # Ruta a static/pdf dentro de tu proyecto Flask
    project_root = Path(__file__).parent
    pdf_folder = project_root / "static/pdf"
    pdf_folder.mkdir(parents=True, exist_ok=True)

    tex_path = pdf_folder / tex_file
    pdf_path = pdf_folder / pdf_file

    # Guardar archivo LaTeX
    with open(tex_path, "w") as f:
        f.write(tex_template)

    # Compilar LaTeX directamente en static/pdf
    result = run(["pdflatex", "-output-directory", str(pdf_folder), str(tex_path)], capture_output=True, text=True)
    
    if result.returncode != 0:
        print("Error durante la compilación de LaTeX:")
        print(result.stderr)
        return None

    # Limpiar archivos auxiliares generados
    for ext in [".aux", ".log", ".tex"]:
        aux_file = pdf_folder / f"quotation_{quotation.id}{ext}"
        if aux_file.exists():
            aux_file.unlink()

    return f"static/pdf/{pdf_file}"

@app.route('/generate-pdf', methods=['POST'])
def generate_pdf():
    data = request.json  # Obtener datos del frontend
    quotation = data.get('quotation')
    quotation_details = data.get('quotation_details')[0]

    # Crear la cotización
    quotation = Quotations(
        customer_id     = int(quotation['customer_id']),
        user_id         = quotation['user_id'],
        event_location  = quotation['event_location'],
        event_type      = quotation['event_type'],
        guest_count     = int(quotation['guest_count']),
        quotation_date  = quotation['quotation_date'],
        total           = quotation['total']
    )
    db.session.add(quotation)
    db.session.commit()
    
    detail = QuotationDetails(
        quotation_id    = quotation_details['id'],
        product_id      = quotation_details['product_id'],
        quantity        = quotation_details['quantity'],
        unit_price      = quotation_details['down_price'],
        days            = quotation_details['days'],
        subtotal        = quotation_details['subtotal'],
        tax             = quotation_details['tax']
    )
    db.session.add(detail)

    # Generar el PDF
    pdf_path = generate_quotation_pdf(quotation, quotation_details)  
    return send_file(pdf_path, as_attachment=True)

@app.route('/download/<path:filename>')
def download_pdf(filename):
    return send_from_directory('static/pdf', filename, as_attachment=True)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=8000)
