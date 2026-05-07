from flask import Blueprint, jsonify

from app.utils import success


test_bp = Blueprint("test", __name__, url_prefix="/api/test")


@test_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify(success({"status": "ok"}))

