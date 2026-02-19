"""Custom Alembic revision template."""
from __future__ import annotations

from alembic import op


revision = ${repr(revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the migration."""
    # Example:
    # op.execute("""
    #     CREATE TABLE example (
    #         id BIGSERIAL PRIMARY KEY,
    #         name TEXT NOT NULL
    #     );
    # """)
    pass


def downgrade() -> None:
    """Rollback the migration."""
    pass
