"""Centralized prompt definitions.

All LLM prompts used across the application are defined here to avoid
duplication and ensure consistency.
"""
from __future__ import annotations

# ── Report extraction prompt (shared by consultation.py and reports.py) ──

EXTRACT_PROMPT = """\
你是一个医疗报告解析助手。请仔细分析上传的健康报告图片/PDF，提取以下结构化信息。

要求：
1. 只提取报告中明确出现的数据，不要编造或推断
2. 如果某个字段无法识别，返回null或空数组
3. 分类规则：只有血压、血糖、心率、体重/BMI 四类家庭指标可放入 metrics；血液、体液、尿液等检验结果放入 lab_tests；影像、电生理、核医学等检查结果放入 exam_findings
4. 检查指标（exam_findings）：异常发现必须提取；可量化的检查参数（如心电图 P-R间期、QRS时限）即使正常也提取，用于时间轴展示；无具体参数的"未见异常"类描述不提取
5. 如果报告中有姓名，尝试识别归属人

请严格按照以下JSON格式返回（不要包含markdown代码块标记）：
{
  "patient_name": "报告中识别到的姓名，没有则为null",
  "report_type": "报告类型，如：检查报告单、检验报告单、血压记录、血糖记录、其他 等",
  "report_date": "报告日期 YYYY-MM-DD 格式，无法识别则为null",
  "metrics": [
    {
      "metric_name": "指标标识符，只能使用以下固定指标之一：systolic_blood_pressure, diastolic_blood_pressure, fasting_glucose, postmeal_glucose, random_glucose, postmeal_1h_glucose, bedtime_glucose, heart_rate, weight, bmi。血糖映射：空腹血糖=fasting_glucose、餐后1h=postmeal_1h_glucose、餐后2h=postmeal_glucose、睡前=bedtime_glucose、未明确状态=random_glucose。其他任何指标一律不得放入 metrics，必须按医学规则归入 lab_tests 或 exam_findings",
      "label": "报告中显示的指标中文名",
      "value": 数值或文本（定性结果如"淡黄色"、"透明"用文本，定量结果用数值）,
      "unit": "单位",
      "reference_lower": 参考下限数值或null,
      "reference_upper": 参考上限数值或null,
      "is_abnormal": true或false
    }
  ],
  "diagnoses": [
    {
      "disease_name": "诊断名称",
      "severity": "严重程度或null",
      "diagnosed_date": "日期或null"
    }
  ],
  "medications": [
    {
      "drug_name": "药品名称",
      "dosage": "剂量",
      "frequency": "用药频次"
    }
  ],
  "lab_tests": [
    {
      "report_name": "检验报告名称（血液/体液/尿液/生化/免疫等检验），单个报告一个名称，如 肝功能。不要将多个报告名合并。必须与已有标签保持一致（见下方已有标签列表），如已有则复用，没有的按医学逻辑新建简短标准名",
      "test_name": "指标名称，如 白细胞/血红蛋白/谷丙转氨酶",
      "value": 数值或文本（定性结果如"淡黄色"、"透明"用文本，定量结果用数值）,
      "unit": "单位",
      "reference_lower": 参考下限或null,
      "reference_upper": 参考上限或null,
      "is_abnormal": true或false
    }
  ],
  "exam_findings": [
    {
      "finding_category": "检查分类（影像/电生理/核医学等），如 心电图/胸部CT/肺功能/甲状腺超声。必须与已有标签保持一致（见下方已有标签列表），如已有则复用，没有的按医学逻辑新建简短标准类别名",
      "finding_desc": "检查项目参数或诊断描述，如 P-R间期/右肺水平裂旁微小磨玻璃结节 等",
      "value_num": "可量化的数值或文本（复合值如 375/411 用文本）或null，如 P-R间期189则填189",
      "unit": "数值的单位或null，如 ms/mm",
      "conclusion": "检查结论或建议或null，如 建议随诊/考虑良性 等",
      "is_abnormal": "true表示该检查发现有异常（如结节、囊肿、心律失常），false表示正常（如窦性心律、正常范围心电图、视力正常）"
    }
  ],
  "summary": "报告摘要，1-3句话概述"
}
"""
