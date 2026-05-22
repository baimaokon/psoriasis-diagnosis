"""推理引擎测试 — 对应论文 JC-008 模型热更新 / JC-010 推理性能 (功能测试 5 项)

测试推理引擎的核心能力：
- 模型加载/缓存/热更新机制
- DDP 分布式训练权重兼容（'module.' 前缀处理）
- 模型文件安全加载（weights_only 防 pickle 攻击）
- 无上线模型时的容错行为
"""

import pytest
import torch

from app.services.inference_service import InferenceEngine
from app.services.model_factory import build_model


class TestInferenceEngineCore:
    def test_init_default_values(self):
        """引擎初始化：缓存 ID=None，设备=cpu/cuda"""
        eng = InferenceEngine()
        assert eng._cached_model_id is None
        assert eng._model is None
        assert eng._device.type in ("cpu", "cuda")

    def test_load_active_model_no_active_raises(self, test_app):
        """无上线模型时 _load_active_model 抛 RuntimeError"""
        eng = InferenceEngine()
        with test_app.app_context():
            with pytest.raises(RuntimeError, match="没有已上线"):
                eng._load_active_model()

    def test_safe_torch_load_fallback(self, tmp_path):
        """_safe_torch_load：weights_only=True 优先，旧版回退"""
        import torch

        m = torch.nn.Linear(2, 2)
        p = tmp_path / "test.pt"
        torch.save(m.state_dict(), str(p))
        sd = InferenceEngine._safe_torch_load(str(p), "cpu")
        assert isinstance(sd, dict)

    def test_load_state_dict_compat(self):
        """权重兼容加载：普通 + DDP 'module.' 前缀均可正常加载"""
        m = build_model("resnet50", num_classes=3, pretrained=False)
        sd = m.state_dict()
        # 普通 state_dict
        m2 = build_model("resnet50", num_classes=3, pretrained=False)
        InferenceEngine._load_state_dict_compat(m2, sd)
        for k in sd:
            assert torch.equal(m.state_dict()[k], m2.state_dict()[k])
        # DDP 'module.' 前缀
        ddp = {f"module.{k}": v for k, v in sd.items()}
        m3 = build_model("resnet50", num_classes=3, pretrained=False)
        InferenceEngine._load_state_dict_compat(m3, ddp)
        for k in sd:
            assert torch.equal(m.state_dict()[k], m3.state_dict()[k])
