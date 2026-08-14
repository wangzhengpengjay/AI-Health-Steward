"""End-to-end single run: report upload -> AI extraction -> confirm (archival).

Makes one paid multimodal call. Creates a disposable member and cleans up.
"""
from __future__ import annotations

import argparse
import io
import sys

import httpx
from PIL import Image, ImageDraw

BASE = "http://localhost:8000"
PREFIX = "/api/v1"


def _fake_report_png() -> bytes:
    img = Image.new("RGB", (600, 400), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 20), "2026年体检报告  姓名:王五", fill=(0, 0, 0))
    d.text((20, 80), "血压 152/95 mmHg", fill=(0, 0, 0))
    d.text((20, 120), "空腹血糖 6.8 mmol/L", fill=(0, 0, 0))
    d.text((20, 160), "总胆固醇 5.9 mmol/L", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=None)
    parser.add_argument("--token", default=None)
    args = parser.parse_args()
    base = (args.base or BASE).rstrip("/")
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    client = httpx.Client(base_url=base, timeout=120, headers=headers)

    r = client.post(f"{PREFIX}/members", json={"name": "报告E2E", "gender": "male", "birth_date": "1970-01-01"})
    member_id = r.json()["id"]
    print(f"member created id={member_id}")

    files = {"file": ("report.png", _fake_report_png(), "image/png")}
    files = {"file": ("report.png", _fake_report_png(), "image/png")}
    r = client.post(f"{PREFIX}/members/{member_id}/reports/upload", files=files, data={"source": "report_page"})
    print(f"upload -> {r.status_code}")
    if r.status_code != 200:
        print(r.text[:1000])
        client.delete(f"{PREFIX}/members/{member_id}")
        return 1
    rec = r.json()
    report_id = rec["id"]
    print(f"report id={report_id} status={rec['status']}")
    print("extraction:", (rec.get("extraction") or {}))

    # Confirm/archive the extracted report
    ext = rec.get("extraction")
    if ext:
        keep = {"keep_metric_indices": list(range(len(ext.get("metrics", []))))} if ext.get("metrics") else {}
        cr = client.post(
            f"{PREFIX}/members/{member_id}/reports/{report_id}/confirm",
            json={"extraction": ext, **keep},
        )
        print(f"confirm -> {cr.status_code} {cr.text[:300]}")
        if cr.status_code != 200:
            client.delete(f"{PREFIX}/members/{member_id}")
            return 1
        # verify metrics were archived for the member
        mr = client.get(f"{PREFIX}/members/{member_id}/metrics")
        print(f"member metrics count -> {len(mr.json())}")

    client.delete(f"{PREFIX}/members/{member_id}")
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())