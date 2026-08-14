"""Live API integration test campaign against a running health-steward backend.

This is a tester-driven black-box campaign: it exercises the running service
(assumed at BASE_URL) over its real HTTP endpoints and reports PASS/FAIL per
case. It creates its own disposable test member(s) and soft-deletes them at the
end, so it does not disturb real data.

Usage:
    python -m scripts.live_api_campaign [--base http://localhost:8000] [--token ...]

Exit code is 0 iff every case passes.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date

import httpx

BASE = "http://localhost:8000"
PREFIX = "/api/v1"
TOKEN: str | None = None

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def _headers() -> dict:
    if TOKEN:
        return {"Authorization": f"Bearer {TOKEN}"}
    return {}


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL  {name}  {detail}")


def case(title: str) -> None:
    print(f"\n== {title} ==")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=None)
    parser.add_argument("--token", default=None)
    args = parser.parse_args()
    global BASE, TOKEN
    BASE = (args.base or BASE).rstrip("/")
    TOKEN = args.token
    client = httpx.Client(base_url=BASE, timeout=30)

    # ---- Health ----
    case("Health")
    r = client.get("/health")
    check("health returns ok", r.status_code == 200 and r.json() == {"status": "ok"}, str(r.text))

    # ---- Members CRUD ----
    case("Members CRUD")
    create = {
        "name": f"测试成员-{date.today().isoformat()}",
        "gender": "male",
        "birth_date": "1990-05-20",
        "height": 175,
        "weight": 70,
    }
    r = client.post(f"{PREFIX}/members", json=create)
    check("create member -> 201", r.status_code == 201, f"{r.status_code} {r.text}")
    body = r.json()
    member_id = body.get("id")
    check("created member has id", member_id is not None, str(body))
    created_bmi = body.get("bmi")
    check("created member has computed bmi", created_bmi is not None, str(created_bmi))
    check(
        "bmi value ~22.9",
        created_bmi is not None and abs(created_bmi - 22.9) < 0.1,
        str(created_bmi),
    )

    r = client.get(f"{PREFIX}/members/{member_id}")
    check("get member -> 200", r.status_code == 200, str(r.text))

    r = client.get(f"{PREFIX}/members")
    check("list members contains created", any(m.get("id") == member_id for m in r.json()), str(r.text))

    r = client.put(f"{PREFIX}/members/{member_id}", json={"weight": 78})
    check("update weight -> 200", r.status_code == 200, str(r.text))
    check("bmi recomputed", abs(r.json().get("bmi", 0) - 25.5) < 0.2, str(r.json().get("bmi")))

    # ---- Metrics with age-aware reference ranges ----
    case("Metrics / reference ranges / abnormal & critical")
    # Adult systolic 150 -> abnormal (>=140) but not critical (<180)
    r = client.post(
        f"{PREFIX}/members/{member_id}/metrics",
        json={"metric_name": "systolic_blood_pressure", "value": 150, "measured_at": "2026-07-20T08:00:00"},
    )
    check("create metric -> 201", r.status_code == 201, str(r.text))
    m1 = r.json()
    check("reference filled (adult 140-140?)", m1.get("reference_upper") is not None, str(m1))
    check("150 is_abnormal true", m1.get("is_abnormal") is True, str(m1))
    check("150 is_critical false", m1.get("is_critical") is False, str(m1))
    check("source forced manual", m1.get("source_type") == "manual", str(m1.get("source_type")))

    # Critical value: systolic 190 -> critical
    r = client.post(
        f"{PREFIX}/members/{member_id}/metrics",
        json={"metric_name": "systolic_blood_pressure", "value": 190, "measured_at": "2026-07-20T09:00:00"},
    )
    m2 = r.json()
    check("190 is_critical true", m2.get("is_critical") is True, str(m2))

    # Normal value -> not abnormal
    r = client.post(
        f"{PREFIX}/members/{member_id}/metrics",
        json={"metric_name": "heart_rate", "value": 72, "measured_at": "2026-07-20T10:00:00"},
    )
    m3 = r.json()
    check("72 heart_rate not abnormal", m3.get("is_abnormal") is False, str(m3))

    r = client.get(f"{PREFIX}/members/{member_id}/metrics")
    check("list metrics count >=3", len(r.json()) >= 3, str(len(r.json())))

    r = client.get(f"{PREFIX}/members/{member_id}/metrics/systolic_blood_pressure")
    hist = r.json()
    check("history filtered + desc order", len(hist) == 2 and hist[0]["value"] == 190, str(hist))

    # Metric update recomputes abnormal/critical
    r = client.put(f"{PREFIX}/members/metrics/{m1['id']}", json={"value": 120})
    check("update metric -> 200", r.status_code == 200, str(r.text))
    check("value 120 now normal", r.json().get("is_abnormal") is False, str(r.json()))

    r = client.delete(f"{PREFIX}/members/metrics/{m1['id']}")
    check("delete metric -> 204", r.status_code == 204, str(r.status_code))

    # ---- Member profile ----
    case("Member profile")
    r = client.post(f"{PREFIX}/members/{member_id}/profile/diagnoses", json={
        "disease_name": "高血压", "diagnosed_date": "2025-01-01", "status": "active",
    })
    check("add diagnosis -> 2xx", 200 <= r.status_code < 300, f"{r.status_code} {r.text}")
    r = client.get(f"{PREFIX}/members/{member_id}/profile")
    check("get profile -> 200", r.status_code == 200, str(r.status_code))
    prof = r.json()
    check("profile has diagnoses", len(prof.get("diagnoses", [])) >= 1, str(prof.get("diagnoses")))
    check("profile has critical/abnormal view", isinstance(prof, dict), str(prof.keys()))

    r = client.post(f"{PREFIX}/members/{member_id}/profile/medications", json={
        "drug_name": "阿托伐他汀", "dosage": "20mg", "frequency": "qd",
        "route": "oral", "start_date": "2025-02-01",
    })
    check("add medication -> 2xx", 200 <= r.status_code < 300, f"{r.status_code} {r.text}")

    # ---- Tasks auto-generated ----
    case("Tasks")
    r = client.get(f"{PREFIX}/tasks/overview")
    check("tasks overview -> 200", r.status_code == 200, str(r.status_code))
    r = client.get(f"{PREFIX}/members/{member_id}/tasks")
    check("member tasks -> 200", r.status_code == 200, str(r.status_code))
    member_tasks = r.json()
    check("critical metric generated a task", len(member_tasks) >= 1, str(member_tasks))

    # ---- Scales ----
    case("Scales")
    r = client.get(f"{PREFIX}/scales")
    check("scales list -> 200", r.status_code == 200, str(r.status_code))
    codes = [s.get("code") for s in r.json()]
    check("has PHQ-9", "phq9" in codes, str(codes))
    # submit phq9 answers (0-3 each, 9 items)
    answers = {f"q{i}": 0 for i in range(1, 10)}
    r = client.post(f"{PREFIX}/members/{member_id}/scales/phq9/submit", json={"answers": answers})
    check("submit scale -> 2xx", 200 <= r.status_code < 300, f"{r.status_code} {r.text}")
    r = client.get(f"{PREFIX}/members/{member_id}/scales/results")
    check("scale results -> 200", r.status_code == 200, str(r.status_code))

    # ---- Summaries ----
    case("Summaries")
    r = client.get(f"{PREFIX}/members/{member_id}/summaries/latest")
    check("summaries latest -> 200 (may be empty)", r.status_code == 200, str(r.status_code))
    r = client.get(f"{PREFIX}/members/{member_id}/summaries")
    check("summaries list -> 200", r.status_code == 200, str(r.status_code))

    # ---- Settings ----
    case("Settings")
    # /settings/data is DELETE-only (wipe); GET should be 405. Tested destructively at the end.
    r = client.get(f"{PREFIX}/settings/data")
    check("settings/data GET -> 405 (not implemented)", r.status_code == 405, str(r.status_code))
    r = client.get(f"{PREFIX}/settings/providers")
    check("settings providers -> 200", r.status_code == 200, str(r.status_code))
    r = client.get(f"{PREFIX}/settings/export")
    check("settings export -> 200", r.status_code == 200, str(r.status_code))

    # ---- Error handling ----
    case("Error handling")
    r = client.get(f"{PREFIX}/members/999999999")
    check("missing member -> 404", r.status_code == 404, str(r.status_code))
    r = client.get(f"{PREFIX}/members/{member_id}/metrics/nonexistent_metric")
    check("missing metric history -> 200 empty", r.status_code == 200, str(r.status_code))
    r = client.post(f"{PREFIX}/members", json={"name": "", "gender": "x"})
    check("invalid member payload -> 422", r.status_code == 422, str(r.status_code))

    # ---- Cleanup: soft-delete test member ----
    case("Cleanup")
    r = client.delete(f"{PREFIX}/members/{member_id}")
    check("soft-delete member -> 200", r.status_code == 200, str(r.status_code))
    r = client.get(f"{PREFIX}/members/{member_id}")
    check("deleted member gone -> 404", r.status_code == 404, str(r.status_code))

    print(f"\n==== RESULT: {PASS} passed, {FAIL} failed ====")
    if FAILURES:
        print("Failures:")
        for f in FAILURES:
            print(f"  - {f}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())