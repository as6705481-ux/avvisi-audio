from flask import Blueprint

bp = Blueprint("verify", __name__, url_prefix="/verificar")

from blueprints.verify import routes  # noqa
