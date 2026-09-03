from __future__ import annotations

from pathlib import Path

import pytest

from kokoro_link.application.services.object_storage_upload import put_file
from kokoro_link.contracts.object_storage import StoredObject


class _StreamRecorder:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    async def put_stream(self, **kwargs) -> StoredObject:  # noqa: ANN003
        async for chunk in kwargs["chunks"]:
            self.chunks.append(chunk)
        return StoredObject(
            object_key=kwargs["object_key"],
            url="/v1/public/" + kwargs["object_key"],
            content_type=kwargs["content_type"],
            size_bytes=sum(map(len, self.chunks)),
        )


class _BytesOnlyRecorder:
    def __init__(self) -> None:
        self.content: bytes | None = None

    async def put_bytes(self, **kwargs) -> StoredObject:  # noqa: ANN003
        self.content = kwargs["content"]
        return StoredObject(
            object_key=kwargs["object_key"],
            url="/v1/public/" + kwargs["object_key"],
            content_type=kwargs["content_type"],
            size_bytes=len(self.content),
        )


@pytest.mark.asyncio
async def test_put_file_prefers_stream_and_bounds_file_chunks(tmp_path: Path) -> None:
    path = tmp_path / "artifact.lumebackup"
    path.write_bytes(b"0123456789")
    storage = _StreamRecorder()

    stored = await put_file(
        storage,  # type: ignore[arg-type]
        path,
        object_key="character-backups/u1/job.lumebackup",
        content_type="application/octet-stream",
        chunk_size=3,
    )

    assert stored.size_bytes == 10
    assert storage.chunks == [b"012", b"345", b"678", b"9"]


@pytest.mark.asyncio
async def test_put_file_falls_back_to_put_bytes_for_legacy_adapters(
    tmp_path: Path,
) -> None:
    path = tmp_path / "small.bin"
    path.write_bytes(b"legacy")
    storage = _BytesOnlyRecorder()

    stored = await put_file(
        storage,  # type: ignore[arg-type]
        path,
        object_key="characters/u1/small.bin",
        content_type="application/octet-stream",
    )

    assert stored.size_bytes == len(b"legacy")
    assert storage.content == b"legacy"
