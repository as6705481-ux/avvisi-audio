from flask import Flask, render_template
from config import Settings
from utils.dates import fmt_ampm

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Config
    s = Settings()
    app.config["SECRET_KEY"] = s.secret_key

    @app.get("/")
    def home():
        return render_template("home.html")  

    # Blueprints (import aquí adentro evita imports circulares)
    from blueprints.auth.routes import bp as auth_bp
    from blueprints.dashboard.routes import bp as dashboard_bp
    from blueprints.items.routes import bp as items_bp
    from blueprints.suppliers.routes import bp as suppliers_bp
    from blueprints.clients.routes import bp as clients_bp
    from blueprints.contacts.routes import bp as contacts_bp
    from blueprints.events.routes import bp as events_bp
    from blueprints.quotations.routes import bp as quotations_bp
    from blueprints.users import bp as users_bp
    from blueprints.catalogos.routes import bp as catalogos_bp
    from blueprints.import_quotes import bp as import_quotes_bp
    from blueprints.verify import bp as verify_bp
    from blueprints.payroll import bp as payroll_bp

    # ✅ register_blueprint: método de Flask
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(items_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(contacts_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(quotations_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(catalogos_bp)
    app.register_blueprint(import_quotes_bp)
    app.register_blueprint(verify_bp)
    app.register_blueprint(payroll_bp)

    # Filtros Jinja2
    app.add_template_filter(fmt_ampm, "ampm")

    # ✅ context_processor: decorador de Flask
    from services.session_user import inject_user
    app.context_processor(inject_user)

    from services.translations import (
        QUOTE_STATUS_ES, ITEM_TYPE_ES,
        RESERVATION_STATUS_ES, USER_ROLE_ES,
        PAYROLL_STATUS_ES, PAYROLL_KIND_ES,
    )

    @app.context_processor
    def inject_globals():
        return {
            "APP_NAME": "Avvisi",
            "QUOTE_STATUS_ES": QUOTE_STATUS_ES,
            "ITEM_TYPE_ES": ITEM_TYPE_ES,
            "RESERVATION_STATUS_ES": RESERVATION_STATUS_ES,
            "USER_ROLE_ES": USER_ROLE_ES,
            "PAYROLL_STATUS_ES": PAYROLL_STATUS_ES,
            "PAYROLL_KIND_ES": PAYROLL_KIND_ES,
        }

    return app
