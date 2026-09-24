"""Deterministic evidence locators for HTML, PDF bytes and plain text."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from typing import Any


class _HtmlTextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.segments: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack.append(tag.lower())

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.segments.append(("", tag.lower()))

    def handle_endtag(self, tag: str) -> None:
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if normalized:
            self.segments.append((normalized, ">".join(self.stack[-4:])))


def build_evidence_locator(
    content: bytes,
    *,
    content_type: str | None = None,
    quote: str | None = None,
    page: int | None = None,
) -> dict[str, Any]:
    """Build a stable locator without trusting provider-supplied coordinates."""

    digest = hashlib.sha256(content).hexdigest()
    lowered_type = (content_type or "").lower()
    if "html" in lowered_type or content.lstrip().startswith((b"<", b"<!DOCTYPE", b"<!doctype")):
        return _html_locator(content, quote, digest)
    if "pdf" in lowered_type or content.startswith(b"%PDF"):
        return _pdf_locator(content, quote, page, digest)
    return _text_locator(content, quote, digest)


def _html_locator(content: bytes, quote: str | None, digest: str) -> dict[str, Any]:
    parser = _HtmlTextCollector()
    parser.feed(content.decode("utf-8", errors="replace"))
    text = " ".join(segment for segment, _ in parser.segments if segment)
    normalized_quote = " ".join((quote or "").split())
    start = text.casefold().find(normalized_quote.casefold()) if normalized_quote else -1
    selector = next((path for segment, path in parser.segments if segment), "body")
    return {
        "format": "html",
        "selector": selector or "body",
        "text_quote": normalized_quote or None,
        "char_start": start if start >= 0 else None,
        "char_end": start + len(normalized_quote) if start >= 0 else None,
        "content_sha256": digest,
    }


def _pdf_locator(content: bytes, quote: str | None, page: int | None, digest: str) -> dict[str, Any]:
    normalized_quote = " ".join((quote or "").split())
    byte_start: int | None = None
    if normalized_quote:
        encoded_quote = normalized_quote.encode("utf-8")
        byte_start = content.find(encoded_quote)
        if byte_start < 0:
            byte_start = content.lower().find(normalized_quote.encode("latin-1", errors="ignore").lower())
    resolved_page = page or (content[:byte_start].count(b"\f") + 1 if byte_start is not None and byte_start >= 0 else None)
    return {
        "format": "pdf",
        "page": resolved_page,
        "text_quote": normalized_quote or None,
        "byte_start": byte_start if byte_start is not None and byte_start >= 0 else None,
        "byte_end": byte_start + len(normalized_quote.encode("utf-8")) if byte_start is not None and byte_start >= 0 else None,
        "content_sha256": digest,
    }


def _text_locator(content: bytes, quote: str | None, digest: str) -> dict[str, Any]:
    text = content.decode("utf-8", errors="replace")
    normalized_quote = " ".join((quote or "").split())
    start = text.casefold().find(normalized_quote.casefold()) if normalized_quote else -1
    return {
        "format": "text",
        "text_quote": normalized_quote or None,
        "char_start": start if start >= 0 else None,
        "char_end": start + len(normalized_quote) if start >= 0 else None,
        "content_sha256": digest,
    }
