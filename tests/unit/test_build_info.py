from __future__ import annotations

import json
from pathlib import Path

import pytest

from kokoro_link.infrastructure import build_info
from kokoro_link.infrastructure.build_info import get_build_info

PRODUCTION_METADATA_PATH = build_info.BUILD_METADATA_PATH


@pytest.fixture(autouse=True)
def isolated_build_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(build_info, "BUILD_METADATA_PATH", tmp_path / "build_metadata.json")


def test_build_info_reads_project_version() -> None:
    info = get_build_info({})

    assert info.name == "Yuralume Core"
    assert info.version
    assert info.api_version == "v1"
    assert info.build.image_tag is None
    assert info.build.commit_sha is None
    assert info.build.built_at is None
    assert info.build.metadata_file_status == "missing"
    assert info.build.metadata_file_bytes is None


def test_build_info_uses_runtime_build_metadata() -> None:
    info = get_build_info(
        {
            "YURALUME_BUILD_TAG": "v0.2.0",
            "YURALUME_BUILD_SHA": "abcdef123456",
            "YURALUME_BUILD_TIME": "2026-06-14T12:00:00Z",
        },
    )

    assert info.build.image_tag == "v0.2.0"
    assert info.build.commit_sha == "abcdef123456"
    assert info.build.built_at == "2026-06-14T12:00:00Z"


def test_build_info_falls_back_to_operator_image_tag() -> None:
    info = get_build_info({"YURALUME_IMAGE_TAG": "sha-deadbeef"})

    assert info.build.image_tag == "sha-deadbeef"


def test_image_file_fallback_and_environment_override() -> None:
    build_info.BUILD_METADATA_PATH.write_text(json.dumps({
        "schema_version": 1, "image_tag": "local", "commit_sha": "a" * 40,
        "built_at": "2026-10-15T12:00:00Z", "source_digest": "sha256:" + "b" * 64,
    }), encoding="utf-8")
    fallback = get_build_info({}).build
    assert fallback.commit_sha == "a" * 40
    assert fallback.built_at == "2026-10-15T12:00:00Z"
    assert fallback.metadata_source == "image"
    assert fallback.missing_fields == ()
    assert fallback.metadata_file_status == "valid"
    assert fallback.metadata_file_bytes is not None
    overridden = get_build_info({"YURALUME_BUILD_SHA": "c" * 40, "YURALUME_BUILD_TAG": "", "YURALUME_BUILD_TIME": "bad"}).build
    assert overridden.commit_sha == "c" * 40
    assert overridden.image_tag == "local"
    assert overridden.built_at == fallback.built_at
    assert overridden.source_digest == fallback.source_digest
    assert overridden.metadata_source == "environment+image"


@pytest.mark.parametrize(
    ("raw", "expected_status"),
    [
        (b"not json", "invalid_json"),
        (b"[]", "invalid_schema"),
        (b'{"schema_version":true}', "invalid_schema"),
        (b'{"schema_version":2}', "invalid_schema"),
        (b"\xff", "invalid_json"),
        (b" " * 4097, "too_large"),
    ],
    ids=["malformed", "array", "boolean-version", "future-schema", "encoding", "oversized"],
)
def test_invalid_bounded_image_file_does_not_break_startup(raw: bytes, expected_status: str) -> None:
    build_info.BUILD_METADATA_PATH.write_bytes(raw)
    result = get_build_info({}).build
    assert result.commit_sha is None
    assert result.metadata_source == "unknown"
    assert result.metadata_file_status == expected_status
    assert result.metadata_file_bytes == min(len(raw), build_info.MAX_BUILD_METADATA_BYTES + 1)
    assert "commit_sha" in result.missing_fields


def test_invalid_image_fields_and_runtime_values_are_not_published() -> None:
    build_info.BUILD_METADATA_PATH.write_text(json.dumps({
        "schema_version": 1, "image_tag": "x" * 129, "commit_sha": ["secret"],
        "built_at": "2026-10-15", "source_digest": "looks-like-a-commit",
        "ignored": "value",
    }), encoding="utf-8")
    result = get_build_info({"YURALUME_BUILD_SHA": "not-a-sha", "YURALUME_BUILD_TAG": "line\nbreak"}).build
    assert result.metadata_source == "unknown"
    assert len(result.missing_fields) == 4


def test_production_metadata_path_is_fixed_beside_module() -> None:
    assert PRODUCTION_METADATA_PATH == Path(build_info.__file__).with_name("build_metadata.json")
