"""认证与鉴权测试 — 对应论文 JC-001 Token 携带 / JC-002 失效处理 / JC-009 权限隔离 (5 项)

JWT 认证流程：签发 Token (HS256, 7天过期) → 请求头携带 Bearer Token
→ login_required 装饰器解码验证 → 过期/无效/缺失均返回 401
权限隔离：普通用户 (role=0) 无法访问管理端 (admin_required)，返回 403
"""

import jwt as pyjwt

from app.utils.auth import create_token


class TestTokenCreate:
    def test_returns_string_token(self, test_app):
        """签到 Token 返回有效字符串"""
        with test_app.app_context():
            token = create_token(user_id=42, role=0)
        assert isinstance(token, str) and len(token) > 20

    def test_token_payload_roundtrip(self, test_app):
        """Token 编码/解码闭环：user_id、role、7 天过期、不同用户不同 Token"""
        from datetime import datetime, timezone

        with test_app.app_context():
            t1 = create_token(user_id=99, role=1)
            p1 = pyjwt.decode(t1, test_app.config["SECRET_KEY"], algorithms=["HS256"])
        assert p1["user_id"] == 99 and p1["role"] == 1

        with test_app.app_context():
            t2 = create_token(user_id=1, role=0)
            p2 = pyjwt.decode(
                t2, test_app.config["SECRET_KEY"], algorithms=["HS256"],
                options={"verify_exp": False},
            )
        diff = p2["exp"] - int(datetime.now(timezone.utc).timestamp())
        assert 6 * 86400 <= diff <= 8 * 86400

        with test_app.app_context():
            assert create_token(user_id=1, role=0) != create_token(user_id=2, role=0)


class TestAuthEndpoints:
    def test_missing_or_invalid_token(self, test_app):
        """无 Token → 401「请先登录」；无效 Token → 401"""
        c = test_app.test_client()
        r1 = c.get("/api/user/records")
        assert r1.status_code == 401 and "登录" in r1.get_json()["message"]
        r2 = c.get("/api/user/records", headers={"Authorization": "Bearer bad.token"})
        assert r2.status_code == 401

    def test_expired_token(self, test_app):
        """过期 Token → 401，提示「过期」"""
        from datetime import datetime, timedelta, timezone

        payload = {"user_id": 1, "role": 0, "exp": datetime.now(timezone.utc) - timedelta(hours=1)}
        expired = pyjwt.encode(payload, test_app.config["SECRET_KEY"], algorithm="HS256")
        r = test_app.test_client().get("/api/user/records", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401 and "过期" in r.get_json()["message"]

    def test_role_permission_enforcement(self, test_app):
        """普通用户访问管理端 → 403「无权限」"""
        with test_app.app_context():
            token = create_token(user_id=1, role=0)
        r = test_app.test_client().get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403
