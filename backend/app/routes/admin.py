"""
admin.py — 管理端路由（/api/admin/*）
─────────────────────────────────────
端点（全部需 @admin_required，仅 role=1 可访问）：
  仪表盘     GET  /api/admin/dashboard
  数据集     GET  /api/admin/dataset/summary | samples/random
  训练管理   POST /api/admin/train/start | GET /param-spec | GET /jobs
             POST /api/admin/train/jobs/<id>/terminate | revive | DELETE
  模型管理   GET  /api/admin/models | POST /models/<id>/activate | DELETE /models/<id>
  诊断记录   GET  /api/admin/records | DELETE /api/admin/records/<id>
  SSE推送    GET  /api/admin/train/stream（长连接，服务端实时推送训练进度）
  实验对比   GET  /api/admin/experiments/compare
  错误分析   GET  /api/admin/analysis/error-cases
SSE 流认证：通过查询参数 ?token= 传递 JWT，在 _decode_admin_stream_token() 中验证
依赖：
  所有 models、services/training_service.py（TrainingManager + TrainEventHub）
  services/dataset_service.py
前端对接：
  frontend/src/views/admin/Dashboard.vue → 管理端仪表盘
  frontend/src/api/admin.js → 所有管理端 API 调用
"""

import json
import queue
import time
from pathlib import Path

import jwt
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from sqlalchemy import or_

from app.models import DiagnosisRecord, ModelVersion, TrainingJob, User, db
from app.services import (
    get_dataset_summary,
    get_train_param_spec,
    has_job_checkpoint,
    normalize_train_params,
    remove_job_checkpoint,
    train_event_hub,
    training_manager,
)
from app.utils import admin_required, error, success
from app.utils.model_path import model_path_exists, resolve_model_path


admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _model_with_urls(item: ModelVersion):
    row = item.to_dict()
    row["file_exists"] = model_path_exists(
        item.model_path, current_app.config["MODEL_DIR"]
    )
    return row


def _resolve_heatmap_or_fallback(record: DiagnosisRecord):
    storage_dir = Path(current_app.config["STORAGE_DIR"])
    heatmap_path = record.heatmap_path
    if (storage_dir / heatmap_path).exists():
        return heatmap_path, False
    return record.image_path, True


def _is_sub_path(path: Path, root: Path):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _delete_model_file(model_path: str):
    model_root = Path(current_app.config["MODEL_DIR"]).resolve()
    try:
        full_path = resolve_model_path(model_path, model_root).resolve()
    except Exception:
        return False
    if not _is_sub_path(full_path, model_root):
        return False
    if full_path.exists() and full_path.is_file():
        full_path.unlink()
        return True
    return False


def _delete_storage_relative_file(relative_path: str):
    if not relative_path:
        return False
    root_dir = Path(current_app.config["STORAGE_DIR"]).resolve()
    rel_path = Path(relative_path)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return False
    full_path = (root_dir / rel_path).resolve()
    if not _is_sub_path(full_path, root_dir):
        return False
    if full_path.exists() and full_path.is_file():
        full_path.unlink()
        return True
    return False


def _is_record_file_referenced(relative_path: str):
    if not relative_path:
        return False
    row = (
        db.session.query(DiagnosisRecord.id)
        .filter(
            or_(
                DiagnosisRecord.image_path == relative_path,
                DiagnosisRecord.heatmap_path == relative_path,
            )
        )
        .first()
    )
    return row is not None


def _decode_admin_stream_token():
    token = (request.args.get("token") or "").strip()
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            current_app.config["SECRET_KEY"],
            algorithms=["HS256"],
        )
    except jwt.InvalidTokenError:
        return None
    if int(payload.get("role", 0)) != 1:
        return None
    return payload


def _sse_pack(event_name: str, payload: dict):
    """构建 SSE (Server-Sent Events) 格式的数据帧"""
    safe_payload = payload or {}
    return f"event: {event_name}\ndata: {json.dumps(safe_payload, ensure_ascii=False)}\n\n"


@admin_bp.route("/dataset/summary", methods=["GET"])
@admin_required
def dataset_summary():
    dataset_dir = request.args.get("dataset_dir") or str(current_app.config["DATASET_DIR"])
    try:
        summary = get_dataset_summary(dataset_dir)
    except Exception as exc:
        return jsonify(error(str(exc))), 400
    return jsonify(
        success(
            {
                "dataset_dir": summary.dataset_dir,
                "total_images": summary.total_images,
                "class_count": summary.class_count,
                "classes": summary.classes,
            }
        )
    )


@admin_bp.route("/dataset/classes/<class_name>/samples", methods=["GET"])
@admin_required
def class_samples(class_name):
    """获取指定类别的样本缩略图列表"""
    from urllib.parse import unquote
    
    dataset_dir = request.args.get("dataset_dir") or str(current_app.config["DATASET_DIR"])
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 30)), 10), 100)
    
    try:
        from pathlib import Path
        from app.services.dataset_service import resolve_dataset_path
        from app.utils.label_mapping import get_label_info
        
        root = resolve_dataset_path(dataset_dir)
        if not root.exists():
            return jsonify(error(f"数据集目录不存在: {root}")), 404
        
        class_dir = root / unquote(class_name)
        if not class_dir.exists() or not class_dir.is_dir():
            return jsonify(error(f"类别目录不存在: {class_name}")), 404
        
        SUPPORTED_IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        image_files = []
        
        for file_path in sorted(class_dir.rglob("*")):
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_IMAGE_SUFFIX:
                relative_path = str(file_path.relative_to(root))
                image_files.append({
                    "filename": file_path.name,
                    "relative_path": relative_path,
                    "url": f"/api/files/datasets/{relative_path}"
                })
        
        total = len(image_files)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_samples = image_files[start:end]
        
        return jsonify(success({
            "class_name": class_name,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "samples": paginated_samples
        }))
    except Exception as exc:
        current_app.logger.error(f"获取类别样本失败: {exc}")
        return jsonify(error(str(exc))), 500


@admin_bp.route("/dataset/samples/random", methods=["GET"])
@admin_required
def random_samples():
    """随机获取各类别的样本（用于概览展示）"""
    from app.services.dataset_service import resolve_dataset_path
    
    dataset_dir = request.args.get("dataset_dir") or str(current_app.config["DATASET_DIR"])
    per_class = min(max(int(request.args.get("per_class", 8)), 1), 20)
    
    try:
        import random
        from pathlib import Path
        
        root = resolve_dataset_path(dataset_dir)
        if not root.exists():
            return jsonify(error(f"数据集目录不存在: {root}")), 404
        
        SUPPORTED_IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        result = {}
        
        for class_dir in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if not class_dir.is_dir():
                continue
            
            class_files = []
            for file_path in class_dir.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_IMAGE_SUFFIX:
                    relative_path = str(file_path.relative_to(root))
                    class_files.append({
                        "filename": file_path.name,
                        "relative_path": relative_path,
                        "url": f"/api/files/datasets/{relative_path.replace(chr(92), '/')}"
                    })
            
            if class_files:
                sampled = random.sample(class_files, min(per_class, len(class_files)))
                result[class_dir.name] = sampled
        
        return jsonify(success(result))
    except Exception as exc:
        return jsonify(error(str(exc))), 500


@admin_bp.route("/train/param-spec", methods=["GET"])
@admin_required
def train_param_spec():
    return jsonify(success(get_train_param_spec()))


@admin_bp.route("/train/start", methods=["POST"])
@admin_required
def train_start():
    training_manager.recover_stale_jobs()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip() or "银屑病训练任务"
    dataset_dir = data.get("dataset_dir") or str(current_app.config["DATASET_DIR"])
    raw_params = data.get("params") or {}

    if training_manager.has_running_job():
        return jsonify(error("已有训练任务在运行，请等待当前任务完成")), 400

    try:
        params = normalize_train_params(raw_params)
        summary = get_dataset_summary(dataset_dir)
    except Exception as exc:
        return jsonify(error(str(exc))), 400

    job = TrainingJob(
        name=name,
        status="queued",
        dataset_dir=summary.dataset_dir,
        total_epochs=params["epochs"],
        message="任务已创建，等待启动",
    )
    job.set_params(params)
    db.session.add(job)
    db.session.commit()

    try:
        training_manager.start(current_app._get_current_object(), job.id)
    except Exception as exc:
        job = TrainingJob.query.get(job.id)
        if job:
            job.status = "failed"
            job.message = str(exc)
            db.session.commit()
        return jsonify(error(str(exc))), 400
    train_event_hub.publish(
        "job_update",
        {"type": "queued", "job": job.to_dict()},
    )
    return jsonify(success(job.to_dict(), message="训练任务已启动"))


@admin_bp.route("/train/jobs", methods=["GET"])
@admin_required
def train_jobs():
    training_manager.recover_stale_jobs()
    limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    jobs = TrainingJob.query.order_by(TrainingJob.created_at.desc()).limit(limit).all()
    return jsonify(success([item.to_dict() for item in jobs]))


@admin_bp.route("/train/jobs/<int:job_id>", methods=["GET"])
@admin_required
def train_job_detail(job_id):
    training_manager.recover_stale_jobs()
    job = TrainingJob.query.get(job_id)
    if not job:
        return jsonify(error("训练任务不存在")), 404
    return jsonify(success(job.to_dict()))


@admin_bp.route("/models", methods=["GET"])
@admin_required
def model_list():
    rows = ModelVersion.query.order_by(ModelVersion.created_at.desc()).all()
    return jsonify(success([_model_with_urls(item) for item in rows]))


@admin_bp.route("/models/<int:model_id>/activate", methods=["POST"])
@admin_required
def model_activate(model_id):
    target = ModelVersion.query.get(model_id)
    if not target:
        return jsonify(error("模型不存在")), 404
    if not model_path_exists(target.model_path, current_app.config["MODEL_DIR"]):
        return jsonify(error("模型文件不存在，无法上线")), 400

    ModelVersion.query.update({"is_active": False})
    target.is_active = True
    db.session.commit()
    return jsonify(success(target.to_dict(), message="模型已上线"))


@admin_bp.route("/models/<int:model_id>", methods=["DELETE"])
@admin_required
def model_delete(model_id):
    target = ModelVersion.query.get(model_id)
    if not target:
        return jsonify(error("模型不存在")), 404

    model_path = target.model_path
    was_active = bool(target.is_active)

    TrainingJob.query.filter_by(model_version_id=model_id).update(
        {"model_version_id": None}
    )
    db.session.delete(target)
    db.session.flush()

    activated_model_id = None
    if was_active:
        replacement = (
            ModelVersion.query.order_by(
                ModelVersion.created_at.desc(), ModelVersion.id.desc()
            ).first()
        )
        if replacement:
            replacement.is_active = True
            activated_model_id = replacement.id

    db.session.commit()
    file_deleted = _delete_model_file(model_path)
    return jsonify(
        success(
            {
                "deleted_id": model_id,
                "file_deleted": file_deleted,
                "activated_model_id": activated_model_id,
            },
            message="模型已删除",
        )
    )


@admin_bp.route("/records", methods=["GET"])
@admin_required
def record_list():
    limit = min(max(int(request.args.get("limit", 50)), 1), 300)
    keyword = (request.args.get("keyword") or "").strip().lower()

    query = DiagnosisRecord.query.join(User, DiagnosisRecord.user_id == User.id).order_by(
        DiagnosisRecord.created_at.desc()
    )
    rows = query.limit(500 if keyword else limit).all()

    data = []
    for item in rows:
        row = item.to_dict()
        heatmap_path, heatmap_fallback = _resolve_heatmap_or_fallback(item)
        row["image_url"] = f"/api/files/{item.image_path}"
        row["heatmap_url"] = f"/api/files/{heatmap_path}"
        row["heatmap_fallback"] = heatmap_fallback
        if keyword:
            if (
                keyword not in (row.get("username") or "").lower()
                and keyword not in (row.get("predicted_label_zh") or "").lower()
                and keyword not in (row.get("predicted_label_en") or "").lower()
            ):
                continue
        data.append(row)
        if len(data) >= limit:
            break
    return jsonify(success(data))


@admin_bp.route("/records/<int:record_id>", methods=["DELETE"])
@admin_required
def record_delete(record_id):
    target = DiagnosisRecord.query.get(record_id)
    if not target:
        return jsonify(error("诊断记录不存在")), 404

    related_paths = {target.image_path, target.heatmap_path}
    db.session.delete(target)
    db.session.commit()

    removed_files = []
    for item in related_paths:
        if not item:
            continue
        if _is_record_file_referenced(item):
            continue
        if _delete_storage_relative_file(item):
            removed_files.append(item)

    return jsonify(
        success(
            {
                "deleted_id": record_id,
                "removed_files": removed_files,
            },
            message="诊断记录已删除",
        )
    )


@admin_bp.route("/train/jobs/<int:job_id>", methods=["DELETE"])
@admin_required
def train_job_delete(job_id):
    training_manager.recover_stale_jobs()
    target = TrainingJob.query.get(job_id)
    if not target:
        return jsonify(error("训练任务不存在")), 404

    if target.status in {"running", "canceling"}:
        accepted = training_manager.request_cancel(job_id, delete_after=True)
        if accepted:
            target.status = "canceling"
            target.message = "已请求终止并删除，等待训练线程结束"
            db.session.commit()
            train_event_hub.publish(
                "job_update",
                {"type": "canceling", "job": target.to_dict()},
            )
            return jsonify(
                success(
                    {"job_id": job_id, "pending": True},
                    message="已请求终止并删除",
                )
            )

    db.session.delete(target)
    db.session.commit()
    remove_job_checkpoint(current_app.config["CHECKPOINT_DIR"], job_id)
    train_event_hub.publish("job_deleted", {"job_id": job_id, "reason": "manual_delete"})
    return jsonify(success({"deleted_id": job_id}, message="训练任务已删除"))


@admin_bp.route("/train/jobs/<int:job_id>/terminate", methods=["POST"])
@admin_required
def train_job_terminate(job_id):
    training_manager.recover_stale_jobs()
    target = TrainingJob.query.get(job_id)
    if not target:
        return jsonify(error("训练任务不存在")), 404
    if target.status in {"success", "failed", "canceled"}:
        return jsonify(error("该任务已结束，无需终止")), 400

    accepted = training_manager.request_cancel(job_id, delete_after=False)
    if not accepted:
        target.status = "failed"
        target.message = "训练线程已中断，可点击复活重新启动"
        db.session.commit()
        train_event_hub.publish(
            "job_update",
            {"type": "failed", "job": target.to_dict()},
        )
        return jsonify(error("任务线程不在运行状态，已标记为失败")), 400

    target.status = "canceling"
    target.message = "已请求终止，等待当前批次安全退出"
    db.session.commit()
    train_event_hub.publish(
        "job_update",
        {"type": "canceling", "job": target.to_dict()},
    )
    return jsonify(success(target.to_dict(), message="终止请求已提交"))


@admin_bp.route("/train/jobs/<int:job_id>/revive", methods=["POST"])
@admin_required
def train_job_revive(job_id):
    training_manager.recover_stale_jobs()
    source = TrainingJob.query.get(job_id)
    if not source:
        return jsonify(error("训练任务不存在")), 404
    if training_manager.has_running_job():
        return jsonify(error("已有训练任务在运行，请先终止当前任务")), 400
    if source.status in {"running", "canceling"} and training_manager.is_job_running(job_id):
        return jsonify(error("该任务仍在运行，无法复活")), 400
    resume_from_checkpoint = has_job_checkpoint(
        current_app.config["CHECKPOINT_DIR"], source.id
    )

    try:
        params = normalize_train_params(source.get_params())
        summary = get_dataset_summary(source.dataset_dir)
    except Exception as exc:
        return jsonify(error(str(exc))), 400

    revived = TrainingJob(
        name=f"{source.name}-复活",
        status="queued",
        dataset_dir=summary.dataset_dir,
        total_epochs=params["epochs"],
        message=(
            f"由任务#{source.id}复活创建，"
            + ("准备从检查点续训" if resume_from_checkpoint else "未找到检查点，将从头开始")
        ),
    )
    revived.set_params(params)
    if resume_from_checkpoint:
        revived.progress = float(source.progress or 0.0)
        revived.current_epoch = int(source.current_epoch or 0)
        revived.train_loss = float(source.train_loss or 0.0)
        revived.val_loss = float(source.val_loss or 0.0)
        revived.val_accuracy = float(source.val_accuracy or 0.0)
        revived.val_precision = float(source.val_precision or 0.0)
        revived.val_recall = float(source.val_recall or 0.0)
        revived.val_f1 = float(source.val_f1 or 0.0)
        source_logs = source.get_logs()
        if isinstance(source_logs, list) and source_logs:
            revived.set_logs(source_logs[-200:])
    db.session.add(revived)
    db.session.commit()

    try:
        training_manager.start(
            current_app._get_current_object(),
            revived.id,
            resume_from_job_id=source.id if resume_from_checkpoint else 0,
        )
    except Exception as exc:
        revived = TrainingJob.query.get(revived.id)
        if revived:
            revived.status = "failed"
            revived.message = str(exc)
            db.session.commit()
        return jsonify(error(str(exc))), 400

    train_event_hub.publish(
        "job_update",
        {"type": "queued", "job": revived.to_dict()},
    )
    return jsonify(
        success(
            {
                "source_job_id": source.id,
                "job": revived.to_dict(),
                "resume_from_checkpoint": bool(resume_from_checkpoint),
            },
            message=(
                "复活任务已启动（已从检查点续训）"
                if resume_from_checkpoint
                else "复活任务已启动（未找到检查点，已从头训练）"
            ),
        )
    )


@admin_bp.route("/dashboard", methods=["GET"])
@admin_required
def dashboard():
    training_manager.recover_stale_jobs()
    user_count = User.query.filter_by(role=0).count()
    model_count = ModelVersion.query.count()
    record_count = DiagnosisRecord.query.count()
    latest_job = (
        TrainingJob.query.order_by(TrainingJob.created_at.desc()).first()
    )
    active_model = ModelVersion.query.filter_by(is_active=True).first()
    return jsonify(
        success(
            {
                "user_count": user_count,
                "model_count": model_count,
                "record_count": record_count,
                "latest_job": latest_job.to_dict() if latest_job else None,
                "active_model": active_model.to_dict() if active_model else None,
                "is_training": training_manager.has_running_job(),
            }
        )
    )


@admin_bp.route("/train/stream", methods=["GET"])
def train_stream():
    """训练进度实时推送（SSE 长连接）

    客户端通过 EventSource 连接此端点，服务端通过 TrainEventHub 发布/订阅模式
    将训练进度、状态变更实时推送到前端，前端无需轮询。
    每 20 秒发送心跳包保持连接，同时自动检测并清理僵尸训练任务。
    """
    payload = _decode_admin_stream_token()
    if not payload:
        return Response("unauthorized", status=401)

    training_manager.recover_stale_jobs()

    @stream_with_context
    def _event_stream():
        subscriber_id, event_queue = train_event_hub.subscribe()
        try:
            yield _sse_pack(
                "sync",
                {"message": "connected", "at": int(time.time())},
            )
            while True:
                try:
                    event_name, data = event_queue.get(timeout=20)
                    yield _sse_pack(event_name, data)
                except queue.Empty:
                    # 心跳 + 僵尸任务回收
                    training_manager.recover_stale_jobs()
                    yield _sse_pack("heartbeat", {"at": int(time.time())})
        finally:
            train_event_hub.unsubscribe(subscriber_id)

    response = Response(_event_stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response


@admin_bp.route("/experiments/compare", methods=["GET"])
@admin_required
def compare_experiments():
    """模型对比与实验管理"""
    job_ids = request.args.getlist("job_ids")
    if not job_ids:
        return jsonify(error("请提供要对比的任务ID")), 400
    
    jobs = TrainingJob.query.filter(TrainingJob.id.in_(job_ids)).all()
    results = []
    for job in jobs:
        data = job.to_dict()
        # 提取关键指标用于对比
        data["metrics"] = {
            "val_accuracy": job.val_accuracy,
            "val_f1": job.val_f1,
            "val_precision": job.val_precision,
            "val_recall": job.val_recall,
            "duration": (job.finished_at - job.started_at).total_seconds() if job.finished_at and job.started_at else None
        }
        results.append(data)
    
    return jsonify(success(results))


@admin_bp.route("/training/<int:job_id>/visualization", methods=["GET"])
@admin_required
def training_visualization(job_id):
    """训练过程可视化数据"""
    job = TrainingJob.query.get_or_404(job_id)
    logs = job.get_logs()
    
    # 提取 Loss 和 Accuracy 曲线数据
    epochs = []
    train_losses = []
    val_losses = []
    val_accuracies = []
    
    for log in logs:
        if log.get("type") == "epoch_summary":
            epochs.append(log["epoch"])
            train_losses.append(log.get("train_loss", 0))
            val_losses.append(log.get("val_loss", 0))
            val_accuracies.append(log.get("val_accuracy", 0))
            
    return jsonify(success({
        "epochs": epochs,
        "train_losses": train_losses,
        "val_losses": val_losses,
        "val_accuracies": val_accuracies
    }))


@admin_bp.route("/analysis/error-cases", methods=["GET"])
@admin_required
def error_cases_analysis():
    """错误案例分析（低置信度或疑似误诊）"""
    limit = int(request.args.get("limit", 20))
    # 查找置信度较低但有明确预测的记录
    records = DiagnosisRecord.query.order_by(DiagnosisRecord.confidence.asc()).limit(limit).all()
    
    cases = []
    for record in records:
        row = record.to_dict()
        heatmap_path, _ = _resolve_heatmap_or_fallback(record)
        row["image_url"] = _build_file_url(record.image_path)
        row["heatmap_url"] = _build_file_url(heatmap_path)
        cases.append(row)
        
    return jsonify(success(cases))
