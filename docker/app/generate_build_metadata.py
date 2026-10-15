"""Generate image metadata from explicitly copied application artifacts, never Git.

The digest identifies these artifacts; it is deliberately not a commit SHA.
No environment files, uploads, Git data, symlinks or arbitrary context roots are read.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT_FILES = ("pyproject.toml", "uv.lock", "README.md", "alembic.ini", "usage-prices.openai.json")
SOURCE_DIRS = ("src", "alembic")
SUFFIXES = {".py", ".json", ".toml", ".lock", ".md", ".ini", ".mako", ".js", ".css", ".html", ".svg", ".txt"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", "uploads", "temp", ".venv"}
OUTPUT = Path("src/kokoro_link/infrastructure/build_metadata.json")


def source_digest(root: Path) -> str:
    paths = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for name in SOURCE_DIRS:
        directory = root / name
        if directory.is_symlink():
            continue
        if directory.exists():
            for parent, dirs, files in os.walk(directory, followlinks=False):
                base = Path(parent)
                dirs[:] = [item for item in dirs if item not in SKIP_DIRS and not (base / item).is_symlink()]
                paths.extend(base / item for item in files if Path(item).suffix in SUFFIXES and not item.startswith(".env"))
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink() or path.relative_to(root) == OUTPUT:
            continue
        name = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        content_digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                content_digest.update(chunk)
        digest.update(content_digest.digest())
    return "sha256:" + digest.hexdigest()


def generate(root: Path) -> dict[str, str | int | None]:
    # Import only the dependency-free metadata module from the copied source.
    import importlib.util

    spec = importlib.util.spec_from_file_location("image_build_info", root / "src/kokoro_link/infrastructure/build_info.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    validate = module._metadata_value
    return {
        "schema_version": 1,
        "image_tag": validate("image_tag", os.environ.get("YURALUME_BUILD_TAG")),
        "commit_sha": validate("commit_sha", os.environ.get("YURALUME_BUILD_SHA")),
        "built_at": validate("built_at", os.environ.get("YURALUME_BUILD_TIME")) or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_digest": source_digest(root),
    }


if __name__ == "__main__":
    root = Path("/app")
    (root / OUTPUT).write_text(json.dumps(generate(root), sort_keys=True) + "\n", encoding="utf-8")
