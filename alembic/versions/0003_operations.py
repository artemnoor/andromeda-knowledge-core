"""Create human review, audit and change classification tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_operations"
down_revision = "0002_rules_derived"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
DT = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_json", JSON, nullable=False),
        sa.Column("proposed_change_json", JSON, nullable=False),
        sa.Column("decision_json", JSON, nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Column("decided_at", DT),
        sa.Column("decided_by", sa.String(255)),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("row_version > 0", name="ck_review_row_version"),
    )
    op.create_index("ix_reviews_status_reason", "review_items", ["status", "reason"])
    op.create_index("ix_review_items_reason", "review_items", ["reason"])
    op.create_index("ix_review_items_status", "review_items", ["status"])
    op.create_index("ix_review_items_entity_id", "review_items", ["entity_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("before_json", JSON),
        sa.Column("after_json", JSON),
        sa.Column("reason", sa.Text()),
        sa.Column("source_id", sa.String(36)),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("created_at", DT, nullable=False),
    )
    op.create_index("ix_audit_events_created", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])
    op.create_index("ix_audit_events_entity_type", "audit_events", ["entity_type"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.create_table(
        "change_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("classification", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("before_json", JSON),
        sa.Column("after_json", JSON),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", DT, nullable=False),
    )
    op.create_index("ix_change_events_classification", "change_events", ["classification", "created_at"])


def downgrade() -> None:
    for table in ["change_events", "audit_events", "review_items"]:
        op.drop_table(table)
