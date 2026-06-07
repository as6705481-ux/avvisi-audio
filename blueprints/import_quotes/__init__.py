from flask import Blueprint

bp = Blueprint("import_quotes", __name__, url_prefix="/importar")

from blueprints.import_quotes import routes  # noqa: E402,F401
