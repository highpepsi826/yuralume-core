# FORK_DELTA — 與官方版本的差異清冊

**建立：** 2026-11-21
**基線：** `upstream/main`（`Yuralume/yuralume-core`）
**當前分叉：** 171 個本地 commit、494 個檔案、+53,176 / −1,365 行

## 這份文件要解決什麼

這個 fork 在官方版本之上加了很多東西。下次官方更新時，需要回答兩個問題：

1. **官方這次改了什麼？** — `git log upstream/main..local/customizations` 反向看，
   或直接看 GitHub 的 release notes。
2. **我要不要溶合？** — 取決於官方是否已經做了同一件事（那就丟掉自己的）、
   還是做了衝突的設計（那就要手動合）。

本檔記錄**每一個 fork 獨有的功能**，讓第 2 題有依據，而不是每次重新考古。

它不是 changelog，不是設計文件，也不是 deployment runbook。功能的行為細節仍以
對應的 `*_REFERENCE.md` 與 `docs/atlas/` 為準。

## 怎麼用

```powershell
make fork-delta-check
```

會輸出：分叉規模、上游自 merge-base 以來的新 commit、**與 fork 重疊的檔案**
（= 衝突風險最高的地方），以及本檔所有路徑錨點是否仍然存在。

上游更新時的流程：

1. `git fetch upstream` — 只抓不改。
2. `make fork-delta-check` — 看 overlap 清單。
3. 對每個 overlap 檔案，在下表找到它屬於哪個 F-xx，讀「溶合判斷」欄。
4. 依 `AGENTS.md` 的規則 merge `main` 進 `local/customizations`，不要丟掉本地 commit
   來讓 diff 看起來乾淨。
5. merge 完成後更新本檔的「基線」與每個 F-xx 的 `Status`。

## 狀態用語

| 欄位值 | 意義 |
|---|---|
| `KEEP` | fork 獨有，官方沒有。繼續保留。 |
| `MERGE` | 官方有等價或更完整的實作時，手動合併並移除此列。 |
| `WATCH` | 官方可能正在做同一件事。每次上游更新都要重新判斷。 |
| `DROP-CANDIDATE` | 已經不需要，但先留著確認沒有依賴。 |

---

## 差異清冊

### F-01 — Prompt Studio / Prompt 自訂 / Playground

**類型：** feature
**狀態：** WATCH — 這是最可能被上游吸收的功能，也是本 fork 最大的自製區塊。

把 prompt 從硬編碼變成可管理資產：Admin 可覆寫、可存草稿、有唯讀的
playground 可預覽組裝結果。

| 層 | 檔案 |
|---|---|
| api | `src/kokoro_link/api/routes/prompt_customizations.py`、`src/kokoro_link/api/routes/prompt_playground.py` |
| application | `src/kokoro_link/application/services/prompt_customization_service.py`、`src/kokoro_link/application/services/prompt_playground_service.py` |
| infrastructure | `src/kokoro_link/infrastructure/prompt/`、`src/kokoro_link/data/prompts/` |
| frontend | `frontend/src/utils/api/promptCustomizations.ts`、`frontend/src/utils/api/promptPlayground.ts`、`frontend/src/pages/admin/PromptCustomizationsAdminPage.vue`、`frontend/src/components/PromptCustomizationSetting.vue` |

**相關 reference：** `PROMPT_CUSTOMIZATION_IMPLEMENTATION_REFERENCE.md`、
`PROMPT_PLAYGROUND_IMPLEMENTATION_REFERENCE.md`

**溶合判斷：**
- 若上游推出 prompt 管理功能 → 優先評估改用上游的，本 fork 的差異可能只在
  「草稿 / 發布」語意與 role-aware 模板。
- `src/kokoro_link/data/prompts/` 下的 `*_style.txt` 是 fork 特有的附加檔。
  上游若改動同名檔案，會是實質衝突。
- **注意：** 這個功能動了 `prompt/sections/` 與 prompt golden snapshots
  （`tests/unit/prompt_golden/`，21 個檔案）。上游改 prompt 就一定衝突。

---

### F-02 — 診斷匯出與可觀測性

**類型：** feature
**狀態：** WATCH

把診斷從單一服務擴展到多服務：分層匯出控制、時間範圍、持久化 log、
token 計數保留、heartbeat schema、build metadata 內嵌、檔名唯一化。

| 層 | 檔案 |
|---|---|
| api | `src/kokoro_link/api/routes/observability.py` |
| contracts | `src/kokoro_link/contracts/observability.py` |
| infrastructure | `src/kokoro_link/infrastructure/observability/` 下：`diagnostic_buffer.py`、`persistent_diagnostics.py`、`diagnostic_export_sources.py`、`diagnostic_sources.py`、`runtime_diagnostics.py`、`turn_recorder.py`（同目錄） |
| frontend | `frontend/src/utils/api/observability.ts`、`frontend/src/pages/admin/ObservabilityAdminPage.vue` |

**相關 reference：** `DIAGNOSTIC_COMPLETENESS_IMPLEMENTATION_REFERENCE.md`

**溶合判斷：**
- 上游若重做 observability，這整塊要重評。`src/kokoro_link/api/routes/observability.py`
  是 90 天內單檔最熱（16 次），雙方都在動的機率最高。
- 診斷格式若改變，`scripts/` 下的 rehearsal 工具要同步。

---

### F-03 — Durable chat / 同場聊天可恢復性

**類型：** feature + schema
**狀態：** WATCH

把同場聊天做成可跨裝置恢復：`client_message_id` 冪等、turn effect 記錄、
recovery state 前端呈現、runtime role cutover。

| 層 | 檔案 |
|---|---|
| domain | `src/kokoro_link/domain/entities/durable_chat_command.py` |
| contracts | `src/kokoro_link/contracts/durable_chat_commands.py`、`durable_chat_effects.py`、`durable_chat_execution.py` |
| application | `src/kokoro_link/application/services/durable_chat_executor.py`、`durable_chat_handler.py`、`durable_chat_turn.py` |
| persistence | `src/kokoro_link/infrastructure/persistence/sa_durable_chat_commands.py`、`sa_durable_chat_effects.py` |
| frontend | `frontend/src/utils/durableChatClient.ts` |

**相關 reference：** `SAME_SPACE_DURABLE_CHAT_IMPLEMENTATION_REFERENCE.md`

**溶合判斷：**
- **這是 schema 層的改動，溶合成本最高。** 有 migration、有 unique index
  （`uq_chat_turn_commands_owner_client_message`、
  `uq_chat_turn_commands_active_conversation`、`uq_chat_turn_effects_*`）。
- 上游若推出自己的 durable chat，兩邊的 schema 幾乎不可能自動合併，需要人工設計。
- **遷移前必須備份。** 見 `AGENTS.md` §Safety Checks。

---

### F-04 — Commitment reconciliation（承諾同步）

**類型：** feature + schema
**狀態：** WATCH

跨 projection（排程、story arc、goals、pending follow-up）同步承諾身分，
讓同一件事在不同投影裡是同一個 commitment。

| 層 | 檔案 |
|---|---|
| domain | `src/kokoro_link/domain/entities/pending_follow_up.py`、`src/kokoro_link/domain/entities/story_arc.py` |
| application | `src/kokoro_link/application/services/schedule_service.py`、`story_arc_service.py` |
| infrastructure | `src/kokoro_link/infrastructure/post_turn/llm_processor.py`、`src/kokoro_link/data/prompts/post_turn/processor.txt` |
| tools | `tools/legacy_commitment_repair_live.sql` |

**相關 reference：** `COMMITMENT_RECONCILIATION_IMPLEMENTATION_REFERENCE.md`

**溶合判斷：**
- `AGENTS.md` 明訂這份 reference 是該行為的唯一權威，改動前必須先讀。
- **migration 存在但尚未在生產執行** — 狀態見 reference 的 Status 段。
- 上游若改 post-turn 契約或 schedule 語意，這裡必衝。

---

### F-05 — 玩家性別／代名詞／persona 閘門（I-09）

**類型：** feature
**狀態：** WATCH

玩家可設定代名詞；角色學習玩家性別但需引用證據才能改稱呼；
persona 衍生的改名受閘門控制。

| 層 | 檔案 |
|---|---|
| domain | `src/kokoro_link/domain/entities/operator_profile.py`、`src/kokoro_link/domain/entities/operator_address_preference.py` |
| application | `src/kokoro_link/application/services/address_preference_observer_service.py`、`src/kokoro_link/application/services/operator_persona_projection_service.py`、`src/kokoro_link/application/services/operator_persona_service.py` |
| infrastructure | `src/kokoro_link/infrastructure/persona/llm_extractor.py`、`src/kokoro_link/infrastructure/persona/llm_consolidator.py`、`src/kokoro_link/data/prompts/persona/extractor.txt` |
| frontend | `frontend/src/components/PersonalSettingsSection.vue` |

**相關 reference：** `GENDER_AND_ADDRESS_SEPARATION_IMPLEMENTATION_REFERENCE.md`、
`PLAYER_IDENTITY_AND_SETTINGS_PLACEMENT_REFERENCE.md`

**溶合判斷：**
- 部分已發布（`PLAYER_IDENTITY_AND_SETTINGS_PLACEMENT` 於 2026-10-24 發布）。
- `GENDER_AND_ADDRESS_SEPARATION` 的清單 1–12 完成但**未 commit／未部署** —
  確認是否已隨其他 commit 落地。
- 上游若改 operator profile schema 或 persona 流程，這裡會衝突。

---

### F-06 — 角色影片預覽與影片參數

**類型：** feature
**狀態：** WATCH

影片生成預覽、可設定的影片參數、profile registry、多家 provider。

| 層 | 檔案 |
|---|---|
| contracts | `src/kokoro_link/contracts/video_profile.py`、`async_video_job.py` |
| infrastructure | `src/kokoro_link/infrastructure/video/profile_registry.py`、`src/kokoro_link/infrastructure/video/elevenlabs_video_provider.py`、`src/kokoro_link/infrastructure/video/openai_compatible_provider.py`；另 `src/kokoro_link/bootstrap/video_profiles.py` |
| application | `src/kokoro_link/application/services/video_storyboard_service.py` |
| frontend | `frontend/src/utils/api/videoPreview.ts` |
| 設定檔 | `video-profiles.json`、`image-profiles.json` |

**相關 reference：** `CHARACTER_VIDEO_PREVIEW_REFERENCE.md`、
`VIDEO_PROVIDER_GENERATION_TEST_REFERENCE.md`

**溶合判斷：**
- 設定檔（`video-profiles.json`、`image-profiles.json`）是部署資料，
  不是程式碼。上游若改 schema，本地的 profile 定義要手動遷移。

---

### F-07 — 頻道 allowlist 警告

**類型：** fix
**狀態：** KEEP

Telegram 綁定帳號的 allowlist 狀態在收合卡片上也顯示警告。
起因：2026-08 的 migration 掉了 allowlist，導致 persona 被靜默扣留兩個月，
而收合卡片只顯示「啟用 + 最近連線」，看起來一切正常。

| 層 | 檔案 |
|---|---|
| frontend | `frontend/src/utils/allowlistWarning.ts`、`frontend/src/components/` 相關帳號卡片 |

**溶合判斷：**
- 這是 UI 層的小修正，上游若重做頻道管理頁面，直接重寫即可。
- 但要保留**語意**：allowlist 未設定時必須可見，不能只放在展開區。

---

### F-08 — 同場聊天節奏、時間錨點、訊息時間戳

**類型：** feature + prompt
**狀態：** WATCH

每行對話加時間錨點、同場扮演節奏控制、前端顯示訊息時間戳。

| 層 | 檔案 |
|---|---|
| infrastructure | `src/kokoro_link/infrastructure/prompt/`（時間錨點相關）、`src/kokoro_link/data/prompts/chat/instructions_footer.txt`、`instructions_footer_style.txt` |
| frontend | `frontend/src/components/ChatPanel.vue` |

**相關 reference：** `SAME_SPACE_DETAIL_GUIDANCE_REFERENCE.md`

**溶合判斷：** 純 prompt 與前端改動，衝突好解，但會影響 prompt golden snapshots。

---

### F-09 — Prompt 中的私密 NPC 同伴

**類型：** feature + prompt
**狀態：** WATCH

把私有的 NPC 同伴名冊帶進聊天 prompt。

| 層 | 檔案 |
|---|---|
| infrastructure | `src/kokoro_link/infrastructure/prompt/`（`peer_roster` / `companion_roster` section） |
| domain | `src/kokoro_link/domain/entities/character_peer_profile.py` |

**溶合判斷：** 若上游有自己的 peer 名冊設計，兩者要二選一，不要並存。

---

### F-10 — AIRP：誠實邊界與承諾一致性

**類型：** fix + prompt
**狀態：** WATCH

角色不得在虛構中做出系統無法兌現的承諾；對外聲明的一致性稽核。

| 層 | 檔案 |
|---|---|
| infrastructure | `src/kokoro_link/infrastructure/prompt/outcome_claim_honesty.py`、`src/kokoro_link/infrastructure/prompt/sections/honesty.py` |
| application | `src/kokoro_link/application/services/`（outcome audit 相關） |

**相關 reference：** `docs/archive/AIRP_HONESTY_BOUNDARY_REFERENCE.md`（已歸檔）、
`PROACTIVE_AUDIT_RECORDING_FIX_REFERENCE.md`

**溶合判斷：**
- `feat: limit outcome audits to image delivery` 這個 commit 縮小了稽核範圍，
  上游若擴大回來要確認是不是刻意的。

---

### F-11 — 基礎 image 與依賴 pin

**類型：** chore / infra
**狀態：** KEEP

`Node` base image 固定在 22.23.4（2026-10 安全更新）。

| 檔案 | `frontend/` 或 `docker/` 下的 Dockerfile |
|---|---|

**溶合判斷：**
- 上游若也 pin 到相同版本 → 直接採用上游的，移除此列。
- 上游若 pin 到不同版本 → 比較安全公告，不要盲目跟隨。

---

### F-12 — 文件與流程（本地特有）

**類型：** docs
**狀態：** KEEP

本 fork 特有的文件體系，上游沒有：

| 檔案 | 用途 |
|---|---|
| `AGENTS.md` | 開發與部署規則（含 OVHcloud/Coolify、PowerShell 環境） |
| `CLAUDE.md` | Claude 專屬慣例 |
| `LOCAL_CUSTOMIZATION_WORKFLOW.md` | 本地客製流程 |
| `FEATURE_MANUAL.md` | 操作者與玩家面向的功能說明 |
| `IDEAS_BACKLOG.md` | 想法待辦 |
| `PENDING_FIXES.md` | 已驗證缺陷待修 |
| `FORK_DELTA.md` | 本檔 |
| `docs/atlas/` | 架構圖譜 |
| `.codex-round.md` | 執行 checkpoint |
| `待修.md` | 早期 compaction workaround 文件（歷史性） |

**溶合判斷：** 上游若也有 `AGENTS.md`，merge 時要逐段合，不要整檔覆蓋。

---

### F-13 — 前端玩家身分與設定位置（I-09 相關）

**類型：** feature
**狀態：** KEEP（已發布）

| 檔案 | `frontend/src/components/PersonalSettingsSection.vue`、`PlayerGuideModal.vue` |
|---|---|

已於 2026-10-24 發布（`32090f1`、`968a1bd`）。

---

### F-14 — NSFW 模式的寫作方向（`intimacy_directive`、界線變體、記憶親密度）

**類型：** feature
**狀態：** KEEP（已發布 2026-11-21，`055580b`）

上游的 NSFW mode 只換路由與資料流（模型、圖片 profile、tolerance），
system prompt 與 NORMAL 逐位元組相同。本 fork 讓它同時切換**寫作方向**：

| 項目 | 位置 |
|---|---|
| `intimacy_directive` 區塊（只在 `content_mode == "nsfw"` 渲染，`turn_register` 之後） | `src/kokoro_link/infrastructure/prompt/sections/intimacy.py`、`src/kokoro_link/infrastructure/prompt/sections/order.py` |
| `content_mode` 傳入 prompt context（`RailsContext`） | `src/kokoro_link/infrastructure/prompt/default.py`、`src/kokoro_link/infrastructure/prompt/sections/context.py`、`src/kokoro_link/application/services/chat_service.py` |
| 「互動界線」NSFW 變體 | `src/kokoro_link/infrastructure/prompt/sections/state.py` |
| 事後記憶：保留已發生的親密程度（仍 born-safe） | `src/kokoro_link/infrastructure/post_turn/llm_processor.py` |

**相關 reference：** `NSFW_INTIMACY_DIRECTION_REFERENCE.md`

**溶合判斷：**
- 上游若開始在 prompt 裡處理 NSFW（例如 prompt 層的尺度開關），優先評估
  改用上游的接法，本 fork 保留的差異應只剩文字取向。
- NORMAL 輸出逐位元組不變，由 prompt golden 的孿生案例
  （`nsfw_intimacy_directive` ↔ `normal_boundary_variant`）把關。
- `chat_service.py` 與 `prompt_golden/snapshots/` 都在下方「衝突熱區」，
  merge 時預期衝突。

### F-15 — NSFW 路由分流（結構性任務不跟隨 NSFW target）

**類型：** feature
**狀態：** WATCH（source 完成 2026-11-22，未 commit／未部署）

上游的 NSFW mode 只要開啟，任何 `feature_key` 都無條件改走 NSFW target。
本 fork 讓「不吃對話原文」的結構性任務留在正常路由：排程規劃、劇情弧
規劃／改編／季度判斷／重試判讀／完成記憶、動態貼文撰寫／留言回覆、
記憶合併、目標審核（共 11 個 key）。未列入的 feature（含日後新增）一律
仍走 target，fail-closed。

同時修正一個安全前提：原本只要 `content_mode` 是 NSFW，tolerance 就回
`community` 而不論 provider。分流後被 cut-out 的任務可能落到 frontier
provider，因此改用 `content_tolerance_for_route`——只有**真的**走了 NSFW
target 才給 community，否則由實際 provider 決定，露骨原文仍會清洗。

| 項目 | 位置 |
|---|---|
| `content_tolerance_for_route`（舊 helper 簽名與行為不變） | `src/kokoro_link/domain/value_objects/content_flow.py` |
| `structural_features` 欄位與解析／寫入 | `src/kokoro_link/application/services/nsfw_mode.py`（`NsfwModeTarget`） |
| `_nsfw_target_for` 單一判斷點（四個分支） | `src/kokoro_link/application/services/active_llm_provider.py` |
| 回合 tolerance 由實際 provider 決定 | `src/kokoro_link/application/services/chat_service.py` |
| API 欄位（未帶＝保留原值、`[]`＝清空） | `src/kokoro_link/api/routes/nsfw_mode.py` |
| Admin 勾選清單 +「套用建議組合」 | `frontend/src/components/NsfwStructuralFeaturesFields.vue`、`frontend/src/utils/nsfwStructuralFeatures.ts` |

**相關 reference：** `NSFW_ROUTING_CARVE_OUT_REFERENCE.md`

**溶合判斷：**
- 上游若自行加上 feature 分類或「安全 feature」清單，優先評估改用上游的
  分類方式，本 fork 保留的差異應只剩 allowlist 內容。
- 灰區 feature（翻譯、場景寫作、改寫、判讀類、圖片／影片生成）刻意不在
  allowlist 內，需以 diagnostic export 實測輸入後再逐個加入。
- `src/kokoro_link/application/services/active_llm_provider.py`、`src/kokoro_link/application/services/chat_service.py`、`src/kokoro_link/application/services/nsfw_mode.py` 都在衝突熱區。

---

## 衝突熱區

以下檔案同時是「fork 改過」與「最可能被上游改」。merge 時優先看這些。

| 檔案 | 為什麼危險 |
|---|---|
| `src/kokoro_link/bootstrap/container.py` | 7,112 行，每個新服務都要改；90 天內 14 次 |
| `src/kokoro_link/infrastructure/persistence/models.py` | 4,104 行，無專屬測試 |
| `src/kokoro_link/api/app.py` | 路由註冊集中一處，90 天內 13 次 |
| `src/kokoro_link/application/services/chat_service.py` | 10,000 行，90 天內 15 次 |
| `src/kokoro_link/api/routes/observability.py` | 90 天內 16 次，單檔最熱 |
| `tests/unit/prompt_golden/snapshots/` | byte-identical 快照，prompt 一變就全紅 |
| `src/kokoro_link/data/prompts/` | fork 有大量 `*_style.txt` 附加檔 |

## 維護規則

- 新增 fork 獨有功能 → 在本檔加一列 `F-xx`，寫明類型、狀態、檔案、溶合判斷。
- 上游吸收某功能 → 把該列狀態改 `MERGE`，合併完成後刪除該列。
- 每次上游 merge 後 → 更新本檔頂部的「基線」與 commit 數。
- 本檔的路徑錨點由 `make fork-delta-check` 驗證；失效路徑會報錯。
- 不要在本檔寫 secrets、聊天內容或資料庫資料列。
