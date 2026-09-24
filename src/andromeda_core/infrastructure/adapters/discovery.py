"""Bounded, allowlisted source discovery beyond a single static URL."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from html.parser import HTMLParser
from urllib.parse import ParseResult, urljoin
from xml.etree import ElementTree

from andromeda_core.domain.common import SourceType
from andromeda_core.domain.identity import identity_hash
from andromeda_core.domain.ports.sources import SourceDescriptor
from andromeda_core.infrastructure.adapters.http_source import (
    HttpSourceFetcher,
    SourceFetchError,
    validate_source_url,
)

logger = logging.getLogger(__name__)


class DiscoveryMode:
    STATIC_URL = "STATIC_URL"
    SITEMAP_URL = "SITEMAP_URL"
    HTML_LINKS = "HTML_LINKS"


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


class HttpDiscoveryAdapter:
    def __init__(
        self,
        *,
        fetcher: HttpSourceFetcher,
        allowed_hosts: Iterable[str] | None = None,
        max_items: int = 100,
        same_origin_only: bool = True,
    ) -> None:
        self.fetcher = fetcher
        self.allowed_hosts = tuple(allowed_hosts) if allowed_hosts is not None else None
        self.max_items = max_items
        self.same_origin_only = same_origin_only

    async def discover(self, source_url: str, mode: str = DiscoveryMode.STATIC_URL) -> list[SourceDescriptor]:
        root = validate_source_url(source_url, self.allowed_hosts)
        if mode == DiscoveryMode.STATIC_URL:
            return [self._descriptor(source_url, SourceType.WEB_PAGE)]
        fetched = await self.fetcher.fetch(source_url)
        content = fetched.content
        if mode == DiscoveryMode.SITEMAP_URL:
            candidates = self._sitemap_urls(content)
        elif mode == DiscoveryMode.HTML_LINKS:
            parser = _LinkCollector()
            parser.feed(content.decode("utf-8", errors="replace"))
            candidates = parser.links
        else:
            raise ValueError(f"Unsupported discovery mode: {mode}")

        result: list[SourceDescriptor] = []
        seen: set[str] = set()
        for candidate in candidates:
            absolute = urljoin(source_url, candidate)
            try:
                parsed = validate_source_url(absolute, self.allowed_hosts)
            except SourceFetchError:
                continue
            if self.same_origin_only and self._origin(parsed) != self._origin(root):
                continue
            normalized = absolute.split("#", 1)[0]
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(self._descriptor(normalized, SourceType.WEB_PAGE))
            if len(result) >= self.max_items:
                break
        logger.debug("[FIX:discovery] discovered source URLs", extra={"fix": True, "mode": mode, "count": len(result)})
        return result

    @staticmethod
    def _sitemap_urls(content: bytes) -> list[str]:
        root = ElementTree.fromstring(content)
        return [element.text.strip() for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "loc" and element.text and element.text.strip()]

    @staticmethod
    def _descriptor(url: str, source_type: SourceType) -> SourceDescriptor:
        return SourceDescriptor(source_id=identity_hash("discovered-source", url), source_type=source_type, locator=url)

    @staticmethod
    def _origin(parsed: ParseResult) -> tuple[str, str | None, int]:
        scheme = parsed.scheme
        return scheme, parsed.hostname, parsed.port or (443 if scheme == "https" else 80)
