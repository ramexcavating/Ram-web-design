#!/usr/bin/env python3
"""Build timecards/app/data/reference.json from the cost code CSV, the job list and the fleet list.

    python3 timecards/tools/build_reference.py

Sources (kept in this folder so the app never depends on SharePoint at runtime):
  timecards/data/cost_codes.csv   exported from 03_AP/5.1.08 Budget & Cost Codes/260112_Standard Cost Codes List RAM.xlsx
  timecards/data/jobs.csv         active project folders in PROJECTS/01_ACTIVE_PROJECTS
  timecards/data/equipment.csv    RESOURCES/02_RESOURCES/04_EQUIPMENT/01_EQUIPMENT_INVENTORY/Equipment inventory.xlsx
`ramfin timecards reference` regenerates the same file from the finance database once that is the source of truth.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "app" / "data" / "reference.json"

# Codes a field crew reaches for most days. They float to the top of the picker; everything else is searchable.
FAVOURITES = [
    "2-100", "2-101", "2-102", "2-106", "2-107", "2-108", "2-111", "2-114", "2-200", "2-201", "2-202", "2-204", "2-205", "2-206",
    "2-215", "2-217", "2-219", "2-226", "2-240", "2-261", "1-041", "1-042", "1-062", "1-067", "1-293", "1-294", "1-295", "1-296",
    "50-120", "50-121", "50-160", "50-932", "70-001",
]


def read(name: str) -> list[dict]:
    p = DATA / name
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8-sig") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]


def main() -> None:
    codes = [{"code": r["code"], "desc": r["description"], "cat": r.get("category", "")} for r in read("cost_codes.csv") if r.get("code")]
    known = {c["code"] for c in codes}
    ref = {
        "version": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "company": "RAM Excavating Limited",
        "submitTo": "accounts@ramexcavating.ca",
        "payPeriod": {"anchorEnd": "2026-08-29", "days": 14},          # bi-weekly, ends Saturday
        "allowances": {"loa": 220.0, "pickup": 150.0, "travelKm": 0.73},
        "maxHoursDay": 14,
        "jobs": [{"no": r["job_no"], "name": r["name"], "client": r.get("client", "")} for r in read("jobs.csv") if r.get("job_no")],
        "equipment": [{"unit": r["unit"], "type": r["type"]} for r in read("equipment.csv") if r.get("unit")],
        "costCodes": codes,
        "favouriteCodes": [c for c in FAVOURITES if c in known],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ref, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(ref['jobs'])} jobs, {len(ref['equipment'])} units, {len(codes)} cost codes")


if __name__ == "__main__":
    main()
