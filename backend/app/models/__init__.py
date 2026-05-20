"""
models/ — 数据持久化层（SQLAlchemy ORM）
────────────────────────────────────────
本包定义数据库全部5张表的结构，是系统所有数据读写的唯一入口。
每张表对应一个模型类，通过 Flask-SQLAlchemy 映射到 MySQL。
对外统一导出：from app.models import db, User, TrainingJob, ModelVersion, DiagnosisRecord, DiagnosisFeedback

连接关系：
  models → app/extensions.py（db实例）
  models → app/utils/label_mapping.py（标签中英文映射）
  被 routes/（所有路由模块）和 services/（推理、训练、报告服务）消费
"""
from app.extensions import db

from .diagnosis_feedback import DiagnosisFeedback
from .diagnosis_record import DiagnosisRecord
from .model_version import ModelVersion
from .training_job import TrainingJob
from .user import User

__all__ = [
    "db",
    "User",
    "TrainingJob",
    "ModelVersion",
    "DiagnosisRecord",
    "DiagnosisFeedback",
]

