"""Normalize ontology version uniqueness to the explicit unique index."""

from alembic import op

revision = "0007_norm_ontology_unique"
down_revision = "0006_remove_ingestion_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL reflects the inline ``unique=True`` column constraint from
    # 0001 as ``ontology_versions_version_code_key``.  The declarative model
    # intentionally keeps the named unique index as the single canonical
    # uniqueness primitive.  SQLite does not expose inline unique constraints
    # consistently through Alembic, so leave its compatible legacy auto-index
    # untouched.
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "ontology_versions_version_code_key",
            "ontology_versions",
            type_="unique",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.create_unique_constraint(
            "ontology_versions_version_code_key",
            "ontology_versions",
            ["version_code"],
        )
