"""SSRF-aware HTTP source fetching with bounded redirects and bodies."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import socket
from collections.abc import Callable, Iterable
from urllib.parse import ParseResult, urljoin, urlparse

import httpx

from andromeda_core.domain.common import SourceType
from andromeda_core.domain.ports.ai import ExtractionContext
from andromeda_core.domain.ports.ingestion import FetchedDocument
from andromeda_core.domain.ports.sources import SourceDescriptor, SourceFetchResult

logger = logging.getLogger(__name__)


class SourceFetchError(RuntimeError):
    """Safe, operator-facing source fetch failure without response-body leakage."""


def _is_unsafe_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not address.is_global or address.is_loopback or address.is_private or address.is_link_local


def _default_resolve_host(hostname: str) -> list[str]:
    records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    return sorted({str(item[4][0]) for item in records})


def validate_source_url(url: str, allowed_hosts: Iterable[str] | None = None) -> ParseResult:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SourceFetchError("Only http and https source URLs are allowed.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise SourceFetchError("Source URL must contain a hostname and no credentials.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise SourceFetchError("Local source hosts are not allowed.")
    if allowed_hosts is not None:
        normalized = {item.rstrip(".").lower() for item in allowed_hosts}
        if hostname not in normalized:
            raise SourceFetchError("Source host is not in the configured allowlist.")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None and _is_unsafe_address(str(literal)):
        raise SourceFetchError("Private or non-global source addresses are not allowed.")
    return parsed


class HttpSourceFetcher:
    """Fetch a source only after validating every hostname and redirect."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        resolve_host: Callable[[str], list[str]] | None = None,
        allowed_hosts: Iterable[str] | None = None,
        timeout_seconds: float = 20.0,
        max_body_bytes: int = 10_000_000,
        max_redirects: int = 3,
    ) -> None:
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False)
        self._owns_client = client is None
        self.resolve_host = resolve_host or _default_resolve_host
        self.allowed_hosts = tuple(allowed_hosts) if allowed_hosts is not None else None
        self.max_body_bytes = max_body_bytes
        self.max_redirects = max_redirects

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def fetch(self, source: str | ExtractionContext | SourceDescriptor) -> SourceFetchResult | FetchedDocument:
        source_id = "http-source"
        if isinstance(source, ExtractionContext):
            url = source.source_url
            source_id = source.source_id
        elif isinstance(source, SourceDescriptor):
            url = source.locator
            source_id = source.source_id
        else:
            url = source

        current_url = url
        for redirect_count in range(self.max_redirects + 1):
            parsed = validate_source_url(current_url, self.allowed_hosts)
            await self._validate_resolved_addresses(parsed.hostname or "")
            logger.debug(
                "[FIX:ssrf] fetching validated source",
                extra={"fix": True, "hostname": parsed.hostname, "path": parsed.path, "redirect_count": redirect_count},
            )
            response = await self.client.get(current_url)
            if 300 <= response.status_code < 400:
                location = response.headers.get("location")
                if not location or redirect_count >= self.max_redirects:
                    raise SourceFetchError("Source redirect limit was exceeded or Location was missing.")
                current_url = urljoin(current_url, location)
                continue
            if response.status_code >= 400:
                logger.warning(
                    "[FIX:ssrf] source returned an HTTP error",
                    extra={"fix": True, "hostname": parsed.hostname, "status_code": response.status_code},
                )
                raise SourceFetchError(f"Source fetch failed with status {response.status_code}.")
            length = response.headers.get("content-length")
            if length and length.isdigit() and int(length) > self.max_body_bytes:
                raise SourceFetchError("Source response exceeds the configured body limit.")
            content = response.content
            if len(content) > self.max_body_bytes:
                raise SourceFetchError("Source response exceeds the configured body limit.")
            checksum = hashlib.sha256(content).hexdigest()
            metadata = {
                "url": current_url,
                "checksum": checksum,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
            }
            result = SourceFetchResult(
                source=SourceDescriptor(source_id=source_id, source_type=SourceType.WEB_PAGE, locator=current_url, checksum=checksum),
                content=content,
                content_type=response.headers.get("content-type"),
                metadata=metadata,
            )
            logger.debug(
                "[FIX:ssrf] source fetch completed",
                extra={"fix": True, "hostname": parsed.hostname, "bytes": len(content), "checksum": checksum[:16]},
            )
            if isinstance(source, ExtractionContext):
                return FetchedDocument(content=content, content_type=result.content_type, metadata=metadata)
            return result
        raise SourceFetchError("Source redirect limit was exceeded.")

    async def _validate_resolved_addresses(self, hostname: str) -> None:
        addresses = await asyncio.to_thread(self.resolve_host, hostname)
        if not addresses:
            raise SourceFetchError("Source hostname did not resolve.")
        for address in addresses:
            try:
                unsafe = _is_unsafe_address(address)
            except ValueError as exc:
                raise SourceFetchError("Source hostname resolved to an invalid address.") from exc
            if unsafe:
                raise SourceFetchError("Source hostname resolves to a private or non-global address.")
