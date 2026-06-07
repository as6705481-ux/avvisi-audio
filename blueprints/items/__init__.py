from flask import Blueprint

bp = Blueprint("items", __name__, url_prefix="/items")

from . import routes  # noqa: E402,F401
