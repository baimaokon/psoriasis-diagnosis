"""模型路径工具测试 (功能测试 3 项)"""

import pytest

from app.utils.model_path import model_path_exists, resolve_model_path, to_model_relative_path


class TestModelPath:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.model_dir = tmp_path / "models"
        self.model_dir.mkdir()

    def test_resolve_model_path(self):
        """解析模型路径：相对路径拼接、空/None 返回 sentinel"""
        (self.model_dir / "best.pt").write_bytes(b"mock")
        assert resolve_model_path("best.pt", self.model_dir) == self.model_dir / "best.pt"
        assert "__invalid_model_path__" in str(resolve_model_path("", self.model_dir))
        assert "__invalid_model_path__" in str(resolve_model_path(None, self.model_dir))

    def test_model_path_exists(self):
        """model_path_exists 正确判断存在/不存在"""
        (self.model_dir / "model.pt").write_bytes(b"data")
        assert model_path_exists("model.pt", self.model_dir) is True
        assert model_path_exists("missing.pt", self.model_dir) is False

    def test_to_model_relative_path(self):
        """已相对路径不变，空串返回空"""
        assert to_model_relative_path("checkpoints/best.pt", self.model_dir) == "checkpoints/best.pt"
        assert to_model_relative_path("", self.model_dir) == ""
