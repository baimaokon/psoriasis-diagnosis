"""标签映射测试 — 对应论文 JC-004 Grad-CAM 可视化展示 (功能测试 5 项)

10 种皮肤病数据集标签（英文→中文）的精确映射、未知标签回退、
银屑病相关标记、以及 LABEL_ZH_MAP 字典的完整性校验。
"""

from app.utils.label_mapping import LABEL_ZH_MAP, get_label_info


class TestLabelMapping:
    def test_label_info_exact_match(self):
        """精确匹配返回中文、英文、显示名、银屑病标记"""
        info = get_label_info("1. Eczema 1677")
        assert info["label_zh"] == "湿疹" and info["label_en"] == "1. Eczema 1677"
        assert info["matched"] is True
        assert "湿疹" in info["label_display"] and "Eczema" in info["label_display"]
        assert info["is_psoriasis_related"] is False

    def test_psoriasis_label_detection(self):
        """银屑病标签标记 is_psoriasis_related=True，非银屑病=False"""
        ps = get_label_info("7. Psoriasis pictures Lichen Planus and related diseases - 2k")
        assert ps["is_psoriasis_related"] is True and "银屑病" in ps["label_zh"]
        assert get_label_info("1. Eczema 1677")["is_psoriasis_related"] is False

    def test_fallback_for_unknown_label(self):
        """未知标签回退：matched=False，空/None→「未知类别」"""
        assert get_label_info("completely_unknown")["matched"] is False
        assert get_label_info("")["label_zh"] == "未知类别"
        assert get_label_info(None)["label_zh"] == "未知类别"

    def test_all_ten_labels_mapped(self):
        """全部 10 个数据集标签精确映射为中文"""
        expected = [
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
        ]
        for label_en, expected_zh in expected:
            info = get_label_info(label_en)
            assert info["label_zh"] == expected_zh and info["matched"] is True

    def test_label_zh_map_integrity(self):
        """LABEL_ZH_MAP 共 10 项，每项 key 以数字开头"""
        assert len(LABEL_ZH_MAP) == 10
        for key in LABEL_ZH_MAP:
            assert key[0].isdigit()
