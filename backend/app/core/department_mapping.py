"""Department suggestion rules for visit preparation.

Maps chief complaints and diagnosis history to clinical departments
using keyword matching. No LLM calls — pure deterministic rules.
"""
from __future__ import annotations


# (keywords, department) — ordered by priority
_CHIEF_COMPLAINT_RULES: list[tuple[list[str], str]] = [
    (["胸痛", "胸闷", "心慌", "心悸", "心绞痛", "高血压", "血压"], "心内科"),
    (["血糖", "糖尿病", "多饮", "多尿", "甲状腺", "甲亢", "甲减"], "内分泌科"),
    (["头晕", "头痛", "眩晕", "手脚麻木", "肢体无力", "言语不清"], "神经内科"),
    (["咳嗽", "气喘", "呼吸困难", "气短", "肺", "咳血"], "呼吸科"),
    (["胃痛", "腹痛", "腹泻", "便秘", "反酸", "恶心", "呕吐", "便血", "胃胀"], "消化科"),
    (["关节", "腰痛", "颈椎", "骨折", "腰间盘", "膝盖", "骨质"], "骨科"),
    (["视力", "眼睛", "眼花", "眼睛干涩", "飞蚊"], "眼科"),
    (["皮肤", "皮疹", "瘙痒", "湿疹", "荨麻疹", "痤疮"], "皮肤科"),
    (["尿频", "尿急", "尿痛", "肾", "结石", "血尿", "蛋白尿"], "泌尿科"),
    (["失眠", "抑郁", "焦虑", "强迫", "幻觉", "妄想"], "精神心理科"),
    (["耳鸣", "听力", "耳痛", "鼻塞", "鼻炎", "咽喉", "嗓子"], "耳鼻喉科"),
    (["牙痛", "牙龈", "口腔溃疡", "智齿"], "口腔科"),
    (["月经", "痛经", "妇科", "白带", "盆腔"], "妇科"),
    (["骨折", "外伤", "烧伤", "烫伤", "割伤"], "急诊科"),
]

# Diagnosis name → department (fallback when complaint doesn't match)
_DIAGNOSIS_DEPARTMENT: list[tuple[str, str]] = [
    ("高血压", "心内科"),
    ("冠心病", "心内科"),
    ("心绞痛", "心内科"),
    ("心律失常", "心内科"),
    ("心力衰竭", "心内科"),
    ("糖尿病", "内分泌科"),
    ("甲状腺", "内分泌科"),
    ("痛风", "内分泌科"),
    ("高尿酸", "内分泌科"),
    ("高血脂", "内分泌科"),
    ("哮喘", "呼吸科"),
    ("慢阻肺", "呼吸科"),
    ("肺炎", "呼吸科"),
    ("胃炎", "消化科"),
    ("胃溃疡", "消化科"),
    ("脂肪肝", "消化科"),
    ("肝硬化", "消化科"),
    ("结肠炎", "消化科"),
    ("颈椎病", "骨科"),
    ("腰椎", "骨科"),
    ("关节炎", "骨科"),
    ("骨质疏松", "骨科"),
    ("抑郁", "精神心理科"),
    ("焦虑", "精神心理科"),
    ("失眠", "精神心理科"),
    ("脑梗", "神经内科"),
    ("脑出血", "神经内科"),
    ("癫痫", "神经内科"),
    ("帕金森", "神经内科"),
    ("肾结石", "泌尿科"),
    ("前列腺", "泌尿科"),
    ("肾炎", "泌尿科"),
]

# Special cross-matching rules: (complaint_keyword, diagnosis_keyword, department)
# E.g. "头晕" + "高血压" → 心内科 (not 神经内科)
_CROSS_RULES: list[tuple[str, str, str]] = [
    ("头晕", "高血压", "心内科"),
    ("头痛", "高血压", "心内科"),
    ("头晕", "颈椎", "骨科"),
    ("头痛", "颈椎", "骨科"),
]


def suggest_department(
    chief_complaint: str,
    diagnoses: list[str] | None = None,
) -> tuple[str | None, str]:
    """Suggest a clinical department based on chief complaint and diagnoses.

    Returns (department, reason). Department is None if no match found.
    """
    complaint_lower = chief_complaint.lower()
    diagnoses = diagnoses or []

    # 1. Check cross-rules first (highest priority)
    for complaint_kw, diag_kw, dept in _CROSS_RULES:
        if complaint_kw in complaint_lower and any(diag_kw in d for d in diagnoses):
            return dept, f"主诉含「{complaint_kw}」+ 既往「{diag_kw}」→ {dept}"

    # 2. Match chief complaint keywords
    for keywords, dept in _CHIEF_COMPLAINT_RULES:
        for kw in keywords:
            if kw in complaint_lower:
                return dept, f"主诉关键词「{kw}」→ {dept}"

    # 3. Fallback to diagnosis mapping
    for diag_name in diagnoses:
        for key, dept in _DIAGNOSIS_DEPARTMENT:
            if key in diag_name:
                return dept, f"既往诊断「{diag_name}」→ {dept}"

    return None, "未匹配到相关科室，请手动选择"


# Common departments for frontend dropdown
DEPARTMENTS: list[str] = [
    "心内科",
    "内分泌科",
    "神经内科",
    "呼吸科",
    "消化科",
    "骨科",
    "眼科",
    "皮肤科",
    "泌尿科",
    "精神心理科",
    "耳鼻喉科",
    "口腔科",
    "妇科",
    "急诊科",
    "全科",
    "其他",
]
