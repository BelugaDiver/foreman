import uuid
from datetime import datetime, timezone

from foreman.models.user import User

# Fixed UUIDs for stable test output and readable assertion messages
USER_A_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_B_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def make_user(user_id: uuid.UUID, email: str, full_name: str = "Test User") -> User:
    """Return a User dataclass pre-populated for test fixtures."""
    return User(
        id=user_id,
        email=email,
        full_name=full_name,
        is_active=True,
        is_deleted=False,
        created_at=datetime.now(timezone.utc),
        updated_at=None,
    )
