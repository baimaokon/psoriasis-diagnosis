"""
routes/ — API 路由层（HTTP 入口）
──────────────────────────────────
将后端功能对外暴露为 RESTful API，共 5 个 Blueprint：
  test_bp   → 健康检查与调试端点（/api/test/*）
  auth_bp   → 认证端点：注册/登录/获取个人信息（/api/auth/*）
  user_bp   → 用户端端点：诊断/历史记录/PDF报告（/api/user/*）
  admin_bp  → 管理端端点：仪表盘/数据集/训练/模型/SSE（/api/admin/*）
  feedback_bp → 反馈端点：纠错提交/统计（/api/feedback/*）
在 app/__init__.py create_app() 中注册到 Flask 应用。
"""

from .admin import admin_bp
from .auth import auth_bp
from .feedback import feedback_bp
from .test import test_bp
from .user import user_bp

__all__ = ["test_bp", "auth_bp", "user_bp", "admin_bp", "feedback_bp"]

