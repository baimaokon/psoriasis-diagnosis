"""
feedback.py — 诊断反馈路由（/api/feedback/*）
─────────────────────────────────────────────
实现"人机协同"纠错闭环：
  用户对 AI 诊断结果标记正确/错误 → 系统统计准确率 → 指导模型迭代
端点：
  GET  /api/feedback/labels         — 获取可选诊断标签列表（供纠错下拉框使用）
  POST /api/feedback/submit         — 提交反馈（每条记录限一次）
  GET  /api/feedback/record/<id>    — 查询单条记录的反馈状态
  GET  /api/feedback/my             — 当前用户的反馈列表
  GET  /api/feedback/batch          — 批量查询多条记录的反馈状态
  GET  /api/feedback/stats          — 基于反馈的 AI 准确率统计
依赖：
  models/diagnosis_feedback.py、diagnosis_record.py
  utils/label_mapping.py → LABEL_ZH_MAP 提供可纠错标签
前端对接：
  frontend/src/api/feedback.js → 反馈 API 封装
"""

from flask import Blueprint, g, jsonify, request

from app.models import DiagnosisFeedback, DiagnosisRecord, db
from app.utils import error, login_required, success
from app.utils.label_mapping import LABEL_ZH_MAP, get_label_info

feedback_bp = Blueprint("feedback", __name__, url_prefix="/api/feedback")


def _build_label_options():
    """构建可用于纠错下拉的完整标签列表"""
    options = []
    for label_en, label_zh in LABEL_ZH_MAP.items():
        options.append({
            "label_en": label_en,
            "label_zh": label_zh,
            "label_display": f"{label_zh}（{label_en}）",
        })
    return options


@feedback_bp.route("/labels", methods=["GET"])
@login_required
def available_labels():
    """返回所有可选的诊断标签（供用户纠错时选择）"""
    return jsonify(success(_build_label_options()))


@feedback_bp.route("/submit", methods=["POST"])
@login_required
def submit_feedback():
    """提交诊断反馈"""
    data = request.get_json(silent=True) or {}
    record_id = data.get("record_id")
    is_correct = data.get("is_correct")

    if record_id is None:
        return jsonify(error("请提供诊断记录ID")), 400
    if is_correct is None:
        return jsonify(error("请提供反馈类型（正确/错误）")), 400

    record = DiagnosisRecord.query.get(record_id)
    if not record:
        return jsonify(error("诊断记录不存在")), 404
    if record.user_id != g.user_id:
        return jsonify(error("无权对此记录提交反馈")), 403

    existing = DiagnosisFeedback.query.filter_by(record_id=record_id).first()
    if existing:
        return jsonify(error("已对此记录提交过反馈，无需重复提交")), 400

    corrected_label = None
    comment = None
    if not is_correct:
        corrected_label = (data.get("corrected_label") or "").strip()
        comment = (data.get("comment") or "").strip()
        if not corrected_label:
            return jsonify(error("请提供正确的诊断标签")), 400

    feedback = DiagnosisFeedback(
        record_id=record_id,
        user_id=g.user_id,
        is_correct=is_correct,
        corrected_label=corrected_label,
        comment=comment,
    )
    db.session.add(feedback)
    db.session.commit()

    return jsonify(success(feedback.to_dict(), message="反馈提交成功"))


@feedback_bp.route("/record/<int:record_id>", methods=["GET"])
@login_required
def get_record_feedback(record_id):
    """查询某条诊断记录的反馈状态"""
    record = DiagnosisRecord.query.get(record_id)
    if not record:
        return jsonify(error("诊断记录不存在")), 404

    fb = DiagnosisFeedback.query.filter_by(record_id=record_id).first()
    if not fb:
        return jsonify(success({"has_feedback": False, "feedback": None}))

    # 管理员可看所有反馈，普通用户只能看自己的
    if g.user_role != 1 and fb.user_id != g.user_id:
        return jsonify(success({"has_feedback": True, "feedback": {"id": fb.id, "is_correct": fb.is_correct}}))

    return jsonify(success({"has_feedback": True, "feedback": fb.to_dict()}))


@feedback_bp.route("/my", methods=["GET"])
@login_required
def my_feedback_list():
    """获取当前用户的所有反馈记录"""
    limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    page = max(int(request.args.get("page", 1)), 1)

    query = DiagnosisFeedback.query.filter_by(user_id=g.user_id) \
        .order_by(DiagnosisFeedback.created_at.desc())
    pagination = query.paginate(page=page, per_page=limit, error_out=False)

    rows = []
    for fb in pagination.items:
        row = fb.to_dict()
        row["predicted_label"] = fb.record.predicted_label if fb.record else ""
        rows.append(row)

    return jsonify(success({
        "list": rows,
        "page": page,
        "limit": limit,
        "total": pagination.total,
    }))


@feedback_bp.route("/batch", methods=["GET"])
@login_required
def batch_feedback():
    """批量查询多条记录的反馈状态"""
    ids_str = request.args.get("record_ids", "")
    if not ids_str:
        return jsonify(success({}))

    try:
        ids = [int(x.strip()) for x in ids_str.split(",") if x.strip()]
    except ValueError:
        return jsonify(error("record_ids 格式错误")), 400

    if len(ids) > 200:
        ids = ids[:200]

    records = DiagnosisRecord.query.filter(
        DiagnosisRecord.id.in_(ids),
        DiagnosisRecord.user_id == g.user_id,
    ).all()
    valid_ids = {r.id for r in records}

    feedbacks = DiagnosisFeedback.query.filter(
        DiagnosisFeedback.record_id.in_(ids)
    ).all()

    result = {}
    for fb in feedbacks:
        if fb.record_id in valid_ids:
            result[str(fb.record_id)] = {
                "has_feedback": True,
                "is_correct": fb.is_correct,
                "corrected_label": fb.corrected_label,
                "comment": fb.comment,
            }

    for rid in ids:
        if str(rid) not in result and rid in valid_ids:
            result[str(rid)] = {"has_feedback": False}

    return jsonify(success(result))


@feedback_bp.route("/stats", methods=["GET"])
@login_required
def feedback_stats():
    """人机协同效果评估：基于用户反馈计算 AI 准确率

    返回指标可用于论文中"决策支持系统准确率评估"章节的量化分析。
    """
    total = DiagnosisFeedback.query.filter_by(user_id=g.user_id).count()
    correct = DiagnosisFeedback.query.filter_by(user_id=g.user_id, is_correct=True).count()
    wrong = total - correct

    record_total = DiagnosisRecord.query.filter_by(user_id=g.user_id).count()
    feedback_rate = round(total / record_total * 100, 2) if record_total > 0 else 0
    correct_rate = round(correct / total * 100, 2) if total > 0 else 0

    return jsonify(success({
        "total_feedback": total,
        "correct_count": correct,
        "wrong_count": wrong,
        "feedback_rate": feedback_rate,
        "ai_accuracy_by_feedback": correct_rate,
        "total_records": record_total,
    }))
