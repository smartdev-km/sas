from flask import Blueprint, jsonify
from flask_login import login_required

from app.models import AppState

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/last-modified")
@login_required
def last_modified():
    state = AppState.query.first()
    ts = state.last_modified_at.isoformat() if state else ""
    return jsonify({"last_modified": ts})
