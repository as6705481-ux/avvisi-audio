from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Función para escapar caracteres en LaTeX
def escape_latex(text):
    """
    Escapa caracteres especiales para LaTeX.
    """
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "\\&")
            .replace("%", "\\%")
            .replace("#", "\\#")
            .replace("_", "\\_")
            .replace("-", "{-}")
    )

# Modelo de Usuarios
class Users(db.Model):
    __tablename__ = 'Users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    _password = db.Column("password", db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'seller'), default='seller')
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())

    @property
    def password(self):
        raise AttributeError("La contraseña no es accesible directamente.")

    @password.setter
    def password(self, password):
        self._password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self._password, password)

# Modelo de Clientes
class Customers(db.Model):
    __tablename__ = 'Customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())

# Modelo de Proveedores
class Suppliers(db.Model):
    __tablename__ = 'Suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())

# Modelo de Productos
class Products(db.Model):
    __tablename__ = 'Products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    unit_price = db.Column(db.Float, nullable=False)
    up_price = db.Column(db.Float, nullable=False)
    down_price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('Suppliers.id'), nullable=True)
    category = db.Column(db.Enum('Pantalla Led', 'Microfonía', 'Efectos e Iluminacion', 'Audio', 'Pantallas Tv', 'Otros servicios'), nullable=False, default='Otros')
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())

    # Relación con proveedores
    supplier = db.relationship('Suppliers', backref=db.backref('products', lazy=True))

    # Relación con comentarios
    comments = db.relationship('ProductComments', back_populates='product', cascade='all, delete-orphan')
    

# Modelo de Cotizaciones
class Quotations(db.Model):
    __tablename__ = 'Quotations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('Customers.id'), nullable=False)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('Users.id'), nullable=True)
    event_location = db.Column(db.String(200))
    event_type = db.Column(db.String(100))
    guest_count = db.Column(db.Integer)
    quotation_date = db.Column(db.String(30))
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())
    total = db.Column(db.Float, default=0.0)
    status = db.Column(db.Enum('pending', 'approved', 'rejected', 'finalized'), default='pending')
    user = db.relationship('Users', foreign_keys=[user_id], backref=db.backref('quotations_created', lazy=True))
    assigned_user = db.relationship('Users', foreign_keys=[assigned_user_id], backref=db.backref('quotations_assigned', lazy=True))
    customer = db.relationship('Customers', backref=db.backref('quotations', lazy=True))

# Modelo de Detalles de Cotización
class QuotationDetails(db.Model):
    __tablename__ = 'Quotation_Details'
    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.Integer, db.ForeignKey('Quotations.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('Products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    days = db.Column(db.Integer, default=1)
    subtotal = db.Column(db.Float, nullable=False)
    tax = db.Column(db.Float, default=0.0)

    quotation = db.relationship('Quotations', backref=db.backref('details', lazy=True))
    product = db.relationship('Products', backref=db.backref('details', lazy=True))

# Modelo de Comentarios de Productos
class ProductComments(db.Model):
    __tablename__ = 'Product_Comments'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('Products.id'), nullable=False)
    quotation_id = db.Column(db.Integer, db.ForeignKey('Quotations.id'), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())

    # Relaciones
    product = db.relationship('Products', backref=db.backref('product_comments', lazy=True))
    quotation = db.relationship('Quotations', backref=db.backref('quotation_comments', lazy=True))



