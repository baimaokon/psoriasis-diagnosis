import pytest

from app.utils.response import error, success


class TestSuccess:
    def test_default_structure(self):
        result = success()
        assert result == {"code": 0, "message": "操作成功", "data": None}

    def test_with_data(self):
        result = success({"id": 1, "name": "test"})
        assert result["code"] == 0
        assert result["data"] == {"id": 1, "name": "test"}

    def test_custom_message(self):
        result = success(message="诊断完成")
        assert result["message"] == "诊断完成"
        assert result["code"] == 0

    def test_data_is_none_when_not_provided(self):
        result = success()
        assert result["data"] is None

    def test_preserves_falsy_data(self):
        result = success(data=0)
        assert result["data"] == 0

    def test_preserves_empty_list(self):
        result = success(data=[])
        assert result["data"] == []


class TestError:
    def test_default_structure(self):
        result = error()
        assert result == {"code": 1, "message": "操作失败", "data": None}

    def test_custom_message(self):
        result = error("用户名已存在")
        assert result["message"] == "用户名已存在"

    def test_custom_code(self):
        result = error("未找到", code=404)
        assert result["code"] == 404
        assert result["data"] is None

    def test_data_is_always_none(self):
        result = error("错误")
        assert result["data"] is None
