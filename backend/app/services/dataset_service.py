"""
dataset_service.py — 数据集服务
────────────────────────────────
职责：
  1. 扫描数据集目录，自动从子目录名识别标签 → list_class_distribution()
  2. 汇总统计（总图像数、类别数） → get_dataset_summary()
  3. 构建 (路径, 标签索引) 样本对 → build_classification_samples()
  4. 分层随机划分训练/验证/测试集 → build_train_val_test_split()
被调方：
  routes/admin.py — 数据集摘要、随机样本、划分可视化
  services/training_service.py — 训练时加载数据和划分
依赖：
  无数据库依赖（纯文件系统操作）
  utils/label_mapping.py → get_label_info() 中英文翻译
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split

from app.utils.label_mapping import get_label_info


SUPPORTED_IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass
class DatasetSummary:
    dataset_dir: str
    total_images: int
    class_count: int
    classes: list


def resolve_dataset_path(dataset_dir: str) -> Path:
    path = Path(dataset_dir).expanduser().resolve()
    return path


def list_class_distribution(dataset_dir: str):
    path = resolve_dataset_path(dataset_dir)
    if not path.exists():
        raise FileNotFoundError(f"数据集目录不存在: {path}")

    rows = []
    for class_dir in sorted(path.iterdir(), key=lambda item: item.name.lower()):
        if not class_dir.is_dir():
            continue
        count = 0
        for file_path in class_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_IMAGE_SUFFIX:
                count += 1
        label_info = get_label_info(class_dir.name)
        rows.append(
            {
                "name": class_dir.name,
                "zh_name": label_info["label_zh"],
                "display_name": label_info["label_display"],
                "count": count,
            }
        )
    return rows


def get_dataset_summary(dataset_dir: str):
    rows = list_class_distribution(dataset_dir)
    total = int(sum(item["count"] for item in rows))
    summary = DatasetSummary(
        dataset_dir=str(resolve_dataset_path(dataset_dir)),
        total_images=total,
        class_count=len(rows),
        classes=rows,
    )
    return summary


def _split_indices(labels, val_ratio: float, test_ratio: float, seed: int):
    """分层随机划分：确保训练/验证/测试集中各类别比例一致

    优先使用 stratify 保持类别平衡；若某类别样本过少导致分层失败，则回退为普通随机划分。
    """
    labels = np.asarray(labels)
    all_indices = np.arange(labels.shape[0])
    holdout_ratio = val_ratio + test_ratio
    if holdout_ratio <= 0 or holdout_ratio >= 1:
        raise ValueError("验证集比例+测试集比例必须在(0,1)区间内")

    try:
        train_idx, holdout_idx = train_test_split(
            all_indices,
            test_size=holdout_ratio,
            random_state=seed,
            stratify=labels,
        )
    except ValueError:
        train_idx, holdout_idx = train_test_split(
            all_indices,
            test_size=holdout_ratio,
            random_state=seed,
            stratify=None,
        )

    holdout_labels = labels[holdout_idx]
    test_part = test_ratio / holdout_ratio
    try:
        val_idx, test_idx = train_test_split(
            holdout_idx,
            test_size=test_part,
            random_state=seed,
            stratify=holdout_labels,
        )
    except ValueError:
        val_idx, test_idx = train_test_split(
            holdout_idx,
            test_size=test_part,
            random_state=seed,
            stratify=None,
        )

    return train_idx.tolist(), val_idx.tolist(), test_idx.tolist()


def build_classification_samples(dataset_dir: str):
    root = resolve_dataset_path(dataset_dir)
    if not root.exists():
        raise FileNotFoundError(f"数据集目录不存在: {root}")

    class_names = []
    samples = []
    for class_dir in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not class_dir.is_dir():
            continue
        class_index = len(class_names)
        class_names.append(class_dir.name)
        for file_path in class_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIX:
                continue
            samples.append((str(file_path), class_index))

    if len(class_names) < 2:
        raise ValueError("分类训练至少需要2个类别")
    if len(samples) < 20:
        raise ValueError("样本量过少，至少需要20张图像")
    return class_names, samples


def build_train_val_test_split(samples, val_ratio: float, test_ratio: float, seed: int):
    labels = [label for _, label in samples]
    train_idx, val_idx, test_idx = _split_indices(labels, val_ratio, test_ratio, seed)

    train_samples = [samples[i] for i in train_idx]
    val_samples = [samples[i] for i in val_idx]
    test_samples = [samples[i] for i in test_idx]

    if not train_samples or not val_samples or not test_samples:
        raise ValueError("数据划分失败，训练/验证/测试集不能为空")
    return train_samples, val_samples, test_samples
