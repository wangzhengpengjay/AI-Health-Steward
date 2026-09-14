"""assess_scale tool — deliver a risk self-assessment scale in conversation.

Two modes:
  - no answers: returns the scale questions for the model to present to the user
  - with answers: scores the submission and returns the risk result + advice
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.assessment_scales import get_scale, list_scales
from app.models.assessments import ScaleResult
from app.services.tools.base import HealthTool

_SCALE_CODES = ["phq9", "gad7", "diabetes", "ascvd", "isi", "hypertension", "dyslipidemia", "ad8", "stroke"]


class AssessScaleTool(HealthTool):
    name: str = "assess_scale"
    description: str = (
        "对家庭成员进行风险自测量表（糖尿病/心血管/抑郁PHQ-9/焦虑GAD-7/失眠ISI/高血压/血脂异常/认知AD8/脑卒中）。"
        "调用时不带 answers 会返回量表题目供用户作答；用户完成作答后传入 scale_code 与 answers 进行计分。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "scale_code": {
                "type": "string",
                "enum": _SCALE_CODES,
                "description": "量表编码：phq9/diabetes/gad7/ascvd",
            },
            "answers": {
                "type": "object",
                "description": "题目答案映射 {question_id: 选项分值}，完成作答后传入",
            },
        },
        "required": ["scale_code"],
    }

    async def execute(
        self, db: AsyncSession, member_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        code = kwargs.get("scale_code")
        scale = get_scale(code) if code else None
        if scale is None:
            return {
                "ok": False,
                "message": "未知量表编码，可用：\n" + "\n".join(
                    f"- {s.code}: {s.name}" for s in list_scales()
                ),
            }

        answers = kwargs.get("answers")
        if not answers:
            # Mode 1: return questions for the model to present
            return {
                "ok": True,
                "mode": "questions",
                "code": scale.code,
                "name": scale.name,
                "description": scale.description,
                "scoring": scale.scoring,
                "caveat": scale.caveat,
                "questions": [
                    {
                        "id": q["id"],
                        "text": q["text"],
                        "options": [
                            {"value": opt["value"], "label": opt["label"]}
                            for opt in q["options"]
                        ],
                    }
                    for q in scale.questions
                ],
            }

        # Mode 2: score submission
        problems = scale.validate_answers(answers)
        if problems:
            return {"ok": False, "message": "答卷不完整或取值非法：" + "；".join(problems)}

        try:
            total, detail = scale.score(answers)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"答案格式不正确：{exc}"}

        tier = detail["tier"]
        risk_level = tier["level"]
        risk_label = tier["label"]
        advice = tier.get("advice")

        # Item-level safety rules override the total-score tier (e.g. PHQ-9
        # item 9 self-harm). Must match the REST endpoint's behaviour.
        red_flags = scale.evaluate_red_flags(answers)
        if red_flags:
            primary = red_flags[0]
            risk_level = primary.get("level", "critical")
            risk_label = primary.get("label", risk_label)
            advice = primary.get("advice", advice)

        # Persist every submission. Previously results were only stored when the
        # member had no prior result for this scale, so all later assessments
        # were silently dropped from the history.
        result = ScaleResult(
            member_id=member_id,
            scale_code=code,
            answers=json.dumps(answers, ensure_ascii=False),
            total_score=total,
            risk_level=risk_level,
            risk_label=risk_label,
            advice=advice,
        )
        db.add(result)
        await db.flush()

        return {
            "ok": True,
            "mode": "result",
            "code": scale.code,
            "name": scale.name,
            "total_score": total,
            "risk_level": risk_level,
            "risk_label": risk_label,
            "advice": advice,
            "red_flags": [rule["label"] for rule in red_flags],
            "caveat": scale.caveat,
        }
