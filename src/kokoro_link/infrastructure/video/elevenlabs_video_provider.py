"""Native ElevenLabs video adapter for the hosted Veo 3.1 models."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from urllib.parse import quote, urljoin, urlparse
from uuid import uuid4

import httpx

from kokoro_link.contracts.provider_probe import (
    ProbeCheck,
    probe_http_client,
    probe_http_error_detail,
    run_probe_check,
)
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


DEFAULT_BASE_URL = "https://api.elevenlabs.io"
VIDEO_PATH = "/v1/flows/video"

ASPECT_TO_RATIO: dict[str, str] = {
    "portrait": "9:16",
    "landscape": "16:9",
    # Veo does not expose a square output, so square requests use landscape.
    "square": "16:9",
}

_IN_PROGRESS_STATUSES = frozenset({"pending", "generating"})


class ElevenLabsVideoProvider(VideoProviderPort):
    """Generate a short clip through ElevenLabs' asynchronous Flows API.

    ElevenLabs hosts Google's Veo 3.1 models behind ``/v1/flows/video``.
    Unlike OpenAI-compatible video endpoints, the API uses ``model_id`` and
    returns a signed ``content_url`` after polling the generation id.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str,
        model: str = "veo-3.1-generate-001",
        timeout_seconds: float = 1800.0,
        poll_interval_seconds: float = 10.0,
    ) -> None:
        normalized_base = base_url or DEFAULT_BASE_URL
        if not normalized_base.strip():
            raise ValueError("ElevenLabs video base_url is required")
        if not api_key.strip():
            raise ValueError("ElevenLabs video api_key is required")
        if not model.strip():
            raise ValueError("ElevenLabs video model is required")
        self._base_url = normalized_base.rstrip("/")
        self._api_key = api_key
        self._model = model
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
        # The port accepts image-to-video references, but forwarding one here
        # would require uploading Yuralume's asset to ElevenLabs first. Keep
        # this native text-to-video path deterministic until that asset bridge
        # exists, as the other hosted adapters currently do.
        del first_frame_url
        prompt = _build_prompt(
            character=character,
            positive=positive,
            recent_dialogue=recent_dialogue,
            use_runtime_state=use_runtime_state,
        )
        if not prompt.strip():
            raise VideoGenerationError("ElevenLabs video prompt is empty")
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
            raise VideoTimeoutError("ElevenLabs video API timed out") from exc
        except VideoGenerationError:
            raise
        except Exception as exc:
            raise VideoGenerationError(str(exc)) from exc

    async def probe_video(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float | None = None,
    ) -> list[ProbeCheck]:
        """Run a cheap authenticated check without creating a video job."""

        async def check() -> tuple[bool, str]:
            async with probe_http_client(
                timeout_seconds or self._timeout,
                transport,
            ) as client:
                response = await client.get(
                    f"{self._base_url}/v1/user",
                    headers={
                        "xi-api-key": self._api_key,
                        "Accept": "application/json",
                    },
                )
            if response.status_code >= 400:
                return False, (
                    "ElevenLabs account check: "
                    f"{probe_http_error_detail(response)}"
                )
            try:
                body = response.json()
            except ValueError:
                return False, "ElevenLabs account check returned non-JSON"
            if not isinstance(body, Mapping):
                return False, "ElevenLabs account check returned a non-object"
            return True, (
                "authenticated account endpoint reachable; video generation "
                f"not submitted (model {self._model!r})"
            )

        return [await run_probe_check("reachability", check)]

    async def _submit(
        self,
        client: httpx.AsyncClient,
        *,
        prompt: str,
        aspect: str,
        length_frames: int,
    ) -> Mapping:
        response = await client.post(
            f"{self._base_url}{VIDEO_PATH}",
            headers=self._headers(),
            json=self._payload(
                prompt=prompt,
                aspect=aspect,
                length_frames=length_frames,
            ),
        )
        return _json_or_raise(response, "ElevenLabs video")

    def _payload(
        self,
        *,
        prompt: str,
        aspect: str,
        length_frames: int,
    ) -> dict[str, str | int | bool]:
        return {
            "model_id": self._model,
            "prompt": prompt,
            "duration_secs": _duration_seconds(length_frames),
            "aspect_ratio": ASPECT_TO_RATIO.get(
                aspect,
                ASPECT_TO_RATIO["portrait"],
            ),
            "resolution": "720p",
            "generate_audio": True,
        }

    async def _wait_for_video(
        self,
        client: httpx.AsyncClient,
        *,
        submitted: Mapping,
        deadline: float,
    ) -> bytes:
        status = submitted
        generation_id = _generation_id(status)
        if not generation_id:
            raise VideoGenerationError(
                "ElevenLabs video API returned no generation id",
            )
        while True:
            state = _status(status)
            if state == "completed":
                content_url = _content_url(status)
                if not content_url:
                    raise VideoNoOutputError(
                        "ElevenLabs video completed without a content URL",
                    )
                return await self._download_content(client, content_url)
            if state == "failed":
                raise VideoGenerationError(_failure_message(status))
            if state not in _IN_PROGRESS_STATUSES:
                raise VideoGenerationError(
                    f"ElevenLabs video returned unsupported status {state!r}",
                )
            if time.monotonic() >= deadline:
                raise VideoTimeoutError("ElevenLabs video API timed out")
            await asyncio.sleep(
                min(self._poll_interval, max(0.0, deadline - time.monotonic())),
            )
            status = await self._poll(client, generation_id)

    async def _poll(
        self,
        client: httpx.AsyncClient,
        generation_id: str,
    ) -> Mapping:
        encoded_id = quote(generation_id, safe="")
        response = await client.get(
            f"{self._base_url}{VIDEO_PATH}/{encoded_id}",
            headers=self._headers(),
        )
        return _json_or_raise(response, "ElevenLabs video generation")

    async def _download_content(
        self,
        client: httpx.AsyncClient,
        content_url: str,
    ) -> bytes:
        resolved = content_url if content_url.startswith(
            ("http://", "https://"),
        ) else urljoin(f"{self._base_url}/", content_url.lstrip("/"))
        # The normal response is a signed storage URL. Do not leak the API
        # key to a third-party host; only send it for same-origin downloads.
        headers = self._headers() if _same_origin(resolved, self._base_url) else {}
        response = await client.get(
            resolved,
            headers=headers,
            follow_redirects=True,
        )
        if not response.is_success:
            raise VideoGenerationError(
                "ElevenLabs video download failed: "
                f"HTTP {response.status_code}",
            )
        return response.content

    def _headers(self) -> dict[str, str]:
        return {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Request-Id": f"elevenlabs-video-{uuid4().hex}",
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
            emotion = getattr(state, "emotion", "")
            if emotion:
                parts.append(f"Current emotion: {emotion}")
            intent = getattr(state, "current_intent", None)
            if intent:
                parts.append(f"Current intent: {intent}")
    if positive.strip():
        parts.append(f"Scene: {positive.strip()}")
    if recent_dialogue.strip():
        parts.append(f"Recent dialogue context: {recent_dialogue.strip()}")
    return "\n".join(part for part in parts if part.strip())


def _duration_seconds(length_frames: int) -> int:
    seconds = round(max(1, int(length_frames or 81)) / 16)
    if seconds <= 4:
        return 4
    if seconds <= 6:
        return 6
    return 8


def _generation_id(data: Mapping) -> str:
    value = data.get("id")
    return value if isinstance(value, str) else ""


def _status(data: Mapping) -> str:
    value = data.get("status")
    return value.strip().lower() if isinstance(value, str) else ""


def _content_url(data: Mapping) -> str:
    value = data.get("content_url")
    return value if isinstance(value, str) and value.strip() else ""


def _failure_message(data: Mapping) -> str:
    reason = data.get("failure_reason")
    message = data.get("error_message")
    detail = message if isinstance(message, str) and message.strip() else reason
    if isinstance(detail, str) and detail.strip():
        return f"ElevenLabs video generation failed: {detail.strip()[:500]}"
    return "ElevenLabs video generation failed"


def _same_origin(left: str, right: str) -> bool:
    left_url = urlparse(left)
    right_url = urlparse(right)
    return (
        left_url.scheme == right_url.scheme
        and left_url.netloc == right_url.netloc
    )


def _json_or_raise(response: httpx.Response, label: str) -> Mapping:
    if response.status_code >= 400:
        raise VideoGenerationError(
            f"{label} API error {response.status_code}: {response.text[:500]}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise VideoGenerationError(f"{label} API returned non-JSON") from exc
    if not isinstance(payload, Mapping):
        raise VideoGenerationError(f"{label} API returned non-object JSON")
    return payload
