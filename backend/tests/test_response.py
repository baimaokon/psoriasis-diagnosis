"""统一响应格式测试 (功能测试 2 项：success / error)"""

from app.utils.response import error, success


class TestUnifiedResponse:
    def test_success_format(self):
        """success()：默认格式、自定义 data/message、falsy 值保留"""
        assert success() == {"code": 0, "message": "操作成功", "data": None}
        assert success({"id": 1})["data"] == {"id": 1}
        assert success(message="诊断完成")["message"] == "诊断完成"
        assert success(data=0)["data"] == 0
        assert success(data=[])["data"] == []

    def test_error_format(self):
        """error()：默认格式、自定义 code/message、data 恒为 None"""
        assert error() == {"code": 1, "message": "操作失败", "data": None}
        r = error("用户名已存在")
        assert r["message"] == "用户名已存在"
        r = error("未找到", code=404)
        assert r["code"] == 404
        assert r["data"] is None
