"""OpenAI-compatible asynchronous video adapters.

This module deliberately models protocol families rather than individual
vendors.  A provider must opt into one of the documented request and polling
contracts below; a base URL alone is not enough to make a video API compatible.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import time
from collections.abc import Mapping
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx

from kokoro_link.contracts.video_provider import (
    VideoGenerationError,
    VideoNoOutputError,
    VideoProviderPort,
    VideoTimeoutError,
)
from kokoro_link.infrastructure.prompt.character_identity import (
    render_character_visual_identity_lines,
)
from kokoro_link.infrastructure.prompt.visual_subject import (
    render_character_visual_subject_lines,
)


OPENAI_VIDEOS_PROTOCOL = "openai_videos"
"""OpenAI Videos API: ``POST /videos`` then ``GET /videos/{id}``."""

GENERATIONS_POLLING_PROTOCOL = "generations_polling"
"""Common ``/videos/generations`` request-id polling contract."""

SUPPORTED_PROTOCOLS = frozenset({
    OPENAI_VIDEOS_PROTOCOL,
    GENERATIONS_POLLING_PROTOCOL,
})

_ASPECT_TO_OPENAI_SIZE = {
    "portrait": "720x1280",
    "landscape": "1280x720",
    # The OpenAI Videos API has no square output. Keep the established
    # video-port fallback behaviour by using portrait rather than inventing
    # an unsupported size.
    "square": "720x1280",
}
_ASPECT_TO_RATIO = {
    "portrait": "9:16",
    "landscape": "16:9",
    "square": "1:1",
}
_SUCCEEDED_STATUSES = frozenset({"completed", "done", "succeeded", "success"})
_FAILED_STATUSES = frozenset({"failed", "expired", "cancelled", "canceled", "error"})


class OpenAICompatibleVideoProvider(VideoProviderPort):
    """Generate a clip through a supported OpenAI-lineage video protocol.

    ``openai_videos`` follows OpenAI's Videos API exactly: submit a video job,
    poll it, then retrieve ``/videos/{id}/content``.  ``generations_polling``
    handles the widely-used request-id flow: submit ``/videos/generations``,
    poll ``/videos/{request_id}``, and download the completed artifact URL.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        protocol: str = OPENAI_VIDEOS_PROTOCOL,
        timeout_seconds: float = 1800.0,
        poll_interval_seconds: float = 10.0,
    ) -> None:
        if not base_url.strip():
            raise ValueError("OpenAI-compatible video base_url is required")
        if not api_key.strip():
            raise ValueError("OpenAI-compatible video api_key is required")
        if not model.strip():
            raise ValueError("OpenAI-compatible video model is required")
        normalized_protocol = protocol.strip().lower() or OPENAI_VIDEOS_PROTOCOL
        if normalized_protocol not in SUPPORTED_PROTOCOLS:
            raise ValueError(
                "unsupported OpenAI-compatible video protocol "
                f"{normalized_protocol!r}; choose one of "
                f"{', '.join(sorted(SUPPORTED_PROTOCOLS))}",
            )
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._protocol = normalized_protocol
        self._timeout = timeout_seconds
        self._poll_interval = max(0.01, poll_interval_seconds)

    async def generate(
        self,
        *,
        character,
        positive: str,
        aspect: str = "portrait",
        length_frames: int = 81,
        recent_dialogue: str = "",
        use_runtime_state: bool = True,
        first_frame_url: str | None = None,
    ) -> bytes:
        # Image references need multipart upload or provider-specific asset
        # handling. They remain intentionally out of this text-to-video path.
        del first_frame_url
        prompt = _build_prompt(
            character=character,
            positive=positive,
            recent_dialogue=recent_dialogue,
            use_runtime_state=use_runtime_state,
        )
        if not prompt.strip():
            raise VideoGenerationError("video prompt is empty")
        deadline = time.monotonic() + self._timeout
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                submitted = await self._submit(
                    client,
                    prompt=prompt,
                    aspect=aspect,
                    length_frames=length_frames,
                )
                return await self._wait_for_video(
                    client,
                    submitted=submitted,
                    deadline=deadline,
                )
        except httpx.TimeoutException as exc:
            raise VideoTimeoutError("OpenAI-compatible video API timed out") from exc
        except VideoGenerationError:
            raise
        except Exception as exc:
            raise VideoGenerationError(str(exc)) from exc

    async def _submit(
        self,
        client: httpx.AsyncClient,
        *,
        prompt: str,
        aspect: str,
        length_frames: int,
    ) -> Mapping:
        response = await client.post(
            f"{self._base_url}{self._submit_path}",
            headers=self._headers(),
            json=self._request_payload(
                prompt=prompt,
                aspect=aspect,
                length_frames=length_frames,
            ),
        )
        return _json_or_raise(response, "OpenAI-compatible video")

    @property
    def _submit_path(self) -> str:
        if self._protocol == OPENAI_VIDEOS_PROTOCOL:
            return "/videos"
        return "/videos/generations"

    def _request_payload(
        self,
        *,
        prompt: str,
        aspect: str,
        length_frames: int,
    ) -> dict[str, str | int]:
        if self._protocol == OPENAI_VIDEOS_PROTOCOL:
            return {
                "model": self._model,
                "prompt": prompt,
                "seconds": _openai_seconds(length_frames),
                "size": _ASPECT_TO_OPENAI_SIZE.get(
                    aspect,
                    _ASPECT_TO_OPENAI_SIZE["portrait"],
                ),
            }
        return {
            "model": self._model,
            "prompt": prompt,
            "duration": _duration_seconds(length_frames),
            "aspect_ratio": _ASPECT_TO_RATIO.get(
                aspect,
                _ASPECT_TO_RATIO["portrait"],
            ),
            "resolution": "720p",
        }

    async def _wait_for_video(
        self,
        client: httpx.AsyncClient,
        *,
        submitted: Mapping,
        deadline: float,
    ) -> bytes:
        status = submitted
        job_id = _job_id(submitted)
        while True:
            artifact = _artifact(status)
            if artifact is not None:
                return await self._download_artifact(client, artifact)

            state = _status(status)
            if state in _FAILED_STATUSES:
                raise VideoGenerationError(_job_failure_message(status, state))
            if state in _SUCCEEDED_STATUSES:
                if self._protocol == OPENAI_VIDEOS_PROTOCOL and job_id:
                    return await self._download_openai_content(client, job_id)
                raise VideoNoOutputError(
                    "OpenAI-compatible video job completed without a video artifact",
                )
            if not job_id:
                raise VideoNoOutputError(
                    "OpenAI-compatible video API returned neither an artifact nor a job id",
                )
            if time.monotonic() >= deadline:
                raise VideoTimeoutError("OpenAI-compatible video API timed out")
            await asyncio.sleep(min(self._poll_interval, max(0.0, deadline - time.monotonic())))
            status = await self._poll(client, job_id)

    async def _poll(
        self,
        client: httpx.AsyncClient,
        job_id: str,
    ) -> Mapping:
        response = await client.get(
            f"{self._base_url}/videos/{job_id}",
            headers=self._headers(),
        )
        return _json_or_raise(response, "OpenAI-compatible video job")

    async def _download_openai_content(
        self,
        client: httpx.AsyncClient,
        job_id: str,
    ) -> bytes:
        response = await client.get(
            f"{self._base_url}/videos/{job_id}/content",
            headers=self._headers(),
            follow_redirects=True,
        )
        if response.is_success:
            return response.content
        raise VideoGenerationError(
            "OpenAI-compatible video content download failed: "
            f"HTTP {response.status_code}",
        )

    async def _download_artifact(
        self,
        client: httpx.AsyncClient,
        artifact: tuple[str, str],
    ) -> bytes:
        kind, value = artifact
        if kind == "base64":
            try:
                return base64.b64decode(value, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise VideoGenerationError(
                    "OpenAI-compatible video returned invalid base64 data",
                ) from exc
        resolved = value if value.startswith(("http://", "https://")) else urljoin(
            f"{self._base_url}/",
            value,
        )
        response = await client.get(
            resolved,
            headers=self._headers() if _same_origin(resolved, self._base_url) else {},
            follow_redirects=True,
        )
        if response.is_success:
            return response.content
        raise VideoGenerationError(
            "OpenAI-compatible video artifact download from "
            f"{_origin(resolved)} failed: HTTP {response.status_code}",
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Request-Id": f"vid-{uuid4().hex}",
        }


def _build_prompt(
    *,
    character,
    positive: str,
    recent_dialogue: str,
    use_runtime_state: bool,
) -> str:
    parts = [
        f"Character: {character.name}",
        f"Appearance: {getattr(character, 'appearance', '')}",
        *render_character_visual_identity_lines(character),
        *render_character_visual_subject_lines(character),
    ]
    if use_runtime_state:
        state = getattr(character, "state", None)
        if state is not None:
            parts.append(f"Current emotion: {getattr(state, 'emotion', '')}")
            intent = getattr(state, "current_intent", None)
            if intent:
                parts.append(f"Current intent: {intent}")
    if positive.strip():
        parts.append(f"Scene: {positive.strip()}")
    if recent_dialogue.strip():
        parts.append(f"Recent dialogue context: {recent_dialogue.strip()}")
    return "\n".join(part for part in parts if part.strip())


def _duration_seconds(length_frames: int) -> int:
    return max(1, round(max(1, int(length_frames or 81)) / 16))


def _openai_seconds(length_frames: int) -> str:
    """Map the port's arbitrary duration to the Videos API's 4/8/12 choices."""

    duration = _duration_seconds(length_frames)
    if duration <= 4:
        return "4"
    if duration <= 8:
        return "8"
    return "12"


def _job_id(data: Mapping) -> str:
    for key in ("id", "request_id", "job_id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _status(data: Mapping) -> str:
    value = data.get("status")
    return value.strip().lower() if isinstance(value, str) else ""


def _artifact(data: Mapping) -> tuple[str, str] | None:
    candidates: list[Mapping] = [data]
    for key in ("video", "output"):
        value = data.get(key)
        if isinstance(value, Mapping):
            candidates.append(value)
    for key in ("data", "artifacts", "videos", "generated_videos"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, Mapping))

    for candidate in candidates:
        for key in ("b64_json", "b64", "video_bytes", "videoBytes"):
            value = candidate.get(key)
            if isinstance(value, str) and value:
                return "base64", value
        for key in ("url", "video_url", "videoUrl", "uri"):
            value = candidate.get(key)
            if isinstance(value, str) and value:
                return "url", value
    return None


def _job_failure_message(data: Mapping, state: str) -> str:
    error = data.get("error")
    if isinstance(error, Mapping):
        detail = error.get("message") or error.get("code")
    else:
        detail = error
    if isinstance(detail, str) and detail.strip():
        return f"OpenAI-compatible video job {state}: {detail.strip()[:500]}"
    return f"OpenAI-compatible video job {state}"


def _same_origin(left: str, right: str) -> bool:
    left_url = urlparse(left)
    right_url = urlparse(right)
    return left_url.scheme == right_url.scheme and left_url.netloc == right_url.netloc


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "configured video endpoint"


def _json_or_raise(response: httpx.Response, label: str) -> Mapping:
    if response.status_code >= 400:
        raise VideoGenerationError(
            f"{label} API error {response.status_code}: {response.text[:500]}",
        )
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise VideoGenerationError(f"{label} API returned non-object JSON")
    return payload
