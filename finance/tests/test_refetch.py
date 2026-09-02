"""A fresh runner has the database but not the inbox bytes: they must travel with the state or be re-fetched."""
import hashlib
from pathlib import Path

from ramfin import db, pipeline, state_sync
from ramfin.extract.extractor import FakeExtractor
from ramfin.filer import LocalFiler
from ramfin.sources.common import refetch_bytes
from tests.fixtures import extractions as fx


class FakeGraph:
    def __init__(self, files: dict[str, bytes]):
        self.files = files          # attachment name -> bytes
        self.store: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def find_message(self, mailbox, imid):
        return {"id": "m1"} if imid == "<msg1>" else None

    def list_attachments(self, mailbox, msg_id):
        return [{"id": f"a{i}", "name": n} for i, n in enumerate(self.files)]

    def download_attachment(self, mailbox, msg_id, att_id):
        return self.files[list(self.files)[int(att_id[1:])]]

    def download_item(self, drive, item_id):
        return self.store[item_id]

    def upload_replace(self, drive, folder, name, data):
        self.store[f"{folder}/{name}"] = data
        return name

    def download_path(self, drive, path):
        return self.store.get(path)

    def list_children(self, drive, folder):
        return [{"name": k.split("/")[-1], "id": k, "file": {}} for k in self.store if k.startswith(folder + "/") and "/" not in k[len(folder) + 1:]]

    def delete_item(self, drive, item_id):
        self.store.pop(item_id, None); self.deleted.append(item_id)


def test_refetch_from_mailbox_by_hash(conn, settings):
    data = b"brandt invoice bytes"
    h = hashlib.sha256(data).hexdigest()
    doc_id = db.insert(conn, "documents", dict(sha256=h, source="mail:accounts@ramexcavating.ca", source_ref="<msg1>", filename="brandt.pdf",
                                               local_path=str(settings.inbox_dir / "gone.pdf"), status="error", created_at=db.now_iso()))
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    g = FakeGraph({"other.pdf": b"nope", "brandt.pdf": data})
    assert refetch_bytes(conn, settings, doc, {"app": g, "me": None, "finance_drive": "d"})
    assert Path(conn.execute("SELECT local_path FROM documents WHERE id=?", (doc_id,)).fetchone()["local_path"]).read_bytes() == data
    ex = FakeExtractor({"brandt.pdf": fx.INVOICE_BRANDT})
    stats = pipeline.process_new_documents(conn, settings, ex, LocalFiler(settings.data_dir / "sp"))
    assert stats["filed"] == 1 and stats["errors"] == 0


def test_missing_bytes_without_refetch_is_marked(conn, settings):
    db.insert(conn, "documents", dict(sha256="zz", source="mail:x@y", source_ref="<m>", filename="x.pdf", local_path="/nonexistent/x.pdf", status="new", created_at=db.now_iso()))
    stats = pipeline.process_new_documents(conn, settings, FakeExtractor({}), LocalFiler(settings.data_dir / "sp"))
    assert stats["unavailable"] == 1
    assert "unavailable" in conn.execute("SELECT error FROM documents").fetchone()["error"]


def test_inbox_travels_with_state(settings):
    real = db.connect(settings.db_path)
    settings.inbox_dir.mkdir(parents=True, exist_ok=True)
    (settings.inbox_dir / "aaa_pending.pdf").write_bytes(b"pending")
    (settings.inbox_dir / "bbb_done.pdf").write_bytes(b"done")
    db.insert(real, "documents", dict(sha256="a", source="mail:x", filename="pending.pdf", local_path=str(settings.inbox_dir / "aaa_pending.pdf"), status="new", created_at=db.now_iso()))
    db.insert(real, "documents", dict(sha256="b", source="mail:x", filename="done.pdf", local_path=str(settings.inbox_dir / "bbb_done.pdf"), status="filed", created_at=db.now_iso()))
    real.commit(); real.close()
    g = FakeGraph({})
    out = state_sync.push(g, "d", settings)
    assert out["inbox"]["uploaded"] == 1
    remote_inbox = f"{settings.sharepoint['state']}/inbox"
    assert f"{remote_inbox}/aaa_pending.pdf" in g.store and f"{remote_inbox}/bbb_done.pdf" not in g.store
    (settings.inbox_dir / "aaa_pending.pdf").unlink()
    pulled = state_sync.pull(g, "d", settings)
    assert pulled["inbox_files"] == 1 and (settings.inbox_dir / "aaa_pending.pdf").read_bytes() == b"pending"
    # once processed, the remote copy is removed on the next push
    real = db.connect(settings.db_path)
    real.execute("UPDATE documents SET status='filed' WHERE sha256='a'"); real.commit(); real.close()
    out = state_sync.push(g, "d", settings)
    assert out["inbox"]["removed"] == 1
