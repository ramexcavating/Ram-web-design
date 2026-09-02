from datetime import date

from ramfin import db
from ramfin.notify.inbox import open_items
from ramfin.rules import forecast


def seed(conn, cash=20000.0, loc=0.0):
    db.insert(conn, "bank_balances", dict(as_of="2026-08-31", account_key="rbc_chq", balance=cash, source="manual", created_at=db.now_iso()))
    db.insert(conn, "bank_balances", dict(as_of="2026-08-31", account_key="td_chq", balance=0.0, source="manual", created_at=db.now_iso()))
    db.insert(conn, "bank_balances", dict(as_of="2026-08-31", account_key="td_loc", balance=loc, source="manual", created_at=db.now_iso()))


def test_no_breach_moves_discretionary_only(conn, settings):
    seed(conn, cash=20000.0, loc=55000.0)      # position -35,000 against a floor of -60,000
    v_sub = conn.execute("SELECT id FROM vendors WHERE norm_name='ONLINECURBING'").fetchone()["id"]
    v_fuel = conn.execute("SELECT id FROM vendors WHERE norm_name='FOURRIVERS'").fetchone()["id"]
    db.insert(conn, "ap_invoices", dict(vendor_id=v_sub, invoice_no="OC-1", amount=38000.0, amount_confirmed=1, status="Unpaid", planned_pay_date="2026-09-02", created_at=db.now_iso()))
    db.insert(conn, "ap_invoices", dict(vendor_id=v_fuel, invoice_no="FR-1", amount=8367.23, amount_confirmed=1, status="Unpaid", planned_pay_date="2026-09-02", created_at=db.now_iso()))
    db.insert(conn, "ar_invoices", dict(customer="MDM Construction", invoice_no="12", amount=45000.0, status="Open", expected_date="2026-09-25", created_at=db.now_iso()))
    db.insert(conn, "ar_invoices", dict(customer="IDL", invoice_no="606", amount=13860.0, status="Open", expected_date="2026-10-20", created_at=db.now_iso()))
    fc = forecast.build_forecast(conn, settings, as_of=date(2026, 8, 31))
    assert fc.weeks[0].start == date(2026, 8, 31) and len(fc.weeks) == 13
    assert fc.weeks[0].status == "BREACH"
    fc = forecast.apply_no_breach(conn, settings, fc)
    assert fc.deferrals and fc.deferrals[0]["label"].startswith("Online Curbing")
    assert all(d["label"].startswith("Online Curbing") for d in fc.deferrals), "the critical fuel supplier must never be deferred"
    row = conn.execute("SELECT status, planned_pay_date, original_planned_pay_date FROM ap_invoices WHERE invoice_no='OC-1'").fetchone()
    assert row["status"] == "Deferred (no-breach)" and row["original_planned_pay_date"] == "2026-09-02" and row["planned_pay_date"] > "2026-09-25"
    fuel = conn.execute("SELECT status, planned_pay_date FROM ap_invoices WHERE invoice_no='FR-1'").fetchone()
    assert fuel["status"] == "Unpaid" and fuel["planned_pay_date"] == "2026-09-02"
    assert any(i["kind"] == "deferral_to_confirm" for i in open_items(conn))


def test_payroll_and_cra_lines_projected(conn, settings):
    seed(conn, cash=60000.0)
    fc = forecast.build_forecast(conn, settings, as_of=date(2026, 8, 31))
    labels = [ln.label for w in fc.weeks for ln in w.lines]
    assert labels.count("Payroll (net, estimated)") in (6, 7)
    assert "CRA source deductions" in labels
    assert fc.breach_weeks == 0


def test_invisible_ap_warning(conn, settings):
    seed(conn)
    db.insert(conn, "ap_invoices", dict(invoice_no="TAX", amount=18461.95, amount_confirmed=1, status="Unpaid", planned_pay_date=None, created_at=db.now_iso()))
    fc = forecast.build_forecast(conn, settings, as_of=date(2026, 8, 31))
    assert any("INVISIBLE" in w for w in fc.warnings)


def test_missing_balance_warning(conn, settings):
    fc = forecast.build_forecast(conn, settings, as_of=date(2026, 8, 31))
    assert any("No balance on file" in w for w in fc.warnings)


def test_floor_is_the_line_limit(conn, settings):
    assert settings.forecast["floor_amount"] == -60000
    seed(conn, cash=5000.0, loc=58000.0)       # position -53,000: OK but TIGHT
    fc = forecast.build_forecast(conn, settings, as_of=date(2026, 8, 31))
    assert fc.weeks[0].opening == -53000.0
    assert fc.weeks[0].status in ("TIGHT", "BREACH")
