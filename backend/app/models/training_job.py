import json
from datetime import datetime

from sqlalchemy.dialects.mysql import JSON as MySQL_JSON
from app.extensions import db


class TrainingJob(db.Model):
    __tablename__ = "training_jobs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default="queued", nullable=False)
    dataset_dir = db.Column(db.String(500), nullable=False)
    
    # 使用 MySQL JSON 类型（MySQL 5.7+），如果不支持则降级为 Text
    params_json = db.Column(
        db.Text, 
        nullable=False, 
        default="{}"
    )
    logs_json = db.Column(
        db.Text, 
        nullable=False, 
        default="[]"
    )
    
    message = db.Column(db.String(255), default="", nullable=False)

    progress = db.Column(db.Float, default=0.0, nullable=False)
    current_epoch = db.Column(db.Integer, default=0, nullable=False)
    total_epochs = db.Column(db.Integer, default=0, nullable=False)

    train_loss = db.Column(db.Float, default=0.0, nullable=False)
    val_loss = db.Column(db.Float, default=0.0, nullable=False)
    val_accuracy = db.Column(db.Float, default=0.0, nullable=False)
    val_precision = db.Column(db.Float, default=0.0, nullable=False)
    val_recall = db.Column(db.Float, default=0.0, nullable=False)
    val_f1 = db.Column(db.Float, default=0.0, nullable=False)

    model_version_id = db.Column(db.Integer, db.ForeignKey("model_versions.id"))

    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)

    def get_params(self):
        try:
            return json.loads(self.params_json or "{}")
        except json.JSONDecodeError:
            return {}

    def set_params(self, payload):
        self.params_json = json.dumps(payload, ensure_ascii=False)

    def get_logs(self):
        try:
            return json.loads(self.logs_json or "[]")
        except json.JSONDecodeError:
            return []

    def set_logs(self, logs):
        self.logs_json = json.dumps(logs, ensure_ascii=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "dataset_dir": self.dataset_dir,
            "params": self.get_params(),
            "logs": self.get_logs(),
            "message": self.message,
            "progress": round(float(self.progress or 0.0), 2),
            "current_epoch": self.current_epoch,
            "total_epochs": self.total_epochs,
            "train_loss": round(float(self.train_loss or 0.0), 6),
            "val_loss": round(float(self.val_loss or 0.0), 6),
            "val_accuracy": round(float(self.val_accuracy or 0.0), 6),
            "val_precision": round(float(self.val_precision or 0.0), 6),
            "val_recall": round(float(self.val_recall or 0.0), 6),
            "val_f1": round(float(self.val_f1 or 0.0), 6),
            "model_version_id": self.model_version_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S")
            if self.started_at
            else None,
            "finished_at": self.finished_at.strftime("%Y-%m-%d %H:%M:%S")
            if self.finished_at
            else None,
        }

