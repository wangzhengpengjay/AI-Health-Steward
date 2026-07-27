"""Seed demo data for quick trial.

Usage:
    docker exec health-steward-backend python -m scripts.seed_demo_data

Creates a demo family with 2 members and sample health data.
Safe to run multiple times (idempotent by member name).
"""
import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.core.database import async_session_factory
from app.models.family import FamilyMember
from app.models.health import (
    MetricRecord, Diagnosis, Medication, Allergy,
    Lifestyle, FamilyHistory, Surgery, Vaccination,
)


async def seed():
    async with async_session_factory() as db:
        existing = await db.execute(
            select(FamilyMember).where(FamilyMember.name == "张三")
        )
        if existing.scalars().first():
            print("Demo data already exists, skipping.")
            return

        m1 = FamilyMember(name="张三", gender="male", birth_date=date(1985, 3, 15),
                          member_relation="self", is_deleted=False)
        m2 = FamilyMember(name="李四", gender="female", birth_date=date(1988, 7, 22),
                          member_relation="spouse", is_deleted=False)
        db.add(m1)
        db.add(m2)
        await db.flush()

        now = datetime.now(timezone.utc)

        for sys_val, dia_val, days_ago in [
            (125, 82, 90), (128, 85, 60), (122, 80, 30), (130, 88, 15), (120, 78, 7)
        ]:
            db.add(MetricRecord(
                member_id=m1.id, metric_name="systolic_blood_pressure",
                value=sys_val, unit="mmHg", reference_lower=90, reference_upper=120,
                is_abnormal=sys_val > 120, measured_at=now - timedelta(days=days_ago),
                source_type="manual", context="morning",
            ))
            db.add(MetricRecord(
                member_id=m1.id, metric_name="diastolic_blood_pressure",
                value=dia_val, unit="mmHg", reference_lower=60, reference_upper=80,
                is_abnormal=dia_val > 80, measured_at=now - timedelta(days=days_ago),
                source_type="manual", context="morning",
            ))

        for val, days_ago in [(5.2, 60), (5.8, 30), (6.1, 15), (5.5, 7)]:
            db.add(MetricRecord(
                member_id=m1.id, metric_name="fasting_glucose",
                value=val, unit="mmol/L", reference_lower=3.9, reference_upper=6.1,
                is_abnormal=val > 6.1, measured_at=now - timedelta(days=days_ago),
                source_type="manual", context="fasting",
            ))

        for name, val, lower, upper in [
            ("total_cholesterol", 5.2, 3.0, 5.2),
            ("ldl_cholesterol", 3.3, 0, 3.4),
            ("triglycerides", 2.1, 0, 1.7),
            ("hdl_cholesterol", 0.9, 1.0, 999),
        ]:
            db.add(MetricRecord(
                member_id=m1.id, metric_name=name,
                value=val, unit="mmol/L", reference_lower=lower, reference_upper=upper,
                is_abnormal=(val < lower or val > upper),
                measured_at=now - timedelta(days=30),
                source_type="report", context="血脂四项",
            ))

        db.add(Diagnosis(member_id=m1.id, disease_name="高血压",
                         severity="轻度", diagnosed_date=date(2024, 1, 10), status="active"))
        db.add(Diagnosis(member_id=m1.id, disease_name="高脂血症",
                         diagnosed_date=date(2024, 3, 15), status="active"))

        db.add(Medication(member_id=m1.id, drug_name="氨氯地平片",
                          dosage="5mg", frequency="每日一次", start_date=date(2024, 1, 15)))
        db.add(Medication(member_id=m1.id, drug_name="阿托伐他汀钙片",
                          dosage="20mg", frequency="每晚一次", start_date=date(2024, 3, 20)))

        db.add(Allergy(member_id=m1.id, type="drug", name="青霉素",
                       severity="moderate", recorded_at=date(2020, 5, 1)))

        db.add(Lifestyle(member_id=m1.id, category="smoking", status="已戒烟",
                         frequency="戒烟2年", recorded_at=date(2024, 1, 1)))
        db.add(Lifestyle(member_id=m1.id, category="drinking", status="偶尔",
                         frequency="每周1-2次", recorded_at=date(2024, 1, 1)))

        db.add(FamilyHistory(member_id=m1.id, relation="father",
                             disease_name="高血压", recorded_at=date(2024, 1, 1)))
        db.add(FamilyHistory(member_id=m1.id, relation="mother",
                             disease_name="糖尿病", recorded_at=date(2024, 1, 1)))

        db.add(Surgery(member_id=m1.id, surgery_name="阑尾切除术",
                       surgery_date=date(2010, 8, 15), hospital="市人民医院"))

        db.add(Vaccination(member_id=m1.id, vaccine_name="流感疫苗",
                           dose_no="annual", vaccinated_date=date(2024, 10, 15)))

        await db.commit()
        print(f"Demo data created: {m1.name} (id={m1.id}), {m2.name} (id={m2.id})")


if __name__ == "__main__":
    asyncio.run(seed())
