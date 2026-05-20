"""
training_service.py — 训练管理器 + 事件发布中心
───────────────────────────────────────────────
职责：
  TrainingManager — 训练生命周期管理：
    1. 启动训练线程（异步执行，不阻塞 Flask 主进程）
    2. 每个 Epoch 结束后通过 TrainEventHub 发布进度事件
    3. Checkpoint 自动保存与恢复（支持断点续训）
    4. 训练完成自动创建 ModelVersion 记录
    5. 僵尸任务恢复（服务重启后检查 running 状态的任务）
  TrainEventHub — 发布/订阅模式的事件总线：
    - 训练线程发布 "job_update" / "epoch_summary" 事件
    - SSE 端点订阅事件队列，推送到前端浏览器
    - 解耦训练线程与 HTTP 响应层
被调方：
  routes/admin.py — 所有训练相关端点（启动/终止/复活/SSE流）
依赖：
  models/training_job.py、model_version.py
  services/dataset_service.py → 数据加载与划分
  services/model_factory.py → 模型构建
"""

import copy
import json
import math
import os
import queue
import socket
import threading
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
from PIL import Image
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold, train_test_split
from torch import nn
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DistributedSampler
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

from app.extensions import db
from app.models import ModelVersion, TrainingJob
from app.utils.model_path import to_model_relative_path

from .dataset_service import (
    build_classification_samples,
    build_train_val_test_split,
    get_dataset_summary,
)
from .model_factory import (
    SUPPORTED_BACKBONES,
    build_model,
    freeze_backbone_layers,
)


class ClassificationDataset(Dataset):
    def __init__(self, samples, transform=None, image_cache=None):
        self.samples = samples
        self.transform = transform
        self.image_cache = image_cache

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        image_path, label = self.samples[index]
        image = None
        if self.image_cache is not None:
            image = self.image_cache.get(image_path)
        if image is None:
            image = _read_rgb_image(image_path)
            if self.image_cache is not None:
                self.image_cache.put(image_path, image)
        if self.transform is not None:
            image = self.transform(image)
        return image, label


class TrainingCancelled(RuntimeError):
    pass


def _read_rgb_image(image_path: str):
    with Image.open(image_path) as image:
        return image.convert("RGB")


class ImageCache:
    """内存图像缓存：将解码后的 PIL Image 缓存在字典中

    在单进程 DataLoader 场景下，可避免每个 epoch 重复解码图像文件，
    显著加速小规模数据集的训练。线程安全。
    """
    def __init__(self, enabled: bool, max_items: int):
        self.enabled = bool(enabled)
        self.max_items = max(0, int(max_items))
        self._cache = {}
        self._lock = threading.Lock()

    def _has_capacity(self):
        return self.max_items <= 0 or len(self._cache) < self.max_items

    def get(self, image_path: str):
        if not self.enabled:
            return None
        with self._lock:
            cached = self._cache.get(image_path)
            if cached is None:
                return None
            return cached.copy()

    def put(self, image_path: str, image):
        if not self.enabled:
            return
        with self._lock:
            if image_path in self._cache or not self._has_capacity():
                return
            self._cache[image_path] = image.copy()

    def preload_samples(self, samples):
        if not self.enabled:
            return 0
        loaded = 0
        for image_path, _ in samples:
            with self._lock:
                if image_path in self._cache:
                    continue
                if not self._has_capacity():
                    break
            image = _read_rgb_image(image_path)
            with self._lock:
                if image_path in self._cache:
                    continue
                if not self._has_capacity():
                    break
                self._cache[image_path] = image
                loaded += 1
        return loaded

    def size(self):
        with self._lock:
            return len(self._cache)


TRAIN_PARAM_SPEC = [
    {
        "key": "backbone",
        "name": "主干网络",
        "type": "select",
        "description": "决定模型结构。越重的模型通常精度潜力更高，但训练更慢。",
        "base": "efficientnet_b0",
        "balanced": "resnet50",
        "max_performance": "inception_v3",
        "options": list(SUPPORTED_BACKBONES.keys()),
    },
    {
        "key": "epochs",
        "name": "训练轮次",
        "type": "int",
        "description": "完整遍历训练集的次数。轮次越多，收敛更充分，但耗时增加。",
        "base": 15,
        "balanced": 40,
        "max_performance": 80,
        "min": 1,
        "max": 200,
    },
    {
        "key": "batch_size",
        "name": "批大小",
        "type": "int",
        "description": "单次前向/反向使用的图像数量。越大吞吐越高，但显存占用更高。",
        "base": 16,
        "balanced": 32,
        "max_performance": 64,
        "min": 1,
        "max": 256,
    },
    {
        "key": "learning_rate",
        "name": "学习率",
        "type": "float",
        "description": "控制参数更新幅度。过大易震荡，过小收敛慢。",
        "base": 0.001,
        "balanced": 0.0005,
        "max_performance": 0.0003,
        "min": 0.000001,
        "max": 0.1,
    },
    {
        "key": "weight_decay",
        "name": "权重衰减",
        "type": "float",
        "description": "L2正则强度，减少过拟合。数据噪声较高时建议适当增大。",
        "base": 0.0,
        "balanced": 0.0001,
        "max_performance": 0.0005,
        "min": 0.0,
        "max": 0.1,
    },
    {
        "key": "optimizer",
        "name": "优化器",
        "type": "select",
        "description": "AdamW收敛快；SGD泛化稳定，但通常需要更长训练。",
        "base": "adamw",
        "balanced": "adamw",
        "max_performance": "sgd",
        "options": ["adamw", "sgd"],
    },
    {
        "key": "momentum",
        "name": "动量（仅SGD）",
        "type": "float",
        "description": "历史梯度平滑项。仅在SGD时生效。",
        "base": 0.9,
        "balanced": 0.9,
        "max_performance": 0.95,
        "min": 0.0,
        "max": 0.999,
    },
    {
        "key": "image_size",
        "name": "输入尺寸",
        "type": "int",
        "description": "图像缩放边长。更大尺寸可能提高精度，但显著增加算力消耗。",
        "base": 224,
        "balanced": 224,
        "max_performance": 320,
        "min": 160,
        "max": 512,
    },
    {
        "key": "val_ratio",
        "name": "验证集比例",
        "type": "float",
        "description": "用于调参和早停监控的数据比例。",
        "base": 0.15,
        "balanced": 0.15,
        "max_performance": 0.2,
        "min": 0.05,
        "max": 0.4,
    },
    {
        "key": "test_ratio",
        "name": "测试集比例",
        "type": "float",
        "description": "用于最终评估的数据比例。",
        "base": 0.1,
        "balanced": 0.1,
        "max_performance": 0.15,
        "min": 0.05,
        "max": 0.4,
    },
    {
        "key": "split_mode",
        "name": "划分策略",
        "type": "select",
        "description": "fixed为固定划分；kfold会在不同训练批次中轮换验证集，使样本有机会参与不同角色。",
        "base": "fixed",
        "balanced": "fixed",
        "max_performance": "kfold",
        "options": ["fixed", "kfold"],
    },
    {
        "key": "kfold_splits",
        "name": "K折数量",
        "type": "int",
        "description": "仅在kfold模式生效。K越大轮换更充分，但训练时长线性增加。",
        "base": 3,
        "balanced": 5,
        "max_performance": 7,
        "min": 2,
        "max": 10,
    },
    {
        "key": "validation_interval",
        "name": "验证间隔轮次",
        "type": "int",
        "description": "每N轮做一次验证。适当增大可减少纪元间抖动。",
        "base": 1,
        "balanced": 1,
        "max_performance": 2,
        "min": 1,
        "max": 20,
    },
    {
        "key": "freeze_backbone",
        "name": "冻结主干层",
        "type": "bool",
        "description": "仅训练分类头可显著加速；全量微调通常精度更高。",
        "base": True,
        "balanced": False,
        "max_performance": False,
    },
    {
        "key": "label_smoothing",
        "name": "标签平滑",
        "type": "float",
        "description": "缓解过拟合与过度置信。",
        "base": 0.0,
        "balanced": 0.05,
        "max_performance": 0.1,
        "min": 0.0,
        "max": 0.3,
    },
    {
        "key": "scheduler",
        "name": "学习率调度",
        "type": "select",
        "description": "用于后期收敛。none为固定学习率，cosine为余弦退火。",
        "base": "none",
        "balanced": "cosine",
        "max_performance": "cosine",
        "options": ["none", "cosine"],
    },
    {
        "key": "num_workers",
        "name": "数据加载线程",
        "type": "int",
        "description": "提升数据读取吞吐。Windows线程训练场景下建议0。",
        "base": 0,
        "balanced": 4,
        "max_performance": 8,
        "min": 0,
        "max": 16,
    },
    {
        "key": "auto_loader_tune",
        "name": "自动调优加载器",
        "type": "bool",
        "description": "根据GPU数量与CPU核心自动调整加载并行度，减少纪元切换卡顿。",
        "base": True,
        "balanced": True,
        "max_performance": True,
    },
    {
        "key": "prefetch_factor",
        "name": "预取批次数",
        "type": "int",
        "description": "仅多进程加载时生效，提升GPU连续供数能力。",
        "base": 2,
        "balanced": 4,
        "max_performance": 8,
        "min": 2,
        "max": 16,
    },
    {
        "key": "persistent_workers",
        "name": "持久加载进程",
        "type": "bool",
        "description": "开启后各轮次复用数据进程，减少纪元切换抖动。",
        "base": False,
        "balanced": True,
        "max_performance": True,
    },
    {
        "key": "cache_images",
        "name": "图像内存缓存",
        "type": "bool",
        "description": "将部分原图预加载到内存，加速训练但会占用更多内存。",
        "base": False,
        "balanced": False,
        "max_performance": True,
    },
    {
        "key": "cache_limit",
        "name": "缓存图像上限",
        "type": "int",
        "description": "0表示不限制，仅在图像内存缓存开启时生效。",
        "base": 0,
        "balanced": 6000,
        "max_performance": 30000,
        "min": 0,
        "max": 300000,
    },
    {
        "key": "use_amp",
        "name": "混合精度",
        "type": "bool",
        "description": "GPU环境可加速并降低显存占用。",
        "base": True,
        "balanced": True,
        "max_performance": True,
    },
    {
        "key": "seed",
        "name": "随机种子",
        "type": "int",
        "description": "控制数据划分与训练随机性，便于复现实验。",
        "base": 42,
        "balanced": 42,
        "max_performance": 42,
        "min": 1,
        "max": 100000,
    },
    {
        "key": "early_stop_patience",
        "name": "早停耐心轮次",
        "type": "int",
        "description": "验证集长期无提升时提前停止训练，避免浪费算力。",
        "base": 5,
        "balanced": 10,
        "max_performance": 18,
        "min": 1,
        "max": 100,
    },
    {
        "key": "device",
        "name": "训练设备",
        "type": "select",
        "description": "auto自动选择；cuda强制GPU；cpu强制CPU。检测到多卡时默认使用全部可见GPU并行。",
        "base": "auto",
        "balanced": "auto",
        "max_performance": "cuda",
        "options": ["auto", "cuda", "cpu"],
    },
]

DEFAULT_PARAMS = {row["key"]: row["balanced"] for row in TRAIN_PARAM_SPEC}


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _safe_float(value, default: float = 0.0):
    try:
        casted = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(casted) or math.isinf(casted):
        return float(default)
    return casted


def _safe_int(value, default: int = 0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_torch_load(path, map_location="cpu"):
    try:
        return torch.load(path, map_location=map_location, weights_only=True)
    except TypeError:
        return torch.load(path, map_location=map_location)


def _format_training_error(exc: Exception):
    raw = str(exc).strip()
    lower = raw.lower()
    if "out of memory" in lower:
        return (
            "训练失败: CUDA显存不足(OOM)。建议减小批大小(batch_size)、"
            "减小输入尺寸(image_size)，或关闭混合精度(use_amp=false)后重试。"
        )
    if "nan" in lower or "inf" in lower or "非有限loss" in raw:
        return (
            "训练失败: 数值不稳定(NaN/Inf)。建议降低学习率(learning_rate)、"
            "减小批大小(batch_size)，并关闭混合精度(use_amp=false)重试。"
        )
    message = f"训练失败: {raw}" if raw else "训练失败: 未知错误"
    return message[:250]


def _checkpoint_file_path(checkpoint_dir: str, job_id: int):
    return Path(checkpoint_dir) / f"job_{int(job_id)}_resume.pt"


def has_job_checkpoint(checkpoint_dir: str, job_id: int):
    path = _checkpoint_file_path(checkpoint_dir, job_id)
    return path.exists() and path.is_file()


def remove_job_checkpoint(checkpoint_dir: str, job_id: int):
    path = _checkpoint_file_path(checkpoint_dir, job_id)
    if path.exists() and path.is_file():
        try:
            path.unlink()
            return True
        except Exception:
            return False
    return False


def _clone_model_state_to_cpu(model):
    base_model = (
        model.module
        if isinstance(model, (nn.DataParallel, DDP))
        else model
    )
    cpu_state = {}
    for key, value in base_model.state_dict().items():
        if torch.is_tensor(value):
            cpu_state[key] = value.detach().to("cpu").clone()
        else:
            cpu_state[key] = copy.deepcopy(value)
    return cpu_state


def _load_model_state_compat(model, state_dict: dict, strict: bool = True):
    if not isinstance(state_dict, dict):
        raise RuntimeError("模型参数格式错误")
    try:
        model.load_state_dict(state_dict, strict=strict)
        return
    except RuntimeError:
        pass

    if isinstance(model, (nn.DataParallel, DDP)):
        converted = {}
        for key, value in state_dict.items():
            if key.startswith("module."):
                converted[key] = value
            else:
                converted[f"module.{key}"] = value
        model.load_state_dict(converted, strict=strict)
        return

    converted = {}
    for key, value in state_dict.items():
        if key.startswith("module."):
            converted[key[7:]] = value
        else:
            converted[key] = value
    model.load_state_dict(converted, strict=strict)


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _next_resume_position(
    fold_index: int,
    fold_epoch: int,
    max_fold: int,
    max_fold_epoch: int,
    force_next_fold: bool = False,
):
    if force_next_fold or fold_epoch >= max_fold_epoch:
        next_fold_index = fold_index + 1
        next_fold_epoch = 1
    else:
        next_fold_index = fold_index
        next_fold_epoch = fold_epoch + 1
    if next_fold_index > max_fold:
        next_fold_index = max_fold
        next_fold_epoch = max_fold_epoch + 1
    return next_fold_index, next_fold_epoch


def get_train_param_spec():
    return TRAIN_PARAM_SPEC


def normalize_train_params(raw_params):
    """训练参数校验与规范化

    以平衡档位（balanced）为默认值，对用户传入的参数进行类型转换、范围裁剪、
    模式校验（固定划分/K折交叉验证），确保传入训练管道的参数合法。
    """
    params = dict(DEFAULT_PARAMS)
    raw_params = raw_params or {}
    for row in TRAIN_PARAM_SPEC:
        key = row["key"]
        if key not in raw_params:
            continue
        value = raw_params[key]
        if row["type"] == "int":
            value = int(value)
            value = max(row.get("min", value), min(row.get("max", value), value))
        elif row["type"] == "float":
            value = float(value)
            value = max(row.get("min", value), min(row.get("max", value), value))
        elif row["type"] == "bool":
            value = _to_bool(value)
        elif row["type"] == "select":
            options = set(row.get("options") or [])
            value = str(value)
            if options and value not in options:
                value = row["balanced"]
        params[key] = value

    if params["split_mode"] == "fixed":
        if params["val_ratio"] + params["test_ratio"] >= 0.9:
            raise ValueError("验证集比例 + 测试集比例不能过高，建议不超过0.4")
    else:
        if params["test_ratio"] >= 0.5:
            raise ValueError("K折模式下测试集比例过高，建议低于0.5")
        params["val_ratio"] = max(params["val_ratio"], 0.05)
        params["kfold_splits"] = max(2, int(params["kfold_splits"]))
    params["validation_interval"] = max(1, int(params["validation_interval"]))
    params["validation_interval"] = min(params["validation_interval"], int(params["epochs"]))
    params["prefetch_factor"] = max(2, int(params["prefetch_factor"]))
    params["cache_limit"] = max(0, int(params["cache_limit"]))
    if not params["cache_images"]:
        params["cache_limit"] = 0
    if params["backbone"] == "inception_v3" and params["image_size"] < 299:
        params["image_size"] = 299
    return params


def _make_transforms(image_size: int):
    train_transform = transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(8),
            transforms.ColorJitter(brightness=0.12, contrast=0.12, saturation=0.08),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    eval_transform = transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    return train_transform, eval_transform


def _estimate_input_batch_bytes(batch_size: int, image_size: int):
    return int(max(1, batch_size) * 3 * max(1, image_size) * max(1, image_size) * 4)


def _resolve_loader_runtime(params, gpu_count: int):
    requested_workers = max(0, int(params["num_workers"]))
    requested_prefetch = max(2, int(params["prefetch_factor"]))
    requested_persistent = bool(params["persistent_workers"])
    auto_tune = bool(params.get("auto_loader_tune", True))
    cpu_cores = max(1, int(os.cpu_count() or 1))

    num_workers = requested_workers
    if os.name == "nt" and num_workers > 0:
        num_workers = 0
    if auto_tune and os.name != "nt" and gpu_count > 0:
        suggested_workers = min(16, max(2, gpu_count * 3))
        max_workers = max(1, cpu_cores - 1)
        num_workers = max(num_workers, min(suggested_workers, max_workers))
    elif os.name != "nt" and num_workers > 0:
        num_workers = min(num_workers, max(1, cpu_cores - 1))

    prefetch_factor = min(requested_prefetch, 16)
    if auto_tune and gpu_count > 1:
        prefetch_factor = max(prefetch_factor, 6)
    prefetch_factor = min(prefetch_factor, 16)

    if num_workers == 0:
        persistent_workers = False
    elif auto_tune and gpu_count > 0:
        persistent_workers = True
    else:
        persistent_workers = requested_persistent

    return {
        "num_workers": int(num_workers),
        "prefetch_factor": int(prefetch_factor),
        "persistent_workers": bool(persistent_workers),
    }


def _should_enable_cuda_prefetch(device, params, gpu_count: int):
    if device.type != "cuda" or gpu_count != 1:
        return False, 0, 0
    batch_bytes = _estimate_input_batch_bytes(params["batch_size"], params["image_size"])
    try:
        total_vram = int(torch.cuda.get_device_properties(device).total_memory)
    except Exception:
        total_vram = 0
    safe_budget = int(total_vram * 0.08) if total_vram > 0 else 64 * 1024 * 1024
    safe_budget = max(safe_budget, 64 * 1024 * 1024)
    enabled = batch_bytes <= safe_budget
    return bool(enabled), int(batch_bytes), int(safe_budget)


class CudaBatchPrefetcher:
    def __init__(self, data_loader, device, enabled: bool):
        self._iterator = iter(data_loader)
        self._device = device
        self._enabled = bool(enabled and device.type == "cuda")
        self._stream = torch.cuda.Stream(device=device) if self._enabled else None
        self._next_images = None
        self._next_labels = None
        self._preload()

    def _preload(self):
        try:
            images, labels = next(self._iterator)
        except StopIteration:
            self._next_images = None
            self._next_labels = None
            return
        if not self._enabled:
            self._next_images = images
            self._next_labels = labels
            return
        with torch.cuda.stream(self._stream):
            self._next_images = images.to(self._device, non_blocking=True)
            self._next_labels = labels.to(self._device, non_blocking=True)

    def __iter__(self):
        return self

    def __next__(self):
        if self._next_images is None:
            raise StopIteration
        if self._enabled:
            torch.cuda.current_stream(device=self._device).wait_stream(self._stream)
        images = self._next_images
        labels = self._next_labels
        self._preload()
        return images, labels


def _build_loaders(
    train_samples,
    val_samples,
    test_samples,
    params,
    image_cache=None,
    gpu_count=0,
    local_batch_size=0,
    distributed_rank=-1,
    distributed_world_size=0,
):
    train_transform, eval_transform = _make_transforms(params["image_size"])
    runtime_loader = _resolve_loader_runtime(params, gpu_count=gpu_count)
    num_workers = int(runtime_loader["num_workers"])
    # 多进程DataLoader场景下不共享Python内存缓存，避免额外开销和兼容性问题。
    active_cache = image_cache if num_workers == 0 else None

    train_dataset = ClassificationDataset(
        train_samples,
        transform=train_transform,
        image_cache=active_cache,
    )
    val_dataset = ClassificationDataset(
        val_samples,
        transform=eval_transform,
        image_cache=active_cache,
    )
    test_dataset = ClassificationDataset(
        test_samples,
        transform=eval_transform,
        image_cache=active_cache,
    )

    preloaded_count = 0
    if active_cache is not None:
        preloaded_count = active_cache.preload_samples(train_samples)

    pin_memory = torch.cuda.is_available()
    batch_size = int(local_batch_size) if int(local_batch_size or 0) > 0 else int(
        params["batch_size"]
    )
    train_sampler = None
    if int(distributed_world_size or 0) > 1 and int(distributed_rank) >= 0:
        train_sampler = DistributedSampler(
            train_dataset,
            num_replicas=int(distributed_world_size),
            rank=int(distributed_rank),
            shuffle=True,
            drop_last=False,
        )
    loader_kwargs = {
        "batch_size": batch_size,
        "num_workers": num_workers,
        "pin_memory": pin_memory,
    }
    if num_workers > 0:
        loader_kwargs["persistent_workers"] = bool(runtime_loader["persistent_workers"])
        loader_kwargs["prefetch_factor"] = int(runtime_loader["prefetch_factor"])

    train_loader = DataLoader(
        train_dataset,
        shuffle=train_sampler is None,
        sampler=train_sampler,
        **loader_kwargs,
    )
    val_loader = DataLoader(
        val_dataset,
        shuffle=False,
        **loader_kwargs,
    )
    test_loader = DataLoader(
        test_dataset,
        shuffle=False,
        **loader_kwargs,
    )
    return train_loader, val_loader, test_loader, {
        "num_workers": num_workers,
        "prefetch_factor": int(runtime_loader["prefetch_factor"]) if num_workers > 0 else 0,
        "persistent_workers": bool(runtime_loader["persistent_workers"]),
        "pin_memory": bool(pin_memory),
        "distributed": bool(train_sampler is not None),
        "preloaded_count": preloaded_count,
        "cache_size": active_cache.size() if active_cache is not None else 0,
    }


def _split_holdout_indices(labels, test_ratio: float, seed: int):
    all_indices = list(range(len(labels)))
    if len(all_indices) < 2:
        raise ValueError("样本量过少，无法进行训练")

    if test_ratio <= 0:
        return all_indices, []

    stratify = labels if len(set(labels)) > 1 else None
    try:
        train_val_idx, test_idx = train_test_split(
            all_indices,
            test_size=test_ratio,
            random_state=seed,
            stratify=stratify,
        )
    except ValueError:
        train_val_idx, test_idx = train_test_split(
            all_indices,
            test_size=test_ratio,
            random_state=seed,
            stratify=None,
        )
    return train_val_idx, test_idx


def _build_kfold_batches(samples, test_ratio: float, kfold_splits: int, seed: int):
    labels = [label for _, label in samples]
    train_val_idx, test_idx = _split_holdout_indices(labels, test_ratio, seed)
    if len(train_val_idx) < 2:
        raise ValueError("K折模式下训练样本不足")

    train_val_labels = [labels[i] for i in train_val_idx]
    label_counts = Counter(train_val_labels)
    min_class_count = min(label_counts.values()) if label_counts else 0
    if min_class_count < 2:
        raise ValueError("K折模式要求每个类别至少2个样本")

    actual_splits = min(int(kfold_splits), min_class_count)
    if actual_splits < 2:
        raise ValueError("K折数量过高，已超过最小类别样本数")

    skf = StratifiedKFold(n_splits=actual_splits, shuffle=True, random_state=seed)
    fold_batches = []
    for fold_index, (train_rel, val_rel) in enumerate(
        skf.split(train_val_idx, train_val_labels), start=1
    ):
        fold_train_idx = [train_val_idx[i] for i in train_rel]
        fold_val_idx = [train_val_idx[i] for i in val_rel]
        train_samples = [samples[i] for i in fold_train_idx]
        val_samples = [samples[i] for i in fold_val_idx]
        fold_batches.append(
            {
                "fold_index": fold_index,
                "train_samples": train_samples,
                "val_samples": val_samples,
            }
        )

    test_samples = [samples[i] for i in test_idx]
    return fold_batches, test_samples, actual_splits


def _detect_device(device_name: str):
    if device_name == "cpu":
        return torch.device("cpu")
    if device_name == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("当前环境未检测到CUDA GPU，无法按要求使用cuda")
        return torch.device("cuda")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _evaluate(
    model,
    data_loader,
    criterion,
    device,
    gpu_count=0,
    use_amp=False,
    enable_cuda_prefetch=False,
):
    model.eval()
    loss_total = 0.0
    y_true = []
    y_pred = []
    use_cuda_amp = bool(use_amp and device.type == "cuda")
    eval_batches = CudaBatchPrefetcher(
        data_loader,
        device,
        enabled=bool(enable_cuda_prefetch and gpu_count == 1),
    )
    with torch.no_grad():
        for images, labels in eval_batches:
            if gpu_count <= 1:
                if images.device.type != device.type:
                    images = images.to(device, non_blocking=True)
                if labels.device.type != device.type:
                    labels = labels.to(device, non_blocking=True)
            if hasattr(torch, "amp") and hasattr(torch.amp, "autocast"):
                autocast_ctx = torch.amp.autocast(
                    device_type="cuda", enabled=use_cuda_amp
                )
            else:
                autocast_ctx = torch.cuda.amp.autocast(enabled=use_cuda_amp)
            with autocast_ctx:
                outputs = model(images)
                if labels.device != outputs.device:
                    labels = labels.to(outputs.device, non_blocking=True)
                loss = criterion(outputs, labels)
            if not torch.isfinite(loss).item():
                raise RuntimeError(
                    "验证阶段出现非有限loss（NaN/Inf），请降低学习率、减小批大小或关闭混合精度后重试"
                )
            preds = torch.argmax(outputs, dim=1)

            loss_total += loss.item() * images.size(0)
            y_true.extend(labels.detach().cpu().tolist())
            y_pred.extend(preds.detach().cpu().tolist())

    avg_loss = _safe_float(loss_total / max(len(y_true), 1))
    acc = _safe_float(accuracy_score(y_true, y_pred) if y_true else 0.0)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="macro",
        zero_division=0,
    )
    return (
        avg_loss,
        _safe_float(acc),
        _safe_float(precision),
        _safe_float(recall),
        _safe_float(f1),
    )


def _mp_queue_put(queue_obj, payload: dict):
    try:
        queue_obj.put_nowait(payload)
        return
    except Exception:
        pass
    try:
        queue_obj.get_nowait()
    except Exception:
        pass
    try:
        queue_obj.put_nowait(payload)
    except Exception:
        pass


def _ddp_should_cancel(cancel_event, device):
    flag = torch.tensor(
        1 if cancel_event.is_set() else 0,
        dtype=torch.int32,
        device=device,
    )
    dist.all_reduce(flag, op=dist.ReduceOp.SUM)
    return bool(flag.item() > 0)


def _ddp_worker_train(rank, world_size, worker_payload, event_queue, cancel_event):
    checkpoint_writer = None
    try:
        os.environ["MASTER_ADDR"] = str(worker_payload["master_addr"])
        os.environ["MASTER_PORT"] = str(worker_payload["master_port"])
        backend = "nccl" if torch.cuda.is_available() else "gloo"
        dist.init_process_group(
            backend=backend,
            rank=int(rank),
            world_size=int(world_size),
        )
        if torch.cuda.is_available():
            torch.cuda.set_device(rank)
            device = torch.device(f"cuda:{rank}")
        else:
            device = torch.device("cpu")

        params = worker_payload["params"]
        class_names = worker_payload["class_names"]
        fold_batches = worker_payload["fold_batches"]
        test_samples = worker_payload["test_samples"]
        total_epochs = int(worker_payload["total_epochs"])
        actual_folds = int(worker_payload["actual_folds"])
        validation_interval = int(params["validation_interval"])
        local_batch_size = max(
            1, int(math.ceil(float(params["batch_size"]) / float(world_size)))
        )
        use_amp = bool(params["use_amp"] and device.type == "cuda")
        resume_cfg = worker_payload.get("resume") or {}
        resume_checkpoint_path = str(resume_cfg.get("checkpoint_path") or "")
        resume_fold_index = max(1, _safe_int(resume_cfg.get("next_fold_index"), default=1))
        resume_fold_epoch = max(1, _safe_int(resume_cfg.get("next_fold_epoch"), default=1))
        global_epoch = max(0, _safe_int(resume_cfg.get("global_epoch"), default=0))
        best_val_acc = _safe_float(resume_cfg.get("best_val_acc"), default=-1.0)
        best_metrics = (
            dict(resume_cfg.get("best_metrics") or {})
            if isinstance(resume_cfg.get("best_metrics"), dict)
            else {}
        )
        logs = worker_payload.get("initial_logs") or []
        if not isinstance(logs, list):
            logs = []

        model = build_model(
            backbone=params["backbone"],
            num_classes=len(class_names),
            pretrained=True,
        )
        if params["freeze_backbone"]:
            freeze_backbone_layers(model, params["backbone"])
        model = model.to(device)

        checkpoint_state = None
        if rank == 0 and resume_checkpoint_path:
            resume_payload = _safe_torch_load(resume_checkpoint_path, map_location="cpu")
            checkpoint_state = resume_payload.get("model_state_dict")
            if isinstance(checkpoint_state, dict):
                _load_model_state_compat(model, checkpoint_state, strict=True)

        model = DDP(
            model,
            device_ids=[rank] if device.type == "cuda" else None,
            output_device=rank if device.type == "cuda" else None,
            broadcast_buffers=False,
            find_unused_parameters=False,
        )

        criterion = nn.CrossEntropyLoss(
            label_smoothing=float(params["label_smoothing"])
        ).to(device)
        trainable_params = [p for p in model.parameters() if p.requires_grad]
        if params["optimizer"] == "sgd":
            optimizer = torch.optim.SGD(
                trainable_params,
                lr=params["learning_rate"],
                momentum=params["momentum"],
                weight_decay=params["weight_decay"],
            )
        else:
            optimizer = torch.optim.AdamW(
                trainable_params,
                lr=params["learning_rate"],
                weight_decay=params["weight_decay"],
            )

        scheduler = None
        if params["scheduler"] == "cosine":
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=total_epochs
            )
        if hasattr(torch, "amp") and hasattr(torch.amp, "GradScaler"):
            scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
        else:
            scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

        if rank == 0:
            checkpoint_writer = AsyncCheckpointWriter(
                Path(worker_payload["checkpoint_output_path"])
            )
            checkpoint_writer.start()

        best_state_dict = None
        if rank == 0 and isinstance(checkpoint_state, dict):
            best_state_dict = copy.deepcopy(checkpoint_state)

        last_val_metrics = {
            "val_loss": _safe_float(resume_cfg.get("last_val_loss"), default=0.0),
            "val_accuracy": _safe_float(resume_cfg.get("last_val_accuracy"), default=0.0),
            "val_precision": _safe_float(resume_cfg.get("last_val_precision"), default=0.0),
            "val_recall": _safe_float(resume_cfg.get("last_val_recall"), default=0.0),
            "val_f1": _safe_float(resume_cfg.get("last_val_f1"), default=0.0),
        }
        last_loader_meta = {
            "num_workers": 0,
            "prefetch_factor": 0,
            "persistent_workers": False,
            "pin_memory": bool(device.type == "cuda"),
            "distributed": True,
            "preloaded_count": 0,
            "cache_size": 0,
            "cuda_prefetch": False,
        }
        test_loader_rank0 = None
        ran_any_epoch = False

        for fold in fold_batches:
            fold_index = int(fold["fold_index"])
            if fold_index < resume_fold_index:
                continue
            start_fold_epoch = resume_fold_epoch if fold_index == resume_fold_index else 1
            if start_fold_epoch > params["epochs"]:
                continue

            (
                train_loader,
                val_loader,
                test_loader,
                loader_meta,
            ) = _build_loaders(
                fold["train_samples"],
                fold["val_samples"],
                test_samples,
                params,
                image_cache=None,
                gpu_count=1,
                local_batch_size=local_batch_size,
                distributed_rank=rank,
                distributed_world_size=world_size,
            )
            last_loader_meta = loader_meta
            if rank == 0:
                test_loader_rank0 = test_loader
            no_improve_epochs = 0

            for fold_epoch in range(start_fold_epoch, params["epochs"] + 1):
                if isinstance(train_loader.sampler, DistributedSampler):
                    train_loader.sampler.set_epoch(params["seed"] + global_epoch + fold_epoch)
                if _ddp_should_cancel(cancel_event, device):
                    raise TrainingCancelled("训练已被手动终止")

                ran_any_epoch = True
                global_epoch += 1
                model.train()
                train_loss_sum = 0.0
                train_count = 0
                for step, (images, labels) in enumerate(train_loader, start=1):
                    if _ddp_should_cancel(cancel_event, device):
                        raise TrainingCancelled("训练已被手动终止")
                    images = images.to(device, non_blocking=True)
                    labels = labels.to(device, non_blocking=True)
                    optimizer.zero_grad(set_to_none=True)
                    if hasattr(torch, "amp") and hasattr(torch.amp, "autocast"):
                        autocast_ctx = torch.amp.autocast(
                            device_type="cuda", enabled=use_amp
                        )
                    else:
                        autocast_ctx = torch.cuda.amp.autocast(enabled=use_amp)
                    with autocast_ctx:
                        outputs = model(images)
                        loss = criterion(outputs, labels)
                    if not torch.isfinite(loss).item():
                        raise RuntimeError(
                            f"训练阶段出现非有限loss（NaN/Inf），fold={fold_index}, epoch={fold_epoch}, step={step}"
                        )
                    scaler.scale(loss).backward()
                    if use_amp:
                        scaler.unscale_(optimizer)
                    nn.utils.clip_grad_norm_(trainable_params, max_norm=5.0)
                    scaler.step(optimizer)
                    scaler.update()

                    batch_loss = _safe_float(loss.item(), default=float("nan"))
                    train_loss_sum += batch_loss * images.size(0)
                    train_count += images.size(0)

                if scheduler is not None:
                    scheduler.step()

                local_stats = torch.tensor(
                    [train_loss_sum, float(train_count)],
                    device=device,
                    dtype=torch.float64,
                )
                dist.all_reduce(local_stats, op=dist.ReduceOp.SUM)
                avg_train_loss = _safe_float(
                    local_stats[0].item() / max(local_stats[1].item(), 1.0),
                    default=float("nan"),
                )
                if not math.isfinite(avg_train_loss):
                    raise RuntimeError(
                        f"训练阶段平均loss异常（NaN/Inf），fold={fold_index}, epoch={fold_epoch}"
                    )

                need_validate = (
                    fold_epoch % validation_interval == 0
                    or fold_epoch == params["epochs"]
                )
                payload_tensor = torch.zeros(6, dtype=torch.float64, device=device)
                if need_validate and rank == 0:
                    (
                        val_loss,
                        val_acc,
                        val_precision,
                        val_recall,
                        val_f1,
                    ) = _evaluate(
                        model.module,
                        val_loader,
                        criterion,
                        device,
                        gpu_count=1,
                        use_amp=use_amp,
                        enable_cuda_prefetch=False,
                    )
                    last_val_metrics = {
                        "val_loss": val_loss,
                        "val_accuracy": val_acc,
                        "val_precision": val_precision,
                        "val_recall": val_recall,
                        "val_f1": val_f1,
                    }
                    should_stop_early = False
                    if val_acc > best_val_acc:
                        best_val_acc = val_acc
                        best_state_dict = _clone_model_state_to_cpu(model)
                        best_metrics = {
                            "val_loss": val_loss,
                            "val_accuracy": val_acc,
                            "val_precision": val_precision,
                            "val_recall": val_recall,
                            "val_f1": val_f1,
                            "best_epoch": global_epoch,
                            "best_fold": fold_index,
                        }
                        no_improve_epochs = 0
                    else:
                        no_improve_epochs += 1
                        if no_improve_epochs >= params["early_stop_patience"]:
                            should_stop_early = True
                    payload_tensor = torch.tensor(
                        [
                            val_loss,
                            val_acc,
                            val_precision,
                            val_recall,
                            val_f1,
                            1.0 if should_stop_early else 0.0,
                        ],
                        dtype=torch.float64,
                        device=device,
                    )
                elif not need_validate and rank == 0:
                    payload_tensor = torch.tensor(
                        [
                            last_val_metrics["val_loss"],
                            last_val_metrics["val_accuracy"],
                            last_val_metrics["val_precision"],
                            last_val_metrics["val_recall"],
                            last_val_metrics["val_f1"],
                            0.0,
                        ],
                        dtype=torch.float64,
                        device=device,
                    )

                dist.broadcast(payload_tensor, src=0)
                val_loss = _safe_float(payload_tensor[0].item(), default=0.0)
                val_acc = _safe_float(payload_tensor[1].item(), default=0.0)
                val_precision = _safe_float(payload_tensor[2].item(), default=0.0)
                val_recall = _safe_float(payload_tensor[3].item(), default=0.0)
                val_f1 = _safe_float(payload_tensor[4].item(), default=0.0)
                should_stop_early = bool(payload_tensor[5].item() >= 0.5)
                last_val_metrics = {
                    "val_loss": val_loss,
                    "val_accuracy": val_acc,
                    "val_precision": val_precision,
                    "val_recall": val_recall,
                    "val_f1": val_f1,
                }

                if rank == 0:
                    log_row = {
                        "epoch": global_epoch,
                        "fold": fold_index,
                        "fold_epoch": fold_epoch,
                        "evaluated": bool(need_validate),
                        "train_loss": round(_safe_float(avg_train_loss), 6),
                        "val_loss": round(_safe_float(val_loss), 6),
                        "val_accuracy": round(_safe_float(val_acc), 6),
                        "val_precision": round(_safe_float(val_precision), 6),
                        "val_recall": round(_safe_float(val_recall), 6),
                        "val_f1": round(_safe_float(val_f1), 6),
                        "learning_rate": _safe_float(optimizer.param_groups[0]["lr"]),
                    }
                    logs.append(log_row)
                    progress = float(global_epoch * 100.0 / max(total_epochs, 1))
                    message = (
                        f"第 {global_epoch}/{total_epochs} 轮完成"
                        f"（折 {fold_index}/{actual_folds}, 子轮次 {fold_epoch}/{params['epochs']}）"
                    )
                    if not need_validate:
                        message += "，本轮未验证"
                    _mp_queue_put(
                        event_queue,
                        {
                            "type": "epoch",
                            "payload": {
                                "current_epoch": global_epoch,
                                "progress": progress,
                                "train_loss": avg_train_loss,
                                "val_loss": val_loss,
                                "val_accuracy": val_acc,
                                "val_precision": val_precision,
                                "val_recall": val_recall,
                                "val_f1": val_f1,
                                "message": message,
                                "logs": list(logs),
                            },
                        },
                    )
                    if checkpoint_writer is not None:
                        next_fold_index, next_fold_epoch = _next_resume_position(
                            fold_index=fold_index,
                            fold_epoch=fold_epoch,
                            max_fold=actual_folds,
                            max_fold_epoch=params["epochs"],
                            force_next_fold=bool(should_stop_early),
                        )
                        checkpoint_writer.push(
                            {
                                "model_state_dict": _clone_model_state_to_cpu(model),
                                "class_names": class_names,
                                "backbone": params["backbone"],
                                "image_size": params["image_size"],
                                "train_state": {
                                    "global_epoch": global_epoch,
                                    "next_fold_index": next_fold_index,
                                    "next_fold_epoch": next_fold_epoch,
                                    "best_val_acc": _safe_float(
                                        best_val_acc, default=-1.0
                                    ),
                                    "best_metrics": dict(best_metrics),
                                    "last_val_loss": _safe_float(val_loss, default=0.0),
                                    "last_val_accuracy": _safe_float(val_acc, default=0.0),
                                    "last_val_precision": _safe_float(val_precision, default=0.0),
                                    "last_val_recall": _safe_float(val_recall, default=0.0),
                                    "last_val_f1": _safe_float(val_f1, default=0.0),
                                    "saved_at": datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                },
                            }
                        )

                if should_stop_early:
                    break

        if _ddp_should_cancel(cancel_event, device):
            raise TrainingCancelled("训练已被手动终止")

        if rank == 0:
            if best_state_dict is None:
                raise RuntimeError("训练异常结束，未获得有效模型")
            if test_loader_rank0 is None:
                fallback_fold = fold_batches[-1]
                _, _, test_loader_rank0, loader_meta = _build_loaders(
                    fallback_fold["train_samples"],
                    fallback_fold["val_samples"],
                    test_samples,
                    params,
                    image_cache=None,
                    gpu_count=1,
                    local_batch_size=local_batch_size,
                    distributed_rank=0,
                    distributed_world_size=1,
                )
                last_loader_meta = loader_meta
            if not ran_any_epoch and global_epoch > 0:
                _mp_queue_put(
                    event_queue,
                    {
                        "type": "epoch",
                        "payload": {
                            "current_epoch": global_epoch,
                            "progress": float(global_epoch * 100.0 / max(total_epochs, 1)),
                            "train_loss": _safe_float(0.0, default=0.0),
                            "val_loss": _safe_float(last_val_metrics["val_loss"], default=0.0),
                            "val_accuracy": _safe_float(last_val_metrics["val_accuracy"], default=0.0),
                            "val_precision": _safe_float(last_val_metrics["val_precision"], default=0.0),
                            "val_recall": _safe_float(last_val_metrics["val_recall"], default=0.0),
                            "val_f1": _safe_float(last_val_metrics["val_f1"], default=0.0),
                            "message": "检查点已加载，本次直接进入评估与导出",
                            "logs": list(logs),
                        },
                    },
                )
            _load_model_state_compat(model, best_state_dict, strict=True)
            test_loss, test_acc, test_precision, test_recall, test_f1 = _evaluate(
                model.module,
                test_loader_rank0,
                criterion,
                device,
                gpu_count=1,
                use_amp=use_amp,
                enable_cuda_prefetch=False,
            )
            output_path = Path(worker_payload["model_output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "state_dict": _clone_model_state_to_cpu(model),
                    "class_names": class_names,
                    "backbone": params["backbone"],
                    "image_size": params["image_size"],
                    "split_mode": params["split_mode"],
                    "kfold_splits": actual_folds,
                },
                output_path,
            )
            _mp_queue_put(
                event_queue,
                {
                    "type": "success",
                    "payload": {
                        "best_metrics": dict(best_metrics),
                        "test_metrics": {
                            "loss": _safe_float(test_loss, default=0.0),
                            "accuracy": _safe_float(test_acc, default=0.0),
                            "precision": _safe_float(test_precision, default=0.0),
                            "recall": _safe_float(test_recall, default=0.0),
                            "f1": _safe_float(test_f1, default=0.0),
                        },
                        "loader_meta": dict(last_loader_meta),
                    },
                },
            )

    except TrainingCancelled:
        if rank == 0:
            _mp_queue_put(
                event_queue,
                {
                    "type": "canceled",
                    "payload": {
                        "message": "训练已终止",
                        "finished_at": datetime.now(),
                    },
                },
            )
    except Exception as exc:
        if rank == 0:
            _mp_queue_put(
                event_queue,
                {
                    "type": "failed",
                    "payload": {
                        "message": _format_training_error(exc),
                        "traceback": traceback.format_exc(limit=5),
                    },
                },
            )
        raise
    finally:
        try:
            if checkpoint_writer is not None:
                checkpoint_writer.stop()
        finally:
            if dist.is_initialized():
                try:
                    dist.barrier()
                except Exception:
                    pass
                try:
                    dist.destroy_process_group()
                except Exception:
                    pass


class TrainEventHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers = {}
        self._next_id = 1

    def subscribe(self):
        queue_obj = queue.Queue(maxsize=64)
        with self._lock:
            subscriber_id = self._next_id
            self._next_id += 1
            self._subscribers[subscriber_id] = queue_obj
        return subscriber_id, queue_obj

    def unsubscribe(self, subscriber_id: int):
        with self._lock:
            self._subscribers.pop(subscriber_id, None)

    def publish(self, event_name: str, payload: dict):
        with self._lock:
            queues = list(self._subscribers.values())
        message = (event_name, payload)
        for queue_obj in queues:
            try:
                queue_obj.put_nowait(message)
            except queue.Full:
                try:
                    queue_obj.get_nowait()
                except queue.Empty:
                    pass
                try:
                    queue_obj.put_nowait(message)
                except queue.Full:
                    pass


class AsyncJobWriter:
    def __init__(self, flask_app, job_id: int):
        self._flask_app = flask_app
        self._job_id = job_id
        self._queue = queue.Queue(maxsize=24)
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def push_epoch(self, payload: dict):
        self._put("epoch", payload)

    def push_success(self, payload: dict):
        self._put("success", payload)

    def push_failed(self, payload: dict):
        self._put("failed", payload)

    def push_canceled(self, payload: dict):
        self._put("canceled", payload)

    def stop(self):
        if self._stopped.is_set():
            return
        self._stopped.set()
        try:
            self._queue.put_nowait(("stop", None))
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(("stop", None))
        self._thread.join(timeout=20)

    def _put(self, event_name: str, payload: dict):
        if self._stopped.is_set():
            return
        try:
            self._queue.put_nowait((event_name, payload))
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait((event_name, payload))

    def _commit_with_retry(self, retry_times=5):
        for attempt in range(retry_times):
            try:
                db.session.commit()
                return
            except Exception as exc:
                db.session.rollback()
                if "database is locked" in str(exc).lower() and attempt < retry_times - 1:
                    time.sleep(0.08 * (attempt + 1))
                    continue
                raise

    def _run(self):
        with self._flask_app.app_context():
            while True:
                event_name, payload = self._queue.get()
                if event_name == "stop":
                    db.session.remove()
                    break
                try:
                    self._handle_event(event_name, payload)
                except Exception:
                    db.session.rollback()
                finally:
                    db.session.remove()

    def _handle_event(self, event_name: str, payload: dict):
        job = TrainingJob.query.get(self._job_id)
        if not job:
            return

        if event_name == "epoch":
            job.current_epoch = int(payload.get("current_epoch", job.current_epoch))
            job.progress = _safe_float(payload.get("progress", job.progress))
            job.train_loss = _safe_float(payload.get("train_loss", job.train_loss))
            job.val_loss = _safe_float(payload.get("val_loss", job.val_loss))
            job.val_accuracy = _safe_float(payload.get("val_accuracy", job.val_accuracy))
            job.val_precision = _safe_float(payload.get("val_precision", job.val_precision))
            job.val_recall = _safe_float(payload.get("val_recall", job.val_recall))
            job.val_f1 = _safe_float(payload.get("val_f1", job.val_f1))
            job.message = (payload.get("message") or job.message)[:250]
            logs = payload.get("logs")
            if isinstance(logs, list):
                job.set_logs(logs)
            self._commit_with_retry()
            train_event_hub.publish(
                "job_update",
                {"type": "epoch", "job": job.to_dict()},
            )
            return

        if event_name == "success":
            job.status = "success"
            job.progress = 100.0
            job.message = (payload.get("message") or "训练完成")[:250]
            job.model_version_id = payload.get("model_version_id")
            job.finished_at = payload.get("finished_at") or datetime.now()
            job.val_loss = _safe_float(payload.get("val_loss", job.val_loss))
            job.val_accuracy = _safe_float(payload.get("val_accuracy", job.val_accuracy))
            job.val_precision = _safe_float(payload.get("val_precision", job.val_precision))
            job.val_recall = _safe_float(payload.get("val_recall", job.val_recall))
            job.val_f1 = _safe_float(payload.get("val_f1", job.val_f1))
            self._commit_with_retry()
            train_event_hub.publish(
                "job_update",
                {"type": "success", "job": job.to_dict()},
            )
            return

        if event_name == "failed":
            job.status = "failed"
            job.message = (payload.get("message") or "训练失败: 未知错误")[:250]
            job.finished_at = payload.get("finished_at") or datetime.now()
            self._commit_with_retry()
            train_event_hub.publish(
                "job_update",
                {"type": "failed", "job": job.to_dict()},
            )
            return

        if event_name == "canceled":
            job.status = "canceled"
            job.message = (payload.get("message") or "训练已终止")[:250]
            job.finished_at = payload.get("finished_at") or datetime.now()
            self._commit_with_retry()
            train_event_hub.publish(
                "job_update",
                {"type": "canceled", "job": job.to_dict()},
            )


class AsyncCheckpointWriter:
    def __init__(self, checkpoint_path: Path):
        self._checkpoint_path = Path(checkpoint_path)
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._queue = queue.Queue(maxsize=1)
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def push(self, payload: dict):
        if self._stopped.is_set():
            return
        try:
            self._queue.put_nowait(("checkpoint", payload))
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(("checkpoint", payload))

    def stop(self):
        if self._stopped.is_set():
            return
        self._stopped.set()
        try:
            self._queue.put_nowait(("stop", None))
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(("stop", None))
        self._thread.join(timeout=40)

    def _run(self):
        while True:
            event_name, payload = self._queue.get()
            if event_name == "stop":
                break
            if event_name != "checkpoint":
                continue
            try:
                self._write_checkpoint(payload)
            except Exception:
                pass

    def _write_checkpoint(self, payload: dict):
        tmp_path = self._checkpoint_path.with_suffix(
            f"{self._checkpoint_path.suffix}.tmp"
        )
        torch.save(payload, tmp_path)
        os.replace(tmp_path, self._checkpoint_path)


class TrainingManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._threads = {}
        self._cancel_requests = set()
        self._delete_after_cancel = set()

    def _pop_finished_threads(self):
        dead_keys = []
        for job_id, thread in self._threads.items():
            if not thread.is_alive():
                dead_keys.append(job_id)
        for job_id in dead_keys:
            self._threads.pop(job_id, None)

    def _clear_job_state(self, job_id: int):
        with self._lock:
            self._threads.pop(job_id, None)
            self._cancel_requests.discard(job_id)
            self._delete_after_cancel.discard(job_id)

    def has_running_job(self):
        with self._lock:
            self._pop_finished_threads()
            return any(thread.is_alive() for thread in self._threads.values())

    def is_job_running(self, job_id: int):
        with self._lock:
            self._pop_finished_threads()
            thread = self._threads.get(job_id)
            return bool(thread and thread.is_alive())

    def request_cancel(self, job_id: int, delete_after=False):
        with self._lock:
            self._pop_finished_threads()
            thread = self._threads.get(job_id)
            if not thread or not thread.is_alive():
                return False
            self._cancel_requests.add(job_id)
            if delete_after:
                self._delete_after_cancel.add(job_id)
            return True

    def _is_cancel_requested(self, job_id: int):
        with self._lock:
            return job_id in self._cancel_requests

    def _consume_delete_after_cancel(self, job_id: int):
        with self._lock:
            if job_id in self._delete_after_cancel:
                self._delete_after_cancel.discard(job_id)
                return True
            return False

    def recover_stale_jobs(self):
        with self._lock:
            self._pop_finished_threads()
            active_job_ids = {
                item_id for item_id, thread in self._threads.items() if thread.is_alive()
            }

        stale_rows = TrainingJob.query.filter(
            TrainingJob.status.in_(["running", "canceling"])
        ).all()
        if not stale_rows:
            return []

        now = datetime.now()
        changed = []
        for row in stale_rows:
            if row.id in active_job_ids:
                continue
            row.status = "failed"
            row.message = "训练任务异常中断，可点击复活重新启动"
            row.finished_at = now
            changed.append(row)
        if not changed:
            return []
        db.session.commit()
        for item in changed:
            train_event_hub.publish(
                "job_update",
                {"type": "failed", "job": item.to_dict()},
            )
        return [item.id for item in changed]

    def start(self, flask_app, job_id: int, resume_from_job_id: int = 0):
        with self._lock:
            self._pop_finished_threads()
            if any(thread.is_alive() for thread in self._threads.values()):
                raise RuntimeError("已有训练任务在运行，请等待当前任务完成")
            thread = threading.Thread(
                target=self._run_training_job,
                args=(flask_app, job_id, int(resume_from_job_id or 0)),
                daemon=True,
            )
            self._threads[job_id] = thread
            thread.start()

    def _run_ddp_training(
        self,
        job_id: int,
        params: dict,
        class_names: list,
        fold_batches: list,
        test_samples: list,
        actual_folds: int,
        total_epochs: int,
        job_writer,
        checkpoint_path: Path,
        model_dir: Path,
        resume_cfg: dict,
        initial_logs: list,
    ):
        world_size = int(torch.cuda.device_count())
        if world_size <= 1:
            raise RuntimeError("DDP模式至少需要2张可见GPU")

        model_name = (
            f"{params['backbone']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            f"_{uuid.uuid4().hex[:6]}"
        )
        model_path = model_dir / f"{model_name}.pt"
        ctx = mp.get_context("spawn")
        event_queue = ctx.Queue(maxsize=128)
        cancel_event = ctx.Event()
        worker_payload = {
            "master_addr": "127.0.0.1",
            "master_port": _find_free_port(),
            "params": params,
            "class_names": class_names,
            "fold_batches": fold_batches,
            "test_samples": test_samples,
            "actual_folds": int(actual_folds),
            "total_epochs": int(total_epochs),
            "checkpoint_output_path": str(checkpoint_path),
            "model_output_path": str(model_path),
            "resume": dict(resume_cfg or {}),
            "initial_logs": list(initial_logs or []),
        }
        spawn_ctx = mp.spawn(
            _ddp_worker_train,
            args=(world_size, worker_payload, event_queue, cancel_event),
            nprocs=world_size,
            join=False,
        )

        success_payload = None
        failed_message = ""
        canceled = False

        def _drain_events(block=False):
            nonlocal success_payload, failed_message, canceled
            while True:
                try:
                    if block:
                        event = event_queue.get(timeout=0.2)
                    else:
                        event = event_queue.get_nowait()
                except queue.Empty:
                    break
                event_type = event.get("type")
                payload = event.get("payload") or {}
                if event_type == "epoch":
                    job_writer.push_epoch(payload)
                elif event_type == "success":
                    success_payload = payload
                elif event_type == "failed":
                    failed_message = (payload.get("message") or "DDP训练失败")[:250]
                elif event_type == "canceled":
                    canceled = True

        while True:
            if self._is_cancel_requested(job_id):
                cancel_event.set()
            _drain_events(block=False)
            finished = False
            try:
                finished = bool(spawn_ctx.join(timeout=0.2))
            except Exception as exc:
                _drain_events(block=False)
                if failed_message:
                    finished = True
                else:
                    raise RuntimeError(f"DDP子进程异常: {exc}")
            if failed_message or canceled:
                cancel_event.set()
            if finished:
                break

        _drain_events(block=False)
        try:
            spawn_ctx.join(timeout=0.1)
        except Exception:
            pass

        if canceled:
            raise TrainingCancelled("训练已终止")
        if failed_message:
            raise RuntimeError(failed_message)
        if not success_payload:
            raise RuntimeError("DDP训练未返回成功结果")

        return {
            "model_name": model_name,
            "model_path": str(model_path),
            "best_metrics": dict(success_payload.get("best_metrics") or {}),
            "test_metrics": dict(success_payload.get("test_metrics") or {}),
            "loader_meta": dict(success_payload.get("loader_meta") or {}),
            "parallel_mode": "ddp",
            "gpu_count": world_size,
        }

    def _run_training_job(self, flask_app, job_id: int, resume_from_job_id: int = 0):
        with flask_app.app_context():
            job = TrainingJob.query.get(job_id)
            if not job:
                return
            job_writer = None
            checkpoint_writer = None
            delete_after_cancel = False
            training_success = False
            try:
                job.status = "running"
                job.started_at = datetime.now()
                job.message = "准备加载数据集"
                db.session.commit()

                params = normalize_train_params(job.get_params())
                torch.manual_seed(params["seed"])

                summary = get_dataset_summary(job.dataset_dir)
                class_names, samples = build_classification_samples(job.dataset_dir)
                if params["split_mode"] == "kfold":
                    fold_batches, test_samples, actual_folds = _build_kfold_batches(
                        samples=samples,
                        test_ratio=params["test_ratio"],
                        kfold_splits=params["kfold_splits"],
                        seed=params["seed"],
                    )
                else:
                    train_samples, val_samples, test_samples = build_train_val_test_split(
                        samples,
                        val_ratio=params["val_ratio"],
                        test_ratio=params["test_ratio"],
                        seed=params["seed"],
                    )
                    fold_batches = [
                        {
                            "fold_index": 1,
                            "train_samples": train_samples,
                            "val_samples": val_samples,
                        }
                    ]
                    actual_folds = 1
                if not fold_batches:
                    raise RuntimeError("数据划分失败，未生成可用训练批次")
                if not test_samples:
                    raise RuntimeError("测试集为空，请降低test_ratio后重试")

                total_epochs = int(params["epochs"]) * int(actual_folds)
                job.total_epochs = total_epochs
                job.message = "数据集准备完成，开始训练"
                db.session.commit()

                job_writer = AsyncJobWriter(flask_app, job_id)
                job_writer.start()

                def _check_cancel():
                    if self._is_cancel_requested(job_id):
                        raise TrainingCancelled("训练已被手动终止")

                device = _detect_device(params["device"])
                gpu_count = torch.cuda.device_count() if device.type == "cuda" else 0
                use_ddp = bool(device.type == "cuda" and gpu_count > 1)
                validation_interval = int(params["validation_interval"])
                if use_ddp:
                    parallel_mode = "ddp"
                    checkpoint_path = _checkpoint_file_path(
                        flask_app.config["CHECKPOINT_DIR"], job_id
                    )
                    logs = job.get_logs()
                    if not isinstance(logs, list):
                        logs = []
                    resume_cfg = {
                        "checkpoint_path": "",
                        "next_fold_index": 1,
                        "next_fold_epoch": 1,
                        "global_epoch": 0,
                        "best_val_acc": -1.0,
                        "best_metrics": {},
                        "last_val_loss": 0.0,
                        "last_val_accuracy": 0.0,
                        "last_val_precision": 0.0,
                        "last_val_recall": 0.0,
                        "last_val_f1": 0.0,
                    }
                    resume_job_id = _safe_int(resume_from_job_id, default=0)
                    resume_loaded = False
                    if resume_job_id > 0:
                        resume_path = _checkpoint_file_path(
                            flask_app.config["CHECKPOINT_DIR"], resume_job_id
                        )
                        if resume_path.exists() and resume_path.is_file():
                            try:
                                resume_payload = _safe_torch_load(
                                    resume_path, map_location="cpu"
                                )
                                checkpoint_backbone = str(
                                    resume_payload.get("backbone") or ""
                                )
                                if (
                                    checkpoint_backbone
                                    and checkpoint_backbone != params["backbone"]
                                ):
                                    raise RuntimeError("检查点主干网络不一致")
                                checkpoint_class_names = (
                                    resume_payload.get("class_names") or []
                                )
                                if (
                                    checkpoint_class_names
                                    and checkpoint_class_names != class_names
                                ):
                                    raise RuntimeError("检查点类别不一致")
                                checkpoint_state = resume_payload.get("model_state_dict")
                                if not isinstance(checkpoint_state, dict):
                                    raise RuntimeError("检查点权重损坏")
                                train_state = resume_payload.get("train_state") or {}
                                resume_cfg.update(
                                    {
                                        "checkpoint_path": str(resume_path),
                                        "next_fold_index": max(
                                            1,
                                            _safe_int(
                                                train_state.get("next_fold_index"), default=1
                                            ),
                                        ),
                                        "next_fold_epoch": max(
                                            1,
                                            _safe_int(
                                                train_state.get("next_fold_epoch"), default=1
                                            ),
                                        ),
                                        "global_epoch": max(
                                            0,
                                            _safe_int(
                                                train_state.get("global_epoch"), default=0
                                            ),
                                        ),
                                        "best_val_acc": _safe_float(
                                            train_state.get("best_val_acc"),
                                            default=-1.0,
                                        ),
                                        "best_metrics": dict(
                                            train_state.get("best_metrics") or {}
                                        )
                                        if isinstance(
                                            train_state.get("best_metrics"), dict
                                        )
                                        else {},
                                        "last_val_loss": _safe_float(
                                            train_state.get("last_val_loss"), default=0.0
                                        ),
                                        "last_val_accuracy": _safe_float(
                                            train_state.get("last_val_accuracy"),
                                            default=0.0,
                                        ),
                                        "last_val_precision": _safe_float(
                                            train_state.get("last_val_precision"),
                                            default=0.0,
                                        ),
                                        "last_val_recall": _safe_float(
                                            train_state.get("last_val_recall"),
                                            default=0.0,
                                        ),
                                        "last_val_f1": _safe_float(
                                            train_state.get("last_val_f1"), default=0.0
                                        ),
                                    }
                                )
                                resume_loaded = True
                            except Exception as exc:
                                resume_loaded = False
                                resume_cfg["checkpoint_path"] = ""
                                job.message = (
                                    f"检查点不可用，已降级从头训练：{str(exc)[:120]}"
                                )
                        else:
                            job.message = "未找到可用检查点，已从头启动DDP训练"

                    if resume_loaded:
                        job.current_epoch = int(resume_cfg["global_epoch"])
                        job.progress = float(
                            int(resume_cfg["global_epoch"]) * 100.0
                            / max(total_epochs, 1)
                        )
                        job.message = (
                            f"已加载任务#{resume_job_id}检查点，"
                            f"DDP从折{resume_cfg['next_fold_index']}-子轮次{resume_cfg['next_fold_epoch']}继续"
                        )
                    elif not str(job.message or "").startswith("检查点"):
                        job.message = f"已启用{gpu_count}卡DDP并行训练"
                    db.session.commit()
                    train_event_hub.publish(
                        "job_update",
                        {"type": "running", "job": job.to_dict()},
                    )

                    ddp_result = self._run_ddp_training(
                        job_id=job_id,
                        params=params,
                        class_names=class_names,
                        fold_batches=fold_batches,
                        test_samples=test_samples,
                        actual_folds=actual_folds,
                        total_epochs=total_epochs,
                        job_writer=job_writer,
                        checkpoint_path=checkpoint_path,
                        model_dir=Path(flask_app.config["MODEL_DIR"]),
                        resume_cfg=resume_cfg,
                        initial_logs=logs,
                    )
                    best_metrics = dict(ddp_result.get("best_metrics") or {})
                    test_metrics = dict(ddp_result.get("test_metrics") or {})
                    last_loader_meta = dict(ddp_result.get("loader_meta") or {})
                    existing_active = ModelVersion.query.filter_by(is_active=True).first()
                    metrics_payload = {
                        "best": best_metrics,
                        "test": {
                            "loss": _safe_float(test_metrics.get("loss"), default=0.0),
                            "accuracy": _safe_float(
                                test_metrics.get("accuracy"), default=0.0
                            ),
                            "precision": _safe_float(
                                test_metrics.get("precision"), default=0.0
                            ),
                            "recall": _safe_float(
                                test_metrics.get("recall"), default=0.0
                            ),
                            "f1": _safe_float(test_metrics.get("f1"), default=0.0),
                        },
                        "dataset": {
                            "dataset_dir": summary.dataset_dir,
                            "total_images": summary.total_images,
                            "class_count": summary.class_count,
                            "split_mode": params["split_mode"],
                            "folds": actual_folds,
                            "total_epochs": total_epochs,
                            "validation_interval": validation_interval,
                            "train_count": len(fold_batches[0]["train_samples"]),
                            "val_count": len(fold_batches[0]["val_samples"]),
                            "test_count": len(test_samples),
                            "num_workers": int(last_loader_meta.get("num_workers", 0)),
                            "prefetch_factor": int(
                                last_loader_meta.get("prefetch_factor", 0)
                            ),
                            "persistent_workers": bool(
                                last_loader_meta.get("persistent_workers", False)
                            ),
                            "pin_memory": bool(last_loader_meta.get("pin_memory", True)),
                            "preloaded_count": int(
                                last_loader_meta.get("preloaded_count", 0)
                            ),
                            "cache_size": int(last_loader_meta.get("cache_size", 0)),
                            "cuda_prefetch": bool(
                                last_loader_meta.get("cuda_prefetch", False)
                            ),
                            "cuda_prefetch_bytes": 0,
                            "cuda_prefetch_budget": 0,
                            "parallel_mode": parallel_mode,
                            "gpu_count": int(ddp_result.get("gpu_count", gpu_count)),
                        },
                    }
                    stored_model_path = to_model_relative_path(
                        ddp_result["model_path"], flask_app.config["MODEL_DIR"]
                    )
                    version = ModelVersion(
                        name=str(ddp_result["model_name"]),
                        backbone=params["backbone"],
                        model_path=stored_model_path,
                        params_json=json.dumps(params, ensure_ascii=False),
                        metrics_json=json.dumps(metrics_payload, ensure_ascii=False),
                        labels_json=json.dumps(class_names, ensure_ascii=False),
                        is_active=existing_active is None,
                    )
                    db.session.add(version)
                    db.session.commit()
                    training_success = True
                    job_writer.push_success(
                        {
                            "message": "训练完成",
                            "model_version_id": version.id,
                            "finished_at": datetime.now(),
                            "val_loss": best_metrics.get("val_loss", 0.0),
                            "val_accuracy": best_metrics.get("val_accuracy", 0.0),
                            "val_precision": best_metrics.get("val_precision", 0.0),
                            "val_recall": best_metrics.get("val_recall", 0.0),
                            "val_f1": best_metrics.get("val_f1", 0.0),
                        }
                    )
                    return

                checkpoint_writer = AsyncCheckpointWriter(
                    _checkpoint_file_path(flask_app.config["CHECKPOINT_DIR"], job_id)
                )
                checkpoint_writer.start()
                use_amp = bool(params["use_amp"] and device.type == "cuda")
                model = build_model(
                    backbone=params["backbone"],
                    num_classes=len(class_names),
                    pretrained=True,
                )
                if params["freeze_backbone"]:
                    freeze_backbone_layers(model, params["backbone"])
                model = model.to(device)
                parallel_mode = "single_gpu" if gpu_count == 1 else "cpu"
                cuda_prefetch_enabled, cuda_prefetch_bytes, cuda_prefetch_budget = (
                    _should_enable_cuda_prefetch(device, params, gpu_count=gpu_count)
                )
                criterion = nn.CrossEntropyLoss(
                    label_smoothing=float(params["label_smoothing"])
                )
                trainable_params = [p for p in model.parameters() if p.requires_grad]
                if params["optimizer"] == "sgd":
                    optimizer = torch.optim.SGD(
                        trainable_params,
                        lr=params["learning_rate"],
                        momentum=params["momentum"],
                        weight_decay=params["weight_decay"],
                    )
                else:
                    optimizer = torch.optim.AdamW(
                        trainable_params,
                        lr=params["learning_rate"],
                        weight_decay=params["weight_decay"],
                    )

                scheduler = None
                if params["scheduler"] == "cosine":
                    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                        optimizer, T_max=total_epochs
                    )

                if hasattr(torch, "amp") and hasattr(torch.amp, "GradScaler"):
                    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
                else:
                    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)
                logs = job.get_logs()
                if not isinstance(logs, list):
                    logs = []
                best_val_acc = -1.0
                best_state_dict = None
                best_metrics = {}
                validation_interval = int(params["validation_interval"])
                global_epoch = 0
                resume_fold_index = 1
                resume_fold_epoch = 1
                image_cache = ImageCache(
                    enabled=params["cache_images"],
                    max_items=params["cache_limit"],
                )
                last_loader_meta = {
                    "num_workers": 0,
                    "prefetch_factor": 0,
                    "persistent_workers": False,
                    "pin_memory": bool(device.type == "cuda"),
                    "preloaded_count": 0,
                    "cache_size": 0,
                    "cuda_prefetch": bool(cuda_prefetch_enabled),
                }
                last_val_metrics = {
                    "val_loss": 0.0,
                    "val_accuracy": 0.0,
                    "val_precision": 0.0,
                    "val_recall": 0.0,
                    "val_f1": 0.0,
                }
                test_loader = None
                ran_any_epoch = False
                resume_loaded = False

                resume_job_id = _safe_int(resume_from_job_id, default=0)
                if resume_job_id > 0:
                    resume_path = _checkpoint_file_path(
                        flask_app.config["CHECKPOINT_DIR"], resume_job_id
                    )
                    if resume_path.exists() and resume_path.is_file():
                        resume_payload = _safe_torch_load(resume_path, map_location="cpu")
                        checkpoint_backbone = str(resume_payload.get("backbone") or "")
                        if checkpoint_backbone and checkpoint_backbone != params["backbone"]:
                            raise RuntimeError("检查点主干网络与当前参数不一致，无法续训")
                        checkpoint_class_names = resume_payload.get("class_names") or []
                        if checkpoint_class_names and checkpoint_class_names != class_names:
                            raise RuntimeError("检查点类别与当前数据集不一致，无法续训")
                        checkpoint_state = resume_payload.get("model_state_dict")
                        if not isinstance(checkpoint_state, dict):
                            raise RuntimeError("检查点文件损坏，无法续训")
                        _load_model_state_compat(model, checkpoint_state, strict=True)

                        train_state = resume_payload.get("train_state") or {}
                        resume_fold_index = max(
                            1, _safe_int(train_state.get("next_fold_index"), default=1)
                        )
                        resume_fold_epoch = max(
                            1, _safe_int(train_state.get("next_fold_epoch"), default=1)
                        )
                        global_epoch = max(
                            0, _safe_int(train_state.get("global_epoch"), default=0)
                        )
                        best_val_acc = _safe_float(
                            train_state.get("best_val_acc"), default=-1.0
                        )
                        state_best_metrics = train_state.get("best_metrics")
                        if isinstance(state_best_metrics, dict):
                            best_metrics = state_best_metrics
                        best_state_dict = copy.deepcopy(checkpoint_state)
                        resume_loaded = True

                        job.current_epoch = global_epoch
                        job.progress = float(global_epoch * 100.0 / max(total_epochs, 1))
                        job.message = (
                            f"已加载任务#{resume_job_id}检查点，"
                            f"从折{resume_fold_index}-子轮次{resume_fold_epoch}继续"
                        )
                        if gpu_count > 1:
                            job.message += f"，已启用{gpu_count}卡并行"
                        db.session.commit()
                        train_event_hub.publish(
                            "job_update",
                            {"type": "running", "job": job.to_dict()},
                        )
                if not resume_loaded:
                    if gpu_count > 1:
                        job.message = f"已启用{gpu_count}卡并行训练"
                    elif gpu_count == 1:
                        if cuda_prefetch_enabled:
                            job.message = "已启用单卡GPU训练（显存预取开启）"
                        else:
                            job.message = "已启用单卡GPU训练"
                    else:
                        job.message = "当前使用CPU训练"
                    db.session.commit()
                    train_event_hub.publish(
                        "job_update",
                        {"type": "running", "job": job.to_dict()},
                    )

                for fold in fold_batches:
                    _check_cancel()
                    no_improve_epochs = 0
                    fold_index = int(fold["fold_index"])
                    if fold_index < resume_fold_index:
                        continue
                    start_fold_epoch = (
                        resume_fold_epoch if fold_index == resume_fold_index else 1
                    )
                    if start_fold_epoch > params["epochs"]:
                        continue
                    train_loader, val_loader, test_loader, loader_meta = _build_loaders(
                        fold["train_samples"],
                        fold["val_samples"],
                        test_samples,
                        params,
                        image_cache=image_cache if params["cache_images"] else None,
                        gpu_count=gpu_count,
                    )
                    loader_meta["cuda_prefetch"] = bool(
                        cuda_prefetch_enabled and gpu_count == 1
                    )
                    last_loader_meta = loader_meta

                    for fold_epoch in range(start_fold_epoch, params["epochs"] + 1):
                        _check_cancel()
                        ran_any_epoch = True
                        global_epoch += 1

                        model.train()
                        train_loss_sum = 0.0
                        train_count = 0
                        train_batches = CudaBatchPrefetcher(
                            train_loader,
                            device,
                            enabled=bool(cuda_prefetch_enabled and gpu_count == 1),
                        )
                        for step, (images, labels) in enumerate(train_batches, start=1):
                            _check_cancel()
                            if gpu_count <= 1:
                                if images.device.type != device.type:
                                    images = images.to(device, non_blocking=True)
                                if labels.device.type != device.type:
                                    labels = labels.to(device, non_blocking=True)
                            optimizer.zero_grad(set_to_none=True)
                            if hasattr(torch, "amp") and hasattr(torch.amp, "autocast"):
                                autocast_ctx = torch.amp.autocast(
                                    device_type="cuda", enabled=use_amp
                                )
                            else:
                                autocast_ctx = torch.cuda.amp.autocast(enabled=use_amp)
                            with autocast_ctx:
                                outputs = model(images)
                                if labels.device != outputs.device:
                                    labels = labels.to(outputs.device, non_blocking=True)
                                loss = criterion(outputs, labels)
                            if not torch.isfinite(loss).item():
                                raise RuntimeError(
                                    f"训练阶段出现非有限loss（NaN/Inf），fold={fold_index}, epoch={fold_epoch}, step={step}"
                                )
                            scaler.scale(loss).backward()
                            if use_amp:
                                scaler.unscale_(optimizer)
                            nn.utils.clip_grad_norm_(trainable_params, max_norm=5.0)
                            scaler.step(optimizer)
                            scaler.update()

                            batch_loss = _safe_float(loss.item(), default=float("nan"))
                            train_loss_sum += batch_loss * images.size(0)
                            train_count += images.size(0)

                        if scheduler is not None:
                            scheduler.step()

                        avg_train_loss = _safe_float(
                            train_loss_sum / max(train_count, 1), default=float("nan")
                        )
                        if not math.isfinite(avg_train_loss):
                            raise RuntimeError(
                                f"训练阶段平均loss异常（NaN/Inf），fold={fold_index}, epoch={fold_epoch}"
                            )

                        need_validate = (
                            fold_epoch % validation_interval == 0
                            or fold_epoch == params["epochs"]
                        )
                        if need_validate:
                            (
                                val_loss,
                                val_acc,
                                val_precision,
                                val_recall,
                                val_f1,
                            ) = _evaluate(
                                model,
                                val_loader,
                                criterion,
                                device,
                                gpu_count=gpu_count,
                                use_amp=use_amp,
                                enable_cuda_prefetch=bool(
                                    cuda_prefetch_enabled and gpu_count == 1
                                ),
                            )
                            last_val_metrics = {
                                "val_loss": val_loss,
                                "val_accuracy": val_acc,
                                "val_precision": val_precision,
                                "val_recall": val_recall,
                                "val_f1": val_f1,
                            }
                            if val_acc > best_val_acc:
                                best_val_acc = val_acc
                                best_state_dict = _clone_model_state_to_cpu(model)
                                best_metrics = {
                                    "val_loss": val_loss,
                                    "val_accuracy": val_acc,
                                    "val_precision": val_precision,
                                    "val_recall": val_recall,
                                    "val_f1": val_f1,
                                    "best_epoch": global_epoch,
                                    "best_fold": fold_index,
                                }
                                no_improve_epochs = 0
                            else:
                                no_improve_epochs += 1
                        else:
                            val_loss = last_val_metrics["val_loss"]
                            val_acc = last_val_metrics["val_accuracy"]
                            val_precision = last_val_metrics["val_precision"]
                            val_recall = last_val_metrics["val_recall"]
                            val_f1 = last_val_metrics["val_f1"]

                        log_row = {
                            "epoch": global_epoch,
                            "fold": fold_index,
                            "fold_epoch": fold_epoch,
                            "evaluated": bool(need_validate),
                            "train_loss": round(_safe_float(avg_train_loss), 6),
                            "val_loss": round(_safe_float(val_loss), 6),
                            "val_accuracy": round(_safe_float(val_acc), 6),
                            "val_precision": round(_safe_float(val_precision), 6),
                            "val_recall": round(_safe_float(val_recall), 6),
                            "val_f1": round(_safe_float(val_f1), 6),
                            "learning_rate": _safe_float(optimizer.param_groups[0]["lr"]),
                        }
                        logs.append(log_row)

                        progress = float(global_epoch * 100.0 / max(total_epochs, 1))
                        message = (
                            f"第 {global_epoch}/{total_epochs} 轮完成"
                            f"（折 {fold_index}/{actual_folds}, 子轮次 {fold_epoch}/{params['epochs']}）"
                        )
                        if not need_validate:
                            message += "，本轮未验证"

                        job_writer.push_epoch(
                            {
                                "current_epoch": global_epoch,
                                "progress": progress,
                                "train_loss": avg_train_loss,
                                "val_loss": val_loss,
                                "val_accuracy": val_acc,
                                "val_precision": val_precision,
                                "val_recall": val_recall,
                                "val_f1": val_f1,
                                "message": message,
                                "logs": list(logs),
                            }
                        )
                        should_stop_early = (
                            need_validate
                            and no_improve_epochs >= params["early_stop_patience"]
                        )
                        next_fold_index, next_fold_epoch = _next_resume_position(
                            fold_index=fold_index,
                            fold_epoch=fold_epoch,
                            max_fold=actual_folds,
                            max_fold_epoch=params["epochs"],
                            force_next_fold=should_stop_early,
                        )
                        checkpoint_writer.push(
                            {
                                "model_state_dict": _clone_model_state_to_cpu(model),
                                "class_names": class_names,
                                "backbone": params["backbone"],
                                "image_size": params["image_size"],
                                "train_state": {
                                    "global_epoch": global_epoch,
                                    "next_fold_index": next_fold_index,
                                    "next_fold_epoch": next_fold_epoch,
                                    "best_val_acc": _safe_float(
                                        best_val_acc, default=-1.0
                                    ),
                                    "best_metrics": dict(best_metrics),
                                    "saved_at": datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                },
                            }
                        )

                        if should_stop_early:
                            break

                _check_cancel()
                if best_state_dict is None:
                    raise RuntimeError("训练异常结束，未获得有效模型")
                if test_loader is None:
                    fallback_fold = fold_batches[-1]
                    _, _, test_loader, loader_meta = _build_loaders(
                        fallback_fold["train_samples"],
                        fallback_fold["val_samples"],
                        test_samples,
                        params,
                        image_cache=image_cache if params["cache_images"] else None,
                        gpu_count=gpu_count,
                    )
                    loader_meta["cuda_prefetch"] = bool(
                        cuda_prefetch_enabled and gpu_count == 1
                    )
                    last_loader_meta = loader_meta
                if not ran_any_epoch and global_epoch > 0:
                    job_writer.push_epoch(
                        {
                            "current_epoch": global_epoch,
                            "progress": float(global_epoch * 100.0 / max(total_epochs, 1)),
                            "train_loss": _safe_float(job.train_loss, default=0.0),
                            "val_loss": _safe_float(job.val_loss, default=0.0),
                            "val_accuracy": _safe_float(job.val_accuracy, default=0.0),
                            "val_precision": _safe_float(job.val_precision, default=0.0),
                            "val_recall": _safe_float(job.val_recall, default=0.0),
                            "val_f1": _safe_float(job.val_f1, default=0.0),
                            "message": "检查点已加载，本次直接进入评估与导出",
                            "logs": list(logs),
                        }
                    )

                _load_model_state_compat(model, best_state_dict, strict=True)
                test_loss, test_acc, test_precision, test_recall, test_f1 = _evaluate(
                    model,
                    test_loader,
                    criterion,
                    device,
                    gpu_count=gpu_count,
                    use_amp=use_amp,
                    enable_cuda_prefetch=bool(cuda_prefetch_enabled and gpu_count == 1),
                )

                model_name = (
                    f"{params['backbone']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    f"_{uuid.uuid4().hex[:6]}"
                )
                model_path = Path(flask_app.config["MODEL_DIR"]) / f"{model_name}.pt"
                checkpoint = {
                    "state_dict": _clone_model_state_to_cpu(model),
                    "class_names": class_names,
                    "backbone": params["backbone"],
                    "image_size": params["image_size"],
                    "split_mode": params["split_mode"],
                    "kfold_splits": actual_folds,
                }
                torch.save(checkpoint, model_path)

                existing_active = ModelVersion.query.filter_by(is_active=True).first()
                metrics_payload = {
                    "best": best_metrics,
                    "test": {
                        "loss": test_loss,
                        "accuracy": test_acc,
                        "precision": test_precision,
                        "recall": test_recall,
                        "f1": test_f1,
                    },
                    "dataset": {
                        "dataset_dir": summary.dataset_dir,
                        "total_images": summary.total_images,
                        "class_count": summary.class_count,
                        "split_mode": params["split_mode"],
                        "folds": actual_folds,
                        "total_epochs": total_epochs,
                        "validation_interval": validation_interval,
                        "train_count": len(fold_batches[0]["train_samples"]),
                        "val_count": len(fold_batches[0]["val_samples"]),
                        "test_count": len(test_samples),
                        "num_workers": last_loader_meta["num_workers"],
                        "prefetch_factor": last_loader_meta["prefetch_factor"],
                        "persistent_workers": last_loader_meta["persistent_workers"],
                        "pin_memory": last_loader_meta["pin_memory"],
                        "preloaded_count": last_loader_meta["preloaded_count"],
                        "cache_size": last_loader_meta["cache_size"],
                        "cuda_prefetch": last_loader_meta["cuda_prefetch"],
                        "cuda_prefetch_bytes": cuda_prefetch_bytes,
                        "cuda_prefetch_budget": cuda_prefetch_budget,
                        "parallel_mode": parallel_mode,
                        "gpu_count": gpu_count,
                    },
                }
                stored_model_path = to_model_relative_path(
                    model_path, flask_app.config["MODEL_DIR"]
                )

                version = ModelVersion(
                    name=model_name,
                    backbone=params["backbone"],
                    model_path=stored_model_path,
                    params_json=json.dumps(params, ensure_ascii=False),
                    metrics_json=json.dumps(metrics_payload, ensure_ascii=False),
                    labels_json=json.dumps(class_names, ensure_ascii=False),
                    is_active=existing_active is None,
                )
                db.session.add(version)
                db.session.commit()
                training_success = True
                job_writer.push_success(
                    {
                        "message": "训练完成",
                        "model_version_id": version.id,
                        "finished_at": datetime.now(),
                        "val_loss": best_metrics.get("val_loss", 0.0),
                        "val_accuracy": best_metrics.get("val_accuracy", 0.0),
                        "val_precision": best_metrics.get("val_precision", 0.0),
                        "val_recall": best_metrics.get("val_recall", 0.0),
                        "val_f1": best_metrics.get("val_f1", 0.0),
                    }
                )
            except TrainingCancelled:
                db.session.rollback()
                delete_after_cancel = self._consume_delete_after_cancel(job_id)
                if job_writer is not None and not delete_after_cancel:
                    job_writer.push_canceled(
                        {
                            "message": "训练已终止",
                            "finished_at": datetime.now(),
                        }
                    )
                elif not delete_after_cancel:
                    job = TrainingJob.query.get(job_id)
                    if job:
                        job.status = "canceled"
                        job.message = "训练已终止"
                        job.finished_at = datetime.now()
                        db.session.commit()
            except Exception as exc:
                db.session.rollback()
                failure_message = _format_training_error(exc)
                if job_writer is not None:
                    job_writer.push_failed(
                        {
                            "message": failure_message,
                            "finished_at": datetime.now(),
                        }
                    )
                else:
                    job = TrainingJob.query.get(job_id)
                    if job:
                        job.status = "failed"
                        job.message = failure_message
                        job.finished_at = datetime.now()
                        db.session.commit()
            finally:
                if checkpoint_writer is not None:
                    checkpoint_writer.stop()
                if job_writer is not None:
                    job_writer.stop()
                if not delete_after_cancel:
                    delete_after_cancel = self._consume_delete_after_cancel(job_id)
                if delete_after_cancel:
                    remove_job_checkpoint(flask_app.config["CHECKPOINT_DIR"], job_id)
                    job = TrainingJob.query.get(job_id)
                    if job:
                        db.session.delete(job)
                        db.session.commit()
                    train_event_hub.publish(
                        "job_deleted",
                        {"job_id": job_id, "reason": "canceled_deleted"},
                    )
                elif training_success:
                    remove_job_checkpoint(flask_app.config["CHECKPOINT_DIR"], job_id)
                self._clear_job_state(job_id)
                db.session.remove()

train_event_hub = TrainEventHub()
training_manager = TrainingManager()
