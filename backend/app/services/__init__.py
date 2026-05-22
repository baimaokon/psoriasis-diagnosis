"""
services/ — 核心业务逻辑层
───────────────────────────
本层封装所有与数据库和前端无关的纯业务逻辑，是系统的"大脑"。
  inference_service.py → 推理引擎（模型加载+分类预测+Grad-CAM）
  training_service.py → 训练管理器（训练执行+SSE事件发布+Checkpoint管理）
  dataset_service.py → 数据集服务（目录扫描+分层划分+样本构建）
  model_factory.py → 模型工厂（三种骨干网络构建+分类头替换+权重冻结）
  report_service.py → PDF 诊断报告生成（fpdf2 + 中文渲染）
在 app/__init__.py create_app() 中不直接依赖本层，通过 routes 间接调用。
"""

from .dataset_service import (
    build_classification_samples,
    build_train_val_test_split,
    get_dataset_summary,
    list_class_distribution,
    resolve_dataset_path,
)
from .inference_service import InferenceEngine, inference_engine
from .model_factory import (
    SUPPORTED_BACKBONES,
    build_model,
    find_last_conv_layer,
    list_available_backbones,
)
from .report_service import generate_report_response
from .training_service import (
    TrainingManager,
    TrainEventHub,
    get_train_param_spec,
    has_job_checkpoint,
    normalize_train_params,
    remove_job_checkpoint,
)

train_event_hub = TrainEventHub()
training_manager = TrainingManager()

__all__ = [
    "build_classification_samples",
    "build_train_val_test_split",
    "get_dataset_summary",
    "list_class_distribution",
    "resolve_dataset_path",
    "InferenceEngine",
    "inference_engine",
    "SUPPORTED_BACKBONES",
    "build_model",
    "find_last_conv_layer",
    "list_available_backbones",
    "TrainingManager",
    "TrainEventHub",
    "get_train_param_spec",
    "normalize_train_params",
    "has_job_checkpoint",
    "remove_job_checkpoint",
    "train_event_hub",
    "training_manager",
    "generate_report_response",
]
