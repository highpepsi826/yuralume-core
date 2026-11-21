"""Verify docs/atlas provenance: frontmatter, source paths, symbols, freshness.

Every page under ``docs/atlas/`` carries YAML frontmatter that records what it
describes and where it was last verified::

    ---
    doc: routing
    tier: atlas
    verified_at_commit: 3fc5836
    verified_at: 2026-11-21
    sources:
      - src/kokoro_link/application/services/active_llm_provider.py
    symbols:
      - src/kokoro_link/application/services/active_llm_provider.py::ActiveLLMProvider
    ---

Usage::

    uv run python scripts/atlas_check.py            # report, exit 1 on error
    uv run python scripts/atlas_check.py --strict   # warnings also exit 1
    uv run python scripts/atlas_check.py --json     # machine-readable output

Checks per page:

* frontmatter present and parseable, with every required key;
* each ``sources`` entry exists relative to the repository root;
* each ``symbols`` entry is ``path::Symbol``, its path exists, and the symbol
  string occurs in that file's contents;
* ``verified_at_commit`` is a reachable commit in the repository;
* freshness: commits between ``verified_at_commit`` and ``HEAD`` -- 0-30 ok,
  31-100 warning (due for review), >100 warning (stale).

A missing or unusable git repository degrades the freshness check to a
warning rather than crashing the run.

The frontmatter parser is deliberately minimal (standard library only, no
PyYAML): it understands ``key: value`` scalars and ``key:`` followed by
``  - item`` list entries. Atlas frontmatter is flat by design; nested
mappings are not supported.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_KEYS: tuple[str, ...] = (
    "doc",
    "tier",
    "verified_at_commit",
    "verified_at",
    "sources",
    "symbols",
)

ATLAS_RELATIVE_DIR = "docs/atlas"

FRESH_MAX_COMMITS = 30
STALE_MAX_COMMITS = 100

LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"
LEVEL_OK = "ok"

FRESHNESS_FRESH = "fresh"
FRESHNESS_DUE = "due"
FRESHNESS_STALE = "stale"
FRESHNESS_UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Issue:
    """One finding for a single atlas page."""

    level: str
    message: str


@dataclass(slots=True)
class PageResult:
    """Checks and findings for one atlas page."""

    page: str
    freshness: str = FRESHNESS_UNKNOWN
    commits_behind: int | None = None
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == LEVEL_ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == LEVEL_WARNING]


@dataclass(frozen=True, slots=True)
class Frontmatter:
    """Parsed frontmatter: scalar values and list values, keyed by name."""

    scalars: dict[str, str]
    lists: dict[str, list[str]]

    def get(self, key: str) -> str | None:
        return self.scalars.get(key)

    def items(self, key: str) -> list[str]:
        return self.lists.get(key, [])


def parse_frontmatter(text: str) -> Frontmatter | None:
    """Return parsed frontmatter, or ``None`` when none is present."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        return None

    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    current_list_key: str | None = None
    for raw_line in lines[1:end_index]:
        if not raw_line.strip():
            current_list_key = None
            continue
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            if current_list_key is not None:
                item = stripped[2:].strip()
                if item:
                    lists[current_list_key].append(item)
            continue
        if ":" not in stripped:
            current_list_key = None
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            current_list_key = None
            continue
        if value in ("", "[]"):
            current_list_key = key
            lists.setdefault(key, [])
            if value == "":
                scalars[key] = ""
            continue
        current_list_key = None
        scalars[key] = value
    return Frontmatter(scalars=scalars, lists=lists)


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run a git command under ``root``; ``None`` when git is unusable."""

    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None


def _commit_reachable(root: Path, sha: str) -> bool | None:
    """True/False for reachability; ``None`` when git itself failed."""

    result = _run_git(root, "cat-file", "-e", f"{sha}^{{commit}}")
    if result is None:
        return None
    return result.returncode == 0


def _commits_behind(root: Path, sha: str) -> int | None:
    """Commit count from ``sha`` to HEAD; ``None`` when git failed."""

    result = _run_git(root, "rev-list", "--count", f"{sha}..HEAD")
    if result is None or result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def freshness_for(commits_behind: int) -> str:
    if commits_behind <= FRESH_MAX_COMMITS:
        return FRESHNESS_FRESH
    if commits_behind <= STALE_MAX_COMMITS:
        return FRESHNESS_DUE
    return FRESHNESS_STALE


def _resolve(root: Path, relative: str) -> Path:
    return (root / relative.replace("\\", "/")).resolve()


def _check_symbol(
    root: Path,
    entry: str,
    result: PageResult,
) -> None:
    if "::" not in entry:
        result.issues.append(
            Issue(LEVEL_ERROR, f"symbols entry '{entry}' is not of the form path::Symbol")
        )
        return
    rel_path, symbol = entry.split("::", 1)
    rel_path = rel_path.strip()
    symbol = symbol.strip()
    if not rel_path or not symbol:
        result.issues.append(
            Issue(LEVEL_ERROR, f"symbols entry '{entry}' is not of the form path::Symbol")
        )
        return
    target = _resolve(root, rel_path)
    if not target.is_file():
        result.issues.append(
            Issue(
                LEVEL_ERROR,
                f"symbols entry '{entry}': path '{rel_path}' does not exist",
            )
        )
        return
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.issues.append(
            Issue(
                LEVEL_ERROR,
                f"symbols entry '{entry}': cannot read '{rel_path}': {exc}",
            )
        )
        return
    if symbol not in content:
        result.issues.append(
            Issue(
                LEVEL_ERROR,
                f"symbols entry '{entry}': symbol '{symbol}' not found in '{rel_path}'",
            )
        )


def check_page(root: Path, page_path: Path, git_available: bool) -> PageResult:
    """Run every check for one atlas page."""

    page = page_path.relative_to(root).as_posix()
    result = PageResult(page=page)

    try:
        text = page_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.issues.append(Issue(LEVEL_ERROR, f"cannot read page: {exc}"))
        return result

    frontmatter = parse_frontmatter(text)
    if frontmatter is None:
        result.issues.append(Issue(LEVEL_ERROR, "missing or unterminated frontmatter"))
        return result

    missing = [key for key in REQUIRED_KEYS if key not in frontmatter.scalars and key not in frontmatter.lists]
    for key in missing:
        result.issues.append(Issue(LEVEL_ERROR, f"missing required frontmatter key '{key}'"))

    for source in frontmatter.items("sources"):
        if not _resolve(root, source).exists():
            result.issues.append(
                Issue(LEVEL_ERROR, f"source path '{source}' does not exist")
            )

    for entry in frontmatter.items("symbols"):
        _check_symbol(root, entry, result)

    verified_commit = frontmatter.get("verified_at_commit")
    if verified_commit:
        if not git_available:
            result.issues.append(
                Issue(
                    LEVEL_WARNING,
                    "git is unavailable; freshness and commit reachability not checked",
                )
            )
        else:
            reachable = _commit_reachable(root, verified_commit)
            if reachable is None:
                result.issues.append(
                    Issue(
                        LEVEL_WARNING,
                        "git command failed; freshness and commit reachability not checked",
                    )
                )
            elif not reachable:
                result.issues.append(
                    Issue(
                        LEVEL_ERROR,
                        f"verified_at_commit '{verified_commit}' is not a reachable commit",
                    )
                )
            else:
                behind = _commits_behind(root, verified_commit)
                if behind is None:
                    result.issues.append(
                        Issue(
                            LEVEL_WARNING,
                            "could not count commits to HEAD; freshness unknown",
                        )
                    )
                else:
                    result.commits_behind = behind
                    result.freshness = freshness_for(behind)
                    if result.freshness in (FRESHNESS_DUE, FRESHNESS_STALE):
                        result.issues.append(
                            Issue(
                                LEVEL_WARNING,
                                f"{result.freshness}: {behind} commits behind HEAD "
                                f"since '{verified_commit}'",
                            )
                        )
    return result


def collect_pages(root: Path) -> list[Path]:
    atlas_dir = root / ATLAS_RELATIVE_DIR
    if not atlas_dir.is_dir():
        return []
    return sorted(
        path
        for path in atlas_dir.rglob("*.md")
        if path.is_file() and "__pycache__" not in path.parts
    )


def git_is_usable(root: Path) -> bool:
    result = _run_git(root, "rev-parse", "--is-inside-work-tree")
    return result is not None and result.returncode == 0


def run(root: Path) -> list[PageResult]:
    pages = collect_pages(root)
    git_available = git_is_usable(root)
    return [check_page(root, page, git_available) for page in pages]


def _format_table(results: list[PageResult]) -> str:
    headers = ("page", "freshness", "errors", "warnings")
    rows = [
        (
            result.page,
            result.freshness
            if result.commits_behind is None
            else f"{result.freshness} ({result.commits_behind})",
            str(len(result.errors)),
            str(len(result.warnings)),
        )
        for result in results
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        if rows
        else len(headers[index])
        for index in range(len(headers))
    ]
    lines = [" | ".join(header.ljust(widths[i]) for i, header in enumerate(headers))]
    lines.append("-+-".join("-" * width for width in widths))
    for row in rows:
        lines.append(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def _report(results: list[PageResult]) -> None:
    if not results:
        print(f"No atlas pages found under {ATLAS_RELATIVE_DIR}/.")
        return
    print(_format_table(results))
    print()
    for result in results:
        for issue in result.issues:
            print(f"[{issue.level}] {result.page}: {issue.message}")
    total_errors = sum(len(result.errors) for result in results)
    total_warnings = sum(len(result.warnings) for result in results)
    print()
    print(
        f"{len(results)} page(s): "
        f"{total_errors} error(s), {total_warnings} warning(s)"
    )


def _json_payload(results: list[PageResult]) -> dict[str, object]:
    return {
        "pages": [
            {
                "page": result.page,
                "freshness": result.freshness,
                "commits_behind": result.commits_behind,
                "errors": [issue.message for issue in result.errors],
                "warnings": [issue.message for issue in result.warnings],
            }
            for result in results
        ],
        "summary": {
            "pages": len(results),
            "errors": sum(len(result.errors) for result in results),
            "warnings": sum(len(result.warnings) for result in results),
            "stale": sum(
                1
                for result in results
                if result.freshness in (FRESHNESS_DUE, FRESHNESS_STALE)
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify docs/atlas frontmatter, source paths, symbol anchors and "
            "freshness against the current HEAD."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: parent of this script's directory).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures (exit code 1).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the table.",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    results = _run_safe(root)

    if args.json:
        print(json.dumps(_json_payload(results), ensure_ascii=False, indent=2))
    else:
        _report(results)

    total_errors = sum(len(result.errors) for result in results)
    total_warnings = sum(len(result.warnings) for result in results)
    if total_errors:
        return 1
    if args.strict and total_warnings:
        return 1
    return 0


def _run_safe(root: Path) -> list[PageResult]:
    """``run`` that converts an unexpected failure into a single error row."""

    try:
        return run(root)
    except Exception as exc:  # noqa: BLE001 - keep the checker from crashing
        return [
            PageResult(
                page=ATLAS_RELATIVE_DIR,
                issues=[Issue(LEVEL_ERROR, f"checker crashed: {exc}")],
            )
        ]


if __name__ == "__main__":
    sys.exit(main())
