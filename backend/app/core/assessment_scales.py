"""Risk self-assessment scales (structured definitions).

Each scale defines its questions, scoring rules, risk thresholds, trigger
keywords, and a disclaimer. Scales follow standard instruments where available
(PHQ-9, GAD-7) or simplified risk-screening questions (diabetes, ASCVD).

Disclaimer: results are for self-screening reference only and are NOT a
diagnosis. Users are encouraged to consult a doctor.
"""
from __future__ import annotations

from typing import Any


class AssessmentScale:
    def __init__(
        self,
        code: str,
        name: str,
        description: str,
        questions: list[dict[str, Any]],
        scoring: str,  # "sum" or "weighted"
        thresholds: list[dict[str, Any]],  # [{"min":0,"max":4,"level":"low","label":"低风险","advice":"..."}]
        trigger_keywords: list[str],
        caveat: str,
    ):
        self.code = code
        self.name = name
        self.description = description
        self.questions = questions
        self.scoring = scoring
        self.thresholds = thresholds
        self.trigger_keywords = trigger_keywords
        self.caveat = caveat

    def score(self, answers: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        """Compute total score and matched risk tier from answer values.

        answers: {question_id: selected_option_value}
        """
        total = 0.0
        per_q: list[dict[str, Any]] = []
        for q in self.questions:
            qid = q["id"]
            val = answers.get(qid)
            options = q.get("options", [])
            if val is not None:
                total += float(val)
            # option lookup for label
            opt = next((o for o in options if str(o["value"]) == str(val)), None)
            per_q.append({"question": q["text"], "answer": opt["label"] if opt else val})
        tier = self._tier(total)
        return total, {"per_question": per_q, "tier": tier}

    def _tier(self, total: float) -> dict[str, Any]:
        for th in self.thresholds:
            lo = th.get("min", 0)
            hi = th.get("max", float("inf"))
            if total >= lo and total <= hi:
                return th
        return self.thresholds[-1]


SCALES: dict[str, AssessmentScale] = {}


def _reg(s: AssessmentScale) -> AssessmentScale:
    SCALES[s.code] = s
    return s


# ---- PHQ-9 抑郁自评 ----
PHQ9_QUESTIONS = [
    {"id": "phq1", "text": "做事时提不起劲或没有兴趣", "options": [
        {"value": 0, "label": "完全不会"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "phq2", "text": "感到心情低落、沮丧或绝望", "options": [
        {"value": 0, "label": "完全不会"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "phq3", "text": "入睡困难、睡不安稳或睡太多", "options": [
        {"value": 0, "label": "完全不会"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "phq4", "text": "感觉疲倦或没有活力", "options": [
        {"value": 0, "label": "完全不会"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "phq5", "text": "食欲不振或吃太多", "options": [
        {"value": 0, "label": "完全不会"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "phq6", "text": "觉得自己很糟，或觉得自己让家人失望", "options": [
        {"value": 0, "label": "完全不会"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "phq7", "text": "难以集中注意力（如看电视、读书时）", "options": [
        {"value": 0, "label": "完全不会"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "phq8", "text": "动作或说话变得缓慢，或烦躁坐立不安", "options": [
        {"value": 0, "label": "完全不会"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "phq9", "text": "有过伤害自己的念头", "options": [
        {"value": 0, "label": "完全没有"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
]
_reg(AssessmentScale(
    code="phq9",
    name="抑郁自评量表（PHQ-9）",
    description="评估过去两周情绪状态，帮助识别抑郁风险。",
    questions=PHQ9_QUESTIONS,
    scoring="sum",
    thresholds=[
        {"min": 0, "max": 4, "level": "none", "label": "无明显抑郁", "advice": "状态良好，继续保持。"},
        {"min": 5, "max": 9, "level": "mild", "label": "轻度抑郁", "advice": "情绪有些低落，建议多休息、适度运动，必要时与家人朋友倾诉。"},
        {"min": 10, "max": 14, "level": "moderate", "label": "中度抑郁", "advice": "建议尽快咨询心理或全科医生进一步评估。"},
        {"min": 15, "max": 19, "level": "moderately_severe", "label": "中重度抑郁", "advice": "建议尽快就医，接受专业评估与支持。"},
        {"min": 20, "max": 27, "level": "severe", "label": "重度抑郁", "advice": "请立即寻求专业帮助。若存在自伤念头，请马上联系亲友或拨打心理援助热线。"},
    ],
    trigger_keywords=["情绪低落", "抑郁", "没兴趣", "沮丧", "焦虑", "睡不着", "压力大", "失眠", "想不开"],
    caveat="本结果为自评参考，不能替代专业诊断。若你有自伤或伤害他人的念头，请立即联系专业人士或拨打当地心理援助热线。",
))


# ---- GAD-7 焦虑自评 ----
GAD7_QUESTIONS = [
    {"id": "gad1", "text": "感觉紧张、焦虑或急切", "options": [
        {"value": 0, "label": "完全没有"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "gad2", "text": "无法停止或控制担忧", "options": [
        {"value": 0, "label": "完全没有"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "gad3", "text": "对很多事情担心过度", "options": [
        {"value": 0, "label": "完全没有"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "gad4", "text": "难以放松", "options": [
        {"value": 0, "label": "完全没有"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "gad5", "text": "坐立不安，难以安静坐著", "options": [
        {"value": 0, "label": "完全没有"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "gad6", "text": "变得容易烦恼或易怒", "options": [
        {"value": 0, "label": "完全没有"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
    {"id": "gad7", "text": "感到害怕，似乎将有可怕的事情发生", "options": [
        {"value": 0, "label": "完全没有"}, {"value": 1, "label": "有几天"},
        {"value": 2, "label": "一半以上时间"}, {"value": 3, "label": "几乎每天"}]},
]
_reg(AssessmentScale(
    code="gad7",
    name="焦虑自评量表（GAD-7）",
    description="评估过去两周焦虑程度，帮助识别焦虑风险。",
    questions=GAD7_QUESTIONS,
    scoring="sum",
    thresholds=[
        {"min": 0, "max": 4, "level": "none", "label": "无明显焦虑", "advice": "状态良好，继续保持。"},
        {"min": 5, "max": 9, "level": "mild", "label": "轻度焦虑", "advice": "焦虑程度较轻，可尝试深呼吸、规律作息和适度运动来缓解。"},
        {"min": 10, "max": 14, "level": "moderate", "label": "中度焦虑", "advice": "建议咨询医生或心理专业人士进一步评估。"},
        {"min": 15, "max": 21, "level": "severe", "label": "重度焦虑", "advice": "建议尽快就医，接受专业评估与支持。"},
    ],
    trigger_keywords=["焦虑", "紧张", "担心", "害怕", "心慌", "不安", "压力大", "烦躁"],
    caveat="本结果为自评参考，不能替代专业诊断。",
))


# ---- 糖尿病风险自测（简化版） ----
_reg(AssessmentScale(
    code="diabetes",
    name="糖尿病风险自测",
    description="综合年龄、体重、家族史、生活方式等，评估 2 型糖尿病风险。",
    questions=[
        {"id": "age", "text": "您的年龄？", "options": [
            {"value": 0, "label": "40 岁以下"}, {"value": 1, "label": "40-54 岁"}, {"value": 2, "label": "55-64 岁"}, {"value": 3, "label": "65 岁以上"}]},
        {"id": "bmi", "text": "您的体重指数（BMI）约？", "options": [
            {"value": 0, "label": "低于 23"}, {"value": 1, "label": "23-25"}, {"value": 2, "label": "25-30"}, {"value": 3, "label": "30 以上"}]},
        {"id": "family", "text": "直系亲属（父母/子女/兄弟姐妹）中是否有人患糖尿病？", "options": [
            {"value": 0, "label": "没有"}, {"value": 2, "label": "有"}]},
        {"id": "exercise", "text": "每周中等强度运动（快走、骑车等）的频率？", "options": [
            {"value": 0, "label": "每周 3 次以上"}, {"value": 1, "label": "每周 1-2 次"}, {"value": 2, "label": "几乎不运动"}]},
        {"id": "diet", "text": "是否经常吃甜食或含糖饮料？", "options": [
            {"value": 0, "label": "很少"}, {"value": 1, "label": "有时"}, {"value": 2, "label": "经常"}]},
        {"id": "hypertension", "text": "是否患有高血压或正在服降压药？", "options": [
            {"value": 0, "label": "否"}, {"value": 1, "label": "是"}]},
        {"id": "gestational", "text": "（女性）是否有过妊娠期糖尿病史？", "options": [
            {"value": 0, "label": "无 / 不适用"}, {"value": 1, "label": "有"}]},
        {"id": "thirst", "text": "近期是否经常感到口渴、尿频或不明原因体重下降？", "options": [
            {"value": 0, "label": "没有"}, {"value": 1, "label": "偶尔"}, {"value": 2, "label": "经常"}]},
    ],
    scoring="sum",
    thresholds=[
        {"min": 0, "max": 3, "level": "low", "label": "低风险", "advice": "糖尿病风险较低，建议保持健康饮食和规律运动。"},
        {"min": 4, "max": 7, "level": "moderate", "label": "中风险", "advice": "存在一定风险，建议控制体重、加强运动，并可考虑查一次空腹血糖。"},
        {"min": 8, "max": 15, "level": "high", "label": "高风险", "advice": "风险较高，建议尽快到医院检测空腹血糖/糖化血红蛋白，并咨询医生。"},
    ],
    trigger_keywords=["糖尿病", "血糖高", "血糖", "多饮多尿", "体重下降", "想吃甜"],
    caveat="本结果为自筛参考，不能替代血液检查与专业诊断。",
))


# ---- ASCVD 心血管风险自测（简化版） ----
_reg(AssessmentScale(
    code="ascvd",
    name="心血管（ASCVD）风险自测",
    description="综合年龄、血脂、血压、吸烟等，评估 10 年动脉粥样硬化性心血管病风险。",
    questions=[
        {"id": "age", "text": "您的年龄？", "options": [
            {"value": 0, "label": "40 岁以下"}, {"value": 1, "label": "40-49 岁"}, {"value": 2, "label": "50-59 岁"}, {"value": 3, "label": "60 岁以上"}]},
        {"id": "gender", "text": "您的性别？", "options": [
            {"value": 0, "label": "女性"}, {"value": 1, "label": "男性"}]},
        {"id": "systolic", "text": "最近收缩压（高压）约？", "options": [
            {"value": 0, "label": "低于 120"}, {"value": 1, "label": "120-139"}, {"value": 2, "label": "140-159"}, {"value": 3, "label": "160 以上"}]},
        {"id": "ldl", "text": "最近低密度脂蛋白胆固醇（LDL-C）约？", "options": [
            {"value": 0, "label": "低于 2.6"}, {"value": 1, "label": "2.6-3.4"}, {"value": 2, "label": "3.4-4.1"}, {"value": 3, "label": "高于 4.1"}]},
        {"id": "hdl", "text": "最近高密度脂蛋白胆固醇（HDL-C）约？", "options": [
            {"value": 2, "label": "低于 1.0"}, {"value": 1, "label": "1.0-1.3"}, {"value": 0, "label": "高于 1.3"}]},
        {"id": "smoke", "text": "您是否吸烟？", "options": [
            {"value": 0, "label": "从不吸烟"}, {"value": 2, "label": "正在吸烟"}]},
        {"id": "diabetes", "text": "是否患有糖尿病？", "options": [
            {"value": 0, "label": "否"}, {"value": 2, "label": "是"}]},
        {"id": "family", "text": "直系亲属是否有人早年（男<55/女<65岁）发生心血管病？", "options": [
            {"value": 0, "label": "没有"}, {"value": 1, "label": "有"}]},
    ],
    scoring="sum",
    thresholds=[
        {"min": 0, "max": 4, "level": "low", "label": "低风险", "advice": "心血管风险较低，建议保持健康生活方式。"},
        {"min": 5, "max": 9, "level": "moderate", "label": "中风险", "advice": "存在一定心血管风险，建议控制血压/血脂、戒烟限酒并定期体检。"},
        {"min": 10, "max": 16, "level": "high", "label": "高风险", "advice": "心血管风险较高，建议尽快咨询心内科医生，完善风险评估。"},
    ],
    trigger_keywords=["心血管", "冠心病", "心梗", "脑梗", "血脂高", "血压高", "心慌", "胸闷"],
    caveat="本结果为自筛参考，不能替代医生进行的心血管风险评估与诊断。",
))


def get_scale(code: str) -> AssessmentScale | None:
    return SCALES.get(code)


def list_scales() -> list[AssessmentScale]:
    return list(SCALES.values())
