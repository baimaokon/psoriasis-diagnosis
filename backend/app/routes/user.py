import io
import uuid
from pathlib import Path

from flask import Blueprint, Response, current_app, g, jsonify, request, send_file
from werkzeug.utils import secure_filename

from app.models import DiagnosisRecord, User, db
from app.services import generate_report_response, inference_engine
from app.utils import error, login_required, success


user_bp = Blueprint("user", __name__, url_prefix="/api/user")

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'bmp', 'webp'}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


def _validate_image_file(file):
    """
    完整的图片文件验证
    
    Args:
        file: Flask FileStorage 对象
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    # 1. 检查文件对象
    if not file or not file.filename:
        return False, "请选择文件"
    
    # 2. 安全检查文件名
    original_filename = secure_filename(file.filename)
    if not original_filename:
        return False, "无效的文件名"
    
    # 3. 检查扩展名
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"不支持的文件格式（支持：{', '.join(ALLOWED_EXTENSIONS)}）"
    
    # 4. 检查文件大小（seek 到末尾读取，再重置指针）
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    
    if size == 0:
        return False, "文件为空"
    
    if size > MAX_IMAGE_SIZE:
        return False, f"文件大小超过 {MAX_IMAGE_SIZE // 1024 // 1024}MB 限制"
    
    # 5. 读取文件内容用于魔数校验和 PIL 验证，读取后重置指针
    file_bytes = file.read()
    file.seek(0)

    # 6. 魔数校验：验证文件头与实际类型一致，防止伪装扩展名的恶意文件
    try:
        import imghdr
        detected_type = imghdr.what(None, file_bytes)
        
        # imghdr 可能返回 None 或不准确的类型
        if detected_type:
            # 映射 imghdr 返回的类型到允许的扩展名
            type_to_ext = {
                'jpeg': ['jpg', 'jpeg'],
                'png': ['png'],
                'bmp': ['bmp'],
                'gif': ['gif'],  # GIF 不在允许列表中
                'webp': ['webp'],
            }
            
            allowed_exts = type_to_ext.get(detected_type, [])
            if ext not in allowed_exts:
                return False, f"文件类型与扩展名不匹配（检测为 {detected_type}）"
    except Exception:
        # imghdr 失败时继续，依赖后续 PIL 验证
        pass
    
    # 7. 使用 PIL 双重验证（最可靠）
    try:
        from PIL import Image
        image = Image.open(io.BytesIO(file_bytes))
        image.verify()  # 验证图片完整性
        
        # 重新打开以检查图片尺寸（防止像素炸弹攻击）
        image = Image.open(io.BytesIO(file_bytes))
        width, height = image.size
        
        # 检查图片尺寸合理性
        max_dimension = 10000  # 最大边长 10000px
        if width > max_dimension or height > max_dimension:
            return False, f"图片尺寸过大（{width}x{height}），最大支持 {max_dimension}x{max_dimension}"
        
        min_dimension = 10  # 最小边长 10px
        if width < min_dimension or height < min_dimension:
            return False, f"图片尺寸过小（{width}x{height}），最小支持 {min_dimension}x{min_dimension}"
        
    except Exception as e:
        return False, f"图片文件损坏或格式错误：{str(e)}"
    
    return True, None


def _build_file_url(relative_path: str):
    return f"/api/files/{relative_path}"


def _resolve_heatmap_or_fallback(record: DiagnosisRecord):
    storage_dir = Path(current_app.config["STORAGE_DIR"])
    heatmap_path = record.heatmap_path
    full_heatmap = storage_dir / heatmap_path
    if full_heatmap.exists():
        return heatmap_path, False
    return record.image_path, True


@user_bp.route("/diagnose", methods=["POST"])
@login_required
def diagnose():
    if "image" not in request.files:
        return jsonify(error("请上传图像文件，字段名应为image")), 400
    
    file = request.files["image"]
    
    # 执行完整的文件验证
    is_valid, error_msg = _validate_image_file(file)
    if not is_valid:
        return jsonify(error(error_msg)), 400
    
    upload_dir = Path(current_app.config["UPLOAD_DIR"])
    heatmap_dir = Path(current_app.config["HEATMAP_DIR"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    heatmap_dir.mkdir(parents=True, exist_ok=True)

    # 使用 UUID 生成安全的文件名，保留原始扩展名
    original_filename = secure_filename(file.filename)
    suffix = f".{original_filename.rsplit('.', 1)[1].lower()}" if '.' in original_filename else '.jpg'
    file_name = f"{uuid.uuid4().hex}{suffix}"
    full_image_path = upload_dir / file_name
    
    # 保存文件
    try:
        file.save(full_image_path)
    except Exception as e:
        current_app.logger.error(f"文件保存失败：{e}")
        return jsonify(error("文件保存失败，请重试")), 500
    
    # 验证文件是否成功保存且大小合理
    if not full_image_path.exists():
        return jsonify(error("文件保存失败")), 500
    
    saved_size = full_image_path.stat().st_size
    if saved_size == 0:
        full_image_path.unlink(missing_ok=True)
        return jsonify(error("文件保存异常")), 500

    try:
        prediction = inference_engine.predict(
            image_path=str(full_image_path),
            heatmap_dir=str(heatmap_dir),
        )
    except Exception as exc:
        # 诊断失败时删除上传的文件
        full_image_path.unlink(missing_ok=True)
        current_app.logger.error(f"诊断失败：{exc}")
        return jsonify(error(f"诊断失败：{str(exc)}")), 400

    image_rel_path = f"uploads/{file_name}"
    heatmap_rel_path = f"heatmaps/{prediction['heatmap_file']}"

    record = DiagnosisRecord(
        user_id=g.user_id,
        image_path=image_rel_path,
        heatmap_path=heatmap_rel_path,
        predicted_label=prediction["predicted_label_en"],
        confidence=prediction["confidence"],
    )
    record.set_predictions(prediction["predictions"])
    db.session.add(record)
    db.session.commit()

    row = record.to_dict()
    heatmap_path, heatmap_fallback = _resolve_heatmap_or_fallback(record)
    row["image_url"] = _build_file_url(record.image_path)
    row["heatmap_url"] = _build_file_url(heatmap_path)
    row["heatmap_fallback"] = heatmap_fallback
    return jsonify(success(row, message="诊断完成"))


@user_bp.route("/records/<int:record_id>/report", methods=["GET"])
@login_required
def download_report(record_id):
    """下载诊断报告 PDF"""
    record = DiagnosisRecord.query.get(record_id)
    if not record:
        return jsonify(error("诊断记录不存在")), 404
    if record.user_id != g.user_id:
        return jsonify(error("无权访问此记录")), 403

    user = User.query.get(g.user_id)
    username = user.username if user else "未知用户"

    try:
        pdf_bytes, filename = generate_report_response(record.to_dict(), username)
    except Exception as exc:
        current_app.logger.error(f"生成报告失败：{exc}")
        return jsonify(error("报告生成失败，请稍后重试")), 500

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@user_bp.route("/records", methods=["GET"])
@login_required
def my_records():
    limit = min(max(int(request.args.get("limit", 20)), 1), 200)
    page = max(int(request.args.get("page", 1)), 1)
    query = DiagnosisRecord.query.filter_by(user_id=g.user_id)
    
    # 新增筛选逻辑
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    disease = request.args.get("disease")
    min_conf = request.args.get("min_confidence")

    if start_date:
        query = query.filter(DiagnosisRecord.created_at >= start_date)
    if end_date:
        query = query.filter(DiagnosisRecord.created_at <= end_date + ' 23:59:59')
    if disease:
        query = query.filter(DiagnosisRecord.predicted_label_zh.like(f"%{disease}%"))
    if min_conf:
        query = query.filter(DiagnosisRecord.confidence >= float(min_conf))

    query = query.order_by(DiagnosisRecord.created_at.desc())
    pagination = query.paginate(page=page, per_page=limit, error_out=False)

    rows = []
    for item in pagination.items:
        row = item.to_dict()
        heatmap_path, heatmap_fallback = _resolve_heatmap_or_fallback(item)
        row["image_url"] = _build_file_url(item.image_path)
        row["heatmap_url"] = _build_file_url(heatmap_path)
        row["heatmap_fallback"] = heatmap_fallback
        rows.append(row)

    return jsonify(
        success({"list": rows, "page": page, "limit": limit, "total": pagination.total})
    )


@user_bp.route("/diagnose/batch", methods=["POST"])
@login_required
def diagnose_batch():
    if "images" not in request.files:
        return jsonify(error("请上传图像文件")), 400
    
    files = request.files.getlist("images")
    if not files:
        return jsonify(error("未找到文件")), 400
    if len(files) > 10:
        return jsonify(error("一次最多支持10张图像")), 400

    results = []
    for idx, file in enumerate(files):
        is_valid, error_msg = _validate_image_file(file)
        if not is_valid:
            results.append({"index": idx, "status": "failed", "error": error_msg})
            continue

        upload_dir = Path(current_app.config["UPLOAD_DIR"])
        heatmap_dir = Path(current_app.config["HEATMAP_DIR"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        heatmap_dir.mkdir(parents=True, exist_ok=True)

        original_filename = secure_filename(file.filename)
        suffix = f".{original_filename.rsplit('.', 1)[1].lower()}" if '.' in original_filename else '.jpg'
        file_name = f"{uuid.uuid4().hex}{suffix}"
        full_image_path = upload_dir / file_name
        
        try:
            file.save(full_image_path)
            prediction = inference_engine.predict(image_path=str(full_image_path), heatmap_dir=str(heatmap_dir))
            
            image_rel_path = f"uploads/{file_name}"
            heatmap_rel_path = f"heatmaps/{prediction['heatmap_file']}"
            
            record = DiagnosisRecord(
                user_id=g.user_id, image_path=image_rel_path, heatmap_path=heatmap_rel_path,
                predicted_label=prediction["predicted_label_en"], confidence=prediction["confidence"],
            )
            record.set_predictions(prediction["predictions"])
            db.session.add(record)
            db.session.commit()
            
            row = record.to_dict()
            row["image_url"] = _build_file_url(image_rel_path)
            row["heatmap_url"] = _build_file_url(heatmap_rel_path)
            results.append({"index": idx, "status": "success", "data": row})
        except Exception as exc:
            full_image_path.unlink(missing_ok=True)
            results.append({"index": idx, "status": "failed", "error": str(exc)})

    return jsonify(success(results))
