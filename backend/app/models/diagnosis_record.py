import json
from datetime import datetime

from app.extensions import db
from app.utils.label_mapping import get_label_info


class DiagnosisRecord(db.Model):
    __tablename__ = "diagnosis_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    image_path = db.Column(db.String(500), nullable=False)
    heatmap_path = db.Column(db.String(500), nullable=False)
    predicted_label = db.Column(db.String(200), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    prediction_json = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    user = db.relationship("User", backref=db.backref("diagnosis_records", lazy=True))

    def set_predictions(self, payload):
        self.prediction_json = json.dumps(payload, ensure_ascii=False)

    def get_predictions(self):
        try:
            return json.loads(self.prediction_json or "[]")
        except json.JSONDecodeError:
            return []

    def to_dict(self):
        label_info = get_label_info(self.predicted_label)
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else "",
            "image_path": self.image_path,
            "heatmap_path": self.heatmap_path,
            "predicted_label": label_info["label_display"],
            "predicted_label_en": label_info["label_en"],
            "predicted_label_zh": label_info["label_zh"],
            "is_psoriasis_related": label_info["is_psoriasis_related"],
            "confidence": round(float(self.confidence or 0.0), 6),
            "predictions": self.get_predictions(),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
