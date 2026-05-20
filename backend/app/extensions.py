"""
extensions.py — Flask 扩展实例化
─────────────────────────────────
职责：创建 SQLAlchemy 数据库实例（db），供 Flask 工厂函数和所有模型文件共享。
被 app/__init__.py 通过 db.init_app(app) 绑定到 Flask 应用。
被 app/models/ 下所有模型文件引用（from app.extensions import db）。
"""
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()

