"""
model_path.py — 模型文件路径解析
───────────────────────────────
兼容历史绝对路径与当前相对路径两种存储方式，
安全地将模型路径解析到模型目录下。
消费方：
  services/inference_service.py → 加载在线模型权重
  routes/admin.py → 模型上线前校验文件存在性、删除模型文件
"""
from pathlib import Path


def resolve_model_path(model_path: str, model_dir: str | Path) -> Path:
    model_root = Path(model_dir).resolve()
    raw_path = str(model_path or "").strip()
    if not raw_path:
        return model_root / "__invalid_model_path__.pt"

    candidate = Path(raw_path)
    is_absolute_like = candidate.is_absolute() or raw_path.startswith(("/", "\\"))
    if is_absolute_like:
        if candidate.exists() and candidate.is_file():
            return candidate
        # 兼容历史绝对路径：若迁移后仅文件名一致，则回落到当前模型目录
        if candidate.name:
            fallback = model_root / candidate.name
            if fallback.exists() and fallback.is_file():
                return fallback
            return fallback
        return candidate.resolve()

    resolved = (model_root / candidate).resolve()
    if resolved.exists() and resolved.is_file():
        return resolved
    return model_root / candidate


def model_path_exists(model_path: str, model_dir: str | Path) -> bool:
    resolved = resolve_model_path(model_path, model_dir)
    return resolved.exists() and resolved.is_file()


def to_model_relative_path(model_path: str | Path, model_dir: str | Path) -> str:
    model_root = Path(model_dir).resolve()
    raw_path = str(model_path or "").strip()
    if not raw_path:
        return ""

    path_obj = Path(raw_path)
    is_absolute_like = path_obj.is_absolute() or raw_path.startswith(("/", "\\"))
    if not is_absolute_like:
        return path_obj.as_posix()

    try:
        return path_obj.resolve().relative_to(model_root).as_posix()
    except Exception:
        normalized = raw_path.replace("\\", "/")
        segments = [segment for segment in normalized.split("/") if segment not in ("", ".")]
        lower_segments = [segment.lower() for segment in segments]
        model_dir_name = model_root.name.lower()
        if model_dir_name in lower_segments:
            index = max(
                idx for idx, segment in enumerate(lower_segments) if segment == model_dir_name
            )
            tail_segments = segments[index + 1 :]
            if tail_segments:
                return "/".join(tail_segments)
        if path_obj.name:
            return path_obj.name
        return path_obj.as_posix()
