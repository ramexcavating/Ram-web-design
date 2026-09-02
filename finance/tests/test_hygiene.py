from datetime import date, timedelta

from ramfin import db
from ramfin.ledger import intake
from ramfin.models import Extraction
from ramfin.rules import hygiene
from tests.fixtures import extractions as fx


def _doc(conn, name):
    return db.insert(conn, "documents", dict(sha256=name, source="test", filename=name, status="new", created_at=db.now_iso()))


def test_historical_invoice_is_reference_only(conn, settings):
    old = {**fx.INVOICE_BRANDT, "invoice_no": "118281", "vendor_name": "A1 Driveline Ltd.", "doc_date": "2021-09-02", "due_date": "2021-10-02"}
    out = intake.record(conn, settings, _doc(conn, "wo.pdf"), Extraction.from_dict(old), None, None)
    assert "historical" in out
    r = conn.execute("SELECT status, planned_pay_date FROM ap_invoices").fetchone()
    assert r["status"] == "Reference only" and r["planned_pay_date"] is None


def test_hygiene_reclassifies_existing_old_unpaid(conn):
    d = _doc(conn, "x.pdf")
    db.insert(conn, "ap_invoices", dict(invoice_no="9394", invoice_date="2020-06-25", due_date="2020-07-25", amount=10133.12, status="Unpaid", planned_pay_date="2020-07-25", document_id=d, created_at=db.now_iso()))
    db.insert(conn, "ap_invoices", dict(invoice_no="OC-1", invoice_date=(date.today() - timedelta(days=10)).isoformat(), amount=38000.0, status="Unpaid", planned_pay_date="2026-10-12", document_id=d, created_at=db.now_iso()))
    out = hygiene.apply(conn)
    assert out["historical_ap"] == 1
    assert conn.execute("SELECT status FROM ap_invoices WHERE invoice_no='9394'").fetchone()["status"] == "Reference only"
    assert conn.execute("SELECT status FROM ap_invoices WHERE invoice_no='OC-1'").fetchone()["status"] == "Unpaid"


def test_dfa_is_backing_not_ar(conn, settings):
    dfa = {"doc_type": "customer_invoice", "confidence": 0.9, "legible": True, "customer_name": "MDM Construction", "invoice_no": "240617-20", "doc_date": "2026-07-20", "total": 1818.09}
    out = intake.record(conn, settings, _doc(conn, "July 20 DFA_0025.pdf"), Extraction.from_dict(dfa), None, None)
    assert "backing document" in out
    assert conn.execute("SELECT COUNT(*) n FROM ar_invoices").fetchone()["n"] == 0


def test_combined_tracker_row_superseded_by_invoices(conn, settings):
    db.insert(conn, "ar_invoices", dict(customer="MDM Construction", invoice_no="INV 597/598/599 (Aug 1 billing)", amount=62279.14, status="Open", expected_date="2026-09-04", created_at=db.now_iso()))
    for no, amt in (("597", 21269.78), ("598", 49603.09), ("599", 12256.05)):
        inv = {"doc_type": "customer_invoice", "confidence": 0.95, "legible": True, "customer_name": "MDM Construction", "invoice_no": no, "doc_date": "2026-08-01", "due_date": "2026-08-31", "total": amt}
        intake.record(conn, settings, _doc(conn, f"INV {no}.pdf"), Extraction.from_dict(inv), None, None)
    out = hygiene.apply(conn)
    assert out["superseded_combined_ar"] == 1
    st = {r["invoice_no"]: r["status"] for r in conn.execute("SELECT invoice_no, status FROM ar_invoices")}
    assert st["INV 597/598/599 (Aug 1 billing)"] == "Superseded" and st["597"] == "Open" and st["598"] == "Open"
    open_total = conn.execute("SELECT SUM(amount) s FROM ar_invoices WHERE status='Open'").fetchone()["s"]
    assert round(open_total, 2) == 83128.92
    assert any("total $83,128.92 but the tracker had $62,279.14" in r["title"] for r in conn.execute("SELECT title FROM action_items"))


def test_same_amount_invoice_attaches_to_tracker_row(conn, settings):
    db.insert(conn, "ar_invoices", dict(customer="MDM Construction", invoice_no="442 Kinchant St project 200617", amount=21269.78, status="Open", expected_date="2026-09-11", created_at=db.now_iso()))
    inv = {"doc_type": "customer_invoice", "confidence": 0.95, "legible": True, "customer_name": "MDM Construction", "invoice_no": "597", "doc_date": "2026-08-01", "total": 21269.78}
    out = intake.record(conn, settings, _doc(conn, "INV 597.pdf"), Extraction.from_dict(inv), None, None)
    assert "matched an existing tracker row" in out
    assert conn.execute("SELECT COUNT(*) n FROM ar_invoices").fetchone()["n"] == 1
