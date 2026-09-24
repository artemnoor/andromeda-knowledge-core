"""Add idempotency keys for rule mutation requests."""

import sqlalchemy as sa
from alembic import op

revision = "0004_rule_idempotency"
down_revision = "0003_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.create_index("ux_rules_idempotency_key", "rules", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_rules_idempotency_key", table_name="rules")
    op.drop_column("rules", "idempotency_key")
