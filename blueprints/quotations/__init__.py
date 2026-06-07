from flask import Blueprint

bp = Blueprint("quotations", __name__, url_prefix="/quotations")

from . import routes  # noqa: E402,F401
