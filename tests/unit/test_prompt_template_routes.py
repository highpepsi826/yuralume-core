from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kokoro_link.api.dependencies import get_container, get_current_user
from kokoro_link.api.routes.prompt_customizations import router, admin_router
from kokoro_link.application.services.prompt_customization_service import PromptCustomizationService
from kokoro_link.domain.entities.operator_profile import OperatorProfile
from kokoro_link.infrastructure.repositories.in_memory_preferences import InMemoryPreferencesRepository
from kokoro_link.infrastructure.prompts.loader import set_admin_template_overrides


@pytest.fixture
def studio():
    set_admin_template_overrides({})
    app = FastAPI()
    container = SimpleNamespace(prompt_customization_service=PromptCustomizationService(InMemoryPreferencesRepository()))
    app.dependency_overrides[get_container] = lambda: container
    app.include_router(router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    yield app, TestClient(app)
    set_admin_template_overrides({})


def test_player_style_crud_isolation_and_core_authorization(studio):
    app, client = studio
    app.dependency_overrides[get_current_user] = lambda: OperatorProfile(id="alice", display_name="Alice")
    listing = client.get("/api/v1/prompt-templates")
    assert listing.status_code == 200
    assert len(listing.json()["templates"]) == 5
    assert all(item["name"].endswith("_style") for item in listing.json()["templates"])
    assert client.get("/api/v1/admin/prompt-templates").status_code == 403
    assert client.get("/api/v1/prompt-templates/feed/composer").status_code == 404
    assert client.put("/api/v1/prompt-templates/feed/composer", json={"content": "changed"}).status_code == 400
    path = "/api/v1/prompt-templates/chat/instructions_footer_style"
    assert client.put(path, json={"content": "speak playfully"}).json()["content"] == "speak playfully\n"
    app.dependency_overrides[get_current_user] = lambda: OperatorProfile(id="bob", display_name="Bob")
    assert not client.get(path).json()["overridden"]
    app.dependency_overrides[get_current_user] = lambda: OperatorProfile(id="alice", display_name="Alice")
    assert client.get(path).json()["content"] == "speak playfully\n"
    assert not client.put(path, json={"content": ""}).json()["overridden"]


def test_admin_core_warning_and_variable_validation(studio):
    app, client = studio
    app.dependency_overrides[get_current_user] = lambda: OperatorProfile(id="admin", display_name="Admin", is_admin=True)
    response = client.get("/api/v1/admin/prompt-templates")
    assert response.status_code == 200
    items = response.json()["templates"]
    assert any(item["name"] == "schedule/planner" and item["important"] and item["impact"] for item in items)
    assert all("（" in item["title"] and item["title"].endswith("）") for item in items)
    assert all("（" in item["category"] and item["category"].endswith("）") for item in items)
    path = "/api/v1/admin/prompt-templates/feed/composer"
    template = client.get(path).json()
    assert client.put(path, json={"content": "missing variables"}).status_code == 400
    assert client.put(path, json={"content": template["content"] + "\nExtra instruction."}).status_code == 200
    assert not client.put(path, json={"content": ""}).json()["overridden"]


def test_player_draft_routes_publish_and_discard(studio):
    app, client = studio
    app.dependency_overrides[get_current_user] = lambda: OperatorProfile(id="alice", display_name="Alice")
    path = "/api/v1/prompt-templates/chat/instructions_footer_style"
    draft = client.get(path).json()["content"] + "\nDraft text."

    saved = client.put(path + "/draft", json={"content": draft})
    assert saved.status_code == 200
    assert saved.json()["has_draft"]
    assert not saved.json()["overridden"]
    assert client.post(path + "/publish-draft").json()["content"] == draft.strip() + "\n"
    assert not client.get(path).json()["has_draft"]
    assert client.put(path + "/draft", json={"content": draft + "\nDiscard me."}).status_code == 200
    assert not client.delete(path + "/draft").json()["has_draft"]


def test_admin_draft_routes_require_admin_and_publish_globally(studio):
    app, client = studio
    path = "/api/v1/admin/prompt-templates/chat/instructions_footer"
    app.dependency_overrides[get_current_user] = lambda: OperatorProfile(id="owner", display_name="Owner")
    assert client.put(path + "/draft", json={"content": "nope"}).status_code == 403

    app.dependency_overrides[get_current_user] = lambda: OperatorProfile(id="admin", display_name="Admin", is_admin=True)
    draft = client.get(path).json()["content"] + "\nGlobal draft note."
    assert client.put(path + "/draft", json={"content": draft}).json()["has_draft"]
    assert client.post(path + "/publish-draft").json()["content"] == draft.strip() + "\n"
