import pytest

from app.utils.label_mapping import LABEL_ZH_MAP, get_label_info


class TestGetLabelInfo:
    def test_exact_match_returns_correct_zh(self):
        info = get_label_info("1. Eczema 1677")
        assert info["label_zh"] == "湿疹"
        assert info["label_en"] == "1. Eczema 1677"
        assert info["matched"] is True

    def test_psoriasis_label_flags_is_psoriasis_related(self):
        info = get_label_info(
            "7. Psoriasis pictures Lichen Planus and related diseases - 2k"
        )
        assert info["is_psoriasis_related"] is True
        assert "银屑病" in info["label_zh"]

    def test_non_psoriasis_label_not_flagged(self):
        info = get_label_info("1. Eczema 1677")
        assert info["is_psoriasis_related"] is False

    def test_unknown_label_returns_fallback(self):
        info = get_label_info("completely_unknown_disease")
        assert info["label_zh"] == "completely_unknown_disease"
        assert info["is_psoriasis_related"] is False
        assert info["matched"] is False

    def test_display_format_includes_both_languages_when_matched(self):
        info = get_label_info("1. Eczema 1677")
        assert "湿疹" in info["label_display"]
        assert "Eczema" in info["label_display"]

    def test_empty_string(self):
        info = get_label_info("")
        assert info["label_zh"] == "未知类别"
        assert info["matched"] is False

    def test_none_input(self):
        info = get_label_info(None)
        assert info["label_zh"] == "未知类别"

    @pytest.mark.parametrize(
        "label_en, expected_zh",
        [
            ("1. Eczema 1677", "湿疹"),
            ("2. Melanoma 15.75k", "黑色素瘤"),
            ("3. Atopic Dermatitis - 1.25k", "特应性皮炎"),
            ("4. Basal Cell Carcinoma (BCC) 3323", "基底细胞癌"),
            ("5. Melanocytic Nevi (NV) - 7970", "黑素细胞痣"),
            ("6. Benign Keratosis-like Lesions (BKL) 2624", "良性角化样病变"),
            ("7. Psoriasis pictures Lichen Planus and related diseases - 2k", "银屑病/扁平苔藓及相关病变"),
            ("8. Seborrheic Keratoses and other Benign Tumors - 1.8k", "脂溢性角化及其他良性肿瘤"),
            ("9. Tinea Ringworm Candidiasis and other Fungal Infections - 1.7k", "体癣/念珠菌等真菌感染"),
            ("10. Warts Molluscum and other Viral Infections - 2103", "疣/传染性软疣等病毒感染"),
        ],
    )
    def test_all_ten_labels_map_correctly(self, label_en, expected_zh):
        info = get_label_info(label_en)
        assert info["label_zh"] == expected_zh
        assert info["matched"] is True


class TestLabelZhMap:
    def test_has_exactly_ten_entries(self):
        assert len(LABEL_ZH_MAP) == 10

    def test_all_keys_contain_digit_prefix(self):
        for key in LABEL_ZH_MAP:
            assert key[0].isdigit(), f"Key '{key}' should start with a digit"
