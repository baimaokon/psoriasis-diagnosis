import json
from datetime import datetime

from app.extensions import db


class ModelVersion(db.Model):
    __tablename__ = "model_versions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    backbone = db.Column(db.String(50), nullable=False)
    model_path = db.Column(db.String(500), nullable=False)
    
    # 使用 Text 存储 JSON（兼容性好）
    params_json = db.Column(db.Text, nullable=False, default="{}")
    metrics_json = db.Column(db.Text, nullable=False, default="{}")
    labels_json = db.Column(db.Text, nullable=False, default="[]")
    
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    jobs = db.relationship("TrainingJob", backref="model_version", lazy=True)

    def get_params(self):
        try:
            return json.loads(self.params_json or "{}")
        except json.JSONDecodeError:
            return {}

    def get_metrics(self):
        try:
            return json.loads(self.metrics_json or "{}")
        except json.JSONDecodeError:
            return {}

    def get_labels(self):
        try:
            return json.loads(self.labels_json or "[]")
        except json.JSONDecodeError:
            return []

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "backbone": self.backbone,
            "model_path": self.model_path,
            "params": self.get_params(),
            "metrics": self.get_metrics(),
            "labels": self.get_labels(),
            "is_active": bool(self.is_active),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

