"""管理端 API 测试 — 对应论文 JC-006/007/008/009 (功能测试 8 项)

覆盖管理端鉴权（JC-009）、数据集统计接口（JC-006）、模型版本管理（JC-008）。
所有接口需要 admin role=1，普通用户 (role=0) 应被 403 拦截。
"""

from unittest.mock import patch

from app.utils.auth import create_token


def _admin_headers(test_app):
    """构造管理员 (role=1) 的 Bearer Token 请求头"""
    with test_app.app_context():
        token = create_token(user_id=1, role=1)
    return {"Authorization": f"Bearer {token}"}


def _user_headers(test_app):
    """构造普通用户 (role=0) 的 Bearer Token 请求头"""
    with test_app.app_context():
        token = create_token(user_id=2, role=0)
    return {"Authorization": f"Bearer {token}"}


class TestAdminAuth:
    """管理端鉴权"""

    def test_unauthenticated_returns_401(self, test_app):
        """未登录访问管理端→401"""
        r = test_app.test_client().get("/api/admin/dashboard")
        assert r.status_code == 401

    def test_user_cannot_access_admin(self, test_app):
        """普通用户访问管理端→403"""
        r = test_app.test_client().get("/api/admin/dashboard", headers=_user_headers(test_app))
        assert r.status_code == 403

    def test_admin_can_access_dashboard(self, test_app):
        """管理员访问仪表盘→200"""
        r = test_app.test_client().get("/api/admin/dashboard", headers=_admin_headers(test_app))
        assert r.status_code == 200
        d = r.get_json()
        assert d["code"] == 0


class TestDatasetStatistics:
    """数据集统计：JC-006"""

    def test_dataset_summary_endpoint_auth_required(self, test_app):
        """未登录→401"""
        r = test_app.test_client().get("/api/admin/dataset/summary")
        assert r.status_code == 401

    @patch("app.routes.admin.get_dataset_summary")
    def test_dataset_summary_success(self, mock_summary, test_app):
        """管理员获取数据集摘要→200"""
        mock_summary.return_value.total_images = 100
        mock_summary.return_value.class_count = 5
        mock_summary.return_value.classes = [{"name": "Eczema", "count": 30}]
        mock_summary.return_value.dataset_dir = "/data"
        r = test_app.test_client().get("/api/admin/dataset/summary", headers=_admin_headers(test_app))
        assert r.status_code == 200
        d = r.get_json()["data"]
        assert d["total_images"] == 100 and d["class_count"] == 5


class TestDatasetManagement:
    """数据集浏览、上传、删除"""

    def _make_jpeg_bytes(self):
        from io import BytesIO
        from PIL import Image
        img = Image.new("RGB", (32, 32), color=(100, 100, 100))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return buf

    def test_list_dirs(self, test_app):
        """数据集目录列表→200"""
        r = test_app.test_client().get("/api/admin/dataset/list-dirs",
                                        headers=_admin_headers(test_app))
        assert r.status_code == 200
        assert r.get_json()["code"] == 0

    def test_add_image_no_file_returns_400(self, test_app):
        """未上传图片→400"""
        r = test_app.test_client().post("/api/admin/dataset/add-image",
                                         headers=_admin_headers(test_app),
                                         data={"class_name": "test_class"})
        assert r.status_code == 400

    def test_delete_image_success(self, test_app, tmp_path):
        """管理员删除图片：创建临时文件→删除→验证文件不存在"""
        cls_dir = tmp_path / "eczema"
        cls_dir.mkdir()
        img = cls_dir / "test.jpg"
        img.write_bytes(self._make_jpeg_bytes().getvalue())
        with patch("app.services.dataset_service.resolve_dataset_path", return_value=tmp_path):
            r = test_app.test_client().delete(
                "/api/admin/dataset/image?image_path=eczema/test.jpg",
                headers=_admin_headers(test_app))
        assert r.status_code == 200
        assert r.get_json()["code"] == 0
        assert not img.exists()


class TestModelManagement:
    """模型版本管理：JC-008"""

    def test_model_list_requires_admin(self, test_app):
        """普通用户→403"""
        r = test_app.test_client().get("/api/admin/models", headers=_user_headers(test_app))
        assert r.status_code == 403

    def test_model_list_empty(self, test_app):
        """无模型版本时返回空列表"""
        r = test_app.test_client().get("/api/admin/models", headers=_admin_headers(test_app))
        assert r.status_code == 200
        assert r.get_json()["data"] == []

    def test_activate_nonexistent_model(self, test_app):
        """上线不存在的模型→404"""
        r = test_app.test_client().post("/api/admin/models/99999/activate", headers=_admin_headers(test_app))
        assert r.status_code == 404
