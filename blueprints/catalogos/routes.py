from flask import render_template

from blueprints.catalogos import bp

@bp.get("/catalogo-social")
def catalogo_social():
    return render_template("catalogos/catalogo-social.html")

@bp.get("/catalogo-btl")
def catalogo_btl():
    return render_template("catalogos/catalogo-btl.html")  

@bp.get("/catalogo-corporativo")
def catalogo_corporativo():
    return render_template("catalogos/catalogo-corporativo.html")