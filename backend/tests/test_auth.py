import pytest
import jwt as pyjwt

from app.utils.auth import create_token
from app.utils.response import error as error_response


class TestCreateToken:
    def test_returns_string_token(self, test_app):
        with test_app.app_context():
            token = create_token(user_id=42, role=0)
        assert isinstance(token, str)
        assert len(token) > 20

    def test_encodes_user_id_and_role(self, test_app):
        with test_app.app_context():
            token = create_token(user_id=99, role=1)
            payload = pyjwt.decode(
                token, test_app.config["SECRET_KEY"], algorithms=["HS256"]
            )
        assert payload["user_id"] == 99
        assert payload["role"] == 1

    def test_different_users_produce_different_tokens(self, test_app):
        with test_app.app_context():
            t1 = create_token(user_id=1, role=0)
            t2 = create_token(user_id=2, role=0)
        assert t1 != t2

    def test_default_expiry_is_seven_days(self, test_app):
        from datetime import datetime, timezone

        with test_app.app_context():
            token = create_token(user_id=1, role=0)
            payload = pyjwt.decode(
                token, test_app.config["SECRET_KEY"], algorithms=["HS256"],
                options={"verify_exp": False},
            )
        now = datetime.now(timezone.utc)
        diff = payload["exp"] - int(now.timestamp())
        assert 6 * 86400 <= diff <= 8 * 86400  # ~7 days


class TestAuthEndpoints:
    def test_records_returns_401_without_token(self, test_app):
        client = test_app.test_client()
        resp = client.get("/api/user/records")
        assert resp.status_code == 401
        data = resp.get_json()
        assert "登录" in data.get("message", "")

    def test_records_returns_401_with_invalid_token(self, test_app):
        client = test_app.test_client()
        resp = client.get(
            "/api/user/records",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_user_cannot_access_admin_dashboard(self, test_app):
        with test_app.app_context():
            token = create_token(user_id=1, role=0)
        client = test_app.test_client()
        resp = client.get(
            "/api/admin/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
