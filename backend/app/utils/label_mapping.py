"""
label_mapping.py — 疾病标签英文↔中文映射
─────────────────────────────────────────
维护 10 类皮肤病的中英文对照表，提供模糊匹配查询。
消费方：
  models/diagnosis_record.py → to_dict() 时注入中文病名
  services/inference_service.py → 推理结果翻译为中文
  services/dataset_service.py → 数据集类别统计时翻译
  routes/feedback.py → 纠错时提供可选标签列表
"""
LABEL_ZH_MAP = {
    "1. Eczema 1677": "湿疹",
    "2. Melanoma 15.75k": "黑色素瘤",
    "3. Atopic Dermatitis - 1.25k": "特应性皮炎",
    "4. Basal Cell Carcinoma (BCC) 3323": "基底细胞癌",
    "5. Melanocytic Nevi (NV) - 7970": "黑素细胞痣",
    "6. Benign Keratosis-like Lesions (BKL) 2624": "良性角化样病变",
    "7. Psoriasis pictures Lichen Planus and related diseases - 2k": "银屑病/扁平苔藓及相关病变",
    "8. Seborrheic Keratoses and other Benign Tumors - 1.8k": "脂溢性角化及其他良性肿瘤",
    "9. Tinea Ringworm Candidiasis and other Fungal Infections - 1.7k": "体癣/念珠菌等真菌感染",
    "10. Warts Molluscum and other Viral Infections - 2103": "疣/传染性软疣等病毒感染",
}


def _fuzzy_lookup(label_en: str):
    if not label_en:
        return "", False
    if label_en in LABEL_ZH_MAP:
        return LABEL_ZH_MAP[label_en], True
    for key, value in LABEL_ZH_MAP.items():
        if label_en.startswith(key.split(" - ")[0]) or key.startswith(label_en):
            return value, True
    return "", False


def get_label_info(label_en: str):
    zh_name, matched = _fuzzy_lookup(label_en or "")
    if not zh_name:
        zh_name = label_en or "未知类别"
    return {
        "label_en": label_en,
        "label_zh": zh_name,
        "label_display": f"{zh_name}（{label_en}）" if matched and label_en else zh_name,
        "is_psoriasis_related": "Psoriasis" in (label_en or ""),
        "matched": matched,
    }

