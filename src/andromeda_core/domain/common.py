"""Small, framework-free domain value objects and enums."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceType(StrEnum):
    WEB_PAGE = "WEB_PAGE"
    PDF = "PDF"
    API = "API"
    DOCUMENT = "DOCUMENT"
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"


class ConfidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    UNCERTAIN = "UNCERTAIN"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class ObservationStatus(StrEnum):
    RAW = "RAW"
    PARSED = "PARSED"
    MAPPED = "MAPPED"
    VALIDATED = "VALIDATED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class OntologyStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    MIGRATING = "MIGRATING"


class OntologyChangeType(StrEnum):
    BACKWARD_COMPATIBLE = "BACKWARD_COMPATIBLE"
    BREAKING = "BREAKING"
    MIGRATION_REQUIRED = "MIGRATION_REQUIRED"


class ProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    VALIDATING = "VALIDATING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"
    MIGRATING = "MIGRATING"
    ACTIVE = "ACTIVE"


class RuleStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    TESTING = "TESTING"
    REVIEW = "REVIEW"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class DerivedStatus(StrEnum):
    VALID = "VALID"
    INVALIDATED = "INVALIDATED"


class ReviewStatus(StrEnum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


class ReviewReason(StrEnum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    RULE_CONFLICT = "RULE_CONFLICT"
    UNKNOWN_CONCEPT = "UNKNOWN_CONCEPT"
    BREAKING_ONTOLOGY_CHANGE = "BREAKING_ONTOLOGY_CHANGE"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    SUSPICIOUS_LARGE_CHANGE = "SUSPICIOUS_LARGE_CHANGE"


class ChangeClassification(StrEnum):
    NEW_FACT = "NEW_FACT"
    FACT_CHANGED = "FACT_CHANGED"
    FACT_REMOVED = "FACT_REMOVED"
    NEW_RELATION = "NEW_RELATION"
    RELATION_CHANGED = "RELATION_CHANGED"
    NEW_RULE = "NEW_RULE"
    RULE_CHANGED = "RULE_CHANGED"
    RULE_REMOVED = "RULE_REMOVED"
    UNKNOWN_CONCEPT = "UNKNOWN_CONCEPT"
    CONFLICT = "CONFLICT"


class TemporalAxis(StrEnum):
    VALID_TIME = "valid_time"
    TRANSACTION_TIME = "transaction_time"


class EffectType(StrEnum):
    SET = "SET"
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    GRANT = "GRANT"
    DENY = "DENY"
    MARK_ELIGIBLE = "MARK_ELIGIBLE"
    MARK_INELIGIBLE = "MARK_INELIGIBLE"
    EMIT_DERIVED = "EMIT_DERIVED"


@dataclass(frozen=True, slots=True)
class TemporalWindow:
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    transaction_from: datetime | None = None
    transaction_to: datetime | None = None

    def __post_init__(self) -> None:
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        if self.transaction_from and self.transaction_to and self.transaction_to <= self.transaction_from:
            raise ValueError("transaction_to must be after transaction_from")

    def contains_valid(self, moment: datetime) -> bool:
        return (self.valid_from is None or self.valid_from <= moment) and (
            self.valid_to is None or moment < self.valid_to
        )

    def contains_transaction(self, moment: datetime) -> bool:
        return (self.transaction_from is None or self.transaction_from <= moment) and (
            self.transaction_to is None or moment < self.transaction_to
        )


def validate_temporal_values(
    *,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    transaction_from: datetime | None = None,
    transaction_to: datetime | None = None,
) -> None:
    """Validate half-open temporal intervals at the domain boundary."""

    try:
        TemporalWindow(valid_from, valid_to, transaction_from, transaction_to)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class Confidence:
    score: Decimal
    status: ConfidenceStatus = ConfidenceStatus.UNKNOWN

    def __post_init__(self) -> None:
        if self.score < 0 or self.score > 1:
            raise ValueError("confidence score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ProvenanceRef:
    provenance_id: str
    source_id: str
    observation_id: str | None
    evidence_locator: dict[str, Any]
