"""Create rules, derived knowledge and dependency graph tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_rules_derived"
down_revision = "0001_core_knowledge"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
DT = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("logical_key", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rule_type", sa.String(128), nullable=False),
        sa.Column("scope_json", JSON, nullable=False),
        sa.Column("conditions_json", JSON, nullable=False),
        sa.Column("effects_json", JSON, nullable=False),
        sa.Column("exceptions_json", JSON, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_from", DT),
        sa.Column("valid_to", DT),
        sa.Column("transaction_from", DT, nullable=False),
        sa.Column("transaction_to", DT),
        sa.Column("provenance_id", sa.String(36), sa.ForeignKey("provenance_records.id")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("ontology_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id"), nullable=False),
        sa.Column("replaces_rule_id", sa.String(36), sa.ForeignKey("rules.id")),
        sa.Column("validation_report", JSON, nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_rule_valid_interval"),
        sa.CheckConstraint("row_version > 0", name="ck_rule_row_version"),
        sa.UniqueConstraint("logical_key", "version", name="uq_rule_logical_key_version"),
    )
    op.create_index("ix_rules_logical_key", "rules", ["logical_key"])
    op.create_index("ix_rules_status", "rules", ["status"])
    op.create_index("ix_rules_status_scope", "rules", ["status", "ontology_version_id"])
    op.create_index("ix_rules_valid_time", "rules", ["valid_from", "valid_to"])
    op.create_index("ix_rules_ontology_version_id", "rules", ["ontology_version_id"])
    op.create_index("ix_rules_replaces_rule_id", "rules", ["replaces_rule_id"])
    op.create_table(
        "rule_test_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rule_id", sa.String(36), sa.ForeignKey("rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("given_facts", JSON, nullable=False),
        sa.Column("given_relations", JSON, nullable=False),
        sa.Column("context", JSON, nullable=False),
        sa.Column("applicant", JSON, nullable=False),
        sa.Column("expected_effects", JSON, nullable=False),
        sa.Column("expected_explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("passed", sa.Boolean()),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_run_at", DT),
        sa.UniqueConstraint("rule_id", "name", name="uq_rule_test_name"),
    )
    op.create_index("ix_rule_test_cases_rule_id", "rule_test_cases", ["rule_id"])
    op.create_table(
        "rule_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_rule_id", sa.String(36), sa.ForeignKey("rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("target_rule_id", sa.String(36), sa.ForeignKey("rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.UniqueConstraint("source_rule_id", "relation_type", "target_rule_id", name="uq_rule_relation"),
    )
    op.create_index("ix_rule_relations_source_rule_id", "rule_relations", ["source_rule_id"])
    op.create_index("ix_rule_relations_relation_type", "rule_relations", ["relation_type"])
    op.create_index("ix_rule_relations_target_rule_id", "rule_relations", ["target_rule_id"])
    op.create_table(
        "derived_values",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("derived_type", sa.String(128), nullable=False),
        sa.Column("value_json", JSON, nullable=False),
        sa.Column("context_json", JSON, nullable=False),
        sa.Column("query_context_json", JSON, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("invalidation_reason", sa.Text()),
        sa.Column("computed_at", DT, nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("ontology_version_id", sa.String(36), sa.ForeignKey("ontology_versions.id"), nullable=False),
        sa.Column("rule_versions_json", JSON, nullable=False),
        sa.Column("trace_json", JSON, nullable=False),
        sa.Column("result_key", sa.String(512), nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("row_version > 0", name="ck_derived_row_version"),
        sa.UniqueConstraint("result_key", name="uq_derived_result_key"),
    )
    op.create_index("ix_derived_values_derived_type", "derived_values", ["derived_type"])
    op.create_index("ix_derived_values_status", "derived_values", ["status"])
    op.create_index("ix_derived_status_type", "derived_values", ["status", "derived_type"])
    op.create_index("ix_derived_values_ontology_version_id", "derived_values", ["ontology_version_id"])
    op.create_table(
        "dependencies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("dependency_type", sa.String(64), nullable=False, server_default="SUPPORTS"),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("invalidated_at", DT),
        sa.UniqueConstraint("source_kind", "source_id", "target_kind", "target_id", "dependency_type", name="uq_dependency_edge"),
    )
    op.create_index("ix_dependencies_source", "dependencies", ["source_kind", "source_id"])
    op.create_index("ix_dependencies_target", "dependencies", ["target_kind", "target_id"])


def downgrade() -> None:
    for table in ["dependencies", "derived_values", "rule_relations", "rule_test_cases", "rules"]:
        op.drop_table(table)
