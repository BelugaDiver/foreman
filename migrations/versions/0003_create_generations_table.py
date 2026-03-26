"""create generations table

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-22 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS generations (
        id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id         UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        parent_id          UUID        REFERENCES generations(id) ON DELETE SET NULL,
        status             TEXT        NOT NULL DEFAULT 'pending',
        prompt             TEXT        NOT NULL,
        style_id           TEXT,
        input_image_url    TEXT        NOT NULL,
        output_image_url   TEXT,
        error_message      TEXT,
        model_used         TEXT,
        processing_time_ms INTEGER,
        metadata           JSONB       NOT NULL DEFAULT '{}',
        created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at         TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_generations_project_id ON generations(project_id);
    CREATE INDEX IF NOT EXISTS ix_generations_parent_id ON generations(parent_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS generations CASCADE;")
