"""Player and administrator APIs for bounded prompt customization."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kokoro_link.api.dependencies import get_container, get_current_user, require_admin
from kokoro_link.application.services.prompt_customization_service import (
    PROMPT_CUSTOMIZATION_MAX_CHARS,
    PromptCustomizationService,
)
from kokoro_link.bootstrap.container import ServiceContainer
from kokoro_link.domain.entities.operator_profile import OperatorProfile


class PromptCustomizationsPayload(BaseModel):
    chat: str = Field(default="", max_length=PROMPT_CUSTOMIZATION_MAX_CHARS)
    feed: str = Field(default="", max_length=PROMPT_CUSTOMIZATION_MAX_CHARS)
    media: str = Field(default="", max_length=PROMPT_CUSTOMIZATION_MAX_CHARS)
    proactive: str = Field(default="", max_length=PROMPT_CUSTOMIZATION_MAX_CHARS)


router = APIRouter(tags=["prompt-customizations"])
admin_router = APIRouter(
    prefix="/admin/prompt-customizations", tags=["admin-prompt-customizations"],
    dependencies=[Depends(require_admin)],
)


def _service(container: ServiceContainer) -> PromptCustomizationService:
    service = getattr(container, "prompt_customization_service", None)
    if service is None:
        raise HTTPException(503, "prompt customization service not wired")
    return service


@router.get("/prompt-customizations", response_model=PromptCustomizationsPayload)
async def get_player_prompt_customizations(
    container: ServiceContainer = Depends(get_container),
    current_user: OperatorProfile = Depends(get_current_user),
) -> PromptCustomizationsPayload:
    return PromptCustomizationsPayload(**await _service(container).get_player(user_id=current_user.id))


@router.put("/prompt-customizations", response_model=PromptCustomizationsPayload)
async def put_player_prompt_customizations(
    payload: PromptCustomizationsPayload,
    container: ServiceContainer = Depends(get_container),
    current_user: OperatorProfile = Depends(get_current_user),
) -> PromptCustomizationsPayload:
    try:
        values = await _service(container).set_player(
            user_id=current_user.id, values=payload.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return PromptCustomizationsPayload(**values)


@admin_router.get("", response_model=PromptCustomizationsPayload)
async def get_admin_prompt_customizations(
    container: ServiceContainer = Depends(get_container),
) -> PromptCustomizationsPayload:
    return PromptCustomizationsPayload(**await _service(container).get_admin())


@admin_router.put("", response_model=PromptCustomizationsPayload)
async def put_admin_prompt_customizations(
    payload: PromptCustomizationsPayload,
    container: ServiceContainer = Depends(get_container),
) -> PromptCustomizationsPayload:
    try:
        values = await _service(container).set_admin(values=payload.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return PromptCustomizationsPayload(**values)
