"""Create images table

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-24 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE images (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id),
            filename VARCHAR(512) NOT NULL,
            content_type VARCHAR(100) NOT NULL,
            size_bytes INTEGER NOT NULL,
            storage_key VARCHAR(1024) NOT NULL,
            url VARCHAR(2048),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    op.execute("CREATE INDEX idx_images_project_id ON images(project_id);")
    op.execute("CREATE INDEX idx_images_user_id ON images(user_id);")


def downgrade() -> None:
    op.execute("DROP TABLE images;")
