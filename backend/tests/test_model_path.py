from pathlib import Path

from app.utils.model_path import model_path_exists, resolve_model_path, to_model_relative_path


class TestResolveModelPath:
    def test_relative_path_joined_with_model_dir(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_file = model_dir / "best.pt"
        model_file.write_bytes(b"mock model data")

        result = resolve_model_path("best.pt", model_dir)
        assert result == model_file

    def test_empty_path_returns_fallback(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        result = resolve_model_path("", model_dir)
        assert "__invalid_model_path__" in str(result)

    def test_none_path_returns_fallback(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        result = resolve_model_path(None, model_dir)
        assert "__invalid_model_path__" in str(result)


class TestModelPathExists:
    def test_existing_file_returns_true(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        (model_dir / "model.pt").write_bytes(b"data")
        assert model_path_exists("model.pt", model_dir) is True

    def test_nonexistent_file_returns_false(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        assert model_path_exists("missing.pt", model_dir) is False


class TestToModelRelativePath:
    def test_already_relative_path_unchanged(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        result = to_model_relative_path("checkpoints/best.pt", model_dir)
        assert result == "checkpoints/best.pt"

    def test_empty_string_returns_empty(self, tmp_path):
        model_dir = tmp_path / "models"
        result = to_model_relative_path("", model_dir)
        assert result == ""
