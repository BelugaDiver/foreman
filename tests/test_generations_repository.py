"""Tests for the generations repository layer."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from foreman.repositories import postgres_generations_repository as repo
from foreman.schemas.generation import GenerationCreate, GenerationUpdate
from tests.conftest import USER_A_ID, USER_B_ID


def _generation_record(
    generation_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    prompt: str = "Modern minimalist living room",
    status: str = "pending",
) -> dict:
    """Return a generation row-like dictionary for repository tests."""
    now = datetime.now(timezone.utc)
    return {
        "id": generation_id,
        "project_id": project_id,
        "parent_id": None,
        "status": status,
        "prompt": prompt,
        "style_id": "minimal",
        "input_image_url": "https://example.com/original.jpg",
        "output_image_url": None,
        "error_message": None,
        "model_used": "gpt-image-1",
        "processing_time_ms": None,
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }


@pytest.mark.asyncio
async def test_create_generation_inserts_and_returns_generation() -> None:
    """create_generation should persist and return the resulting Generation model."""
    # Arrange
    db = AsyncMock()
    project_id = uuid.uuid4()
    generation_id = uuid.uuid4()
    db.fetchrow = AsyncMock(return_value=_generation_record(generation_id, project_id))
    generation_in = GenerationCreate(prompt="Warm contemporary bedroom", style_id="warm")

    # Act
    generation = await repo.create_generation(
        db=db,
        project_id=project_id,
        input_image_url="https://example.com/original.jpg",
        generation_in=generation_in,
    )

    # Assert
    assert generation.id == generation_id
    assert generation.project_id == project_id
    stmt = db.fetchrow.await_args.args[0]
    assert "INSERT INTO generations" in stmt.text
    assert stmt.params == (
        project_id,
        None,
        "Warm contemporary bedroom",
        "warm",
        None,
        "https://example.com/original.jpg",
    )


@pytest.mark.asyncio
async def test_get_generation_by_id_scopes_by_owner() -> None:
    """get_generation_by_id should return a generation only when user scope matches."""
    # Arrange
    db = AsyncMock()
    generation_id = uuid.uuid4()
    project_id = uuid.uuid4()
    db.fetchrow = AsyncMock(return_value=_generation_record(generation_id, project_id))

    # Act
    generation = await repo.get_generation_by_id(db=db, generation_id=generation_id, user_id=USER_A_ID)

    # Assert
    assert generation is not None
    assert generation.id == generation_id
    stmt = db.fetchrow.await_args.args[0]
    assert "JOIN projects" in stmt.text
    assert "p.user_id=$2" in stmt.text
    assert stmt.params == (generation_id, USER_A_ID)


@pytest.mark.asyncio
async def test_get_generation_by_id_returns_none_when_not_owned_or_missing() -> None:
    """get_generation_by_id should return None when no scoped record exists."""
    # Arrange
    db = AsyncMock()
    generation_id = uuid.uuid4()
    db.fetchrow = AsyncMock(return_value=None)

    # Act
    generation = await repo.get_generation_by_id(db=db, generation_id=generation_id, user_id=USER_B_ID)

    # Assert
    assert generation is None


@pytest.mark.asyncio
async def test_list_generations_by_project_returns_paginated_rows() -> None:
    """list_generations_by_project should apply user scope, ordering, and pagination."""
    # Arrange
    db = AsyncMock()
    project_id = uuid.uuid4()
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    db.fetch = AsyncMock(
        return_value=[
            _generation_record(first_id, project_id, prompt="Design A"),
            _generation_record(second_id, project_id, prompt="Design B"),
        ]
    )

    # Act
    generations = await repo.list_generations_by_project(
        db=db,
        project_id=project_id,
        user_id=USER_A_ID,
        limit=10,
        offset=5,
    )

    # Assert
    assert len(generations) == 2
    assert [g.prompt for g in generations] == ["Design A", "Design B"]
    stmt = db.fetch.await_args.args[0]
    assert "ORDER BY g.created_at DESC" in stmt.text
    assert stmt.params == (project_id, USER_A_ID, 10, 5)


@pytest.mark.asyncio
async def test_update_generation_with_no_fields_returns_current_record() -> None:
    """update_generation should return the current scoped generation when no fields change."""
    # Arrange
    db = AsyncMock()
    generation_id = uuid.uuid4()
    project_id = uuid.uuid4()
    db.fetchrow = AsyncMock(return_value=_generation_record(generation_id, project_id))

    # Act
    generation = await repo.update_generation(
        db=db,
        generation_id=generation_id,
        user_id=USER_A_ID,
        generation_in=GenerationUpdate(),
    )

    # Assert
    assert generation is not None
    assert generation.id == generation_id
    stmt = db.fetchrow.await_args.args[0]
    assert "SELECT g.*" in stmt.text


@pytest.mark.asyncio
async def test_update_generation_updates_allowed_fields_with_scope() -> None:
    """update_generation should update only allowed fields and enforce user scoping."""
    # Arrange
    db = AsyncMock()
    generation_id = uuid.uuid4()
    project_id = uuid.uuid4()
    updated_row = _generation_record(generation_id, project_id, status="completed")
    updated_row["output_image_url"] = "https://example.com/result.jpg"
    updated_row["processing_time_ms"] = 1375
    updated_row["metadata"] = {"seed": 123}
    db.fetchrow = AsyncMock(return_value=updated_row)

    # Act
    generation = await repo.update_generation(
        db=db,
        generation_id=generation_id,
        user_id=USER_A_ID,
        generation_in=GenerationUpdate(
            status="completed",
            output_image_url="https://example.com/result.jpg",
            processing_time_ms=1375,
            metadata={"seed": 123},
        ),
    )

    # Assert
    assert generation is not None
    assert generation.status == "completed"
    stmt = db.fetchrow.await_args.args[0]
    assert "UPDATE generations AS g" in stmt.text
    assert "FROM projects AS p" in stmt.text
    assert "p.user_id=$6" in stmt.text
    assert stmt.params == (
        "completed",
        "https://example.com/result.jpg",
        1375,
        {"seed": 123},
        generation_id,
        USER_A_ID,
    )


@pytest.mark.asyncio
async def test_update_generation_returns_none_when_scoped_row_missing() -> None:
    """update_generation should return None when no row matches generation and user."""
    # Arrange
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)

    # Act
    generation = await repo.update_generation(
        db=db,
        generation_id=uuid.uuid4(),
        user_id=USER_B_ID,
        generation_in=GenerationUpdate(status="failed"),
    )

    # Assert
    assert generation is None


@pytest.mark.asyncio
async def test_delete_generation_returns_true_when_row_deleted() -> None:
    """delete_generation should delete only scoped rows and return True on success."""
    # Arrange
    db = AsyncMock()
    generation_id = uuid.uuid4()
    db.fetchrow = AsyncMock(return_value={"id": generation_id})

    # Act
    deleted = await repo.delete_generation(db=db, generation_id=generation_id, user_id=USER_A_ID)

    # Assert
    assert deleted is True
    stmt = db.fetchrow.await_args.args[0]
    assert "DELETE FROM generations AS g" in stmt.text
    assert "p.user_id=$2" in stmt.text
    assert stmt.params == (generation_id, USER_A_ID)


@pytest.mark.asyncio
async def test_delete_generation_returns_false_when_not_found_or_not_owned() -> None:
    """delete_generation should return False when no scoped generation is deleted."""
    # Arrange
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)

    # Act
    deleted = await repo.delete_generation(
        db=db,
        generation_id=uuid.uuid4(),
        user_id=USER_B_ID,
    )

    # Assert
    assert deleted is False
