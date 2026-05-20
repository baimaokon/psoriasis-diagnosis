"""
test.py — 测试与健康检查路由（/api/test/*）
───────────────────────────────────────────
提供无需认证的测试端点，用于开发调试和 CI/CD 健康检查：
  GET /api/test/ping — 返回 pong，验证服务是否正常运行
"""

from flask import Blueprint, jsonify

from app.utils import success


test_bp = Blueprint("test", __name__, url_prefix="/api/test")


@test_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify(success({"status": "ok"}))

