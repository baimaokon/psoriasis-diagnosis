from flask import Blueprint, g, jsonify, request

from app.models import User, db
from app.utils import create_token, error, login_required, success


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if len(username) < 3:
        return jsonify(error("用户名至少3位")), 400
    if len(password) < 6:
        return jsonify(error("密码至少6位")), 400

    if User.query.filter_by(username=username).first():
        return jsonify(error("用户名已存在")), 400

    user = User(username=username, role=0)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(success(message="注册成功"))


def _login_by_role(expected_role=None):
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify(error("请输入用户名和密码")), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify(error("账号或密码错误")), 401

    if expected_role is not None and user.role != expected_role:
        return jsonify(error("账号角色不匹配")), 403

    token = create_token(user.id, user.role)
    return jsonify(
        success(
            {
                "token": token,
                "user": user.to_dict(),
            }
        )
    )


@auth_bp.route("/login", methods=["POST"])
def login():
    return _login_by_role(expected_role=None)


@auth_bp.route("/admin/login", methods=["POST"])
def admin_login():
    return _login_by_role(expected_role=1)


@auth_bp.route("/profile", methods=["GET"])
@login_required
def profile():
    user = User.query.get(g.user_id)
    if not user:
        return jsonify(error("用户不存在")), 404
    return jsonify(success(user.to_dict()))

