from .admin import admin_bp
from .auth import auth_bp
from .feedback import feedback_bp
from .test import test_bp
from .user import user_bp

__all__ = ["test_bp", "auth_bp", "user_bp", "admin_bp", "feedback_bp"]

