# Phase 4: Secure discovery, preparation, evidence and AI

Plan: [index.md](index.md)
Tasks: 10-13
Depends on: Phase 3 / Tasks 7-9 and Phase 2 / Task 4

## Objective

Move the remaining useful fixes into the one Ingestion implementation: robust HTTP security, non-static discovery, evidence locators and ontology-aware structured extraction.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `infrastructure/fetchers/http.py` | `SafeHttpFetcher` | Already bounds redirects/body and allowlists hosts but does not resolve DNS or reject HTTP 4xx/5xx safely. |
| `infrastructure/sources/discovery.py` | `StaticSourceDiscovery` | Current implementation only supports configured static URLs. |
| `infrastructure/preparation/generic.py` | `_html`, `_pdf`, `_split_chunk` | Existing evidence is useful but HTML selectors/offsets and split locators are coarse. |
| `infrastructure/ai/http_json.py` | `StructuredJsonHttpAIAdapter.extract` | Existing adapter sends profile schema but omits `context.ontology`. |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `infrastructure/fetchers/http.py`, `infrastructure/config.py` | modify | DNS resolution, global-address checks, 4xx/5xx policy and injectable client/resolver. |
| `infrastructure/sources/discovery.py`, `application/container.py` | modify | Dispatch STATIC/SITEMAP/HTML_LINK_DISCOVERY with bounded same-origin results. |
| `infrastructure/preparation/generic.py` | modify | Precise selectors/text offsets/page locators and excerpt hashes. |
| `infrastructure/ai/http_json.py` | modify | Send complete ontology/DSL snapshot in trusted request context; keep document data untrusted. |

## Task 10: Strengthen HTTP fetching

### Intent

Make external source access safe against DNS rebinding/SSRF and predictable for 4xx/5xx upstream failures.

### Implementation Steps

1. Keep credential-free HTTP(S), allowlist and redirect validation; add an injectable `resolve_host` callable and resolve every hostname before request/redirect.
2. Reject any resolved address that is not globally routable, including private, loopback, link-local, reserved, multicast and unspecified ranges. Reject DNS failures as `FETCH_SSRF_REJECTED` or bounded `FETCH_FAILED` with safe details.
3. Reject 4xx as non-retryable `FETCH_CLIENT_ERROR` and 5xx as `FETCH_SERVER_ERROR` after bounded retries; do not treat an error page as an artifact. Preserve status code in details.
4. Enforce content-length and streaming/body bounds before storing; retain timeout and total budget settings.

### Error Handling and Logging

- Never log credentials, authorization headers or raw response bodies.
- Include host, status, redirect count, byte limit and elapsed time only.

### Tests

- Reject localhost/127.0.0.1/private DNS result, credential URL and unsafe redirect.
- Assert 404/500 raise stable errors and oversized body is rejected.

### Acceptance Criteria

- A DNS name resolving to a private address never reaches `httpx`.

### Verification

- `pytest -q tests/unit/test_storage_and_security.py`.

## Task 11: Implement configured discovery

### Intent

Support bounded Sitemap and same-origin HTML link discovery without letting discovery become semantic parsing.

### Implementation Steps

1. Add a configured discovery adapter that delegates document retrieval to the safe HTTP fetcher and dispatches by `DiscoveryStrategy`.
2. Parse XML sitemap `<loc>` values, supporting a bounded sitemap index traversal; normalize/remove fragments, deduplicate and cap at `MAX_DISCOVERY_ITEMS`.
3. Parse HTML anchors with BeautifulSoup, keep only same-origin/allowlisted HTTP(S) links, reject credentials/external hosts, normalize and deduplicate.
4. Preserve `document_kind`, `profile_code`, discovery method and source ID in each `DiscoveredItem` metadata; unsupported strategies return a stable `DISCOVERY_FAILED` error rather than silently using static mode.

### Error Handling and Logging

- A malformed sitemap/HTML response is a bounded discovery error with source ID and URL, not a partial success with hidden corruption.
- Log counts and skipped-link reasons, never page contents.

### Tests

- Sitemap test returns two same-host URLs and skips external URL.
- HTML test returns same-origin links, strips fragments and skips external/credential links.
- Bound test proves `MAX_DISCOVERY_ITEMS` is enforced.

### Acceptance Criteria

- `STATIC_URL`, `SITEMAP` and `HTML_LINK_DISCOVERY` have distinct tested behavior.

### Verification

- `pytest -q tests/unit/test_discovery.py tests/api/test_api_contract.py`.

## Task 12: Improve evidence locators

### Intent

Make candidate evidence reproducible against immutable artifacts without moving any parsing responsibility into Core.

### Implementation Steps

1. Generate stable HTML CSS-like ancestry selectors with `id`/`nth-of-type` where needed and calculate text ranges against normalized document text.
2. When chunks are split, create locator copies with chunk-specific `text_start`, `text_end` and quote, not one coarse locator for every piece.
3. For PDF, preserve page plus extracted-text offsets per page; for JSON/text preserve a root/fragment locator and content SHA-256 metadata.
4. Ensure every `EvidenceRef` can carry artifact ID, source URL, locator and excerpt hash/quote, with deterministic hashes.

### Error Handling and Logging

- If a parser cannot produce a reliable locator, fail preparation rather than fabricate a locator that points nowhere.
- Do not log full quotes in normal production logs.

### Tests

- HTML fixture verifies selector and range identify the quoted text.
- PDF fixture verifies page and non-empty quote; split text verifies monotonic ranges.

### Acceptance Criteria

- Evidence points to an immutable artifact and a concrete page/selector/range/fragment.

### Verification

- `pytest -q tests/unit/test_preparation.py tests/integration/test_golden_evaluation.py`.

## Task 13: Pass ontology to structured AI

### Intent

Ensure the real HTTP AI adapter receives the same trusted ontology/DSL context that validation uses; mock correctness alone is insufficient.

### Implementation Steps

1. In `StructuredJsonHttpAIAdapter`, include `context.ontology.model_dump(mode="json")` and `context.profile.metadata.rule_dsl_schema`/snapshot in the trusted system payload and output schema.
2. Keep `context.untrusted_document_data` in a separate user/data payload explicitly delimited as untrusted; never concatenate it into trusted instructions.
3. Inject an `httpx.AsyncClient`/transport for tests, honor the configured timeout and close only owned clients.
4. Validate the provider response as `ExtractionResult`; convert HTTP/JSON/schema errors to stable `UpstreamError`/`ValidationError`.

### Error Handling and Logging

- Log provider/model/profile/version and ontology version, not API key, prompt body or raw document data.
- An absent ontology is an explicit empty snapshot, never an implicit import from Core.

### Tests

- MockTransport captures request and asserts object types, properties, relation types, ontology version and Rule DSL schema are present.
- Prompt-injection fixture proves document text does not replace trusted instructions.

### Acceptance Criteria

- The actual HTTP adapter—not only MockAI—receives the full ontology snapshot.

### Verification

- `pytest -q tests/unit/test_ai_contract.py tests/integration/test_failure_boundaries.py`.

## Phase Risks and Mitigations

- Risk: discovery uses a second unsafe HTTP client. Mitigation: inject/reuse the same safe fetcher seam.
- Risk: overly precise locators become brittle under normalization. Mitigation: keep artifact checksum and quote hash as anchors and test deterministic fixtures.
