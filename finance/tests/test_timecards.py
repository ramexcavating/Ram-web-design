"""Phone timecards: parse the machine block, land it in the timesheet tables, replace a re-sent day, flag the unknown."""
import json
from pathlib import Path

from ramfin import db, pipeline
from ramfin.extract.extractor import FakeExtractor
from ramfin.filer import LocalFiler
from ramfin.ledger import timecards
from ramfin.sources.common import register

CARD = {
    "v": 1, "employee": "Ed Smith", "position": "General Labourer", "supervisor": "Rodney Mickey", "periodEnd": "2026-08-15", "sentAt": "2026-08-12T01:02:03Z",
    "days": [
        {"date": "2026-08-10", "loa": True, "pu": False, "km": 40, "notes": "rain until 10", "lines": [
            {"job": "240617", "cc": "01-100", "reg": 6, "ot": 0, "dt": 0, "unit": "EX-03", "eq": 6, "desc": "Mobe excavator to Kinchant"},
            {"job": "240617", "cc": "02-300", "reg": 2, "ot": 1.5, "dt": 0, "desc": "Fuel run"}]},
        {"date": "2026-08-11", "loa": False, "pu": True, "km": 0, "lines": [
            {"job": "260102", "cc": "01-100", "reg": 8, "ot": 0, "dt": 0.5, "unit": "EX-01", "eq": 8.5}]},
    ],
}


def text_for(card: dict, wrap_html: bool = False) -> str:
    body = "RAM EXCAVATING TIMECARD\nEmployee: Ed Smith\n\n--RAMTC1--\n" + json.dumps(card) + "\n--END--\n"
    if wrap_html:
        body = "<html><body><div>" + body.replace("\n", "<br>").replace('"', "&quot;") + "</div></body></html>"
    return body


def test_parse_plain_and_html_bodies():
    assert timecards.parse(text_for(CARD))["employee"] == "Ed Smith"
    html_payload = timecards.parse(text_for(CARD, wrap_html=True).encode())
    assert html_payload["days"][0]["lines"][0]["unit"] == "EX-03"
    # a mail client that hard-wraps the JSON line still parses
    wrapped = text_for(CARD).replace('"lines"', '\r\n"lines"')
    assert len(timecards.parse(wrapped)["days"]) == 2
    assert timecards.is_timecard(b"anything", subject="Re: RAM Timecard | Ed Smith | 2026-08-10")
    assert timecards.is_timecard(text_for(CARD).encode())
    assert not timecards.is_timecard(b"hello", "receipt.pdf", "Your Home Hardware receipt")


def test_record_lands_labour_equipment_and_allowances(conn, settings):
    for u in ("EX-01", "EX-03"):
        conn.execute("INSERT INTO equipment(unit_id, description) VALUES(?, 'Excavator')", (u,))
    summary = timecards.record_timecard(conn, settings, None, CARD)
    assert "2 day(s), 3 line(s), 0 issue(s)" in summary
    ts = conn.execute("SELECT * FROM timesheets WHERE period_end='2026-08-15'").fetchone()
    assert ts["status"] == "validated" and ts["total_hours"] == 16 and ts["total_ot_hours"] == 1.5
    rows = db.rows(conn, "SELECT * FROM time_entries WHERE timesheet_id=? ORDER BY work_date, id", (ts["id"],))
    assert [(r["job_no"], r["cost_code"], r["hours"], r["ot_hours"], r["dt_hours"], r["equipment_id"], r["equipment_hours"]) for r in rows] == [
        ("240617", "01-100", 6.0, 0.0, 0.0, "EX-03", 6.0), ("240617", "02-300", 2.0, 1.5, 0.0, None, 0.0), ("260102", "01-100", 8.0, 0.0, 0.5, "EX-01", 8.5)]
    days = db.rows(conn, "SELECT * FROM timecard_days WHERE timesheet_id=? ORDER BY work_date", (ts["id"],))
    assert (days[0]["loa"], days[0]["pickup"], days[0]["travel_km"], days[0]["notes"]) == (1, 0, 40.0, "rain until 10")
    assert (days[1]["loa"], days[1]["pickup"]) == (0, 1)
    assert conn.execute("SELECT 1 FROM payroll_runs WHERE period_end='2026-08-15'").fetchone()
    assert conn.execute("SELECT COUNT(*) n FROM action_items WHERE kind='timesheet_issue'").fetchone()["n"] == 0


def test_resent_day_replaces_only_that_day(conn, settings):
    timecards.record_timecard(conn, settings, None, CARD)
    fixed = {**CARD, "days": [{"date": "2026-08-10", "loa": False, "pu": False, "km": 0, "lines": [{"job": "240617", "cc": "01-100", "reg": 8, "ot": 0, "dt": 0}]}]}
    timecards.record_timecard(conn, settings, None, fixed)
    ts = conn.execute("SELECT * FROM timesheets WHERE period_end='2026-08-15'").fetchone()
    assert conn.execute("SELECT COUNT(*) n FROM timesheets").fetchone()["n"] == 1
    by_day = {r["work_date"]: r["n"] for r in db.rows(conn, "SELECT work_date, COUNT(*) n FROM time_entries WHERE timesheet_id=? GROUP BY work_date", (ts["id"],))}
    assert by_day == {"2026-08-10": 1, "2026-08-11": 1}
    assert ts["total_hours"] == 16 and ts["total_ot_hours"] == 0
    assert conn.execute("SELECT loa FROM timecard_days WHERE work_date='2026-08-10'").fetchone()["loa"] == 0


def test_unknowns_become_action_items_not_silence(conn, settings):
    conn.execute("INSERT INTO equipment(unit_id, description) VALUES('EX-01', 'Excavator')")
    card = {**CARD, "employee": "Newbie Person", "days": [
        {"date": "2026-08-10", "lines": [{"job": "999999", "cc": "9-999", "reg": 15, "unit": "ZZ-09", "eq": 15}]},
        {"date": "2026-07-01", "lines": [{"job": "240617", "cc": "01-100", "reg": 1}]}]}
    summary = timecards.record_timecard(conn, settings, None, card)
    assert "issue(s)" in summary and "0 issue(s)" not in summary
    items = db.rows(conn, "SELECT title, detail FROM action_items WHERE kind='timesheet_issue' ORDER BY id")
    titles = " | ".join(i["title"] for i in items)
    assert "New employee on a timecard: Newbie Person" in titles
    detail = next(i["detail"] for i in items if "PP 2026-08-15" in i["title"])
    for needle in ("job 999999", "cost code 9-999", "unit ZZ-09", "15h in one day", "outside pay period"):
        assert needle in detail
    assert conn.execute("SELECT status FROM timesheets").fetchone()["status"] == "received"
    # the hours still land: payroll is not held hostage to a typo, the digest asks the human
    assert conn.execute("SELECT COUNT(*) n FROM time_entries").fetchone()["n"] == 2


def test_filing_decision_matches_timesheet_convention(settings):
    d = timecards.filing_decision(CARD, settings.sharepoint)
    assert d.folder.endswith("/2026/PP_2026-08-15")
    assert d.filename == "2026-08-15_EDSMITH_Timecard_2026-08-10_to_2026-08-11.txt"
    one = timecards.filing_decision({**CARD, "days": CARD["days"][:1]}, settings.sharepoint)
    assert one.filename.endswith("_Timecard_2026-08-10.txt")


def test_pipeline_files_a_timecard_without_the_extractor(conn, settings, tmp_path):
    body = text_for(CARD, wrap_html=True).encode()
    doc_id = register(conn, settings.inbox_dir, body, "RAM_Timecard_Ed_Smith_PP_2026-08-15.ramtc.txt", source="mail:accounts@ramexcavating.ca",
                      sender="ed@example.com", subject="RAM Timecard | Ed Smith | PP 2026-08-15", received_at="2026-08-12T01:05:00Z", mime="text/plain")
    filed_root = tmp_path / "filed"
    stats = pipeline.process_new_documents(conn, settings, FakeExtractor({}), LocalFiler(filed_root))
    assert stats["filed"] == 1 and stats["errors"] == 0
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    assert doc["doc_type"] == "timecard" and doc["status"] == "filed"
    assert "PP_2026-08-15" in doc["filed_path"] and doc["filed_path"].endswith("_Timecard_2026-08-10_to_2026-08-11.txt")
    assert conn.execute("SELECT COUNT(*) n FROM time_entries").fetchone()["n"] == 3
    assert len(list(Path(filed_root).rglob("*_Timecard_*.txt"))) == 1


def test_export_reference_for_the_phones(conn, settings, tmp_path):
    conn.execute("INSERT INTO equipment(unit_id, description) VALUES('EX-01', 'Excavator')")
    out = tmp_path / "reference.json"
    info = timecards.export_reference(conn, settings, out)
    ref = json.loads(out.read_text())
    assert info["jobs"] == 3 and len(ref["jobs"]) == 3 and ref["jobs"][0]["no"] == "240617"
    assert ref["equipment"] == [{"unit": "EX-01", "type": "Excavator"}]
    assert {c["code"] for c in ref["costCodes"]} >= {"01-100", "02-300"}
    assert ref["payPeriod"] == {"anchorEnd": "2026-08-08", "days": 14}      # conftest anchors pay day 2026-08-14 (Friday) -> period ended Saturday 08-08
    assert ref["submitTo"] == "accounts@ramexcavating.ca"
