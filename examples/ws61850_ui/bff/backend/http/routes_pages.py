from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    return render_template("index.html")
