"""Integration tests for generation repository persistence behavior."""

from __future__ import annotations

import pytest

from tests.foreman.integration.conftest import (
    create_generation_via_api,
    create_project_via_api,
    create_user_via_api,
)


@pytest.mark.asyncio
async def test_generated_image_description_persists_and_reads(client):
    """Top-level generated_image_description should persist and be readable via API."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)
    generation = await create_generation_via_api(client, headers, project["id"])

    patch_resp = await client.patch(
        f"/v1/generations/{generation['id']}",
        headers=headers,
        json={
            "status": "completed",
            "output_image_url": "https://cdn.example.com/generated.png",
            "generated_image_description": "A modern interior with warm lighting",
        },
    )
    assert patch_resp.status_code == 200

    get_resp = await client.get(f"/v1/generations/{generation['id']}", headers=headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["generated_image_description"] == "A modern interior with warm lighting"
