from flask import Blueprint

bp = Blueprint("contacts", __name__, url_prefix="/contacts")

from . import routes  # noqa: E402,F401
