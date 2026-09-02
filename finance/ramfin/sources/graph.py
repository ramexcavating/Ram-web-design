"""Thin Microsoft Graph client (application permissions). Mail.Read, Mail.Send, Sites.ReadWrite.All.

Application permissions mean the scheduled job never hits an interactive permission prompt - the failure mode that
silently killed the Cowork routine on Aug 20. Register the app in Entra, grant admin consent once, done.
"""
from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any, Iterator

import requests

log = logging.getLogger(__name__)
GRAPH = "https://graph.microsoft.com/v1.0"


class GraphError(RuntimeError):
    pass


class GraphClient:
    def __init__(self, tenant_id: str | None = None, client_id: str | None = None, client_secret: str | None = None,
                 session: requests.Session | None = None):
        self.tenant_id = tenant_id or os.environ.get("MS_TENANT_ID")
        self.client_id = client_id or os.environ.get("MS_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("MS_CLIENT_SECRET")
        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise GraphError("MS_TENANT_ID, MS_CLIENT_ID and MS_CLIENT_SECRET are required")
        self.s = session or requests.Session()
        self._token: str | None = None
        self._token_exp = 0.0

    # ---- auth -----------------------------------------------------------------
    def token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        import msal
        app = msal.ConfidentialClientApplication(self.client_id, authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                                                 client_credential=self.client_secret)
        res = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in res:
            raise GraphError(f"token failure: {res.get('error_description', res)}")
        self._token = res["access_token"]
        self._token_exp = time.time() + int(res.get("expires_in", 3600))
        return self._token

    def _req(self, method: str, url: str, **kw) -> requests.Response:
        if not url.startswith("http"):
            url = GRAPH + url
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token()}"
        for attempt in range(5):
            r = self.s.request(method, url, headers=headers, timeout=120, **kw)
            if r.status_code in (429, 503, 504):
                wait = int(r.headers.get("Retry-After", 2 ** attempt))
                log.warning("Graph %s -> %s, retrying in %ss", url, r.status_code, wait)
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise GraphError(f"{method} {url} -> {r.status_code}: {r.text[:500]}")
            return r
        raise GraphError(f"{method} {url}: gave up after retries")

    def get(self, url: str, **kw) -> dict[str, Any]:
        return self._req("GET", url, **kw).json()

    def paged(self, url: str, **kw) -> Iterator[dict[str, Any]]:
        while url:
            data = self.get(url, **kw)
            yield from data.get("value", [])
            url = data.get("@odata.nextLink")
            kw = {}

    # ---- mail -----------------------------------------------------------------
    @staticmethod
    def _mbx(mailbox: str) -> str:
        return "/me" if mailbox == "me" else f"/users/{mailbox}"

    def list_messages(self, mailbox: str, since_iso: str, folder: str = "inbox", with_attachments_only: bool = False) -> Iterator[dict[str, Any]]:
        flt = f"receivedDateTime ge {since_iso}"
        if with_attachments_only:
            flt += " and hasAttachments eq true"
        url = (f"{self._mbx(mailbox)}/mailFolders/{folder}/messages?$filter={flt}&$orderby=receivedDateTime asc&$top=50"
               f"&$select=id,subject,from,receivedDateTime,hasAttachments,internetMessageId,bodyPreview,body")
        yield from self.paged(url)

    def list_attachments(self, mailbox: str, message_id: str) -> list[dict[str, Any]]:
        return list(self.paged(f"{self._mbx(mailbox)}/messages/{message_id}/attachments?$select=id,name,contentType,size,isInline"))

    def download_attachment(self, mailbox: str, message_id: str, attachment_id: str) -> bytes:
        data = self.get(f"{self._mbx(mailbox)}/messages/{message_id}/attachments/{attachment_id}")
        if "contentBytes" in data:
            return base64.b64decode(data["contentBytes"])
        r = self._req("GET", f"{self._mbx(mailbox)}/messages/{message_id}/attachments/{attachment_id}/$value")
        return r.content

    def get_item_by_path(self, drive_id: str, path: str) -> dict[str, Any] | None:
        try:
            return self.get(f"/drives/{drive_id}/root:/{path}")
        except GraphError as e:
            if "404" in str(e):
                return None
            raise

    def download_path(self, drive_id: str, path: str) -> bytes | None:
        item = self.get_item_by_path(drive_id, path)
        return self.download_item(drive_id, item["id"]) if item else None

    def upload_replace(self, drive_id: str, folder_path: str, filename: str, data: bytes) -> str:
        """Like upload() but overwrites - for the state files that are meant to be replaced each run."""
        self.ensure_folder(drive_id, folder_path)
        r = self._req("PUT", f"/drives/{drive_id}/root:/{folder_path}/{filename}:/content?@microsoft.graph.conflictBehavior=replace",
                      data=data, headers={"Content-Type": "application/octet-stream"})
        return r.json().get("webUrl", f"{folder_path}/{filename}")

    def send_mail(self, sender: str, to: list[str], subject: str, html: str, attachments: list[tuple[str, bytes]] | None = None) -> None:
        msg: dict[str, Any] = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        }
        if attachments:
            msg["attachments"] = [{"@odata.type": "#microsoft.graph.fileAttachment", "name": n,
                                   "contentBytes": base64.b64encode(b).decode()} for n, b in attachments]
        self._req("POST", f"/users/{sender}/sendMail", json={"message": msg, "saveToSentItems": True})

    # ---- sharepoint -----------------------------------------------------------
    def site_id(self, hostname: str, site_path: str) -> str:
        return self.get(f"/sites/{hostname}:/sites/{site_path}")["id"]

    def drive_id(self, site_id: str, library_name: str) -> str:
        for d in self.paged(f"/sites/{site_id}/drives"):
            if d.get("name") == library_name:
                return d["id"]
        raise GraphError(f"library {library_name} not found on site {site_id}")

    def list_children(self, drive_id: str, folder_path: str) -> Iterator[dict[str, Any]]:
        yield from self.paged(f"/drives/{drive_id}/root:/{folder_path}:/children?$top=200")

    def download_item(self, drive_id: str, item_id: str) -> bytes:
        return self._req("GET", f"/drives/{drive_id}/items/{item_id}/content").content

    def ensure_folder(self, drive_id: str, folder_path: str) -> None:
        parts = [p for p in folder_path.split("/") if p]
        cur = ""
        for p in parts:
            nxt = f"{cur}/{p}" if cur else p
            try:
                self.get(f"/drives/{drive_id}/root:/{nxt}")
            except GraphError:
                parent = f"/drives/{drive_id}/root:/{cur}:/children" if cur else f"/drives/{drive_id}/root/children"
                self._req("POST", parent, json={"name": p, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
            cur = nxt

    def upload(self, drive_id: str, folder_path: str, filename: str, data: bytes) -> str:
        """Upload (<4MB direct, else upload session). Returns the webUrl. Renames on conflict rather than overwriting."""
        self.ensure_folder(drive_id, folder_path)
        path = f"{folder_path}/{filename}"
        if len(data) < 4_000_000:
            r = self._req("PUT", f"/drives/{drive_id}/root:/{path}:/content?@microsoft.graph.conflictBehavior=rename",
                          data=data, headers={"Content-Type": "application/octet-stream"})
            return r.json().get("webUrl", path)
        sess = self._req("POST", f"/drives/{drive_id}/root:/{path}:/createUploadSession",
                         json={"item": {"@microsoft.graph.conflictBehavior": "rename"}}).json()
        url, chunk, pos = sess["uploadUrl"], 5 * 1024 * 1024, 0
        last = None
        while pos < len(data):
            end = min(pos + chunk, len(data))
            last = self.s.put(url, data=data[pos:end], headers={"Content-Range": f"bytes {pos}-{end-1}/{len(data)}"}, timeout=300)
            pos = end
        return (last.json() if last is not None else {}).get("webUrl", path)

    def move_item(self, drive_id: str, item_id: str, new_folder_path: str, new_name: str | None = None) -> None:
        self.ensure_folder(drive_id, new_folder_path)
        parent = self.get(f"/drives/{drive_id}/root:/{new_folder_path}")
        body: dict[str, Any] = {"parentReference": {"id": parent["id"]}}
        if new_name:
            body["name"] = new_name
        self._req("PATCH", f"/drives/{drive_id}/items/{item_id}", json=body)


class DelegatedGraphClient(GraphClient):
    """Reads a mailbox AS THE USER after a one-time device-code sign-in. Used for the old ramcontracting@live.ca
    (a personal Microsoft account: application permissions cannot reach it, and Outlook.com dropped password IMAP).
    The refresh token is kept in an MSAL token cache file that travels with the database, so the sign-in is done once."""

    SCOPES = ["Mail.Read", "User.Read"]

    def __init__(self, cache_path: str, client_id: str | None = None, session: requests.Session | None = None):
        self.client_id = client_id or os.environ.get("MS_CLIENT_ID")
        if not self.client_id:
            raise GraphError("MS_CLIENT_ID is required")
        self.cache_path = cache_path
        self.s = session or requests.Session()
        self._token = None
        self._token_exp = 0.0

    def _app(self):
        import msal
        cache = msal.SerializableTokenCache()
        if os.path.exists(self.cache_path):
            with open(self.cache_path, "r", encoding="utf-8") as fh:
                cache.deserialize(fh.read())
        app = msal.PublicClientApplication(self.client_id, authority="https://login.microsoftonline.com/consumers", token_cache=cache)
        return app, cache

    def _save(self, cache) -> None:
        if cache.has_state_changed:
            os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as fh:
                fh.write(cache.serialize())

    def signed_in(self) -> bool:
        app, _ = self._app()
        return bool(app.get_accounts())

    def sign_in_interactive(self, printer=print) -> str:
        """Device-code flow: prints a URL and a code, the user signs in on any browser, done. Returns the account name."""
        app, cache = self._app()
        flow = app.initiate_device_flow(scopes=self.SCOPES)
        if "user_code" not in flow:
            raise GraphError(f"device flow failed: {flow}")
        printer(flow["message"])
        res = app.acquire_token_by_device_flow(flow)
        if "access_token" not in res:
            raise GraphError(f"sign-in failed: {res.get('error_description', res)}")
        self._save(cache)
        return (res.get("id_token_claims") or {}).get("preferred_username", "signed in")

    def token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        app, cache = self._app()
        accounts = app.get_accounts()
        if not accounts:
            raise GraphError("legacy mailbox not signed in; run: ramfin auth legacy")
        res = app.acquire_token_silent(self.SCOPES, account=accounts[0])
        self._save(cache)
        if not res or "access_token" not in res:
            raise GraphError("legacy mailbox sign-in expired; run: ramfin auth legacy")
        self._token = res["access_token"]
        self._token_exp = time.time() + int(res.get("expires_in", 3600))
        return self._token
