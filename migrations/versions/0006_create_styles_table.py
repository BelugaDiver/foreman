"""Create styles table

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE styles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            example_image_url VARCHAR(2048),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    op.execute("CREATE INDEX idx_styles_name ON styles(name);")


def downgrade() -> None:
    op.execute("DROP TABLE styles;")
