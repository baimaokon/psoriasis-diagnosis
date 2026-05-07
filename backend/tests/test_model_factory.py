import pytest
import torch

from app.services.model_factory import (
    SUPPORTED_BACKBONES,
    list_available_backbones,
)


class TestListAvailableBackbones:
    def test_returns_all_backbones(self):
        backbones = list_available_backbones()
        assert len(backbones) == len(SUPPORTED_BACKBONES)
        keys = {b["key"] for b in backbones}
        assert keys == set(SUPPORTED_BACKBONES.keys())

    def test_each_has_key_and_name(self):
        for b in list_available_backbones():
            assert "key" in b
            assert "name" in b
            assert b["key"] in SUPPORTED_BACKBONES


class TestSupportedBackbones:
    def test_includes_three_options(self):
        assert len(SUPPORTED_BACKBONES) == 3

    def test_keys_are_recognized(self):
        assert "efficientnet_b0" in SUPPORTED_BACKBONES
        assert "resnet50" in SUPPORTED_BACKBONES
        assert "inception_v3" in SUPPORTED_BACKBONES


class TestModelBuilder:
    @pytest.mark.parametrize("backbone", ["efficientnet_b0", "resnet50"])
    def test_builds_with_pretrained_false(self, backbone):
        from app.services.model_factory import build_model
        model = build_model(backbone, num_classes=5, pretrained=False)
        assert isinstance(model, torch.nn.Module)
        # Check output layer has correct number of classes
        if backbone == "efficientnet_b0":
            out = model.classifier[1]
        else:
            out = model.fc
        assert out.out_features == 5

    def test_build_raises_for_unknown_backbone(self):
        from app.services.model_factory import build_model
        with pytest.raises(ValueError, match="不支持的模型"):
            build_model("nonexistent_model", num_classes=3)


class TestFindLastConvLayer:
    def test_finds_conv_layer(self):
        from app.services.model_factory import build_model, find_last_conv_layer
        model = build_model("resnet50", num_classes=3, pretrained=False)
        layer = find_last_conv_layer(model)
        assert isinstance(layer, torch.nn.Conv2d)
