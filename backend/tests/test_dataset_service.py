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


class TestResolveDatasetPath:
    def test_returns_path_object(self):
        result = resolve_dataset_path("/tmp/some_dataset")
        assert result is not None
        assert result.is_absolute()

    def test_expands_home_directory(self):
        result = resolve_dataset_path("~/my_dataset")
        assert "~" not in str(result)


class TestListClassDistribution:
    def test_returns_correct_class_count(self, tmp_dataset_dir):
        rows = list_class_distribution(tmp_dataset_dir)
        assert len(rows) == 2
        names = {r["name"] for r in rows}
        assert "1. Eczema 1677" in names

    def test_returns_correct_sample_counts(self, tmp_dataset_dir):
        rows = list_class_distribution(tmp_dataset_dir)
        eczema = next(r for r in rows if r["name"] == "1. Eczema 1677")
        assert eczema["count"] == 12
        psoriasis = next(
            r
            for r in rows
            if r["name"]
            == "7. Psoriasis pictures Lichen Planus and related diseases - 2k"
        )
        assert psoriasis["count"] == 10

    def test_nonexistent_directory_raises(self):
        with pytest.raises(FileNotFoundError):
            list_class_distribution("/nonexistent/path/12345")


class TestGetDatasetSummary:
    def test_total_images_sum(self, tmp_dataset_dir):
        summary = get_dataset_summary(tmp_dataset_dir)
        assert summary.total_images == 22  # 12 + 10
        assert summary.class_count == 2

    def test_dataset_dir_is_absolute(self, tmp_dataset_dir):
        summary = get_dataset_summary(tmp_dataset_dir)
        assert summary.dataset_dir.startswith("/") or summary.dataset_dir[1:3] == ":\\"


class TestBuildClassificationSamples:
    def test_produces_enough_samples(self, tmp_dataset_dir):
        names, samples = build_classification_samples(tmp_dataset_dir)
        assert len(samples) == 22
        assert len(names) == 2

    def test_each_sample_is_path_and_label(self, tmp_dataset_dir):
        _, samples = build_classification_samples(tmp_dataset_dir)
        for path, label in samples:
            assert path.endswith(".jpg")
            assert label in (0, 1)

    def test_too_few_classes_raises(self, tmp_dataset_dir):
        class_dir = next(
            d
            for d in Path(tmp_dataset_dir).iterdir()
            if d.is_dir() and d.name != "1. Eczema 1677"
        )
        shutil.rmtree(str(class_dir))
        with pytest.raises(ValueError, match="至少需要2个类别"):
            build_classification_samples(tmp_dataset_dir)


class TestBuildTrainValTestSplit:
    def test_produces_three_non_empty_splits(self, tmp_dataset_dir):
        _, samples = build_classification_samples(tmp_dataset_dir)
        train, val, test = build_train_val_test_split(samples, 0.3, 0.3, 42)
        assert len(train) > 0
        assert len(val) > 0
        assert len(test) > 0

    def test_total_samples_preserved(self, tmp_dataset_dir):
        _, samples = build_classification_samples(tmp_dataset_dir)
        train, val, test = build_train_val_test_split(samples, 0.3, 0.3, 42)
        assert len(train) + len(val) + len(test) == len(samples)

    def test_deterministic_with_same_seed(self, tmp_dataset_dir):
        _, samples = build_classification_samples(tmp_dataset_dir)
        t1, v1, e1 = build_train_val_test_split(samples, 0.3, 0.3, 42)
        t2, v2, e2 = build_train_val_test_split(samples, 0.3, 0.3, 42)
        assert [s[0] for s in t1] == [s[0] for s in t2]
