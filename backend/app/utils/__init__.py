"""
utils/ — 通用工具层
───────────────────
为整个后端提供横切关注点：
  auth.py → JWT 令牌签发与认证装饰器（被所有路由使用）
  response.py → 统一 JSON 响应格式 {code, message, data}（被所有路由使用）
  label_mapping.py → 10类皮肤病英文→中文映射（被 models、services、routes 使用）
  model_path.py → 模型文件路径解析兼容（被 inference_service、admin 使用）
"""
from .auth import admin_required, create_token, login_required
from .label_mapping import get_label_info
from .response import error, success

__all__ = [
    "success",
    "error",
    "create_token",
    "login_required",
    "admin_required",
    "get_label_info",
]
