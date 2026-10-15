from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

APP_NAME = "Yuralume Core"
API_VERSION = "v1"
PACKAGE_NAME = "yuralume"
UNKNOWN_VERSION = "0.0.0"
BUILD_METADATA_PATH = Path(__file__).with_name("build_metadata.json")
MAX_BUILD_METADATA_BYTES = 4096
METADATA_FIELDS = ("image_tag", "commit_sha", "built_at", "source_digest")
METADATA_FILE_STATUSES = frozenset({
    "missing", "read_error", "too_large", "invalid_json", "invalid_schema", "valid",
})


def _metadata_value(key: str, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 128:
        return None
    if key == "commit_sha":
        return value.lower() if re.fullmatch(r"[0-9a-fA-F]{7,64}", value) else None
    if key == "source_digest":
        return value if re.fullmatch(r"sha256:[0-9a-f]{64}", value) else None
    if key == "built_at":
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value if parsed.utcoffset() is not None else None
        except ValueError:
            return None
    return value if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.:/@+-]{0,127}", value) else None


def _image_metadata() -> tuple[dict[str, str], str, int | None]:
    try:
        with BUILD_METADATA_PATH.open("rb") as handle:
            raw = handle.read(MAX_BUILD_METADATA_BYTES + 1)
    except FileNotFoundError:
        return {}, "missing", None
    except OSError:
        return {}, "read_error", None
    if len(raw) > MAX_BUILD_METADATA_BYTES:
        return {}, "too_large", len(raw)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return {}, "invalid_json", len(raw)
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
    ):
        return {}, "invalid_schema", len(raw)
    return {
        key: validated
        for key in METADATA_FIELDS
        if (validated := _metadata_value(key, data.get(key))) is not None
    }, "valid", len(raw)


@dataclass(frozen=True, slots=True)
class BuildMetadata:
    image_tag: str | None
    commit_sha: str | None
    built_at: str | None
    source_digest: str | None = None
    metadata_source: str = "unknown"
    missing_fields: tuple[str, ...] = ()
    metadata_file_status: str = "missing"
    metadata_file_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class BuildInfo:
    name: str
    version: str
    api_version: str
    build: BuildMetadata


def get_build_info(environ: Mapping[str, str] | None = None) -> BuildInfo:
    env = environ if environ is not None else os.environ
    app_version = _env_value(env, "YURALUME_APP_VERSION") or _project_version()
    image, metadata_file_status, metadata_file_bytes = _image_metadata()
    runtime = {
        "image_tag": (
            _metadata_value("image_tag", _env_value(env, "YURALUME_BUILD_TAG"))
            or _metadata_value("image_tag", _env_value(env, "YURALUME_IMAGE_TAG"))
        ),
        "commit_sha": _metadata_value("commit_sha", _env_value(env, "YURALUME_BUILD_SHA")),
        "built_at": _metadata_value("built_at", _env_value(env, "YURALUME_BUILD_TIME")),
    }
    fields = {key: runtime.get(key) or image.get(key) for key in METADATA_FIELDS}
    uses_runtime = any(runtime.values())
    uses_image = any(image.get(key) and not runtime.get(key) for key in fields)
    if uses_runtime and uses_image:
        source = "environment+image"
    elif uses_runtime:
        source = "environment"
    else:
        source = "image" if uses_image else "unknown"
    return BuildInfo(
        name=APP_NAME,
        version=app_version,
        api_version=API_VERSION,
        build=BuildMetadata(
            **fields,
            metadata_source=source,
            missing_fields=tuple(key for key in METADATA_FIELDS if not fields[key]),
            metadata_file_status=metadata_file_status,
            metadata_file_bytes=metadata_file_bytes,
        ),
    )


def _env_value(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _project_version() -> str:
    try:
        return package_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return _pyproject_version() or UNKNOWN_VERSION


def _pyproject_version() -> str | None:
    pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError:
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    if not isinstance(version, str):
        return None
    return version.strip() or None
