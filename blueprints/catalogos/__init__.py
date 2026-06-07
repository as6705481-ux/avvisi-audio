from flask import Blueprint

bp = Blueprint("catalogos", __name__, url_prefix="/catalogos")

from . import routes  # noqa: E402,F401
