"""QuickBooks Online REST client. The Claude MCP connector is region-blocked for Canadian companies, but Intuit's
API itself works fine for CA company files - this is how the AP posting gap gets closed for good.

Phase 1: read A/P and A/R aging to compute the register-vs-QBO variance.
Phase 2: push confirmed vendor bills (with job and cost-code class) so the bookkeeper never re-keys them.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any

import requests

from .. import db

log = logging.getLogger(__name__)
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


class QBOClient:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None, refresh_token: str | None = None,
                 realm_id: str | None = None, env: str | None = None, session: requests.Session | None = None):
        self.client_id = client_id or os.environ.get("QBO_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("QBO_CLIENT_SECRET")
        self.refresh_token = refresh_token or os.environ.get("QBO_REFRESH_TOKEN")
        self.realm_id = realm_id or os.environ.get("QBO_REALM_ID")
        env = env or os.environ.get("QBO_ENV", "production")
        self.base = "https://quickbooks.api.intuit.com" if env == "production" else "https://sandbox-quickbooks.api.intuit.com"
        self.s = session or requests.Session()
        self._access: str | None = None
        self._exp = 0.0
        if not all([self.client_id, self.client_secret, self.refresh_token, self.realm_id]):
            raise RuntimeError("QBO_CLIENT_ID, QBO_CLIENT_SECRET, QBO_REFRESH_TOKEN and QBO_REALM_ID are required")

    def token(self) -> str:
        if self._access and time.time() < self._exp - 60:
            return self._access
        r = self.s.post(TOKEN_URL, data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
                        auth=(self.client_id, self.client_secret), headers={"Accept": "application/json"}, timeout=60)
        r.raise_for_status()
        j = r.json()
        self._access = j["access_token"]
        self.refresh_token = j.get("refresh_token", self.refresh_token)   # Intuit rotates it; persist the new one
        self._exp = time.time() + int(j.get("expires_in", 3600))
        return self._access

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        r = self.s.get(f"{self.base}/v3/company/{self.realm_id}/{path}", params=params or {},
                       headers={"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}, timeout=120)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict[str, Any]:
        r = self.s.post(f"{self.base}/v3/company/{self.realm_id}/{path}", json=body,
                        headers={"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}, timeout=120)
        r.raise_for_status()
        return r.json()

    def query(self, sql: str) -> list[dict[str, Any]]:
        j = self._get("query", {"query": sql, "minorversion": "73"})
        qr = j.get("QueryResponse", {})
        for k, v in qr.items():
            if isinstance(v, list):
                return v
        return []

    def report(self, name: str, **params) -> dict[str, Any]:
        return self._get(f"reports/{name}", {**params, "minorversion": "73"})

    def open_bills_total(self) -> float:
        bills = self.query("SELECT * FROM Bill WHERE Balance > '0' MAXRESULTS 1000")
        return round(sum(float(b.get("Balance", 0)) for b in bills), 2)

    def open_invoices_total(self) -> float:
        inv = self.query("SELECT * FROM Invoice WHERE Balance > '0' MAXRESULTS 1000")
        return round(sum(float(i.get("Balance", 0)) for i in inv), 2)

    def create_bill(self, vendor_ref_id: str, txn_date: str, due_date: str, doc_number: str, lines: list[dict]) -> dict[str, Any]:
        """lines: [{amount, account_ref_id, description, class_ref_id (job), customer_ref_id}]"""
        body = {"VendorRef": {"value": vendor_ref_id}, "TxnDate": txn_date, "DueDate": due_date, "DocNumber": doc_number,
                "Line": [{"Amount": ln["amount"], "DetailType": "AccountBasedExpenseLineDetail", "Description": ln.get("description", ""),
                          "AccountBasedExpenseLineDetail": {"AccountRef": {"value": ln["account_ref_id"]},
                                                            **({"ClassRef": {"value": ln["class_ref_id"]}} if ln.get("class_ref_id") else {}),
                                                            **({"CustomerRef": {"value": ln["customer_ref_id"]}} if ln.get("customer_ref_id") else {})}}
                         for ln in lines]}
        return self._post("bill", body)


def check_variance(conn: sqlite3.Connection, qbo: QBOClient, threshold: float = 1000.0) -> dict[str, float]:
    """Register (what we actually owe) vs QuickBooks (what the books say). Raises an action item when they disagree."""
    from ..notify.inbox import raise_item
    reg_ap = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM ap_invoices WHERE status NOT IN ('Paid','Void-Credit','Reference only')").fetchone()["s"]
    reg_ar = conn.execute("SELECT COALESCE(SUM(amount - paid_amount),0) s FROM ar_invoices WHERE status IN ('Open','Partially Paid')").fetchone()["s"]
    qb_ap, qb_ar = qbo.open_bills_total(), qbo.open_invoices_total()
    out = {"register_ap": round(reg_ap, 2), "qbo_ap": qb_ap, "ap_variance": round(reg_ap - qb_ap, 2),
           "register_ar": round(reg_ar, 2), "qbo_ar": qb_ar, "ar_variance": round(reg_ar - qb_ar, 2)}
    db.set_state(conn, "qbo:last_check", db.now_iso())
    for k in ("ap", "ar"):
        v = out[f"{k}_variance"]
        if abs(v) >= threshold:
            raise_item(conn, "qbo_variance", f"QuickBooks {k.upper()} is out by ${v:,.2f} versus the register",
                       f"Register {k.upper()} ${out[f'register_{k}']:,.2f} vs QuickBooks ${out[f'qbo_{k}']:,.2f}. Unposted items understate the balance sheet a lender reads.",
                       "sync_state", 1 if k == "ap" else 2, priority=1)
    return out
