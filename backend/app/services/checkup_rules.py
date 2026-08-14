"""Deterministic checkup rule engine — generates candidates, dedup, contraindication filter."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def generate_candidates(profile: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic rules on health profile, return structured candidates + exclusions."""
    basic = profile.get("基本信息", {})
    age = basic.get("age") or 0
    sex = basic.get("sex", "")
    lifestyle = profile.get("生活方式", {})
    medical = profile.get("既往史与现病史", {}).get("medical_history", [])
    family_history = profile.get("家族史", {}).get("family_history", [])
    recent_exams = profile.get("近期检查记录", {}).get("recent_exams", [])
    special = profile.get("特殊状态", {})

    # item_id -> {layer, reason, tag, freq}
    added: dict[str, dict[str, str]] = {}

    def add(layer: str, item_id: str, reason: str, tag: str, freq: str = "每年") -> None:
        if item_id not in added:
            added[item_id] = {"layer": layer, "reason": reason, "tag": tag, "freq": freq}
        elif layer == "必查":
            added[item_id]["layer"] = "必查"

    # --- Layer 1: base core (all adults) ---
    for iid in [
        "general_exam", "internal_medicine", "surgery", "eye", "ent", "dental",
        "cbc", "urinalysis", "stool", "liver_func", "renal_func", "lipid",
        "glucose", "ecg", "abdomen_us",
    ]:
        add("必查", iid, "基础健康筛查", "core")

    # --- Age-based increments ---
    if age >= 35:
        add("建议查", "thyroid_func", "35岁+甲状腺筛查", "age")
    if age >= 40:
        add("建议查", "ldct", "40岁+肺部初筛", "age")
    if age >= 45:
        add("必查", "ldct", "45岁+肿瘤风险", "age")
        add("必查", "cardiac_us", "45岁+心功能评估", "age")
        add("建议查", "colonoscopy", "45岁+肠道早筛", "age", "每5年")
    if age >= 50:
        add("必查", "bone_density", "50岁+骨密度", "age", "每2年")
    if age >= 60:
        add("必查", "carotid_us", "60岁+动脉硬化", "age")
        add("必查", "homocysteine", "60岁+心脑血管风险", "age")
        add("必查", "tumor_markers", "60岁+肿瘤早筛", "age")
        add("必查", "fundus", "60岁+微血管病变", "age")
        add("必查", "holter_ecg", "60岁+房颤筛查", "age")
        add("建议查", "brain_mri", "60岁+脑结构筛查", "age")

    # --- Sex-based ---
    if sex == "男":
        if age >= 50:
            add("建议查", "psa", "50岁+男性前列腺癌筛查", "gender")
            add("建议查", "prostate_us", "50岁+男性前列腺", "gender")
    elif sex == "女":
        add("必查", "breast_us", "女性乳腺筛查", "gender")
        add("必查", "gynecology", "女性专项检查", "gender")
        if age >= 21:
            add("必查", "tct", "宫颈癌筛查", "gender", "每3年")
        if age >= 30:
            add("必查", "hpv", "HPV感染筛查", "gender", "每5年")
        if age >= 40:
            add("必查", "mammography", "40岁+女性乳腺钼靶", "gender")

    # --- Lifestyle-based ---
    sm = lifestyle.get("smoking", {})
    if sm.get("status") in ("吸烟中", "正在吸烟") or "smoking" in str(lifestyle):
        add("必查", "lung_func", "吸烟伤肺筛查", "risk")
    dr = lifestyle.get("drinking", {})
    if dr.get("status") in ("饮酒中", "经常饮酒", "正在饮酒"):
        add("建议查", "liver_func", "饮酒伤肝监测", "risk", "每半年")

    # --- Chronic disease mapping (X layer) ---
    chronic_map = {
        "高血压": [("abpm", "24h动态血压"), ("cardiac_us", "心脏彩超"), ("urine_microalbumin", "尿微量白蛋白")],
        "2型糖尿病": [("hba1c", "糖化血红蛋白"), ("urine_microalbumin", "尿微量白蛋白"), ("fundus", "眼底检查"), ("leg_vessel_us", "下肢血管超声")],
        "糖尿病": [("hba1c", "糖化血红蛋白"), ("urine_microalbumin", "尿微量白蛋白"), ("fundus", "眼底检查")],
        "血脂异常": [("carotid_us", "颈动脉超声"), ("cardiac_us", "心脏彩超")],
        "冠心病": [("carotid_us", "颈动脉超声"), ("cardiac_us", "心脏彩超"), ("coronary_ct", "冠状动脉CT"), ("homocysteine", "同型半胱氨酸")],
        "脑卒中": [("carotid_us", "颈动脉超声"), ("brain_mri", "头颅核磁共振"), ("leg_vessel_us", "下肢血管超声")],
        "甲状腺结节": [("thyroid_us", "甲状腺彩超"), ("thyroid_func", "甲状腺功能")],
        "骨质疏松": [("bone_density", "骨密度"), ("bone_marker", "骨代谢标志物"), ("vitamin_d", "维生素D")],
        "脂肪肝": [("liver_func", "肝功能全套")],
        "肺结节": [("ldct", "胸部低剂量CT")],
    }
    for d in medical:
        name = d.get("disease_name", "")
        for key, items in chronic_map.items():
            if key in name:
                for iid, label in items:
                    add("必查", iid, f"慢病管理: {name}", "chronic")

    # --- Family history (Y layer) ---
    for fh in family_history:
        dn = fh.get("disease_name", "").lower()
        if any(k in dn for k in ("癌", "肿瘤", "肺", "肝", "胃", "肠", "食管", "胰腺")):
            add("建议查", "tumor_markers", "家族史: 肿瘤广谱筛查", "family")
            add("建议查", "ldct", "家族史: 肺部筛查", "family")
        if any(k in dn for k in ("脑", "脑梗", "脑出血", "中风", "卒中")):
            add("必查", "brain_mri", "家族史: 脑血管筛查", "family")
            add("必查", "carotid_us", "家族史: 颈动脉筛查", "family")
        if any(k in dn for k in ("心脏", "心梗", "冠心病")):
            add("建议查", "cardiac_us", "家族史: 心脏筛查", "family")
        if "糖尿病" in dn:
            add("建议查", "hba1c", "家族史: 糖尿病筛查", "family")

    # --- Contraindication filtering ---
    excluded: list[dict[str, str]] = []
    if special.get("is_pregnant") in ("yes", True) or special.get("is_preparing_pregnancy") in ("yes", True):
        for iid in ["ldct", "bone_density", "coronary_ct"]:
            if iid in added:
                excluded.append({"item": iid, "reason": "孕期禁放射性检查"})
                del added[iid]
    if special.get("contrast_allergy") in ("yes", True):
        for iid in ["coronary_ct"]:
            if iid in added:
                excluded.append({"item": iid, "reason": "造影剂过敏"})
                del added[iid]
    if special.get("has_pacemaker") in ("yes", True) or special.get("has_metal_implant") in ("yes", True):
        if "brain_mri" in added:
            excluded.append({"item": "brain_mri", "reason": "起搏器/金属植入禁MRI"})
            del added["brain_mri"]
    if special.get("on_anticoagulant") in ("yes", True) or special.get("has_coagulopathy") in ("yes", True):
        for iid in ["colonoscopy", "gastroscopy"]:
            if iid in added:
                excluded.append({"item": iid, "reason": "抗凝/凝血障碍禁有创操作"})
                del added[iid]
    if special.get("claustrophobia") in ("yes", True):
        if "brain_mri" in added:
            excluded.append({"item": "brain_mri", "reason": "幽闭恐惧症禁MRI"})
            del added["brain_mri"]

    # --- Recent exam dedup (3mo labs, 6mo imaging) ---
    now = datetime.now()
    three_mo = now - timedelta(days=90)
    six_mo = now - timedelta(days=180)
    deduped: list[str] = []
    for exam in recent_exams:
        name = exam.get("name", "")
        measured = exam.get("measured_at", "")
        is_abn = exam.get("is_abnormal", False)
        try:
            dt = datetime.fromisoformat(measured) if measured else now
        except (ValueError, TypeError):
            continue
        if is_abn:
            continue  # keep abnormal
        if dt >= three_mo:
            deduped.append(name)
        elif dt >= six_mo and "us" in name.lower():
            deduped.append(name)

    return {
        "candidates": added,
        "excluded": excluded,
        "recent_exams_deduped": deduped,
    }


if __name__ == "__main__":
    # ponytail: smoke test — verify rules run without error
    test_profile = {
        "基本信息": {"age": 55, "sex": "男"},
        "生活方式": {"smoking": {"status": "吸烟中"}},
        "既往史与现病史": {"medical_history": [{"disease_name": "高血压"}]},
        "家族史": {"family_history": [{"disease_name": "肺癌"}]},
        "近期检查记录": {"recent_exams": []},
        "特殊状态": {},
    }
    result = generate_candidates(test_profile)
    assert "candidates" in result
    assert "ldct" in result["candidates"]
    assert "lung_func" in result["candidates"]
    assert "abpm" in result["candidates"]
    assert len(result["excluded"]) == 0
    print(f"OK: {len(result['candidates'])} candidates, {len(result['excluded'])} excluded")
