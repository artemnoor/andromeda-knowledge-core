"""Normalized SQLAlchemy persistence schema.

The ORM models are infrastructure details. Domain modules use typed contracts
and repository ports instead of importing these classes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    """Declarative base used only by migrations and persistence adapters."""


class OntologyVersionModel(Base):
    __tablename__ = "ontology_versions"
    __table_args__ = (
        Index("ix_ontology_versions_version_code", "version_code", unique=True),
        Index("ix_ontology_versions_status", "status"),
        CheckConstraint("row_version > 0", name="ck_ontology_row_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_code: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("ontology_versions.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32))
    change_type: Mapped[str] = mapped_column(String(32))
    migration_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ObjectTypeModel(Base):
    __tablename__ = "object_types"
    __table_args__ = (UniqueConstraint("ontology_version_id", "code", name="uq_object_type_version_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"), index=True)
    code: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PropertyDefinitionModel(Base):
    __tablename__ = "property_definitions"
    __table_args__ = (UniqueConstraint("ontology_version_id", "code", name="uq_property_version_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"), index=True)
    code: Mapped[str] = mapped_column(String(128), index=True)
    value_type: Mapped[str] = mapped_column(String(32))
    enum_values: Mapped[list[str] | None] = mapped_column(JSON_TYPE, nullable=True)
    allowed_object_types: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")


class RelationTypeModel(Base):
    __tablename__ = "relation_types"
    __table_args__ = (UniqueConstraint("ontology_version_id", "code", name="uq_relation_version_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"), index=True)
    code: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    allowed_source_types: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    allowed_target_types: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    cardinality: Mapped[str] = mapped_column(String(32), default="MANY_TO_MANY")
    description: Mapped[str] = mapped_column(Text, default="")


class OntologyChangeProposalModel(Base):
    __tablename__ = "ontology_change_proposals"
    __table_args__ = (
        Index("ix_ontology_proposals_status", "status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_proposal_confidence"),
        CheckConstraint("row_version > 0", name="ck_proposal_row_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposed_types: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    proposed_properties: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    proposed_relations: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    reason: Mapped[str] = mapped_column(Text)
    source_evidence: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    impact_analysis: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    status: Mapped[str] = mapped_column(String(32))
    review_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class KnowledgeObjectModel(Base):
    __tablename__ = "knowledge_objects"
    __table_args__ = (
        UniqueConstraint("stable_key", name="uq_knowledge_object_stable_key"),
        Index("ix_knowledge_objects_type", "object_type_code"),
        CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_object_valid_interval"),
        CheckConstraint("row_version > 0", name="ck_object_row_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    stable_key: Mapped[str] = mapped_column(String(255), nullable=False)
    object_type_code: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    properties_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"), index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SourceModel(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("source_type", "external_identifier", name="uq_source_external_identity"),
        Index("ix_sources_checksum", "checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    trust_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceDocumentModel(Base):
    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("source_id", "document_checksum", name="uq_source_document_checksum"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    document_checksum: Mapped[str] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProvenanceRecordModel(Base):
    __tablename__ = "provenance_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    observation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    evidence_locator: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    extraction_method: Mapped[str] = mapped_column(String(128), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ObservationModel(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_observation_idempotency_key"),
        Index("ix_observations_status", "status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_observation_confidence"),
        CheckConstraint("row_version > 0", name="ck_observation_row_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32))
    subject_candidate: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    property_candidate: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    relation_candidate: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    value_json: Mapped[Any] = mapped_column(JSON_TYPE, nullable=True)
    value_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    confidence_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    ontology_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("ontology_versions.id"), nullable=True, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class FactModel(Base):
    __tablename__ = "facts"
    __table_args__ = (
        UniqueConstraint("identity_key", name="uq_fact_identity_key"),
        Index("ix_facts_subject_property_valid", "subject_id", "property_code", "valid_from"),
        Index("ix_facts_transaction_time", "transaction_from", "transaction_to"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fact_confidence"),
        CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_fact_valid_interval"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("knowledge_objects.id"), index=True)
    property_code: Mapped[str] = mapped_column(String(128), index=True)
    value_type: Mapped[str] = mapped_column(String(32))
    value_json: Mapped[Any] = mapped_column(JSON_TYPE, nullable=False)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    integer_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decimal_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_id: Mapped[str] = mapped_column(ForeignKey("provenance_records.id"), index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    confidence_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    verification_status: Mapped[str] = mapped_column(String(32), default="UNVERIFIED")
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"), index=True)
    identity_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RelationModel(Base):
    __tablename__ = "relations"
    __table_args__ = (
        UniqueConstraint("identity_key", name="uq_relation_identity_key"),
        Index("ix_relations_subject_type", "subject_id", "relation_type_code"),
        Index("ix_relations_object_type", "object_id", "relation_type_code"),
        Index("ix_relations_transaction_time", "transaction_from", "transaction_to"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_relation_confidence"),
        CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_relation_valid_interval"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("knowledge_objects.id"), index=True)
    relation_type_code: Mapped[str] = mapped_column(String(128), index=True)
    object_id: Mapped[str] = mapped_column(ForeignKey("knowledge_objects.id"), index=True)
    properties_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_id: Mapped[str] = mapped_column(ForeignKey("provenance_records.id"), index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    confidence_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    verification_status: Mapped[str] = mapped_column(String(32), default="UNVERIFIED")
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"), index=True)
    identity_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RuleModel(Base):
    __tablename__ = "rules"
    __table_args__ = (
        UniqueConstraint("logical_key", "version", name="uq_rule_logical_key_version"),
        Index("ux_rules_idempotency_key", "idempotency_key", unique=True),
        Index("ix_rules_status_scope", "status", "ontology_version_id"),
        Index("ix_rules_valid_time", "valid_from", "valid_to"),
        CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_rule_valid_interval"),
        CheckConstraint("row_version > 0", name="ck_rule_row_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    logical_key: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[int] = mapped_column(Integer)
    rule_type: Mapped[str] = mapped_column(String(128))
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    conditions_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    effects_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    exceptions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_id: Mapped[str | None] = mapped_column(ForeignKey("provenance_records.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"), index=True)
    replaces_rule_id: Mapped[str | None] = mapped_column(ForeignKey("rules.id"), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RuleRelationModel(Base):
    __tablename__ = "rule_relations"
    __table_args__ = (UniqueConstraint("source_rule_id", "relation_type", "target_rule_id", name="uq_rule_relation"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(32), index=True)
    target_rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RuleTestCaseModel(Base):
    __tablename__ = "rule_test_cases"
    __table_args__ = (UniqueConstraint("rule_id", "name", name="uq_rule_test_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    given_facts: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    given_relations: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    context: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    applicant: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    expected_effects: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    expected_explanation: Mapped[str] = mapped_column(Text, default="")
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DerivedValueModel(Base):
    __tablename__ = "derived_values"
    __table_args__ = (
        UniqueConstraint("result_key", name="uq_derived_result_key"),
        Index("ix_derived_status_type", "status", "derived_type"),
        CheckConstraint("row_version > 0", name="ck_derived_row_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    derived_type: Mapped[str] = mapped_column(String(128), index=True)
    value_json: Mapped[Any] = mapped_column(JSON_TYPE, nullable=False)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    query_context_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    status: Mapped[str] = mapped_column(String(32), index=True)
    invalidation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64))
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"), index=True)
    rule_versions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    trace_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    result_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class DependencyModel(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint(
            "source_kind",
            "source_id",
            "target_kind",
            "target_id",
            "dependency_type",
            name="uq_dependency_edge",
        ),
        Index("ix_dependencies_source", "source_kind", "source_id"),
        Index("ix_dependencies_target", "target_kind", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(36))
    target_kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(36))
    dependency_type: Mapped[str] = mapped_column(String(64), default="SUPPORTS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewItemModel(Base):
    __tablename__ = "review_items"
    __table_args__ = (Index("ix_reviews_status_reason", "status", "reason"), CheckConstraint("row_version > 0", name="ck_review_row_version"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reason: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    summary: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    proposed_change_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    decision_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AuditEventModel(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_created", "created_at"), Index("ix_audit_events_entity", "entity_type", "entity_id"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChangeEventModel(Base):
    __tablename__ = "change_events"
    __table_args__ = (Index("ix_change_events_classification", "classification", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    classification: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36))
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
