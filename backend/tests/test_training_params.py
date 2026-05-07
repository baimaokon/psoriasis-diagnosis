import pytest

from app.services.training_service import (
    get_train_param_spec,
    normalize_train_params,
    _to_bool,
    _safe_float,
    _safe_int,
)


class TestToBool:
    def test_bool_true(self):
        assert _to_bool(True) is True

    def test_bool_false(self):
        assert _to_bool(False) is False

    def test_string_true_variants(self):
        for v in ("1", "true", "True", "TRUE", "yes", "YES", "on", "ON"):
            assert _to_bool(v) is True, f"'{v}' should be True"

    def test_other_strings_are_falsy(self):
        for v in ("0", "false", "no", "off", "random"):
            assert _to_bool(v) is False, f"'{v}' should be False"


class TestSafeFloat:
    def test_valid_float(self):
        assert _safe_float("3.14") == 3.14

    def test_integer_string(self):
        assert _safe_float("42") == 42.0

    def test_invalid_string_returns_default(self):
        assert _safe_float("abc", 0.5) == 0.5

    def test_nan_returns_default(self):
        assert _safe_float(float("nan"), 0.0) == 0.0

    def test_inf_returns_default(self):
        assert _safe_float(float("inf"), 0.0) == 0.0

    def test_none_returns_default(self):
        assert _safe_float(None, 0.5) == 0.5


class TestSafeInt:
    def test_valid_int(self):
        assert _safe_int("10") == 10

    def test_invalid_returns_default(self):
        assert _safe_int("not_a_number", 5) == 5

    def test_none_returns_default(self):
        assert _safe_int(None, 7) == 7


class TestGetTrainParamSpec:
    def test_returns_list(self):
        spec = get_train_param_spec()
        assert isinstance(spec, list)
        assert len(spec) > 5

    def test_each_param_has_required_fields(self):
        spec = get_train_param_spec()
        for row in spec:
            assert "key" in row
            assert "name" in row
            assert "type" in row
            assert "base" in row
            assert "balanced" in row


class TestNormalizeTrainParams:
    def test_applies_defaults(self):
        params = normalize_train_params({})
        assert "backbone" in params
        assert "epochs" in params
        assert "batch_size" in params
        assert "learning_rate" in params

    def test_override_single_param(self):
        params = normalize_train_params({"epochs": 100})
        assert params["epochs"] == 100

    def test_inception_v3_min_image_size(self):
        params = normalize_train_params({"backbone": "inception_v3", "image_size": 128})
        assert params["image_size"] == 299

    def test_fixed_mode_clamps_val_ratio_to_max(self):
        params = normalize_train_params({
            "split_mode": "fixed",
            "val_ratio": 0.99,
            "test_ratio": 0.99,
        })
        assert params["val_ratio"] <= 0.4
        assert params["test_ratio"] <= 0.4

    def test_kfold_mode_enforces_min_splits(self):
        params = normalize_train_params({
            "split_mode": "kfold",
            "kfold_splits": 1,
        })
        assert params["kfold_splits"] >= 2

    def test_cache_disabled_sets_limit_to_zero(self):
        params = normalize_train_params({"cache_images": False, "cache_limit": 2000})
        assert params["cache_limit"] == 0

    def test_clamps_validation_interval(self):
        params = normalize_train_params({"validation_interval": 100, "epochs": 10})
        assert params["validation_interval"] == 10

    def test_backbone_select_type_preserved(self):
        params = normalize_train_params({"backbone": "resnet50"})
        assert params["backbone"] == "resnet50"

    def test_invalid_float_clamped(self):
        params = normalize_train_params({"learning_rate": -0.5})
        assert params["learning_rate"] >= 0
