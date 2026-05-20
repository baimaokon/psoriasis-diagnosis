"""数据集服务测试 — 对应论文 JC-006 数据集统计功能 (功能测试 7 项)

通过 tmp_dataset_dir fixture 创建包含 2 个类别共 22 张假 JPEG 的临时数据集，
验证数据集路径解析、类别分布统计、样本构建、训练/验证/测试集划分的完整流程。
"""

import shutil
from pathlib import Path

import pytest

from app.services.dataset_service import (
    build_classification_samples,
    build_train_val_test_split,
    get_dataset_summary,
    list_class_distribution,
    resolve_dataset_path,
)


class TestDatasetService:
    def test_resolve_dataset_path(self):
        """resolve：返回绝对路径，展开 ~ 家目录"""
        assert resolve_dataset_path("/tmp/ds").is_absolute()
        assert "~" not in str(resolve_dataset_path("~/my_ds"))

    def test_list_class_distribution(self, tmp_dataset_dir):
        """类别分布：正确数量、样本数；不存在的目录抛异常"""
        rows = list_class_distribution(tmp_dataset_dir)
        assert len(rows) == 2
        names = {r["name"] for r in rows}
        assert "1. Eczema 1677" in names
        eczema = next(r for r in rows if r["name"] == "1. Eczema 1677")
        assert eczema["count"] == 12
        with pytest.raises(FileNotFoundError):
            list_class_distribution("/nonexistent/path/12345")

    def test_get_dataset_summary(self, tmp_dataset_dir):
        """摘要统计：总图片数=22，类别数=2，目录为绝对路径"""
        s = get_dataset_summary(tmp_dataset_dir)
        assert s.total_images == 22 and s.class_count == 2
        assert s.dataset_dir.startswith("/") or s.dataset_dir[1:3] == ":\\"

    def test_build_classification_samples(self, tmp_dataset_dir):
        """样本构建：22 个样本，每个是 (路径, 标签)，至少 2 个类别"""
        names, samples = build_classification_samples(tmp_dataset_dir)
        assert len(samples) == 22 and len(names) == 2
        for path, label in samples:
            assert path.endswith(".jpg") and label in (0, 1)
        # 删除一个类别后应抛异常
        class_dir = next(d for d in Path(tmp_dataset_dir).iterdir()
                         if d.is_dir() and d.name != "1. Eczema 1677")
        shutil.rmtree(str(class_dir))
        with pytest.raises(ValueError, match="至少需要2个类别"):
            build_classification_samples(tmp_dataset_dir)

    def test_split_produces_non_empty_subsets(self, tmp_dataset_dir):
        """train/val/test 三层拆分，每层非空，总数不变"""
        _, samples = build_classification_samples(tmp_dataset_dir)
        train, val, test = build_train_val_test_split(samples, 0.3, 0.3, 42)
        for subset in (train, val, test):
            assert len(subset) > 0
        assert len(train) + len(val) + len(test) == len(samples)

    def test_split_deterministic(self, tmp_dataset_dir):
        """相同随机种子产生相同划分结果"""
        _, samples = build_classification_samples(tmp_dataset_dir)
        t1, v1, e1 = build_train_val_test_split(samples, 0.3, 0.3, 42)
        t2, v2, e2 = build_train_val_test_split(samples, 0.3, 0.3, 42)
        assert [s[0] for s in t1] == [s[0] for s in t2]

    def test_build_samples_too_few_images(self, tmp_path):
        """少于 20 张图片时抛异常"""
        d = tmp_path / "tiny"
        d.mkdir()
        for c in ("A", "B"):
            cd = d / c
            cd.mkdir()
            for i in range(5):
                (cd / f"{i:03d}.jpg").write_bytes(b"fake")
        with pytest.raises(ValueError):
            build_classification_samples(str(d))
