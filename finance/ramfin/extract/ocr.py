"""Turn whatever arrived into content blocks Claude can read. PDFs go as documents; images as images; spreadsheets as text."""
from __future__ import annotations

import base64
import csv
import io
from pathlib import Path
from typing import Any

IMAGE_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
MAX_IMAGE_BYTES = 4_500_000


def pdf_has_text(data: bytes) -> bool:
    try:
        import pymupdf  # type: ignore
    except ImportError:  # pragma: no cover
        return False
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return any(page.get_text().strip() for page in doc)
    except Exception:
        return False


def heic_to_jpeg(data: bytes) -> bytes | None:
    try:
        import pillow_heif  # type: ignore
        from PIL import Image  # type: ignore
        pillow_heif.register_heif_opener()
        im = Image.open(io.BytesIO(data)).convert("RGB")
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        return out.getvalue()
    except Exception:
        return None


def downscale_jpeg(data: bytes) -> bytes:
    if len(data) <= MAX_IMAGE_BYTES:
        return data
    try:
        from PIL import Image  # type: ignore
        im = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = im.size
        scale = (MAX_IMAGE_BYTES / len(data)) ** 0.5
        im = im.resize((max(800, int(w * scale)), max(800, int(h * scale))))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=85)
        return out.getvalue()
    except Exception:
        return data


def spreadsheet_to_text(data: bytes, ext: str, max_rows: int = 400) -> str:
    if ext == "csv":
        text = data.decode("utf-8-sig", errors="replace")
        return "\n".join(text.splitlines()[:max_rows])
    try:
        import openpyxl  # type: ignore
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets:
            parts.append(f"## Sheet: {ws.title}")
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= max_rows:
                    parts.append("...")
                    break
                parts.append("\t".join("" if v is None else str(v) for v in row))
        return "\n".join(parts)
    except Exception as e:  # pragma: no cover
        return f"[could not read spreadsheet: {e}]"


def content_blocks(data: bytes, filename: str) -> list[dict[str, Any]]:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext == "pdf":
        return [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.standard_b64encode(data).decode()}}]
    if ext in ("heic", "heif"):
        jpg = heic_to_jpeg(data)
        if jpg is None:
            return [{"type": "text", "text": f"[HEIC image {filename} could not be converted; install pillow-heif]"}]
        data, ext = jpg, "jpg"
    if ext in IMAGE_TYPES:
        if ext in ("jpg", "jpeg"):
            data = downscale_jpeg(data)
        return [{"type": "image", "source": {"type": "base64", "media_type": IMAGE_TYPES[ext],
                                             "data": base64.standard_b64encode(data).decode()}}]
    if ext in ("xlsx", "xlsm", "xls", "csv"):
        return [{"type": "text", "text": f"Spreadsheet {filename}:\n{spreadsheet_to_text(data, ext)}"}]
    if ext in ("txt", "html", "htm", "eml", "md"):
        return [{"type": "text", "text": data.decode("utf-8", errors="replace")[:60000]}]
    return [{"type": "text", "text": f"[unsupported file type .{ext} for {filename}]"}]
