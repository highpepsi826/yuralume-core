"""Check FORK_DELTA.md against the live fork/upstream state.

Purpose
-------
The fork carries a large set of local changes on top of `upstream/main`.
Before an upstream update, two questions matter:

  1. How far has the fork drifted, and what is upstream doing?
  2. Which files did *both* sides change? Those are the conflict hotspots.

This script answers both mechanically and also verifies that every file path
cited in FORK_DELTA.md still exists, so the register cannot silently rot.

It never fetches by itself unless `--fetch` is passed, and it never writes.

Usage
-----
    uv run python scripts/fork_delta_check.py
    uv run python scripts/fork_delta_check.py --fetch
    uv run python scripts/fork_delta_check.py --json
    uv run python scripts/fork_delta_check.py --strict

Exit codes
----------
    0  no problems (or problems exist but --strict was not given)
    1  a cited path is missing, the fork/upstream refs are unusable,
       or --strict was passed while drift was reported
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

DOC_NAME = "FORK_DELTA.md"
FORK_BRANCH = "local/customizations"
UPSTREAM_REF = "upstream/main"

# Only backticked spans that look like a file path are treated as anchors.
# Commands, refs and IDs (`make fork-delta-check`, `upstream/main`, `F-xx`)
# deliberately do not match because they carry no file extension.
_PATH_RE = re.compile(
    r"`([A-Za-z0-9_][A-Za-z0-9_./\-]*\.(?:py|ts|vue|md|txt|json|yml|yaml|sql|ps1|sh))`",
)


@dataclass
class GitResult:
    ok: bool
    out: str


@dataclass
class Report:
    merge_base: str = ""
    fork_commits: int = 0
    upstream_commits: int = 0
    fork_files: int = 0
    upstream_files: int = 0
    fork_insertions: int = 0
    fork_deletions: int = 0
    overlap: list[str] = field(default_factory=list)
    missing_anchors: list[tuple[str, str]] = field(default_factory=list)
    ambiguous_anchors: list[tuple[str, str, int]] = field(default_factory=list)
    anchors_checked: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _git(root: Path, *args: str) -> GitResult:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:  # git missing entirely
        return GitResult(ok=False, out=str(exc))
    if proc.returncode != 0:
        return GitResult(ok=False, out=(proc.stderr or proc.stdout).strip())
    return GitResult(ok=True, out=proc.stdout)


def _lines(value: str) -> list[str]:
    return [line for line in value.splitlines() if line.strip()]


def _ref_exists(root: Path, ref: str) -> bool:
    return _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").ok


def collect_git_state(root: Path, report: Report) -> None:
    for ref in (FORK_BRANCH, UPSTREAM_REF):
        if not _ref_exists(root, ref):
            report.errors.append(
                f"git ref {ref!r} is not resolvable; "
                f"fetch it first (git fetch upstream)",
            )
    if report.errors:
        return

    base = _git(root, "merge-base", UPSTREAM_REF, FORK_BRANCH)
    if not base.ok:
        report.errors.append(f"merge-base failed: {base.out}")
        return
    report.merge_base = base.out.strip()

    counts = _git(
        root, "rev-list", "--left-right", "--count", f"{UPSTREAM_REF}...{FORK_BRANCH}",
    )
    if counts.ok:
        parts = counts.out.split()
        if len(parts) == 2:
            report.upstream_commits = int(parts[0])
            report.fork_commits = int(parts[1])

    stat = _git(
        root, "diff", "--shortstat", f"{UPSTREAM_REF}...{FORK_BRANCH}",
    )
    if stat.ok:
        numbers = re.findall(r"(\d+)", stat.out)
        if len(numbers) >= 3:
            report.fork_files = int(numbers[0])
            report.fork_insertions = int(numbers[1])
            report.fork_deletions = int(numbers[2])

    fork_changed = _git(
        root, "diff", "--name-only", f"{UPSTREAM_REF}...{FORK_BRANCH}",
    )
    upstream_changed = _git(
        root, "diff", "--name-only", f"{report.merge_base}..{UPSTREAM_REF}",
    )
    if not fork_changed.ok or not upstream_changed.ok:
        report.errors.append("could not enumerate changed files")
        return

    fork_set = set(_lines(fork_changed.out))
    upstream_set = set(_lines(upstream_changed.out))
    report.fork_files = len(fork_set)
    report.upstream_files = len(upstream_set)
    report.overlap = sorted(fork_set & upstream_set)


_PRUNE_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "temp",
    ".mypy_cache",
}


def _file_index(root: Path) -> dict[str, list[str]]:
    """Map basename -> repo-relative paths, for bare-name anchors.

    The register frequently lists several files that live in one directory,
    naming the directory once and the basenames after it. Requiring a full
    path for every entry would make the document unreadable, so a bare name
    is resolved against this index instead.
    """
    index: dict[str, list[str]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _PRUNE_DIRS for part in path.parts):
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        index.setdefault(path.name, []).append(relative)
    return index


def check_anchors(root: Path, report: Report, doc: Path) -> None:
    if not doc.is_file():
        report.errors.append(f"{DOC_NAME} not found at {doc}")
        return
    text = doc.read_text(encoding="utf-8", errors="replace")
    index = _file_index(root)
    seen: set[str] = set()
    for raw in _PATH_RE.findall(text):
        candidate = raw.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        report.anchors_checked += 1

        if "/" in candidate:
            if not (root / candidate).exists():
                report.missing_anchors.append((DOC_NAME, candidate))
            continue

        matches = index.get(candidate, [])
        if not matches:
            report.missing_anchors.append((DOC_NAME, candidate))
        elif len(matches) > 1:
            report.ambiguous_anchors.append((DOC_NAME, candidate, len(matches)))


def print_report(report: Report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(
            {
                "merge_base": report.merge_base,
                "fork_commits": report.fork_commits,
                "upstream_commits": report.upstream_commits,
                "fork_files": report.fork_files,
                "upstream_files": report.upstream_files,
                "fork_insertions": report.fork_insertions,
                "fork_deletions": report.fork_deletions,
                "overlap": report.overlap,
                "anchors_checked": report.anchors_checked,
                "missing_anchors": [
                    {"doc": d, "path": p} for d, p in report.missing_anchors
                ],
                "ambiguous_anchors": [
                    {"doc": d, "path": p, "matches": n}
                    for d, p, n in report.ambiguous_anchors
                ],
                "errors": report.errors,
                "warnings": report.warnings,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return

    print(f"merge-base                : {report.merge_base or 'unknown'}")
    print(f"fork commits ahead        : {report.fork_commits}")
    print(f"upstream commits ahead    : {report.upstream_commits}")
    print(
        f"fork diff                 : {report.fork_files} files, "
        f"+{report.fork_insertions} / -{report.fork_deletions}",
    )
    print(f"upstream diff since base  : {report.upstream_files} files")
    print(f"anchors checked           : {report.anchors_checked}")
    print()

    if report.overlap:
        print(f"OVERLAP — changed by both sides ({len(report.overlap)}):")
        for path in report.overlap:
            print(f"  ! {path}")
    else:
        print("OVERLAP — none. The fork and upstream touch disjoint file sets.")
    print()

    if report.missing_anchors:
        print(f"[error] missing anchors ({len(report.missing_anchors)}):")
        for doc, path in report.missing_anchors:
            print(f"  {doc}: {path} does not exist")
        print()

    if report.ambiguous_anchors:
        print(f"[warn ] ambiguous bare names ({len(report.ambiguous_anchors)}):")
        for doc, path, count in report.ambiguous_anchors:
            print(f"  {doc}: {path} matches {count} files; use a fuller path")
        print()

    for message in report.errors:
        print(f"[error] {message}")
    for message in report.warnings:
        print(f"[warn ] {message}")

    problems = len(report.errors) + len(report.missing_anchors) + len(report.overlap)
    if problems == 0:
        print("OK: no missing anchors, no overlap, refs resolvable.")
    else:
        print(
            f"{len(report.errors)} error(s), "
            f"{len(report.missing_anchors)} missing anchor(s), "
            f"{len(report.overlap)} overlap file(s).",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root (default: parent of the script directory)",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="run 'git fetch upstream' before analysing",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when any overlap or warning is present",
    )
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    if not (root / ".git").exists():
        print(f"[error] {root} is not a git repository", file=sys.stderr)
        return 1

    if args.fetch:
        fetched = _git(root, "fetch", "upstream")
        if not fetched.ok:
            print(f"[warn ] git fetch upstream failed: {fetched.out}", file=sys.stderr)

    report = Report()
    collect_git_state(root, report)
    check_anchors(root, report, root / DOC_NAME)

    if report.upstream_commits > 0:
        report.warnings.append(
            f"upstream has {report.upstream_commits} commit(s) not yet merged",
        )

    print_report(report, args.json)

    failed = bool(report.errors or report.missing_anchors)
    if args.strict and (
        failed or report.overlap or report.warnings or report.ambiguous_anchors
    ):
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
