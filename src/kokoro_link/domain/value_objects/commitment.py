"""Shared identity helpers for cross-surface commitments."""

from __future__ import annotations


def normalize_commitment_key(value: object) -> str | None:
    """Normalize only an explicitly supplied commitment key."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
