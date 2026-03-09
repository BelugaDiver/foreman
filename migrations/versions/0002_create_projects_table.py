"""create projects table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-08 16:45:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id            UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name               TEXT        NOT NULL,
        original_image_url TEXT,
        room_analysis      JSONB,
        created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at         TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects(user_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS projects CASCADE;")
