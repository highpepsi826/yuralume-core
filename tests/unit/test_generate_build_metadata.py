from __future__ import annotations

import importlib.util
import json
import shutil
from datetime import datetime
from pathlib import Path

from kokoro_link.infrastructure import build_info

HELPER_PATH = Path(__file__).resolve().parents[2] / "docker/app/generate_build_metadata.py"
spec = importlib.util.spec_from_file_location("generate_build_metadata", HELPER_PATH)
assert spec is not None and spec.loader is not None
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def test_source_digest_is_deterministic_and_ignores_private_non_sources(tmp_path: Path) -> None:
    source = tmp_path / "src/kokoro_link"
    source.mkdir(parents=True)
    code = source / "app.py"
    code.write_text("print('hello')\n", encoding="utf-8")
    before = helper.source_digest(tmp_path)
    for name in (".git/config", "temp/private.py", "uploads/private.json", "src/.env", "src/__pycache__/private.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private", encoding="utf-8")
    output = tmp_path / helper.OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("previous generated file", encoding="utf-8")
    assert helper.source_digest(tmp_path) == before
    code.write_text("print('changed')\n", encoding="utf-8")
    assert helper.source_digest(tmp_path) != before


def test_no_git_build_emits_time_and_digest_without_inventing_sha(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "src/kokoro_link/infrastructure/build_info.py"
    destination.parent.mkdir(parents=True)
    shutil.copyfile(build_info.__file__, destination)
    for key in ("YURALUME_BUILD_SHA", "YURALUME_BUILD_TIME", "YURALUME_BUILD_TAG"):
        monkeypatch.delenv(key, raising=False)
    generated = helper.generate(tmp_path)
    assert generated["commit_sha"] is None
    assert generated["image_tag"] is None
    assert datetime.fromisoformat(generated["built_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    assert generated["source_digest"].startswith("sha256:")
    metadata_path = destination.with_name("build_metadata.json")
    metadata_path.write_text(json.dumps(generated), encoding="utf-8")
    monkeypatch.setattr(build_info, "BUILD_METADATA_PATH", metadata_path)
    consumed = build_info.get_build_info({}).build
    assert consumed.source_digest == generated["source_digest"]
    assert consumed.built_at == generated["built_at"]
    assert consumed.commit_sha is None
    assert consumed.metadata_source == "image"
    monkeypatch.setenv("YURALUME_BUILD_SHA", "a" * 40)
    monkeypatch.setenv("YURALUME_BUILD_TIME", "2026-10-15T00:00:00Z")
    monkeypatch.setenv("YURALUME_BUILD_TAG", "local")
    explicit = helper.generate(tmp_path)
    assert explicit["commit_sha"] == "a" * 40
    assert explicit["built_at"] == "2026-10-15T00:00:00Z"
    assert explicit["image_tag"] == "local"
