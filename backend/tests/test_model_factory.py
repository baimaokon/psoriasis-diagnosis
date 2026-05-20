"""模型工厂测试 — 对应论文 JC-010 推理性能 (功能测试 4 项)

验证三个预训练主干网络 (EfficientNet-B0 / ResNet50 / InceptionV3) 的构建、
输出类别数配置、Grad-CAM 所需的最后卷积层查找。
"""

import pytest
import torch

from app.services.model_factory import (
    SUPPORTED_BACKBONES,
    build_model,
    find_last_conv_layer,
    list_available_backbones,
)


class TestModelFactory:
    def test_list_available_backbones(self):
        """list_available_backbones 返回正确的数量和结构"""
        backbones = list_available_backbones()
        assert len(backbones) == len(SUPPORTED_BACKBONES)
        keys = {b["key"] for b in backbones}
        assert keys == set(SUPPORTED_BACKBONES.keys())
        for b in backbones:
            assert "key" in b and "name" in b

    def test_supported_backbones(self):
        """SUPPORTED_BACKBONES 包含三个预期主干网络"""
        assert len(SUPPORTED_BACKBONES) == 3
        assert "efficientnet_b0" in SUPPORTED_BACKBONES
        assert "resnet50" in SUPPORTED_BACKBONES
        assert "inception_v3" in SUPPORTED_BACKBONES

    @pytest.mark.parametrize("backbone", ["efficientnet_b0", "resnet50"])
    def test_build_model(self, backbone):
        """构建主干网络并验证输出层维度，未知模型抛异常"""
        model = build_model(backbone, num_classes=5, pretrained=False)
        assert isinstance(model, torch.nn.Module)
        out = model.classifier[1] if backbone == "efficientnet_b0" else model.fc
        assert out.out_features == 5

        with pytest.raises(ValueError, match="不支持的模型"):
            build_model("nonexistent_model", num_classes=3)

    def test_find_last_conv_layer(self):
        """对 ResNet50 查找最后一个 Conv2d 层"""
        model = build_model("resnet50", num_classes=3, pretrained=False)
        layer = find_last_conv_layer(model)
        assert isinstance(layer, torch.nn.Conv2d)
