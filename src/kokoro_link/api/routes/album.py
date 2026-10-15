"""Character album HTTP routes.

Thin — every action is a one-liner on ``AlbumService`` with service
exceptions mapped to appropriate HTTP statuses. Keep business logic
in the service; keep status-code mapping in the route.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from kokoro_link.api.dependencies import (
    ensure_character_id_owned_by_user,
    ensure_owned_character_id,
    get_container,
    get_current_user_id,
    get_owned_character,
    is_cloud_mode,
)
from kokoro_link.application.dto.album import (
    AlbumItemResponse,
    AlbumListResponse,
    TransferFromStageRequest,
)
from kokoro_link.application.dto.character import CharacterResponse
from kokoro_link.application.services.album_service import (
    AlbumCharacterMismatchError,
    AlbumItemNotFoundError,
    AlbumManagedError,
    StageFullError,
    StageImageNotFoundError,
)
from kokoro_link.bootstrap.container import ServiceContainer
from kokoro_link.domain.entities.character import Character
from kokoro_link.contracts.video_provider import VideoGenerationError

router = APIRouter(tags=["album"])

_DEFAULT_LIMIT = 40
"""Grid view fits more tiles per screen than the feed's list rows, so
the default page is larger than the feed's 20 — still comfortably
smaller than the 500-item sanity cap."""
_MAX_LIMIT = 100


class CharacterVideoPreviewRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


def _video_preview_service(container: ServiceContainer):
    if is_cloud_mode(container):
        raise HTTPException(status_code=403, detail="Character video previews are only available in self-host mode")
    service = getattr(container, "feed_composer_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Video generation service is unavailable")
    return service


@router.get("/characters/{character_id}/album/video-preview")
async def character_video_preview_settings(
    character_id: str,
    response: Response,
    container: ServiceContainer = Depends(get_container),
    character: Character = Depends(get_owned_character),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    service = _video_preview_service(container)
    try:
        return await service.character_video_preview_settings(character)
    except VideoGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/characters/{character_id}/album/video-preview")
async def generate_character_video_preview(
    character_id: str,
    payload: CharacterVideoPreviewRequest,
    container: ServiceContainer = Depends(get_container),
    character: Character = Depends(get_owned_character),
) -> Response:
    service = _video_preview_service(container)
    try:
        blob = await service.generate_character_video_preview(character, payload.prompt)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Video generation timed out; the upstream job may still run") from exc
    except VideoGenerationError as exc:
        # Provider errors can contain credentials and raw upstream bodies. The
        # provider settings test offers a separately scrubbed diagnostic path.
        raise HTTPException(status_code=400, detail="Video generation failed. Check this character's video provider settings and try the provider test for details.") from exc
    return Response(
        content=blob, media_type="video/mp4",
        headers={"Cache-Control": "no-store", "Content-Disposition": 'inline; filename="character-preview.mp4"'},
    )


@router.get(
    "/characters/{character_id}/album",
    response_model=AlbumListResponse,
)
async def list_album(
    character_id: str,
    limit: int | None = Query(default=None, ge=1, le=_MAX_LIMIT),
    before: datetime | None = Query(default=None),
    container: ServiceContainer = Depends(get_container),
    _owned_character_id: str = Depends(ensure_owned_character_id),
) -> AlbumListResponse:
    if limit is None and before is None:
        items = await container.album_service.list_for_character(character_id)
        total = await container.album_service.count_for_character(character_id)
        return AlbumListResponse.from_domain(
            items, total=total, limit=max(len(items) + 1, 1),
        )
    page_limit = limit or _DEFAULT_LIMIT
    items = await container.album_service.list_for_character(
        character_id, limit=page_limit, before=before,
    )
    total = await container.album_service.count_for_character(character_id)
    return AlbumListResponse.from_domain(items, total=total, limit=page_limit)


@router.post(
    "/characters/{character_id}/album/transfer",
    response_model=CharacterResponse,
)
async def transfer_from_stage(
    character_id: str,
    payload: TransferFromStageRequest,
    container: ServiceContainer = Depends(get_container),
    _owned_character_id: str = Depends(ensure_owned_character_id),
) -> CharacterResponse:
    """Move a stage image into the album (stage loses the slot)."""
    try:
        updated, _item = await container.album_service.transfer_from_stage(
            character_id=character_id, url=payload.url,
        )
    except AlbumCharacterMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc
    except StageImageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc
    except AlbumManagedError as exc:
        # EC2-C: the character exists and is the caller's own — a 404 here
        # would be a lie, not an anti-enumeration measure. Mirrors
        # CharacterCardManagedError's "exists, wrong kind, refuse" 403.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This character's stage art is managed by its licensor "
                "and cannot be moved off the carousel"
            ),
        ) from exc
    return CharacterResponse.from_domain(updated)


@router.post(
    "/album/{item_id}/promote",
    response_model=CharacterResponse,
)
async def promote_to_stage(
    item_id: str,
    container: ServiceContainer = Depends(get_container),
    current_user_id: str = Depends(get_current_user_id),
) -> CharacterResponse:
    """Move an album entry back onto the stage carousel."""
    await _ensure_album_item_owner(
        item_id=item_id,
        current_user_id=current_user_id,
        container=container,
    )
    try:
        updated = await container.album_service.promote_to_stage(item_id)
    except AlbumItemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc
    except AlbumCharacterMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc
    except StageFullError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc),
        ) from exc
    except AlbumManagedError as exc:
        # EC2-C: same 403 "exists, wrong kind, refuse" shape as
        # CharacterCardManagedError / the transfer endpoint above.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This character's stage art is managed by its licensor "
                "and cannot be changed from the album"
            ),
        ) from exc
    return CharacterResponse.from_domain(updated)


@router.delete(
    "/album/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_album_item(
    item_id: str,
    container: ServiceContainer = Depends(get_container),
    current_user_id: str = Depends(get_current_user_id),
) -> Response:
    await _ensure_album_item_owner(
        item_id=item_id,
        current_user_id=current_user_id,
        container=container,
    )
    try:
        await container.album_service.delete(item_id)
    except AlbumItemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router", "AlbumItemResponse"]


async def _ensure_album_item_owner(
    *,
    item_id: str,
    current_user_id: str,
    container: ServiceContainer,
) -> None:
    repository = getattr(container, "album_repository", None)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="album repository not wired",
        )
    item = await repository.get(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album item not found",
        )
    await ensure_character_id_owned_by_user(
        item.character_id,
        current_user_id,
        container,
    )
