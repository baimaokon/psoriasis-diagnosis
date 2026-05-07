import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def test_app():
    os.environ["FLASK_ENV"] = "testing"
    os.environ["SECRET_KEY"] = "test-secret-key-for-tests"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    from app import create_app

    application = create_app()
    application.config.update({
        "TESTING": True,
        "SQLALCHEMY_ENGINE_OPTIONS": {},
    })

    with application.app_context():
        from app.extensions import db

        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    return test_app.test_client()


@pytest.fixture
def tmp_dataset_dir(tmp_path):
    """创建一个临时数据集目录结构用于测试"""
    dataset = tmp_path / "test_dataset"
    # 需要至少 20 张图片和 2 个类别才能通过 build_classification_samples 校验
    class_files = [
        ("1. Eczema 1677", 12),
        ("7. Psoriasis pictures Lichen Planus and related diseases - 2k", 10),
    ]
    for class_name, file_count in class_files:
        class_dir = dataset / class_name
        class_dir.mkdir(parents=True)
        for i in range(file_count):
            fpath = class_dir / f"sample_{i:03d}.jpg"
            fpath.write_bytes(
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
                b"\xff\xc0\x00\x11\x08\x00\x10\x00\x10\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
                b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00"
                b"\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
                b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00"
                b"\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81"
                b"\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()"
                b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x12\x12\x12\x12\x12\x12\x12\x12"
                b"\xff\xd9"
            )
    return str(dataset)
