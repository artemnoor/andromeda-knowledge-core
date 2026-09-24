"""Attach rule provenance to the immutable source document."""

import sqlalchemy as sa
from alembic import op

revision = "0008_rule_candidate_prov"
down_revision = "0007_norm_ontology_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("provenance_records", recreate="always") as batch:
            batch.add_column(sa.Column("source_document_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_provenance_source_document",
                "source_documents",
                ["source_document_id"],
                ["id"],
            )
    else:
        op.add_column("provenance_records", sa.Column("source_document_id", sa.String(36), nullable=True))
        op.create_foreign_key(
            "fk_provenance_source_document",
            "provenance_records",
            "source_documents",
            ["source_document_id"],
            ["id"],
        )
    op.create_index(
        "ix_provenance_records_source_document_id",
        "provenance_records",
        ["source_document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_provenance_records_source_document_id", table_name="provenance_records")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("provenance_records", recreate="always") as batch:
            batch.drop_constraint("fk_provenance_source_document", type_="foreignkey")
            batch.drop_column("source_document_id")
    else:
        op.drop_constraint("fk_provenance_source_document", "provenance_records", type_="foreignkey")
        op.drop_column("provenance_records", "source_document_id")
