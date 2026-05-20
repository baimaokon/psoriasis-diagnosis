"""
inference_service.py — 推理引擎
───────────────────────────────
职责：
  InferenceEngine 是系统的核心推理组件，负责：
  1. 加载当前在线模型（is_active=True）→ _load_active_model()
     带双重检查锁定的模型缓存，避免并发重复加载
  2. 图像预处理（ImageNet 标准化） → _preprocess()
  3. 前向推理获取 Top-3 预测 → predict()
  4. Grad-CAM 可解释性热力图生成 → _create_gradcam_overlay()
     通过 hook 捕获最后卷积层的特征图与梯度，
     全局平均池化梯度作为权重 → 加权求和 → ReLU → 上采样 → 伪彩色叠加
  5. 兼容 DDP 训练保存的模型权重（module. 前缀处理）→ _load_state_dict_compat()
被调方：
  routes/user.py — 单张诊断 /api/user/diagnose、批量诊断 /api/user/diagnose/batch
依赖：
  models/model_version.py → 查询 is_active=True 的模型
  services/model_factory.py → build_model() + find_last_conv_layer()
  utils/label_mapping.py → 英→中标签翻译
  utils/model_path.py → 解析模型文件路径
全局单例：inference_engine = InferenceEngine()
"""

import json
import threading
import uuid
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from flask import current_app
from PIL import Image
from torchvision import transforms

from app.models import ModelVersion
from app.utils.label_mapping import get_label_info
from app.utils.model_path import resolve_model_path

from .model_factory import build_model, find_last_conv_layer


class InferenceEngine:
    """推理引擎：加载已上线模型，执行图像分类并生成 Grad-CAM 热力图"""

    def __init__(self):
        self._lock = threading.Lock()
        self._cached_model_id = None
        self._model = None
        self._class_names = []
        self._image_size = 224
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _load_active_model(self):
        """加载当前已上线的模型，带缓存复用"""
        active = (
            ModelVersion.query.filter_by(is_active=True)
            .order_by(ModelVersion.id.desc())
            .first()
        )
        if not active:
            raise RuntimeError("当前没有已上线模型，请先在管理端完成训练并上线")

        # 快速路径：无锁检查
        if self._cached_model_id == active.id and self._model is not None:
            return

        with self._lock:
            # 双重检查：避免并发请求重复加载
            if self._cached_model_id == active.id and self._model is not None:
                return

            labels = active.get_labels()
            if not labels:
                try:
                    labels = json.loads(active.labels_json or "[]")
                except json.JSONDecodeError:
                    labels = []
            if not labels:
                raise RuntimeError("模型标签信息缺失，无法推理")

            resolved_model_path = resolve_model_path(
                active.model_path, current_app.config["MODEL_DIR"]
            )
            if not resolved_model_path.exists() or not resolved_model_path.is_file():
                raise RuntimeError("在线模型文件不存在，请重新训练或重新上线模型")

            checkpoint = self._safe_torch_load(
                str(resolved_model_path), map_location=self._device
            )
            model = build_model(active.backbone, len(labels), pretrained=False)
            state_dict = checkpoint.get("state_dict") or {}
            self._load_state_dict_compat(model, state_dict)
            model.eval()
            model.to(self._device)

            self._cached_model_id = active.id
            self._model = model
            self._class_names = labels
            self._image_size = int(checkpoint.get("image_size", 224))

    @staticmethod
    def _safe_torch_load(path, map_location):
        # weights_only=True 可防范 pickle 反序列化攻击
        # 旧版 PyTorch 不支持该参数时回退
        try:
            return torch.load(path, map_location=map_location, weights_only=True)
        except TypeError:
            return torch.load(path, map_location=map_location)

    @staticmethod
    def _load_state_dict_compat(model, state_dict):
        """兼容 DDP 包装的模型权重（key 前缀 'module.'）"""
        if not isinstance(state_dict, dict):
            raise RuntimeError("模型参数损坏，无法推理")
        try:
            model.load_state_dict(state_dict, strict=True)
            return
        except RuntimeError:
            pass
        # 去掉 DDP 训练时添加的 module. 前缀
        converted = {}
        for key, value in state_dict.items():
            if key.startswith("module."):
                converted[key[7:]] = value
            else:
                converted[key] = value
        model.load_state_dict(converted, strict=True)

    def _preprocess(self, pil_image: Image.Image):
        # 使用 ImageNet 标准均值/标准差做归一化
        transform = transforms.Compose(
            [
                transforms.Resize((self._image_size, self._image_size)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        return transform(pil_image).unsqueeze(0)

    def _create_gradcam_overlay(self, input_tensor, original_rgb, class_idx: int):
        """Grad-CAM 可解释性热力图

        算法步骤：
        1. 注册 hook 捕获最后一个卷积层的特征图与梯度
        2. 对目标类别的 logit 做反向传播，获取梯度
        3. 以全局平均池化梯度作为权重，加权求和特征图
        4. ReLU 过滤、上采样至原图尺寸，生成热力叠加图
        """
        model = self._model
        if model is None:
            raise RuntimeError("模型未加载")

        target_layer = find_last_conv_layer(model)
        activations = {}
        gradients = {}

        def forward_hook(_, __, output):
            activations["value"] = output.detach()

        def backward_hook(_, grad_input, grad_output):
            gradients["value"] = grad_output[0].detach()

        forward_handle = target_layer.register_forward_hook(forward_hook)
        backward_handle = target_layer.register_full_backward_hook(backward_hook)
        try:
            model.zero_grad(set_to_none=True)
            logits = model(input_tensor)
            # 对目标类别得分求和后反向传播，计算特征图梯度
            score = logits[:, class_idx].sum()
            score.backward()
            if "value" not in activations or "value" not in gradients:
                raise RuntimeError("Grad-CAM特征提取失败")

            grad = gradients["value"]
            feat = activations["value"]
            # 全局平均池化梯度 → 每通道的"重要性权重"
            weights = grad.mean(dim=(2, 3), keepdim=True)
            # 加权组合 + ReLU：只保留对目标类别有正向贡献的区域
            cam = torch.relu((weights * feat).sum(dim=1, keepdim=True))
            # 上采样至原始图像尺寸
            cam = F.interpolate(
                cam,
                size=(original_rgb.shape[0], original_rgb.shape[1]),
                mode="bilinear",
                align_corners=False,
            )
            cam = cam.squeeze().detach().cpu().numpy()
            # 归一化到 [0, 1]
            cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)

            # 伪彩色映射 + 原图叠加
            heatmap = cv2.applyColorMap(np.uint8(cam * 255), cv2.COLORMAP_JET)
            overlay = cv2.addWeighted(
                cv2.cvtColor(original_rgb, cv2.COLOR_RGB2BGR), 0.55, heatmap, 0.45, 0
            )
            return overlay
        finally:
            forward_handle.remove()
            backward_handle.remove()

    def predict(self, image_path: str, heatmap_dir: str):
        self._load_active_model()
        assert self._model is not None

        with Image.open(image_path) as pil_image:
            pil_image = pil_image.convert("RGB")
            original_rgb = np.array(pil_image)
            input_tensor = self._preprocess(pil_image).to(self._device)

        self._model.eval()
        with torch.no_grad():
            logits = self._model(input_tensor)
            probabilities = torch.softmax(logits, dim=1)[0]

        top_probs, top_indices = torch.topk(probabilities, k=min(3, len(self._class_names)))
        top_predictions = []
        for prob, idx in zip(top_probs.tolist(), top_indices.tolist()):
            raw_label = self._class_names[idx]
            info = get_label_info(raw_label)
            top_predictions.append(
                {
                    "label": info["label_display"],
                    "label_en": info["label_en"],
                    "label_zh": info["label_zh"],
                    "is_psoriasis_related": info["is_psoriasis_related"],
                    "confidence": float(prob),
                }
            )

        best_idx = int(top_indices[0].item())
        best_raw_label = self._class_names[best_idx]
        best_info = get_label_info(best_raw_label)
        try:
            overlay = self._create_gradcam_overlay(input_tensor, original_rgb, best_idx)
        except Exception:
            overlay = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2BGR)

        heatmap_dir_path = Path(heatmap_dir)
        heatmap_dir_path.mkdir(parents=True, exist_ok=True)
        heatmap_name = f"{uuid.uuid4().hex}.jpg"
        heatmap_path = heatmap_dir_path / heatmap_name
        if not cv2.imwrite(str(heatmap_path), overlay):
            Image.fromarray(original_rgb).save(heatmap_path)

        return {
            "predicted_label": best_info["label_display"],
            "predicted_label_en": best_info["label_en"],
            "predicted_label_zh": best_info["label_zh"],
            "is_psoriasis_related": best_info["is_psoriasis_related"],
            "confidence": float(top_probs[0].item()),
            "predictions": top_predictions,
            "heatmap_file": heatmap_name,
        }


inference_engine = InferenceEngine()
