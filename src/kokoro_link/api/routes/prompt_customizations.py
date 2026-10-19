"""Prompt Studio APIs for player-safe and administrator template overrides."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kokoro_link.api.dependencies import get_container, get_current_user, require_admin
from kokoro_link.application.services.prompt_customization_service import PromptCustomizationService
from kokoro_link.bootstrap.container import ServiceContainer
from kokoro_link.domain.entities.operator_profile import OperatorProfile


class PromptTemplateWrite(BaseModel):
    content: str = Field(default="", max_length=24000)


router = APIRouter(prefix="/prompt-templates", tags=["prompt-studio"])
admin_router = APIRouter(
    prefix="/admin/prompt-templates", tags=["admin-prompt-studio"],
    dependencies=[Depends(require_admin)],
)


def _service(container: ServiceContainer) -> PromptCustomizationService:
    service = getattr(container, "prompt_customization_service", None)
    if service is None:
        raise HTTPException(503, "prompt customization service not wired")
    return service


async def _get(
    name: str, container: ServiceContainer, user: OperatorProfile, admin: bool,
) -> dict[str, Any]:
    try:
        return await _service(container).get_template(
            name=name, user_id=user.id, admin=admin,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


async def _put(
    name: str, payload: PromptTemplateWrite, container: ServiceContainer,
    user: OperatorProfile, admin: bool,
) -> dict[str, Any]:
    try:
        return await _service(container).set_template(
            name=name, content=payload.content, user_id=user.id, admin=admin,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


async def _draft(
    name: str, payload: PromptTemplateWrite, container: ServiceContainer,
    user: OperatorProfile, admin: bool,
) -> dict[str, Any]:
    try:
        return await _service(container).set_draft(
            name=name, content=payload.content, user_id=user.id, admin=admin,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


async def _discard_draft(
    name: str, container: ServiceContainer, user: OperatorProfile, admin: bool,
) -> dict[str, Any]:
    try:
        return await _service(container).discard_draft(
            name=name, user_id=user.id, admin=admin,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


async def _publish_draft(
    name: str, container: ServiceContainer, user: OperatorProfile, admin: bool,
) -> dict[str, Any]:
    try:
        return await _service(container).publish_draft(
            name=name, user_id=user.id, admin=admin,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("")
async def list_player_templates(
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return {"templates": await _service(container).list_templates(
        user_id=user.id, admin=False,
    )}


@router.post("/publish-drafts")
async def publish_player_template_drafts(
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(container).publish_drafts(user_id=user.id, admin=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/{name:path}")
async def get_player_template(
    name: str, container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _get(name, container, user, False)


@router.put("/{name:path}/draft")
async def put_player_template_draft(
    name: str, payload: PromptTemplateWrite,
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _draft(name, payload, container, user, False)


@router.delete("/{name:path}/draft")
async def delete_player_template_draft(
    name: str, container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _discard_draft(name, container, user, False)


@router.post("/{name:path}/publish-draft")
async def publish_player_template_draft(
    name: str, container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _publish_draft(name, container, user, False)


@router.put("/{name:path}")
async def put_player_template(
    name: str, payload: PromptTemplateWrite,
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _put(name, payload, container, user, False)


@admin_router.get("")
async def list_admin_templates(
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return {"templates": await _service(container).list_templates(
        user_id=user.id, admin=True,
    )}


@admin_router.post("/publish-drafts")
async def publish_admin_template_drafts(
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service(container).publish_drafts(user_id=user.id, admin=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@admin_router.get("/{name:path}")
async def get_admin_template(
    name: str, container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _get(name, container, user, True)


@admin_router.put("/{name:path}/draft")
async def put_admin_template_draft(
    name: str, payload: PromptTemplateWrite,
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _draft(name, payload, container, user, True)


@admin_router.delete("/{name:path}/draft")
async def delete_admin_template_draft(
    name: str, container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _discard_draft(name, container, user, True)


@admin_router.post("/{name:path}/publish-draft")
async def publish_admin_template_draft(
    name: str, container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _publish_draft(name, container, user, True)


@admin_router.put("/{name:path}")
async def put_admin_template(
    name: str, payload: PromptTemplateWrite,
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict[str, Any]:
    return await _put(name, payload, container, user, True)
