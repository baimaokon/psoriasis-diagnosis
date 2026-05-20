"""用户端 API 测试 — 对应论文 JC-001/002/003/004/005 (功能测试 8 项)"""

import io
from unittest.mock import patch

from PIL import Image

from app.utils.auth import create_token


def _make_valid_jpeg():
    img = Image.new("RGB", (100, 100), color=(73, 109, 137))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _auth_headers(test_app, role=0):
    with test_app.app_context():
        token = create_token(user_id=1, role=role)
    return {"Authorization": f"Bearer {token}"}


# 模拟推理引擎返回的诊断结果，结构与 InferenceEngine.predict() 完全一致
# 用于 mock 模式下的 JC-003 诊断成功测试，无需真实模型文件
MOCK_PREDICTION = {
    "predicted_label": "湿疹 / Eczema",
    "predicted_label_en": "1. Eczema 1677",
    "predicted_label_zh": "湿疹",
    "is_psoriasis_related": False,
    "confidence": 0.92,
    "predictions": [
        {"label": "湿疹 / Eczema", "label_en": "1. Eczema 1677", "label_zh": "湿疹", "confidence": 0.92},
    ],
    "heatmap_file": "mock_heatmap.jpg",
}


class TestDiagnoseUpload:
    """图像上传与诊断：JC-003"""

    def test_diagnose_no_image_returns_400(self, test_app):
        """未上传图片→400"""
        r = test_app.test_client().post("/api/user/diagnose", headers=_auth_headers(test_app))
        assert r.status_code == 400 and "图像" in r.get_json()["message"]

    def test_diagnose_no_active_model_returns_400(self, test_app):
        """模型未上线→400「诊断失败」（不崩溃）"""
        data = {"image": (io.BytesIO(_make_valid_jpeg()), "test.jpg")}
        r = test_app.test_client().post("/api/user/diagnose", headers=_auth_headers(test_app),
                                         data=data, content_type="multipart/form-data")
        assert r.status_code == 400 and "诊断失败" in r.get_json()["message"]

    def test_diagnose_invalid_file_type_returns_400(self, test_app):
        """非图片扩展名→400 提示格式/类型错误"""
        data = {"image": (io.BytesIO(b"bytes"), "bad.txt")}
        r = test_app.test_client().post("/api/user/diagnose", headers=_auth_headers(test_app),
                                         data=data, content_type="multipart/form-data")
        assert r.status_code == 400

    @patch("app.routes.user.inference_engine.predict", return_value=MOCK_PREDICTION)
    def test_diagnose_success(self, _mock, test_app):
        """正常上传图片→200，返回诊断结果+置信度+Top3预测+热力图"""
        data = {"image": (io.BytesIO(_make_valid_jpeg()), "skin.jpg")}
        r = test_app.test_client().post("/api/user/diagnose", headers=_auth_headers(test_app),
                                         data=data, content_type="multipart/form-data")
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["code"] == 0
        d = payload["data"]
        assert d["predicted_label_zh"] == "湿疹"
        assert d["confidence"] > 0.9
        assert d["image_url"].startswith("/api/files/")
        assert d["heatmap_url"].startswith("/api/files/")


class TestRecordsQuery:
    """历史诊断记录查询：JC-005"""

    def _create_record(self, test_app):
        from app.models import DiagnosisRecord, User, db
        with test_app.app_context():
            u = User.query.filter_by(username="demo").first()
            if not u:
                u = User(username="demo", role=0)
                u.set_password("demo123")
                db.session.add(u)
                db.session.commit()
            r = DiagnosisRecord(
                user_id=u.id, image_path="uploads/test.jpg", heatmap_path="heatmaps/test.jpg",
                predicted_label="1. Eczema 1677", confidence=0.88,
            )
            db.session.add(r)
            db.session.commit()
            return u.id, r.id

    def test_records_list_returns_paginated(self, test_app):
        """查询返回分页结构：code=0, items 为列表"""
        uid, _ = self._create_record(test_app)
        with test_app.app_context():
            token = create_token(user_id=uid, role=0)
        r = test_app.test_client().get("/api/user/records?page=1&limit=10",
                                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        d = r.get_json()["data"]
        assert "list" in d and "total" in d
        assert len(d["list"]) >= 1

    def test_records_filter_by_disease(self, test_app):
        """按疾病名筛选记录"""
        uid, _ = self._create_record(test_app)
        with test_app.app_context():
            token = create_token(user_id=uid, role=0)
        r = test_app.test_client().get("/api/user/records?disease=Eczema",
                                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_records_contains_result_fields(self, test_app):
        """每条记录包含 image_url、heatmap_url、predicted_label_zh、confidence"""
        uid, _ = self._create_record(test_app)
        with test_app.app_context():
            token = create_token(user_id=uid, role=0)
        r = test_app.test_client().get("/api/user/records?limit=1",
                                        headers={"Authorization": f"Bearer {token}"})
        item = r.get_json()["data"]["list"][0]
        for field in ("image_url", "heatmap_url", "predicted_label_zh", "confidence", "created_at"):
            assert field in item
