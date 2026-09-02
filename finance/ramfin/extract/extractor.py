"""Classify and extract one document with Claude. The client is injected so tests run without the network."""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from ..models import Extraction
from . import ocr
from .schemas import EXTRACTION_SCHEMA, SYSTEM_PROMPT

log = logging.getLogger(__name__)


class ExtractorProtocol(Protocol):
    def extract(self, data: bytes, filename: str, context: str = "") -> Extraction: ...


class ClaudeExtractor:
    def __init__(self, client: Any | None = None, model: str = "claude-opus-5", max_tokens: int = 16000):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def extract(self, data: bytes, filename: str, context: str = "") -> Extraction:
        blocks = ocr.content_blocks(data, filename)
        prompt = (f"File name: {filename}\n" + (f"Context from the email or folder it came from: {context}\n" if context else "")
                  + "Return the JSON object describing this document.")
        blocks.append({"type": "text", "text": prompt})
        import anthropic
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": blocks}],
                output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
            )
        except anthropic.RateLimitError as e:
            raise ExtractionError(f"rate limited: {e}") from e
        except anthropic.APIStatusError as e:
            raise ExtractionError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionError(f"network: {e}") from e
        if getattr(resp, "stop_reason", None) == "refusal":
            raise ExtractionError("model declined to process this document")
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "{}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"unparseable JSON from model: {e}") from e
        ex = Extraction.from_dict(payload)
        if filename.lower().endswith(".pdf") and not ocr.pdf_has_text(data) and ex.notes is None:
            ex.notes = "image-only PDF (no text layer)"
        return ex


class ExtractionError(RuntimeError):
    pass


class FakeExtractor:
    """Deterministic extractor for tests and dry runs: maps filename -> Extraction dict."""

    def __init__(self, by_filename: dict[str, dict[str, Any]], default: dict[str, Any] | None = None):
        self.by_filename = by_filename
        self.default = default or {"doc_type": "other", "confidence": 0.2, "legible": True}
        self.calls: list[str] = []

    def extract(self, data: bytes, filename: str, context: str = "") -> Extraction:
        self.calls.append(filename)
        return Extraction.from_dict(self.by_filename.get(filename, self.default))
