"""Create ontology, knowledge, sources and provenance tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_core_knowledge"
down_revision = None
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
DT = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ontology_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_code", sa.String(64), nullable=False, unique=True),
        sa.Column("previous_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("change_type", sa.String(32), nullable=False),
        sa.Column("migration_requirements", sa.Text()),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("activated_at", DT),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("row_version > 0", name="ck_ontology_row_version"),
    )
    op.create_index("ix_ontology_versions_version_code", "ontology_versions", ["version_code"], unique=True)
    op.create_index("ix_ontology_versions_status", "ontology_versions", ["status"])
    op.create_table(
        "object_types",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ontology_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id"), nullable=False),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("lifecycle_status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", DT, nullable=False),
        sa.UniqueConstraint("ontology_version_id", "code", name="uq_object_type_version_code"),
    )
    op.create_index("ix_object_types_ontology_version_id", "object_types", ["ontology_version_id"])
    op.create_index("ix_object_types_code", "object_types", ["code"])
    op.create_table(
        "property_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ontology_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id"), nullable=False),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("value_type", sa.String(32), nullable=False),
        sa.Column("enum_values", JSON),
        sa.Column("allowed_object_types", JSON, nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("ontology_version_id", "code", name="uq_property_version_code"),
    )
    op.create_index("ix_property_definitions_ontology_version_id", "property_definitions", ["ontology_version_id"])
    op.create_index("ix_property_definitions_code", "property_definitions", ["code"])
    op.create_table(
        "relation_types",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ontology_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id"), nullable=False),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("allowed_source_types", JSON, nullable=False),
        sa.Column("allowed_target_types", JSON, nullable=False),
        sa.Column("cardinality", sa.String(32), nullable=False, server_default="MANY_TO_MANY"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("ontology_version_id", "code", name="uq_relation_version_code"),
    )
    op.create_index("ix_relation_types_ontology_version_id", "relation_types", ["ontology_version_id"])
    op.create_index("ix_relation_types_code", "relation_types", ["code"])
    op.create_table(
        "ontology_change_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposed_types", JSON, nullable=False),
        sa.Column("proposed_properties", JSON, nullable=False),
        sa.Column("proposed_relations", JSON, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_evidence", JSON, nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("impact_analysis", JSON, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("review_id", sa.String(36)),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_proposal_confidence"),
        sa.CheckConstraint("row_version > 0", name="ck_proposal_row_version"),
    )
    op.create_index("ix_ontology_proposals_status", "ontology_change_proposals", ["status"])
    op.create_index("ix_ontology_change_proposals_review_id", "ontology_change_proposals", ["review_id"])
    op.create_table(
        "knowledge_objects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stable_key", sa.String(255), nullable=False),
        sa.Column("object_type_code", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("properties_json", JSON, nullable=False),
        sa.Column("ontology_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id"), nullable=False),
        sa.Column("lifecycle_status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("valid_from", DT),
        sa.Column("valid_to", DT),
        sa.Column("transaction_from", DT, nullable=False),
        sa.Column("transaction_to", DT),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_object_valid_interval"),
        sa.CheckConstraint("row_version > 0", name="ck_object_row_version"),
        sa.UniqueConstraint("stable_key", name="uq_knowledge_object_stable_key"),
    )
    op.create_index("ix_knowledge_objects_type", "knowledge_objects", ["object_type_code"])
    op.create_index("ix_knowledge_objects_object_type_code", "knowledge_objects", ["object_type_code"])
    op.create_index("ix_knowledge_objects_ontology_version_id", "knowledge_objects", ["ontology_version_id"])
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("external_identifier", sa.String(255)),
        sa.Column("publisher", sa.String(255)),
        sa.Column("retrieved_at", DT),
        sa.Column("checksum", sa.String(128)),
        sa.Column("content_metadata", JSON, nullable=False),
        sa.Column("trust_metadata", JSON, nullable=False),
        sa.Column("parser_version", sa.String(64)),
        sa.Column("created_at", DT, nullable=False),
        sa.UniqueConstraint("source_type", "external_identifier", name="uq_source_external_identity"),
    )
    op.create_index("ix_sources_source_type", "sources", ["source_type"])
    op.create_index("ix_sources_checksum", "sources", ["checksum"])
    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_checksum", sa.String(128), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("content_metadata", JSON, nullable=False),
        sa.Column("retrieved_at", DT),
        sa.Column("created_at", DT, nullable=False),
        sa.UniqueConstraint("source_id", "document_checksum", name="uq_source_document_checksum"),
    )
    op.create_index("ix_source_documents_source_id", "source_documents", ["source_id"])
    op.create_table(
        "provenance_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("observation_id", sa.String(36)),
        sa.Column("evidence_locator", JSON, nullable=False),
        sa.Column("extraction_method", sa.String(128), nullable=False, server_default="manual"),
        sa.Column("created_at", DT, nullable=False),
    )
    op.create_index("ix_provenance_records_source_id", "provenance_records", ["source_id"])
    op.create_index("ix_provenance_records_observation_id", "provenance_records", ["observation_id"])
    op.create_table(
        "observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("source_document_id", sa.String(36), sa.ForeignKey("source_documents.id")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("subject_candidate", JSON, nullable=False),
        sa.Column("property_candidate", sa.String(128)),
        sa.Column("relation_candidate", JSON),
        sa.Column("value_json", JSON),
        sa.Column("value_type", sa.String(32)),
        sa.Column("evidence_json", JSON, nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_status", sa.String(32), nullable=False),
        sa.Column("ontology_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id")),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("raw_payload", JSON, nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_observation_confidence"),
        sa.CheckConstraint("row_version > 0", name="ck_observation_row_version"),
        sa.UniqueConstraint("idempotency_key", name="uq_observation_idempotency_key"),
    )
    op.create_index("ix_observations_source_id", "observations", ["source_id"])
    op.create_index("ix_observations_source_document_id", "observations", ["source_document_id"])
    op.create_index("ix_observations_status", "observations", ["status"])
    op.create_index("ix_observations_property_candidate", "observations", ["property_candidate"])
    op.create_index("ix_observations_ontology_version_id", "observations", ["ontology_version_id"])
    op.create_table(
        "facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject_id", sa.String(36), sa.ForeignKey("knowledge_objects.id"), nullable=False),
        sa.Column("property_code", sa.String(128), nullable=False),
        sa.Column("value_type", sa.String(32), nullable=False),
        sa.Column("value_json", JSON, nullable=False),
        sa.Column("text_value", sa.Text()),
        sa.Column("integer_value", sa.Integer()),
        sa.Column("decimal_value", sa.Numeric(18, 6)),
        sa.Column("boolean_value", sa.Boolean()),
        sa.Column("valid_from", DT),
        sa.Column("valid_to", DT),
        sa.Column("transaction_from", DT, nullable=False),
        sa.Column("transaction_to", DT),
        sa.Column("provenance_id", sa.String(36), sa.ForeignKey("provenance_records.id"), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_status", sa.String(32), nullable=False),
        sa.Column("verification_status", sa.String(32), nullable=False),
        sa.Column("ontology_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id"), nullable=False),
        sa.Column("identity_key", sa.String(512), nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fact_confidence"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_fact_valid_interval"),
        sa.UniqueConstraint("identity_key", name="uq_fact_identity_key"),
    )
    op.create_index("ix_facts_subject_id", "facts", ["subject_id"])
    op.create_index("ix_facts_property_code", "facts", ["property_code"])
    op.create_index("ix_facts_subject_property_valid", "facts", ["subject_id", "property_code", "valid_from"])
    op.create_index("ix_facts_transaction_time", "facts", ["transaction_from", "transaction_to"])
    op.create_index("ix_facts_provenance_id", "facts", ["provenance_id"])
    op.create_index("ix_facts_ontology_version_id", "facts", ["ontology_version_id"])
    op.create_table(
        "relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject_id", sa.String(36), sa.ForeignKey("knowledge_objects.id"), nullable=False),
        sa.Column("relation_type_code", sa.String(128), nullable=False),
        sa.Column("object_id", sa.String(36), sa.ForeignKey("knowledge_objects.id"), nullable=False),
        sa.Column("properties_json", JSON, nullable=False),
        sa.Column("valid_from", DT),
        sa.Column("valid_to", DT),
        sa.Column("transaction_from", DT, nullable=False),
        sa.Column("transaction_to", DT),
        sa.Column("provenance_id", sa.String(36), sa.ForeignKey("provenance_records.id"), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_status", sa.String(32), nullable=False),
        sa.Column("verification_status", sa.String(32), nullable=False),
        sa.Column("ontology_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id"), nullable=False),
        sa.Column("identity_key", sa.String(512), nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_relation_confidence"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_relation_valid_interval"),
        sa.UniqueConstraint("identity_key", name="uq_relation_identity_key"),
    )
    op.create_index("ix_relations_subject_id", "relations", ["subject_id"])
    op.create_index("ix_relations_relation_type_code", "relations", ["relation_type_code"])
    op.create_index("ix_relations_object_id", "relations", ["object_id"])
    op.create_index("ix_relations_subject_type", "relations", ["subject_id", "relation_type_code"])
    op.create_index("ix_relations_object_type", "relations", ["object_id", "relation_type_code"])
    op.create_index("ix_relations_transaction_time", "relations", ["transaction_from", "transaction_to"])
    op.create_index("ix_relations_provenance_id", "relations", ["provenance_id"])
    op.create_index("ix_relations_ontology_version_id", "relations", ["ontology_version_id"])


def downgrade() -> None:
    for table in [
        "relations",
        "facts",
        "observations",
        "provenance_records",
        "source_documents",
        "sources",
        "knowledge_objects",
        "ontology_change_proposals",
        "relation_types",
        "property_definitions",
        "object_types",
        "ontology_versions",
    ]:
        op.drop_table(table)
