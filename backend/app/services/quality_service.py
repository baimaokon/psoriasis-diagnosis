"""数据集质量分析服务"""
import hashlib
from pathlib import Path
from typing import List, Dict

import numpy as np
from PIL import Image

from .dataset_service import resolve_dataset_path, SUPPORTED_IMAGE_SUFFIX


def calculate_image_blur_score(image_path: str) -> float:
    """图像模糊度检测：使用 Laplacian 方差算子

    原理：Laplacian 算子计算图像二阶导数，方差越小说明边缘越少、图像越模糊。
    经验阈值：< 100 可能模糊，< 50 高度疑似模糊，用于数据集质量筛选。
    """
    try:
        from cv2 import cvtColor, COLOR_RGB2GRAY, Laplacian, CV_64F
        from numpy import var
        
        img = Image.open(image_path).convert('RGB')
        img_array = np.array(img)
        gray = cvtColor(img_array, COLOR_RGB2GRAY)
        laplacian_var = Laplacian(gray, CV_64F).var()
        return float(laplacian_var)
    except Exception:
        return 0.0


def calculate_file_hash(file_path: str, chunk_size: int = 8192) -> str:
    """SHA256 分块哈希：检测数据集中完全相同的重复图像"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def get_image_dimensions(image_path: str) -> tuple:
    """获取图像尺寸"""
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return (0, 0)


def analyze_dataset_quality(dataset_dir: str, blur_threshold: float = 100.0) -> Dict:
    """
    分析数据集质量
    
    Args:
        dataset_dir: 数据集目录路径
        blur_threshold: 模糊度阈值（Laplacian 方差）
    
    Returns:
        质量分析报告
    """
    from app.utils.label_mapping import get_label_info
    
    root = resolve_dataset_path(dataset_dir)
    if not root.exists():
        raise FileNotFoundError(f"数据集目录不存在: {root}")
    
    report = {
        "total_images": 0,
        "blur_samples_data": [],
        "duplicate_images_data": [],
        "class_reports": {},
        "quality_score": 0.0
    }
    
    hash_map = {}
    all_blur_scores = []
    
    for class_dir in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not class_dir.is_dir():
            continue
        
        class_name = class_dir.name
        label_info = get_label_info(class_name)
        
        class_report = {
            "zh_name": label_info["label_zh"],
            "total": 0,
            "blur_count": 0,
            "blur_samples": [],
            "avg_blur_score": 0.0,
            "size_stats": {
                "min_width": float('inf'),
                "max_width": 0,
                "min_height": float('inf'),
                "max_height": 0,
                "avg_width": 0.0,
                "avg_height": 0.0
            },
            "dimensions_list": []
        }
        
        widths = []
        heights = []
        blur_scores = []
        
        for file_path in sorted(class_dir.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIX:
                continue
            
            report["total_images"] += 1
            class_report["total"] += 1
            
            width, height = get_image_dimensions(str(file_path))
            if width > 0 and height > 0:
                widths.append(width)
                heights.append(height)
                
                if width < class_report["size_stats"]["min_width"]:
                    class_report["size_stats"]["min_width"] = width
                if width > class_report["size_stats"]["max_width"]:
                    class_report["size_stats"]["max_width"] = width
                if height < class_report["size_stats"]["min_height"]:
                    class_report["size_stats"]["min_height"] = height
                if height > class_report["size_stats"]["max_height"]:
                    class_report["size_stats"]["max_height"] = height
            
            blur_score = calculate_image_blur_score(str(file_path))
            blur_scores.append(blur_score)
            all_blur_scores.append(blur_score)
            
            relative_path = str(file_path.relative_to(root))
            
            if blur_score < blur_threshold:
                class_report["blur_count"] += 1
                class_report["blur_samples"].append({
                    "filename": file_path.name,
                    "relative_path": relative_path,
                    "blur_score": round(blur_score, 2),
                    "url": f"/api/files/datasets/{relative_path}"
                })
                report["blur_samples_data"].append({
                    "filename": file_path.name,
                    "relative_path": relative_path,
                    "blur_score": round(blur_score, 2),
                    "url": f"/api/files/datasets/{relative_path}"
                })
            
            file_hash = calculate_file_hash(str(file_path))
            if file_hash in hash_map:
                report["duplicate_images_data"].append({
                    "filename": file_path.name,
                    "relative_path": relative_path,
                    "duplicate_of": hash_map[file_hash],
                    "url": f"/api/files/datasets/{relative_path}"
                })
            else:
                hash_map[file_hash] = relative_path
        
        if widths:
            class_report["size_stats"]["avg_width"] = round(np.mean(widths), 2)
            class_report["size_stats"]["avg_height"] = round(np.mean(heights), 2)
        
        if blur_scores:
            class_report["avg_blur_score"] = round(np.mean(blur_scores), 2)
        
        report["class_reports"][class_name] = class_report
    
    # 更新模糊样本比例
    total = report["total_images"]
    if total > 0:
        report["blur_samples"] = len(report["blur_samples_data"])
        report["blur_ratio"] = round(report["blur_samples"] / total * 100, 2)
        # 计算质量分：100 - 模糊比例 * 0.5 - 重复比例 * 0.5
        dup_ratio = len(report["duplicate_images_data"]) / total * 100
        report["quality_score"] = round(max(0, 100 - report["blur_ratio"] * 0.5 - dup_ratio * 0.5), 2)
    
    return report


def generate_split_visualization(dataset_dir: str, val_ratio: float = 0.15, 
                                  test_ratio: float = 0.15, seed: int = 42) -> Dict:
    """
    生成数据集划分可视化数据
    
    Args:
        dataset_dir: 数据集目录
        val_ratio: 验证集比例
        test_ratio: 测试集比例
        seed: 随机种子
    
    Returns:
        划分可视化数据
    """
    from .dataset_service import build_classification_samples, build_train_val_test_split
    from app.utils.label_mapping import get_label_info
    
    class_names, samples = build_classification_samples(dataset_dir)
    
    split_data = {
        "total_samples": len(samples),
        "val_ratio": val_ratio,
        "test_ratio": test_ratio,
        "train_ratio": 1 - val_ratio - test_ratio,
        "classes": []
    }
    
    class_indices = {}
    for idx, (path, label) in enumerate(samples):
        if label not in class_indices:
            class_indices[label] = []
        class_indices[label].append(idx)
    
    try:
        train_samples, val_samples, test_samples = build_train_val_test_split(
            samples, val_ratio, test_ratio, seed
        )
    except Exception:
        train_count = int(len(samples) * (1 - val_ratio - test_ratio))
        val_count = int(len(samples) * val_ratio)
        test_count = len(samples) - train_count - val_count
        
        train_samples = samples[:train_count]
        val_samples = samples[train_count:train_count + val_count]
        test_samples = samples[train_count + val_count:]
    
    for class_idx in range(len(class_names)):
        class_name = class_names[class_idx]
        label_info = get_label_info(class_name)
        
        total_count = len(class_indices.get(class_idx, []))
        train_count = sum(1 for s in train_samples if s[1] == class_idx)
        val_count = sum(1 for s in val_samples if s[1] == class_idx)
        test_count = sum(1 for s in test_samples if s[1] == class_idx)
        
        split_data["classes"].append({
            "class_name": class_name,
            "zh_name": label_info["label_zh"],
            "total": total_count,
            "train": train_count,
            "val": val_count,
            "test": test_count,
            "train_ratio": round(train_count / total_count * 100, 2) if total_count > 0 else 0,
            "val_ratio": round(val_count / total_count * 100, 2) if total_count > 0 else 0,
            "test_ratio": round(test_count / total_count * 100, 2) if total_count > 0 else 0
        })
    
    split_data["summary"] = {
        "train_total": len(train_samples),
        "val_total": len(val_samples),
        "test_total": len(test_samples),
        "train_percentage": round(len(train_samples) / len(samples) * 100, 2),
        "val_percentage": round(len(val_samples) / len(samples) * 100, 2),
        "test_percentage": round(len(test_samples) / len(samples) * 100, 2)
    }
    
    return split_data
