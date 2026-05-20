"""
user.py — 用户表（users）
─────────────────────────
字段：id, username, password_hash, role(0=普通用户/1=管理员), created_at
消费方：
  routes/auth.py — 注册、登录、获取个人信息
  routes/admin.py — 仪表盘统计普通用户数
  utils/auth.py — JWT 创建/验证时通过 user_id 查找用户
"""
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.SmallInteger, default=0, nullable=False)  # 0=用户, 1=管理员
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def set_password(self, raw_password: str):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

