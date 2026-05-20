"""
diagnosis_feedback.py — 诊断反馈表（diagnosis_feedback）
────────────────────────────────────────────────────────
字段：id, record_id(FK→diagnosis_records), user_id(FK→users),
      is_correct, corrected_label, comment, created_at
作用：记录用户对AI诊断结果的纠错反馈，实现"人机协同"闭环。
      每条诊断记录只允许一次反馈（uselist=False 一对一关系）。
消费方：routes/feedback.py — 提交反馈、查询统计、计算 AI 准确率
"""
from datetime import datetime

from app.extensions import db


class DiagnosisFeedback(db.Model):
    __tablename__ = "diagnosis_feedback"

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("diagnosis_records.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    corrected_label = db.Column(db.String(200), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    record = db.relationship("DiagnosisRecord", backref=db.backref("feedback", lazy=True, uselist=False))
    user = db.relationship("User", backref=db.backref("feedbacks", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "user_id": self.user_id,
            "is_correct": bool(self.is_correct),
            "corrected_label": self.corrected_label,
            "comment": self.comment,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
