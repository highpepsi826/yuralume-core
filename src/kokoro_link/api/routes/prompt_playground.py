"""Prompt Studio's no-persistence chat comparison endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from kokoro_link.api.dependencies import get_current_user, get_container
from kokoro_link.application.services.prompt_playground_service import (
    PromptPlaygroundAccessError,
    PromptPlaygroundBusyError,
    PromptPlaygroundGenerationError,
)
from kokoro_link.bootstrap.container import ServiceContainer
from kokoro_link.domain.entities.operator_profile import OperatorProfile

router = APIRouter(tags=["prompt-playground"])


class PromptPlaygroundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    include_current_progress: bool = True
    draft_scope: Literal["player", "admin"] = "player"


@router.get("/prompt-playground/characters")
async def list_prompt_playground_characters(
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict:
    service = container.prompt_playground_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "prompt playground is unavailable")
    characters = await service.list_characters(user_id=user.id, admin=user.is_admin)
    return {"characters": [{"id": item.id, "name": item.name} for item in characters]}


@router.post("/characters/{character_id}/prompt-playground/runs")
async def run_prompt_playground(
    character_id: str,
    payload: PromptPlaygroundRequest,
    container: ServiceContainer = Depends(get_container),
    user: OperatorProfile = Depends(get_current_user),
) -> dict:
    service = container.prompt_playground_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "prompt playground is unavailable")
    try:
        result = await service.run(
            character_id=character_id,
            user_id=user.id,
            admin=user.is_admin,
            message=payload.message,
            include_current_progress=payload.include_current_progress,
            draft_scope=payload.draft_scope,
        )
    except PromptPlaygroundAccessError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except PromptPlaygroundBusyError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from None
    except PromptPlaygroundGenerationError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "模型測試失敗，請稍後再試。") from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return {
        "published_reply": result.published_reply,
        "draft_reply": result.draft_reply,
        "model_id": result.model_id,
        "prompt_hash": result.prompt_hash,
        "snapshot_summary": result.snapshot_summary,
        "has_draft": result.has_draft,
        "draft_prompt_hash": result.draft_prompt_hash,
        "provider_id": result.provider_id,
        "elapsed_ms": result.elapsed_ms,
    }
