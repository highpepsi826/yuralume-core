from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kokoro_link.api.routes.characters import router as character_router
from kokoro_link.application.dto.character import CreateCharacterRequest
from kokoro_link.application.services.character_service import CharacterService
from kokoro_link.infrastructure.repositories.in_memory_characters import (
    InMemoryCharacterRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_initial_relationship import (
    InMemoryCharacterOperatorRelationshipSeedRepository,
)


def _client(
    service: CharacterService,
    seeds: InMemoryCharacterOperatorRelationshipSeedRepository,
) -> TestClient:
    class _Container:
        pass

    container = _Container()
    container.character_service = service
    container.relationship_seed_repository = seeds

    app = FastAPI()
    app.state.container = container
    app.include_router(character_router, prefix="/api/v1")
    return TestClient(app)


@pytest.mark.asyncio
async def test_initial_relationship_can_be_created_and_edited_after_creation() -> None:
    characters = InMemoryCharacterRepository()
    seeds = InMemoryCharacterOperatorRelationshipSeedRepository()
    service = CharacterService(characters, relationship_seed_repository=seeds)
    created = await service.create_character(CreateCharacterRequest(name="Mio"))
    client = _client(service, seeds)

    empty = client.get(
        f"/api/v1/characters/{created.id}/initial-relationship",
    )
    assert empty.status_code == 200
    assert empty.json() is None

    updated = client.put(
        f"/api/v1/characters/{created.id}/initial-relationship",
        json={
            "relationship_label": "一起生活的伴侶",
            "schedule_involvement_policy": "shared_allowed",
            "proactive_permission": True,
            "proactive_cadence_hint": "偶爾主動分享近況",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["schedule_involvement_policy"] == "shared_allowed"
    assert updated.json()["proactive_permission"] is True

    loaded = client.get(
        f"/api/v1/characters/{created.id}/initial-relationship",
    )
    assert loaded.status_code == 200
    assert loaded.json()["relationship_label"] == "一起生活的伴侶"

    stored = await seeds.get(created.id, "default")
    assert stored is not None
    assert stored.schedule_involvement_policy == "shared_allowed"


@pytest.mark.asyncio
async def test_initial_relationship_update_rejects_empty_payload() -> None:
    characters = InMemoryCharacterRepository()
    seeds = InMemoryCharacterOperatorRelationshipSeedRepository()
    service = CharacterService(characters, relationship_seed_repository=seeds)
    created = await service.create_character(CreateCharacterRequest(name="Mio"))
    client = _client(service, seeds)

    response = client.put(
        f"/api/v1/characters/{created.id}/initial-relationship",
        json={},
    )

    assert response.status_code == 400
    assert await seeds.get(created.id, "default") is None


def test_initial_relationship_routes_keep_character_ownership_boundary() -> None:
    service = CharacterService(InMemoryCharacterRepository())
    client = _client(
        service,
        InMemoryCharacterOperatorRelationshipSeedRepository(),
    )

    assert client.get(
        "/api/v1/characters/missing/initial-relationship",
    ).status_code == 404
    assert client.put(
        "/api/v1/characters/missing/initial-relationship",
        json={"relationship_label": "friend"},
    ).status_code == 404
