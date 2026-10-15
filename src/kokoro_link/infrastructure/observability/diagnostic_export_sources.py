"""Bounded, column-allowlisted diagnostic projections of existing business data.

Never load payloads, prompts, content, arbitrary metadata, secrets or settings blobs.
Missing tables are isolated per source; this reader never runs migrations.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import JSON, and_, cast, func, or_, select

from kokoro_link.infrastructure.persistence.models import (
    BackgroundJobRow, BackgroundRuntimeLeaseRow, ChatTurnCommandRow,
    ChatTurnEffectRow, FeedPostRow, GenerationUsageEventRow,
    RuntimeProcessHeartbeatRow, PendingFeedVideoRow, ProviderConnectionRow,
)
from kokoro_link.infrastructure.observability.diagnostic_sources import factory_for, utc

MAX_ROWS = 500
QUERY_TIMEOUT = 5.0


async def projection(factory, row, fields, predicate, order, *, limit=MAX_ROWS, scope="selected_character_window"):
    started = datetime.now(timezone.utc).isoformat()
    if factory is None:
        return [], {"status": "unavailable", "reason": "database_source_not_available", "scope": scope}
    async def query():
        async with factory() as session:
            json_fields = ({"trace_id", "operation_id", "parent_operation_id", "job_id"}
                           if row is GenerationUsageEventRow else
                           {"build_source_digest", "build_time", "build_metadata_source",
                            "build_metadata_file_status", "build_metadata_file_bytes"} if row is RuntimeProcessHeartbeatRow else set())
            json_column = row.metadata_json if row is GenerationUsageEventRow else row.details_json if row is RuntimeProcessHeartbeatRow else None
            columns = [((func.json_extract(json_column, "$." + field) if session.bind.dialect.name == "sqlite"
                         else cast(json_column, JSON)[field].as_string()).label(field)
                        if field in json_fields
                        else getattr(row, field[4:]).is_not(None).label(field) if field.startswith("has_")
                        else getattr(row, field)) for field in fields]
            result = await session.execute(select(*columns)
                .where(predicate).order_by(order.desc()).limit(limit + 1))
            return result.mappings().all()
    try:
        rows = await asyncio.wait_for(query(), QUERY_TIMEOUT)
        values = [{k: utc(v).isoformat() if isinstance(v, datetime) else v for k, v in r.items()}
                  for r in rows[:limit]]
        return values, {"status": "partial" if len(rows) > limit else "complete", "scope": scope,
                        "row_count": len(values), "max_rows": limit, "truncated": len(rows) > limit,
                        "collected_at": started, "query_timeout_seconds": QUERY_TIMEOUT}
    except Exception as exc:
        return [], {"status": "unavailable", "reason": type(exc).__name__, "scope": scope,
                    "collected_at": started}


def overlaps(row, start, end, *end_fields):
    # Include work created before the window but active/updated/completed within it.
    return and_(row.created_at <= end, or_(row.created_at >= start,
                *(and_(getattr(row, field) >= start, getattr(row, field) <= end) for field in end_fields)))


async def read_additional_sources(factory, character_id, start, end):
    sources, coverage = {}, {}
    specs = (
        ("generation_events", GenerationUsageEventRow,
         "id request_id trace_id operation_id parent_operation_id job_id upstream_request_id turn_record_id conversation_id character_id capability feature_key source_surface routing_mode provider_id model_id profile_id latency_ms status error_code artifact_count output_bytes created_at completed_at",
         overlaps(GenerationUsageEventRow, start, end, "completed_at")),
        ("feed_posts", FeedPostRow, "id character_id kind source_kind source_ref_id has_image_url has_video_url created_at",
         and_(FeedPostRow.created_at >= start, FeedPostRow.created_at <= end)),
        ("commands", ChatTurnCommandRow,
         "turn_id character_id conversation_id state phase attempt_count max_attempts failure_code lease_owner lease_until created_at updated_at accepted_at last_heartbeat_at",
         overlaps(ChatTurnCommandRow, start, end, "updated_at", "last_heartbeat_at")),
        ("jobs", BackgroundJobRow,
         "id character_id kind status due_at attempt_count max_attempts lease_owner lease_until created_at updated_at claimed_at finished_at",
         overlaps(BackgroundJobRow, start, end, "updated_at", "finished_at")),
        ("pending_feed_videos", PendingFeedVideoRow,
         "id character_id job_id status post_kind source_kind source_ref_id post_id submitted_at next_poll_at attempts timeout_seconds created_at updated_at",
         overlaps(PendingFeedVideoRow, start, end, "updated_at")),
    )
    for name, row, fields, window in specs:
        sources[name], coverage[name] = await projection(factory, row, fields.split(),
            and_(row.character_id == character_id, window), row.created_at)
        for item in sources[name]:
            item["window_inclusion"] = "created_in_window" if item["created_at"] >= start.isoformat() else "cross_window_activity"
    # Effects may be included by a bounded parent relation even outside the window.
    commands = [item["turn_id"] for item in sources["commands"]]
    sources["effects"], coverage["effects"] = await projection(factory, ChatTurnEffectRow,
        "id turn_id effect_kind state attempt_count created_at updated_at completed_at".split(),
        ChatTurnEffectRow.turn_id.in_(commands), ChatTurnEffectRow.created_at,
        scope="related_to_exported_commands_may_be_outside_window")
    if coverage["commands"]["status"] != "complete":
        coverage["effects"]["parent_coverage"] = coverage["commands"]["status"]
        if coverage["effects"]["status"] == "complete":
            coverage["effects"]["status"] = "partial"
    for name, row, fields, order in (
        ("heartbeats", RuntimeProcessHeartbeatRow,
         "instance_id process_role service_name build_commit_sha build_tag build_source_digest build_time build_metadata_source build_metadata_file_status build_metadata_file_bytes started_at last_seen_at health_state durable_acceptance_enabled durable_worker_enabled durable_worker_alive background_coordinator_alive connector_runtime_state", RuntimeProcessHeartbeatRow.last_seen_at),
        ("leases", BackgroundRuntimeLeaseRow, "name owner_id epoch lease_until updated_at", BackgroundRuntimeLeaseRow.updated_at),
    ):
        sources[name], coverage[name] = await projection(factory, row, fields.split(), True, order,
            limit=100, scope="current_app_wide_snapshot_not_historical")
    return sources, coverage


async def routing_snapshot(container, character_id):
    """Stored current overrides only; never claim resolved routes or historical config."""
    result = {"captured_at": datetime.now(timezone.utc).isoformat(), "scope": "current_snapshot_not_history",
              "effective_runtime_state": "unknown", "preferences": {}, "character_overrides": {}}
    errors = {}
    truncations = []
    character = None
    allowed = ("provider_id", "model_id", "profile_id", "feature_key", "group_key")
    def safe(value, depth=0):
        if depth > 2 or not isinstance(value, dict):
            return {}
        return {str(k)[:128]: (v[:256] if k in allowed and isinstance(v, str) else safe(v, depth + 1))
                for k, v in list(value.items())[:100] if k in allowed or isinstance(v, dict)}
    repo = getattr(container, "preferences_repository", None)
    if repo is not None:
        for key in ("active_model", "feature_models", "feature_model_groups", "active_image_profile", "image_feature_profiles"):
            try:
                result["preferences"][key] = safe(await asyncio.wait_for(repo.get(key), QUERY_TIMEOUT))
            except Exception as exc:
                errors[key] = type(exc).__name__
    else:
        errors["preferences"] = "repository_not_available"
    repo = getattr(container, "character_repository", None)
    if repo is not None:
        try:
            character = await asyncio.wait_for(repo.get(character_id), QUERY_TIMEOUT)
            if character is not None:
                for field in ("feature_models", "feature_image_profiles"):
                    result["character_overrides"][field] = [
                        {k: str(getattr(item, k))[:256] for k in allowed if getattr(item, k, None) is not None}
                        for item in getattr(character, field, ())[:100]]
        except Exception as exc:
            errors["character"] = type(exc).__name__
    else:
        errors["character"] = "repository_not_available"
    preferences = getattr(container, "preferences_repository", None)
    if preferences is not None and repo is not None and "character" not in errors:
        from kokoro_link.application.services.scoped_preferences import user_preference_key
        owner_id = getattr(character, "user_id", None)
        result["owner_scoped_preferences"] = {}
        if owner_id:
            for key in ("active_model", "feature_models", "feature_model_groups", "active_image_profile", "image_feature_profiles"):
                try:
                    raw = await asyncio.wait_for(preferences.get(user_preference_key(owner_id, key)), QUERY_TIMEOUT)
                    if raw is not None:
                        result["owner_scoped_preferences"][key] = safe(raw)
                except Exception as exc:
                    errors["owner_scoped_" + key] = type(exc).__name__
    try:
        registry = getattr(container, "model_registry", None)
        result["registered_provider_ids"] = registry.list_ids()[:100] if registry is not None else []
        registry = getattr(container, "image_profile_registry", None)
        result["registered_image_profile_ids"] = registry.profile_ids[:100] if registry is not None else []
        result["image_profiles"] = []
        for profile in (registry.profiles[:100] if registry is not None else []):
            item = {"id": profile.id, "kind": profile.kind}
            for field in ("api", "openai", "comfyui"):
                config = getattr(profile, field, None)
                if config is not None:
                    for attr in ("model", "provider", "quality", "checkpoint"):
                        value = getattr(config, attr, None)
                        if isinstance(value, str):
                            item[attr] = value[:256]
                            if len(value) > 256:
                                truncations.append({"path": f"image_profiles.{profile.id}.{attr}", "original_chars": len(value), "exported_chars": 256})
            result["image_profiles"].append(item)
    except Exception as exc:
        errors["registry"] = type(exc).__name__
    factory = factory_for(container)
    if factory is not None:
        async def providers():
            async with factory() as session:
                return (await session.execute(select(
                    ProviderConnectionRow.id, ProviderConnectionRow.provider, ProviderConnectionRow.enabled,
                    func.substr(ProviderConnectionRow.config_json, 1, 16000).label("config"),
                    func.length(ProviderConnectionRow.config_json).label("config_chars"),
                ).where(ProviderConnectionRow.deleted_at.is_(None))
                  .order_by(ProviderConnectionRow.id).limit(101))).mappings().all()
        try:
            rows = await asyncio.wait_for(providers(), QUERY_TIMEOUT)
            result["provider_connections"] = []
            if len(rows) > 100:
                truncations.append({"path": "provider_connections", "original_items_at_least": 101, "exported_items": 100})
            for row in rows[:100]:
                item = {key: row[key] for key in ("id", "provider", "enabled")}
                item["config_truncated"] = row["config_chars"] > 16000
                if item["config_truncated"]:
                    truncations.append({"path": f"provider_connections.{row['id']}.config", "original_chars": row["config_chars"], "exported_chars": 0})
                if not item["config_truncated"]:
                    try:
                        config = json.loads(row["config"])
                        if isinstance(config, dict):
                            item["routing_config"] = {key: value[:256] for key, value in config.items()
                                if key in ("model", "model_id", "image_model", "video_model", "connection_slug") and isinstance(value, str)}
                            for key, value in config.items():
                                if key in item["routing_config"] and len(value) > 256:
                                    truncations.append({"path": f"provider_connections.{row['id']}.{key}", "original_chars": len(value), "exported_chars": 256})
                    except (ValueError, TypeError):
                        item["config_status"] = "invalid_json"
                result["provider_connections"].append(item)
        except Exception as exc:
            errors["provider_connections"] = type(exc).__name__
    else:
        errors["provider_connections"] = "database_source_not_available"
    service = getattr(container, "nsfw_mode_service", None)
    result["nsfw_mode"] = {"active": "unknown", "reason": "active_status_api_may_write_expiration_event"}
    if service is not None:
        try:
            owner_id = getattr(character, "user_id", None)
            target = await asyncio.wait_for(service.configured_target(user_id=owner_id), QUERY_TIMEOUT) if owner_id else await asyncio.wait_for(service.get_global_target(), QUERY_TIMEOUT)
            result["nsfw_mode"]["configured"] = target is not None
            if target is not None:
                result["nsfw_mode"]["target"] = {key: getattr(target, key) for key in ("llm_provider_id", "llm_model_id", "image_profile_id")}
        except Exception as exc:
            errors["nsfw_mode"] = type(exc).__name__
    else:
        errors["nsfw_mode"] = "service_not_available"
    result["truncations"] = truncations
    result["source_errors"] = errors
    return result, {"status": "partial" if errors or truncations else "complete", "scope": result["scope"],
                    "limitations": ["stored_overrides_and_registered_ids_only", "nsfw_active_state_unknown",
                                    "no_historical_config_or_applied_revision_inference"]}
