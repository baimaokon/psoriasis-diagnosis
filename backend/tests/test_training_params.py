"""训练参数处理测试 — 对应论文 JC-007 训练任务管理 (功能测试 8 项)

训练参数从前端表单提交到后端，需要经过类型转换（_to_bool / _safe_float / _safe_int）
和归一化（normalize_train_params）两步处理，确保非法输入不会导致崩溃。
"""

from app.services.training_service import (
    _safe_float, _safe_int, _to_bool,
    get_train_param_spec, normalize_train_params,
)


class TestTrainingParams:
    def test_to_bool_conversion(self):
        """布尔/字符串→布尔：True/False 直通，'1'/'true'/'yes'/'on'→True，其余→False"""
        assert _to_bool(True) is True and _to_bool(False) is False
        for v in ("1", "true", "True", "TRUE", "yes", "YES", "on", "ON"):
            assert _to_bool(v) is True
        for v in ("0", "false", "no", "off", "random"):
            assert _to_bool(v) is False

    def test_safe_float_conversion(self):
        """字符串/数值→float：合法值正常转换，非法/NaN/Inf/None 返回默认值"""
        assert _safe_float("3.14") == 3.14 and _safe_float("42") == 42.0
        assert _safe_float("abc", 0.5) == 0.5
        assert _safe_float(float("nan"), 0.0) == 0.0
        assert _safe_float(float("inf"), 0.0) == 0.0
        assert _safe_float(None, 0.5) == 0.5

    def test_safe_int_conversion(self):
        """字符串→int：合法值正常转换，非法/None 返回默认值"""
        assert _safe_int("10") == 10
        assert _safe_int("abc", 5) == 5 and _safe_int(None, 7) == 7

    def test_train_param_spec_structure(self):
        """参数规格表：返回列表，每个条目包含 key/name/type/base/balanced"""
        spec = get_train_param_spec()
        assert isinstance(spec, list) and len(spec) > 5
        for row in spec:
            for field in ("key", "name", "type", "base", "balanced"):
                assert field in row

    def test_normalize_applies_defaults(self):
        """空输入补全所有默认参数 + 单字段覆写生效"""
        params = normalize_train_params({})
        for key in ("backbone", "epochs", "batch_size", "learning_rate"):
            assert key in params
        assert normalize_train_params({"epochs": 100})["epochs"] == 100

    def test_normalize_backbone_specific_rules(self):
        """InceptionV3 最小 image_size=299；ResNet50 覆写正常"""
        assert normalize_train_params({"backbone": "inception_v3", "image_size": 128})["image_size"] == 299
        assert normalize_train_params({"backbone": "resnet50"})["backbone"] == "resnet50"

    def test_normalize_split_mode_rules(self):
        """fixed 模式限制 val/test ratio ≤0.4；kfold 强制 k≥2"""
        p1 = normalize_train_params({"split_mode": "fixed", "val_ratio": 0.99, "test_ratio": 0.99})
        assert p1["val_ratio"] <= 0.4 and p1["test_ratio"] <= 0.4
        p2 = normalize_train_params({"split_mode": "kfold", "kfold_splits": 1})
        assert p2["kfold_splits"] >= 2

    def test_normalize_boundary_values(self):
        """缓存关闭清零、逐 epoch 验证上限、非法 float 钳位"""
        p = normalize_train_params({"cache_images": False, "cache_limit": 2000})
        assert p["cache_limit"] == 0
        p = normalize_train_params({"validation_interval": 100, "epochs": 10})
        assert p["validation_interval"] == 10
        p = normalize_train_params({"learning_rate": -0.5})
        assert p["learning_rate"] >= 0.0
