# Architecture Atlas — Design Reference

**Status:** Implemented 2026-11-21. Steps 1–10 complete: `docs/atlas/` has
`README.md`, `INDEX.md`, `layers.md`, `invariants.md`, `change-map.md`,
`glossary.md`, `domains/nsfw.md`, `flows/chat-turn.md`;
`scripts/atlas_check.py` and `make atlas-check` verify every page; `AGENTS.md`
carries the fourth tier. Remaining domain and flow pages are listed as pending
in `docs/atlas/INDEX.md`. Owner confirmed 繁中正文 and heat-based change-map
selection.
**Date:** 2026-11-21
**Owner:** highpepsi826
**Author:** Claude

---

## 1. Problem

The repository has outgrown ad-hoc lookup. Current scale:

| Surface | Count |
|---|---|
| `application/services/*.py` | 261 |
| `domain/entities/*.py` | 55 |
| Root `*_REFERENCE.md` (in-flight designs) | 17 |
| Archived references | 11 |
| Top-level packages under `src/kokoro_link/` | 12 |

Every non-trivial change currently requires re-deriving the same structural
facts: which layer owns a decision, what the dependency direction allows, which
invariants must not be broken, which tests cover the module, and which existing
reference document already governs the behavior. That work is repeated by both
assistants, after every context compaction, and across sessions.

The cost is not only time. It is drift: two sessions can reach different
conclusions about the same layer because neither has a shared written map.

Existing documents do not solve this, by design:

- `*_REFERENCE.md` — one document per in-flight or recently-implemented feature.
  Scoped to a change, not to a domain. Does not answer "where does chat turn
  assembly live".
- `FEATURE_MANUAL.md` — operator- and player-facing behavior. No code anchors,
  no layering, no invariants.
- `AGENTS.md` — process rules. Not an architecture map.
- `docs/archive/` — read-only history.

There is no artifact that answers: **"I want to change X — which layer, which
files, which invariants, which tests?"**

## 2. Goal

A committed, index-first **Architecture Atlas** under `docs/atlas/` that any
assistant or human can read in under two minutes to locate the right layer for
a change, and that *detects its own staleness* instead of rotting silently.

### Non-goals

- Not a walkthrough of every one of the 261 services. Coverage is
  demand-driven; the atlas expands when a domain is actually touched.
- Not a replacement for `*_REFERENCE.md`. Feature designs stay where they are;
  the atlas indexes them.
- Not a changelog, not a deployment runbook, not user-facing documentation.
- Not a generated API reference. No automated extraction of every symbol; that
  would be stale the moment it is written.
- Not a source of truth for behavior. Where the atlas and the code disagree,
  the code wins and the atlas is broken.

## 3. Proposed structure

```
docs/atlas/
  README.md            # 如何使用、維護契約、staleness 規則
  INDEX.md             # 一頁全貌：分層圖 + 領域清單 + 快速入口
  layers.md            # 分層職責、允許/禁止的依賴方向、跨層規則
  invariants.md        # 硬規則清單（違反即為缺陷）
  change-map.md        # 「我要改 X」→ 動哪幾層 + 檔案 + 測試 + 不可碰的規則
  glossary.md          # 專案詞彙（角色、運營者、deferred intent、…）
  domains/
    chat.md
    prompt.md
    routing.md
    memory.md
    character.md
    scheduling.md
    media.md
    nsfw.md
    admin.md
  flows/
    chat-turn.md
    proactive-message.md
    ...
```

Depth is deliberately uneven. `INDEX.md`, `layers.md`, `invariants.md` and
`change-map.md` are the load-bearing pages and are written first and kept
accurate. Domain and flow pages are added when a domain is actually worked on.

### `change-map.md` is the primary artifact

The single highest-value page, and the one that directly answers the stated
pain. Shape:

| 我想改的東西 | 主要層 | 相關檔案 | 不可違反 | 必跑測試 |
|---|---|---|---|---|
| 聊天回覆的模型選擇 | `application` | `active_llm_provider.py` | 路由順序 NSFW > feature > 全域；不得 fallback 到未註冊 provider | `test_active_llm_provider.py` |
| 訊息寫入的內容標記 | `domain` + `application` | `conversation.py`, `chat_service.py` | `content_mode` 不可由文字推斷、不可回填 | `test_content_flow_tolerance.py` |

This table is the thing an assistant reads before touching anything.

## 4. Page template

Every atlas page carries machine-checkable provenance:

```markdown
---
doc: routing
tier: atlas
verified_at_commit: 3fc5836
verified_at: 2026-11-21
sources:
  - src/kokoro_link/application/services/active_llm_provider.py
  - src/kokoro_link/application/services/nsfw_mode.py
symbols:
  - active_llm_provider.py::ActiveLLMProvider
  - nsfw_mode.py::NsfwModeService
---

# Routing

## 職責
## 不屬於這一層的事
## 關鍵流程（附 file:line 錨點）
## 不變式
## 相關 feature reference
## 已知缺口
```

Rules:

- Every claim that could be checked against code carries a `file:line` or a
  `file::symbol` anchor.
- The 「已知缺口」 section is mandatory and must not be empty-filled with
  platitudes. If a domain genuinely has no known gap, say so explicitly — that
  statement is itself a finding.
- No secrets, no message content, no database rows.

## 5. Staleness contract — the part that makes this survive

Documentation of this kind fails by drifting, not by being absent. The atlas
therefore ships with a checker rather than relying on discipline.

`scripts/atlas_check.py`:

1. Parses YAML frontmatter of every `docs/atlas/**/*.md`.
2. **Path check** — every `sources:` entry must exist. Missing path is an
   error.
3. **Symbol check** — every `symbols:` entry (`path::Name`) must appear in that
   file. `path::Name` with a nested path is supported
   (`application/services/x.py::Class`).
4. **Freshness report** — count commits between `verified_at_commit` and
   `HEAD` for each doc. Report as a warning tier, not an error:
   - `0–30` commits: fresh
   - `31–100`: due for review
   - `>100` or commit not reachable: stale
5. `--strict` promotes warnings to exit code 1, for optional pre-release use.

Wired as `make atlas-check`. Default is a report; CI/pre-release use `--strict`.

**Update obligation.** Any change that alters a domain's behavior, layering, or
invariants must update the affected atlas page in the same commit and refresh
`verified_at_commit` / `verified_at`. This is enforceable by review, and the
checker makes the omission visible afterwards.

**Explicit non-obligation.** Cosmetic code changes that do not alter the claims
in a page do not require an atlas edit — but they do mean the page's
`verified_at_commit` is behind. The freshness tier exists precisely so that
"behind" is visible without being a defect.

## 6. Document Lifecycle integration

`AGENTS.md` currently defines three tiers. The atlas is a fourth, with a
different job:

| Tier | Where | Rule |
|---|---|---|
| Live checkpoint | `.codex-round.md` | current task only |
| **Atlas** | `docs/atlas/` | **stable map of what the code is now; changes when the structure changes** |
| Active reference | root `*_REFERENCE.md` | in-flight design for one change |
| Archive | `docs/archive/` | read-only history |

The distinction that matters: a `*_REFERENCE.md` moves to archive when its work
finishes. An atlas page never archives — it is updated in place, because the
code it describes still runs.

Proposed `AGENTS.md` additions (applied only if the design is approved):

- New 「Architecture Atlas」 section describing the fourth tier and the update
  obligation.
- Inventory step becomes: check `git status` → `.codex-round.md` → **`docs/atlas/INDEX.md`** → only
  then read source.
- `make atlas-check` added to the pre-release checklist.

## 7. First pass — ordered checklist

Deliberately map-first. The first pass does **not** attempt full domain
coverage.

- [ ] 1. `docs/atlas/README.md` — 使用方式、維護契約、staleness 說明
- [ ] 2. `docs/atlas/layers.md` — 12 個套件的職責與依賴方向，逐條標註允許/禁止
- [ ] 3. `docs/atlas/invariants.md` — 從 `AGENTS.md`、既有 reference 與
      contract 檔頭彙整硬規則
- [ ] 4. `docs/atlas/INDEX.md` — 全貌圖 + 領域清單 + 現有 17 份 reference 的歸屬對照
- [ ] 5. `docs/atlas/change-map.md` — 首版涵蓋 8–12 條最常改動的路徑
- [ ] 6. `docs/atlas/glossary.md` — 專案特有詞彙
- [ ] 7. `scripts/atlas_check.py` + `make atlas-check`
- [ ] 8. Domain pages: 先寫 `chat`、`routing`、`nsfw`（三頁，最高流量）
- [ ] 9. `flows/chat-turn.md` 一頁，驗證 flow 頁的格式是否合用
- [ ] 10. `AGENTS.md` 與 `CLAUDE.md` 加入第四層規則
- [ ] 11. 跑 `make atlas-check` 確認 0 error

Steps 1–7 produce a usable atlas. Steps 8–9 prove the template. Step 10 closes
the loop so future sessions actually read it.

## 8. Owner decisions (2026-11-21, confirmed)

1. **語言** — 繁中正文，沿用 `FEATURE_MANUAL.md` 慣例。程式路徑、類別名、symbol
   一律保持英文，不翻譯識別碼。
2. **`change-map.md` 首版範圍** — 按最近 90 天 commit 熱度選題。
3. **freshness 門檻** — 30 / 100 commits（暫定，首版上線後再依實際節奏調整）。
4. **`flows/` 圖形** — Mermaid，與正文同存於 Markdown，可 diff、不會像截圖腐壞。

## 8a. Heat-derived change-map candidates

Measured 2026-11-21 over 140 commits / 90 days (source files only, i18n
locale bundles excluded from selection but noted).

Directory-level concentration:

| Directory | File touches |
|---|---|
| `application/services` | 221 |
| `api/routes` | 55 |
| `infrastructure/persistence` | 52 |
| `infrastructure/prompt` | 46 |
| `data/prompts` | 32 |
| `domain/entities` | 25 |

Derived candidates (hot file → change path):

| # | 我想改的東西 | 熱度證據 |
|---|---|---|
| 1 | 聊天回覆的模型與路由選擇 | `chat_service.py` 15, `active_llm_provider` 相關 |
| 2 | Prompt 組裝（section 順序、identity、dialogue、honesty） | `prompt/sections/*` 合計 17, `prompt/default.py` 4 |
| 3 | Prompt 自訂（Admin 端覆寫） | `prompt_customization_service.py` 4, `PromptCustomizationsAdminPage.vue` 6 |
| 4 | 主動訊息決策與派送 | `proactive_dispatcher.py` 8, `llm_decider.py` 4, `contracts/proactive.py` 4 |
| 5 | 排程建立與規劃 | `llm_planner.py` 6, `schedule_service.py` 4, `sa_schedule_mapping.py` 3 |
| 6 | Pending follow-up／deferred intent | `pending_follow_up.py` 5, `sa_pending_follow_up_repository.py` 4 |
| 7 | Story arc 與 story event | `story_arc_service.py` 5, `story_event_service.py` 4 |
| 8 | Feed 貼文、留言、反應 | `feed_composer_service.py` 5, `llm_composer.py` 3, `llm_comment_reply.py` 3 |
| 9 | 對話檢查點與記憶整合 | `dialogue_checkpoint/*`, `post_turn/llm_processor.py` 4 |
| 10 | 診斷匯出與可觀測性 | `observability.py` 16, `persistent_diagnostics.py` 3, `diagnostic_buffer.py` 3 |
| 11 | Schema 變更與 migration | `persistence/models.py` 11 |
| 12 | 服務接線與容器註冊（DI） | `container.py` 14, `api/app.py` 13 |
| — | 前端聊天面板與 i18n | `ChatPanel.vue` 11, locale bundles 19×3（熱度高但結構單純，列為附註不設獨立頁） |

Items 12 is infrastructure-shaped rather than feature-shaped; it gets its own
`change-map` row because touching it wrongly breaks everything, but it does not
need a domain page.

## 8b. Open questions (non-blocking)

- Freshness 門檻目前以 commit 數計算。若專案節奏改變，改用天數計算只需改
  `atlas_check.py` 的一個常數。

## 9. Verification

The design is satisfied when:

- A fresh session can answer "我要改聊天回覆的模型選擇該動哪裡" using only
  `docs/atlas/INDEX.md` + `change-map.md`, without scanning source.
- `make atlas-check` exits 0 and reports every page's freshness.
- Deliberately deleting one source file causes `atlas-check` to report an
  error naming the page and the missing path.
- `AGENTS.md` contains the fourth tier and the inventory step references the
  atlas.

## 10. Non-goals restated (explicitly out of scope)

- Auto-generating atlas content from AST or docstrings.
- Covering all 261 services in the first pass.
- Migrating or rewriting the existing 17 `*_REFERENCE.md` files.
- Any change to runtime behavior. This is a documentation and tooling change
  only; no application code, migration, or deployment is touched.
