"""Bounded file-to-object-storage uploads.

Large backup artifacts are assembled in a temporary file so the archive can
be encrypted before any byte leaves the process. This helper keeps the final
transfer bounded too: adapters that expose the optional ``put_stream``
capability receive one file chunk at a time, while older adapters retain the
``put_bytes`` compatibility path.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from pathlib import Path

from kokoro_link.contracts.object_storage import (
    DEFAULT_STREAM_CHUNK_BYTES,
    ObjectStoragePort,
    StoredObject,
)


async def put_file(
    object_storage: ObjectStoragePort,
    file_path: Path,
    *,
    object_key: str,
    content_type: str,
    metadata: Mapping[str, str] | None = None,
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> StoredObject:
    """Upload ``file_path`` through the best capability available.

    ``put_stream`` is intentionally discovered at runtime: the core storage
    port remains backwards-compatible with small-object adapters and test
    doubles that predate the streaming capability.
    """
    put_stream = getattr(object_storage, "put_stream", None)
    if callable(put_stream):
        chunks = iter_file_chunks(file_path, chunk_size=chunk_size)
        try:
            return await put_stream(
                object_key=object_key,
                chunks=chunks,
                content_type=content_type,
                metadata=metadata,
            )
        finally:
            close = getattr(chunks, "aclose", None)
            if callable(close):
                await close()

    # Compatibility fallback for adapters without ``put_stream``. The hosted
    # HTTP and local storage adapters both implement the streaming path, so
    # this branch is limited to legacy/custom adapters and small objects.
    content = await asyncio.to_thread(file_path.read_bytes)
    return await object_storage.put_bytes(
        object_key=object_key,
        content=content,
        content_type=content_type,
        metadata=metadata,
    )


async def iter_file_chunks(
    file_path: Path,
    *,
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> AsyncIterator[bytes]:
    """Yield a file in bounded chunks without blocking the event loop."""
    step = max(1, int(chunk_size))
    with file_path.open("rb") as source:
        while True:
            chunk = await asyncio.to_thread(source.read, step)
            if not chunk:
                return
            yield chunk
