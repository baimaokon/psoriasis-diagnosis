from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from .response import error


def create_token(user_id: int, role: int, expires_days: int = 7) -> str:
    """签发 JWT Token，包含用户ID和角色，默认 7 天过期"""
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=expires_days),
    }
    token = jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")
    # PyJWT 不同版本返回值类型不同
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return token


def _decode_token(token: str):
    return jwt.decode(
        token,
        current_app.config["SECRET_KEY"],
        algorithms=["HS256"],
    )


def _extract_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header:
        return ""
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return auth_header


def login_required(func):
    """JWT 认证装饰器：从 Authorization 头提取 Bearer Token 并验证

    验证通过后将 user_id 和 user_role 注入 Flask 全局变量 g，
    之后的路由处理函数可通过 g.user_id / g.user_role 获取当前用户信息。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            return jsonify(error("请先登录")), 401
        try:
            payload = _decode_token(token)
            g.user_id = int(payload.get("user_id", 0))
            g.user_role = int(payload.get("role", 0))
        except jwt.ExpiredSignatureError:
            return jsonify(error("登录已过期，请重新登录")), 401
        except jwt.InvalidTokenError:
            return jsonify(error("登录凭证无效")), 401
        return func(*args, **kwargs)

    return wrapper


def admin_required(func):
    @wraps(func)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user_role != 1:
            return jsonify(error("无权限访问")), 403
        return func(*args, **kwargs)

    return wrapper

