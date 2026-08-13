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


# ---- 失眠严重指数量表（ISI） ----
ISI_QUESTIONS = [
    {"id": "isi1", "text": "入睡困难的严重程度？", "options": [
        {"value": 0, "label": "无"}, {"value": 1, "label": "轻微"},
        {"value": 2, "label": "中度"}, {"value": 3, "label": "严重"}, {"value": 4, "label": "非常严重"}]},
    {"id": "isi2", "text": "维持睡眠困难的严重程度（夜间易醒、醒后难再入睡）？", "options": [
        {"value": 0, "label": "无"}, {"value": 1, "label": "轻微"},
        {"value": 2, "label": "中度"}, {"value": 3, "label": "严重"}, {"value": 4, "label": "非常严重"}]},
    {"id": "isi3", "text": "早醒的严重程度？", "options": [
        {"value": 0, "label": "无"}, {"value": 1, "label": "轻微"},
        {"value": 2, "label": "中度"}, {"value": 3, "label": "严重"}, {"value": 4, "label": "非常严重"}]},
    {"id": "isi4", "text": "目前对睡眠模式的满意/不满意程度？", "options": [
        {"value": 0, "label": "很满意"}, {"value": 1, "label": "满意"},
        {"value": 2, "label": "一般"}, {"value": 3, "label": "不满意"}, {"value": 4, "label": "很不满意"}]},
    {"id": "isi5", "text": "失眠在多大程度上影响到日常功能（如白天疲劳、注意力、情绪）？", "options": [
        {"value": 0, "label": "无影响"}, {"value": 1, "label": "轻微影响"},
        {"value": 2, "label": "一定影响"}, {"value": 3, "label": "较大影响"}, {"value": 4, "label": "严重影响"}]},
    {"id": "isi6", "text": "失眠问题被他人注意到或影响他人的程度？", "options": [
        {"value": 0, "label": "无"}, {"value": 1, "label": "轻微"},
        {"value": 2, "label": "中度"}, {"value": 3, "label": "严重"}, {"value": 4, "label": "非常严重"}]},
    {"id": "isi7", "text": "对目前的睡眠问题感到苦恼/担忧的程度？", "options": [
        {"value": 0, "label": "无"}, {"value": 1, "label": "轻微"},
        {"value": 2, "label": "中度"}, {"value": 3, "label": "严重"}, {"value": 4, "label": "非常严重"}]},
]
_reg(AssessmentScale(
    code="isi",
    name="失眠严重指数量表（ISI）",
    description="评估过去一个月失眠的严重程度，帮助识别睡眠障碍风险。",
    questions=ISI_QUESTIONS,
    scoring="sum",
    thresholds=[
        {"min": 0, "max": 7, "level": "none", "label": "无明显失眠", "advice": "睡眠状况良好，继续保持规律作息。"},
        {"min": 8, "max": 14, "level": "mild", "label": "亚临床失眠", "advice": "存在轻度睡眠困扰，建议改善睡眠环境、减少睡前电子设备使用，必要时尝试放松训练。"},
        {"min": 15, "max": 21, "level": "moderate", "label": "中度失眠", "advice": "建议咨询睡眠或心理科医生进一步评估，必要时进行睡眠监测。"},
        {"min": 22, "max": 28, "level": "severe", "label": "重度失眠", "advice": "建议尽快就医，接受专业睡眠评估与治疗。长期严重失眠可能影响身心健康。"},
    ],
    trigger_keywords=["失眠", "睡不着", "入睡难", "早醒", "多梦", "睡不好", "睡眠差", "半夜醒"],
    caveat="本结果为自评参考，不能替代专业诊断。若失眠严重影响日常生活，建议尽快就医。",
))


# ---- 高血压风险自测（简化版） ----
_reg(AssessmentScale(
    code="hypertension",
    name="高血压风险自测",
    description="综合年龄、家族史、生活方式及血压水平，评估高血压风险。",
    questions=[
        {"id": "age", "text": "您的年龄？", "options": [
            {"value": 0, "label": "35 岁以下"}, {"value": 1, "label": "35-44 岁"},
            {"value": 2, "label": "45-54 岁"}, {"value": 3, "label": "55 岁以上"}]},
        {"id": "family", "text": "直系亲属中是否有人患高血压？", "options": [
            {"value": 0, "label": "没有"}, {"value": 2, "label": "有"}]},
        {"id": "salt", "text": "日常饮食口味偏咸吗？", "options": [
            {"value": 0, "label": "清淡"}, {"value": 1, "label": "一般"}, {"value": 2, "label": "偏咸"}]},
        {"id": "weight", "text": "是否超重或肥胖（BMI≥24 或腰围男≥90cm/女≥85cm）？", "options": [
            {"value": 0, "label": "否"}, {"value": 2, "label": "是"}]},
        {"id": "alcohol", "text": "饮酒情况？", "options": [
            {"value": 0, "label": "不饮/偶尔"}, {"value": 1, "label": "适量"}, {"value": 2, "label": "经常/大量"}]},
        {"id": "exercise", "text": "每周中等强度运动的频率？", "options": [
            {"value": 0, "label": "每周 3 次以上"}, {"value": 1, "label": "每周 1-2 次"}, {"value": 2, "label": "几乎不运动"}]},
        {"id": "stress", "text": "日常精神压力如何？", "options": [
            {"value": 0, "label": "较小"}, {"value": 1, "label": "中等"}, {"value": 2, "label": "较大"}]},
        {"id": "bp", "text": "最近测量的血压水平？", "options": [
            {"value": 0, "label": "正常（<120/80）"}, {"value": 1, "label": "正常高值（120-139/80-89）"},
            {"value": 2, "label": "偏高（≥140/90）"}, {"value": 3, "label": "不确定/未测"}]},
    ],
    scoring="sum",
    thresholds=[
        {"min": 0, "max": 4, "level": "low", "label": "低风险", "advice": "高血压风险较低，建议保持低盐饮食和规律运动，每年至少测一次血压。"},
        {"min": 5, "max": 9, "level": "moderate", "label": "中风险", "advice": "存在一定风险，建议减少盐摄入、控制体重、限酒，并定期监测血压。"},
        {"min": 10, "max": 18, "level": "high", "label": "高风险", "advice": "风险较高，建议尽快到社区或医院测量血压，如确诊高血压需遵医嘱治疗。"},
    ],
    trigger_keywords=["高血压", "血压高", "血压偏高", "头晕", "头胀", "家族高血压", "盐吃多"],
    caveat="本结果为自筛参考，不能替代血压测量与专业诊断。高血压需由医生确诊。",
))


# ---- 血脂异常风险自测（简化版） ----
_reg(AssessmentScale(
    code="dyslipidemia",
    name="血脂异常风险自测",
    description="综合年龄、家族史、生活方式等，评估血脂异常风险。",
    questions=[
        {"id": "age", "text": "您的年龄？", "options": [
            {"value": 0, "label": "40 岁以下"}, {"value": 1, "label": "40-49 岁"},
            {"value": 2, "label": "50-59 岁"}, {"value": 3, "label": "60 岁以上"}]},
        {"id": "family", "text": "直系亲属中是否有人患高血脂或早发心血管病？", "options": [
            {"value": 0, "label": "没有"}, {"value": 2, "label": "有"}]},
        {"id": "weight", "text": "是否超重或肥胖（BMI≥24）？", "options": [
            {"value": 0, "label": "否"}, {"value": 2, "label": "是"}]},
        {"id": "smoke", "text": "是否吸烟？", "options": [
            {"value": 0, "label": "从不吸烟"}, {"value": 2, "label": "正在吸烟"}]},
        {"id": "alcohol", "text": "饮酒情况？", "options": [
            {"value": 0, "label": "不饮/偶尔"}, {"value": 1, "label": "经常"}, {"value": 2, "label": "大量"}]},
        {"id": "exercise", "text": "每周中等强度运动的频率？", "options": [
            {"value": 0, "label": "每周 3 次以上"}, {"value": 1, "label": "每周 1-2 次"}, {"value": 2, "label": "几乎不运动"}]},
        {"id": "diet", "text": "是否经常吃高油、高脂或油炸食品？", "options": [
            {"value": 0, "label": "很少"}, {"value": 1, "label": "有时"}, {"value": 2, "label": "经常"}]},
    ],
    scoring="sum",
    thresholds=[
        {"min": 0, "max": 3, "level": "low", "label": "低风险", "advice": "血脂异常风险较低，建议保持低脂饮食和规律运动。"},
        {"min": 4, "max": 8, "level": "moderate", "label": "中风险", "advice": "存在一定风险，建议控制饮食中脂肪摄入、增加运动，并定期查血脂。"},
        {"min": 9, "max": 15, "level": "high", "label": "高风险", "advice": "风险较高，建议尽快到医院检测血脂四项（总胆固醇/甘油三酯/HDL/LDL），并咨询医生。"},
    ],
    trigger_keywords=["血脂", "胆固醇", "甘油三酯", "血脂高", "血脂异常", "高血脂"],
    caveat="本结果为自筛参考，不能替代血液检查与专业诊断。",
))


# ---- AD8 认知障碍早期筛查 ----
AD8_OPTIONS = [
    {"value": 0, "label": "没有变化"},
    {"value": 1, "label": "有变化"},
]
AD8_QUESTIONS = [
    {"id": "ad8_1", "text": "判断力是否出现问题（如做决定困难、容易受骗）？", "options": AD8_OPTIONS},
    {"id": "ad8_2", "text": "对以前的活动和爱好兴趣是否减退？", "options": AD8_OPTIONS},
    {"id": "ad8_3", "text": "是否经常重复相同的问题、故事或说法？", "options": AD8_OPTIONS},
    {"id": "ad8_4", "text": "学习使用小工具、设备或电器是否有困难？", "options": AD8_OPTIONS},
    {"id": "ad8_5", "text": "是否忘记正确的月份或年份？", "options": AD8_OPTIONS},
    {"id": "ad8_6", "text": "处理复杂的个人事务（如记账、缴费）是否有困难？", "options": AD8_OPTIONS},
    {"id": "ad8_7", "text": "是否记不住与他人的约定或安排？", "options": AD8_OPTIONS},
    {"id": "ad8_8", "text": "日常生活中是否持续出现思维或记忆问题？", "options": AD8_OPTIONS},
]
_reg(AssessmentScale(
    code="ad8",
    name="AD8 认知障碍早期筛查",
    description="通过 8 个日常行为变化问题，帮助早期识别认知功能下降风险。建议由家属或知情者根据被评估者近几年的变化作答。",
    questions=AD8_QUESTIONS,
    scoring="weighted",
    thresholds=[
        {"min": 0, "max": 1, "level": "none", "label": "未见明显认知变化", "advice": "目前未见明显认知功能下降，建议保持社交活动、脑力锻炼和规律运动。"},
        {"min": 2, "max": 8, "level": "high", "label": "可疑认知障碍", "advice": "存在认知功能下降迹象，建议尽快到神经内科或记忆门诊进行专业认知评估（如 MMSE/MoCA），早期发现有助于及时干预。"},
    ],
    trigger_keywords=["记性差", "忘事", "记不清", "认知", "痴呆", "老糊涂", "记忆力下降", "重复问"],
    caveat="本结果为知情者观察自评，不能替代专业认知评估与诊断。AD8 阳性（≥2项有变化）提示需要进一步专业检查。",
))


# ---- 脑卒中风险自测（简化版） ----
_reg(AssessmentScale(
    code="stroke",
    name="脑卒中风险自测",
    description="综合高血压、房颤、吸烟、血脂、糖尿病等危险因素，评估脑卒中风险。",
    questions=[
        {"id": "bp", "text": "是否患有高血压（≥140/90 或服药）？", "options": [
            {"value": 0, "label": "否"}, {"value": 3, "label": "是"}]},
        {"id": "afib", "text": "是否有房颤或心律不齐？", "options": [
            {"value": 0, "label": "否"}, {"value": 3, "label": "是"}]},
        {"id": "smoke", "text": "是否吸烟？", "options": [
            {"value": 0, "label": "从不吸烟"}, {"value": 2, "label": "正在吸烟"}]},
        {"id": "lipid", "text": "是否血脂异常或正在服降脂药？", "options": [
            {"value": 0, "label": "否"}, {"value": 2, "label": "是"}]},
        {"id": "diabetes", "text": "是否患有糖尿病？", "options": [
            {"value": 0, "label": "否"}, {"value": 2, "label": "是"}]},
        {"id": "exercise", "text": "每周中等强度运动是否不足？", "options": [
            {"value": 0, "label": "运动充足（≥3次/周）"}, {"value": 1, "label": "运动不足"}]},
        {"id": "weight", "text": "是否超重或肥胖（BMI≥24）？", "options": [
            {"value": 0, "label": "否"}, {"value": 1, "label": "是"}]},
        {"id": "history", "text": "既往是否有过脑卒中或短暂性脑缺血发作（TIA）？", "options": [
            {"value": 0, "label": "没有"}, {"value": 3, "label": "有"}]},
    ],
    scoring="sum",
    thresholds=[
        {"min": 0, "max": 3, "level": "low", "label": "低风险", "advice": "脑卒中风险较低，建议保持健康生活方式，定期监测血压和血脂。"},
        {"min": 4, "max": 7, "level": "moderate", "label": "中风险", "advice": "存在一定风险，建议积极控制危险因素（降压、戒烟、降脂），定期体检。"},
        {"min": 8, "max": 17, "level": "high", "label": "高风险", "advice": "风险较高，建议尽快咨询神经内科医生，完善脑血管评估。若出现面瘫、肢体麻木、言语不清等症状，请立即拨打 120。"},
    ],
    trigger_keywords=["卒中", "中风", "脑梗", "脑出血", "面瘫", "言语不清", "肢体麻木", "偏瘫", "TIA"],
    caveat="本结果为自筛参考，不能替代专业诊断。若突发一侧肢体无力/麻木、口角歪斜、言语不清、剧烈头痛，请立即拨打 120 就医。",
))


def get_scale(code: str) -> AssessmentScale | None:
    return SCALES.get(code)


def list_scales() -> list[AssessmentScale]:
    return list(SCALES.values())
