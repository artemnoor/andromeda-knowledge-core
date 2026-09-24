"""Add durable, resumable source ingestion pipeline attempts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_ingestion_pipeline"
down_revision = "0004_rule_idempotency"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
DT = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ingestion_pipeline_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pipeline_key", sa.String(128), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("item_key", sa.String(255), nullable=False),
        sa.Column("profile", sa.String(128), nullable=False),
        sa.Column("document_checksum", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_successful_stage", sa.String(32)),
        sa.Column("failed_stage", sa.String(32)),
        sa.Column("fetched_content", sa.LargeBinary()),
        sa.Column("content_type", sa.String(255)),
        sa.Column("fetch_metadata_json", JSON, nullable=False),
        sa.Column("extraction_json", JSON, nullable=False),
        sa.Column("publish_result_json", JSON, nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Column("last_run_at", DT),
        sa.UniqueConstraint("pipeline_key", "document_checksum", name="uq_ingestion_pipeline_checksum"),
    )
    op.create_index("ix_ingestion_pipeline_key", "ingestion_pipeline_runs", ["pipeline_key"])
    op.create_index("ix_ingestion_pipeline_key_created", "ingestion_pipeline_runs", ["pipeline_key", "created_at"])
    op.create_index("ix_ingestion_pipeline_status", "ingestion_pipeline_runs", ["status"])
    op.create_index("ix_ingestion_pipeline_source_id", "ingestion_pipeline_runs", ["source_id"])


def downgrade() -> None:
    op.drop_table("ingestion_pipeline_runs")
