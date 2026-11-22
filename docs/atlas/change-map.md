---
doc: change-map
tier: atlas
verified_at_commit: 3fc5836
verified_at: 2026-11-21
sources:
  - src/kokoro_link/application/services/feature_keys.py
  - src/kokoro_link/application/services/active_llm_provider.py
  - src/kokoro_link/application/services/active_image_provider.py
  - src/kokoro_link/application/services/chat_service.py
  - src/kokoro_link/infrastructure/prompt
  - src/kokoro_link/infrastructure/post_turn/llm_processor.py
  - src/kokoro_link/infrastructure/persistence/models.py
  - src/kokoro_link/bootstrap/container.py
  - src/kokoro_link/application/services/pending_follow_up_dispatcher.py
  - src/kokoro_link/application/services/pending_follow_up_release.py
  - src/kokoro_link/application/services/proactive_dispatcher.py
  - src/kokoro_link/data/prompts/busy/scheduled_promise_composer.txt
  - src/kokoro_link/application/services/ongoing_interaction.py
  - src/kokoro_link/infrastructure/prompt/sections/schedule.py
symbols:
  - src/kokoro_link/application/services/active_llm_provider.py::PreferenceBackedActiveLLMProvider
  - src/kokoro_link/application/services/chat_service.py::ChatService
  - src/kokoro_link/infrastructure/prompt/sections/order.py::SECTION_ORDER
  - src/kokoro_link/infrastructure/post_turn/llm_processor.py::LLMPostTurnProcessor
  - src/kokoro_link/application/services/pending_follow_up_dispatcher.py::PendingFollowUpDispatcher
  - src/kokoro_link/application/services/pending_follow_up_release.py::PendingFollowUpReleaseReconciler
  - src/kokoro_link/application/services/proactive_dispatcher.py::ProactiveDispatcher
  - src/kokoro_link/application/services/schedule_service.py::ScheduleService
  - src/kokoro_link/application/services/ongoing_interaction.py::minutes_since_active_conversation
  - src/kokoro_link/application/services/pending_follow_up_dispatcher.py::promise_intent_has_media_obligation
  - src/kokoro_link/infrastructure/post_turn/llm_processor.py::_render_open_promise_section
  - src/kokoro_link/infrastructure/post_turn/llm_processor.py::_parse_promise_updates
  - src/kokoro_link/infrastructure/prompt/sections/schedule.py::_render_due_promises_block
  - src/kokoro_link/application/services/chat_service.py::_rescheduled_promise
---

# 改動地圖

用法：先用下表找到你的改動落在哪一列，再讀該列的細節區塊。若某列的「必跑測試」
不足以涵蓋你的改動，先補測試再改程式。

選題依據：最近 90 天（140 commits）檔案觸及頻率。這只決定**這頁收錄哪些列**，
不影響列內容——列內容一律以當前程式碼為準。

## 摘要表

| # | 我想改的東西 | 主要層 | 核心檔案 | 必跑測試 |
|---|---|---|---|---|
| 1 | 聊天回覆的模型與路由選擇 | application | `active_llm_provider.py` | `test_active_llm_provider.py` |
| 2 | Prompt 組裝與 section 順序 | infrastructure | `prompt/sections/`, `prompt/default.py` | `prompt_sections/`, `prompt_golden/` |
| 3 | Prompt 自訂（Admin 覆寫） | application + api | `prompt_customization_service.py` | `test_prompt_customization_service.py` |
| 4 | 主動訊息決策與派送 | application + infrastructure | `proactive_dispatcher.py` | `test_proactive_dispatcher.py` |
| 5 | 排程建立與規劃 | application + infrastructure | `schedule_service.py`, `schedule/llm_planner.py` | `test_schedule_service*.py` |
| 6 | Pending follow-up／deferred intent | domain + application | `pending_follow_up.py` | `test_pending_follow_up_*.py` |
| 7 | Story arc 與 story event | application + infrastructure | `story_arc_service.py` | `test_story_arc_service*.py` |
| 8 | Feed 貼文／留言／反應 | application + infrastructure | `feed_composer_service.py` | `test_feed_composer_service.py` |
| 9 | 對話檢查點與記憶整合 | application + infrastructure | `dialogue_checkpoint/`, `post_turn/` | `dialogue_checkpoint/` |
| 10 | 診斷匯出與可觀測性 | api + infrastructure | `routes/observability.py` | `test_observability_routes.py` |
| 11 | Schema 變更與 migration | infrastructure | `persistence/models.py` | 見細節（無專屬測試） |
| 12 | 服務接線與 DI 註冊 | bootstrap | `container.py` | 全套 unit suite |
| — | 前端聊天面板與 i18n | frontend | `ChatPanel.vue`, locale bundles | 專案無前端測試 |

---

## 1. 聊天回覆的模型與路由選擇

**層：** `application`

**檔案：**
- `application/services/active_llm_provider.py` — `PreferenceBackedActiveLLMProvider` (:86)
  - `resolve()` :102（provider 解析 + reasoning/vision/script normalization 綁定）
  - `resolve_model_id()` :178
  - `_read_preferred_provider()` :591
  - `resolve_routing_source()` :310
- `application/services/feature_keys.py` — `FEATURE_CHAT`、`GLOBAL_FEATURE_KEYS` (:633)
- `application/services/chat_service.py` — `_resolve_main_chat_model` (:1546)

**模型優先序（由高到低）：**

| # | 分支 | routing_source | 行 |
|---|---|---|---|
| 1 | Active NSFW-mode target（feature 在 `structural_features` 內則跳過） | `nsfw_mode` | 192–195 |
| 2 | Community tolerance → 已配置 NSFW target（無則拋錯） | `nsfw_content` | 196–205 |
| 3 | 角色層 `feature_model_for(key)` | `character_feature` | 209–223 |
| 4 | 全域 `feature_models[key]` | `global_feature` | 225–245 |
| 5 | 全域群組 `feature_model_groups[...]` | `global_group` | 249–269 |
| 6 | 全域 `active_model` | `active_model` | 272–289 |
| 7 | 無可解析 | `provider_default` | 288–290 |

Provider 解析的順序完全相同（`_read_preferred_provider` :591）。

**不可違反：**
- 順序固定。新增分支必須插在正確位置，且補上對應的 `routing_source` 標籤。
- NSFW target 的 provider 未註冊時**拋錯，不得 fallback**（`_require_registered_nsfw_provider` :708）。
- 角色層若 pin 了 provider 或 model 但沒有 reasoning，回 `None`（用連線預設），
  不得繼承低層的 reasoning posture（:416–425）。
- NSFW／community 路由跳過 vision 綁定（:455–458）。

**必跑測試：** `tests/unit/test_active_llm_provider.py`（62）
雲端變體另跑 `tests/unit/test_cloud_active_llm_provider.py`（19）。

---

## 2. Prompt 組裝與 section 順序

**層：** `infrastructure`（組裝在 `application` 被呼叫）

**檔案：**
- `infrastructure/prompt/sections/order.py` — `SECTION_ORDER` :36–167，**79 個 section**
- `infrastructure/prompt/sections/registry.py` — `assemble()` :208、`default_registry()` :195、`PromptSectionRegistry.ordered()` :85
- `infrastructure/prompt/sections/` — `identity.py`(565)、`dialogue.py`(764)、`state.py`(556)、`schedule.py`(572)、`story.py`(543)、`context.py`(220)、`vision.py`(113)、`honesty.py`(36)、`health_care.py`(93)、`tools.py`(35)、`text.py`(24)
- `infrastructure/prompt/default.py` — `build()` :141、`assemble` :272
- 解析器順序：`DEFAULT_RESOLVERS` :153–157

**組裝流程：** 每個 section 先渲染 → 依序跑 resolvers（`resolve_experiment_overlay`
→ `resolve_material_digest_takeover` → `resolve_scene_exclusivity`）→ 按
`SECTION_ORDER` 的 order 值排序輸出。**表格決定順序，不是模組 import 順序。**

**區段大綱（10 段）：**
1. 可快取前綴（operator zone）— `operator_language` … `companion_roster`
2. 角色設定 — `character_profile` … `residue`
3. 工具軌 — `tools`、`honesty_discipline`、`health_care`
4. 回合框架 — `presence_frame`、`turn_register`
5. 內在狀態 — `character_state` … `direction`
6. 腳本化場景 — `story_scene`、`today_scene`
7. 時地與行程 — `timing` … `upcoming_days`
8. 素材與敘事 — `material_digest` … `arc_history`
9. 對話 — `conversation_id` … `relationship_anchor`
10. 回合尾 — `stage_nudge` … `instructions_footer`

**不可違反：**
- 前綴必須穩定，否則 prefix cache 失效（order.py 檔頭 :1–31）。
- `character_profile` 必須在 `state_behavior` 之前（:49–51）。
- `schedule` 必須在 `story_events` 與 `material_digest` 之前（:120–122）。
- `vision_legend` 必須在 `image_recognition` 之前，且兩者都在對話記錄之前（:140–142）。
- 組裝只讀寫入時標記，不得檢查文字決定 tolerance（見 `invariants.md` §G）。

**必跑測試：**
- `tests/unit/prompt_sections/test_section_registry.py`（17，含順序不變式）
- `tests/unit/prompt_golden/`（9 個測試、19 個 `GOLDEN_CASES`，byte-identical 快照）
- `tests/unit/test_prompt_*.py`（45 個檔，合計 440 個測試函式）

**改完快照的處理：** 只有確認變更是刻意的，才用
`ALLOW_PROMPT_GOLDEN_UPDATE=1 python scripts/regen_prompt_goldens.py` 重生。
不要手改 snapshot。

---

## 3. Prompt 自訂（Admin 覆寫）

**層：** `application` + `api` + `frontend`

**檔案：**
- `application/services/prompt_customization_service.py`
- `api/routes/prompt_customizations.py`
- `frontend/src/pages/admin/PromptCustomizationsAdminPage.vue`
- `frontend/src/components/PromptCustomizationSetting.vue`
- `frontend/src/utils/api/promptCustomizations.ts`

**不可違反：**
- 玩家不得透過覆寫替換身分、事實脈絡、安全／角色邊界、工具指令、輸出契約、
  排程規則（`PROMPT_CUSTOMIZATION_IMPLEMENTATION_REFERENCE.md:12-15,39-42`）。
- 草稿是私有的，在發布前永不生效（`PROMPT_PLAYGROUND_IMPLEMENTATION_REFERENCE.md:14-17`）。

**必跑測試：** `tests/unit/test_prompt_customization_service.py`（13）、
`test_prompt_playground_service.py`、`test_prompt_playground_routes.py`、
`test_prompt_template_routes.py`。

---

## 4. 主動訊息決策與派送

**層：** `application` + `infrastructure`

**檔案：**
- `application/services/proactive_dispatcher.py`（90 天內 8 次）
- `infrastructure/proactive/llm_decider.py`
- `contracts/proactive.py`
- 相關 feature key：`FEATURE_PROACTIVE_INTENTION`、`FEATURE_PROACTIVE_MESSAGE`

**不可違反：**
- 入站投遞 at-most-once，重複一律偏向丟棄（見 `invariants.md` §D）。
- 送往 frontier 前必須 `sanitize_messages_for_tolerance`；若標記訊息沒有
  `safe_summary` 且必須保留原文，走 Rule B 強制社群模型。
- `runtime_process_heartbeats` 只是診斷證據，沒有租約語意。

**必跑測試：** `tests/unit/test_proactive_dispatcher.py`（37），加上 9 個 sibling
檔：`_arc`(5)、`_context`(4)、`_deferred_intent`、`_dialogue_summary`、
`_event_mention`、`_honesty`、`_hosted`、`_just_finished`、`_pre_send_ledger`、
`_story_scene`(6)。整合：`test_pending_follow_up_release_pg.py`、
`test_sa_visible_output_dedup.py`。

---

## 5. 排程建立與規劃

**層：** `application` + `infrastructure/schedule`

**檔案：**
- `application/services/schedule_service.py`
- `infrastructure/schedule/llm_planner.py`
- `infrastructure/persistence/sa_schedule_mapping.py`
- feature key：`FEATURE_SCHEDULE_PLAN`、`FEATURE_SCHEDULE_WEATHER_DRIFT`

**不可違反：**
- 每 `(character, date)` 只能有一份日常排程（`models.py:646-647`）。
- 帶排程時間的實體拒絕 naive datetime（`album_item.py:67`、`pending_follow_up.py:84`）。
- 時間來源用 `ClockPort`，不要 `datetime.now(`（見 `invariants.md` §E）。

**聊天回合也會寫行程：** 除了 planner，聊天回合的 post-turn 會透過
`apply_adjustments` 改寫行程。改行程行為前先讀
[flows/chat-turn.md](flows/chat-turn.md)「行程如何影響一個回合」，那裡記錄了
行程在回合中的作用點、post-turn 改寫的觸發條件、記憶化不看對話、重疊規則，
以及聊天 prompt 看不到玩家參與狀態。（查證於 `d54864b`，2026-11-22）

**未來日子的活動：** post-turn 的 `remove` 可以指向「未來行程」清單裡的活動
（I-19 Part 2）；`modify` 仍只限今日。細節見 #6「I-19 之後的約定流程」。
（查證於 I-19 的 source 改動，2026-11-22）

**必跑測試：** `tests/unit/test_schedule_service.py`（16）、`_calendar`(8)、
`_cross_instance`(7)、`_future_commitment`(5)、`_weather_refresh`(7)、
`_window`(7) — 合計 34。

---

## 6. Pending follow-up／deferred intent

**層：** `domain` + `application`

**檔案：**
- `domain/entities/pending_follow_up.py`（90 天內 5 次）
- `domain/entities/deferred_intent.py`
- `infrastructure/persistence/sa_pending_follow_up_repository.py`
- `application/services/pending_follow_up_dispatcher.py`
- `contracts/pending_follow_up.py`

**不可違反：**
- `delivery_slot_key` 是投遞窗口去重鍵，**不得**當成承諾身分
  （`COMMITMENT_RECONCILIATION_IMPLEMENTATION_REFERENCE.md:27-29`）。
- 每個 delivery slot 對開啟中的 scheduled promise 只能有一列
  （`models.py:1920-1936`）；對同一開啟中的承諾重試要回傳既有列，不得新增。
- deferred intent 的 TTL 是資料列屬性，過期列在注入前過濾。

**忙碌延後（`BUSY_DEFER`）從哪裡來：** 聊天回合的 `_maybe_defer_reply`。判斷
順序、0.7 閘門、判斷器看得到與看不到什麼，見
[flows/chat-turn.md](flows/chat-turn.md)「行程如何影響一個回合」第 1 點。
（查證於 `d066b3e`，2026-11-22）

**約定訊息（`SCHEDULED_PROMISE`）到期時怎麼放行：**（查證於 `fe4910b`，2026-11-22）

- 建立：post-turn 的 `message_promises` →
  `chat_service.py::ChatService._persist_message_promises`
  （`PendingFollowUp.new_promise`）。帶 `commitment_key` 的改期走
  `_reconcile_message_promises`，只會改時間與 intent。**post-turn 沒有「這個約定
  已在對話中履行／取消」的輸出**，也收不到開啟中的約定清單。
- 放行：`pending_follow_up_dispatcher.py::PendingFollowUpDispatcher._maybe_release`
  → `_release_scheduled_promise`。只擋兩件事：角色不存在（取消）、角色 frozen
  （留在 queued）。**不看 `busy_score`，也不看玩家此刻是否正在和角色對話**——
  到點就 `marked_resolving` → 組稿 → `deliver_pre_composed`。
- 組稿（`data/prompts/busy/scheduled_promise_composer.txt`）收到：intent、約定
  時間與遲到標記、原始玩家句、當前／剛結束的活動、**一段對話摘要**
  （`_safe_summarize`：只讀 `row.conversation_id` 那一條 conversation 的最近
  40 則，不是跨來源的統一時間線）。它不知道「對話正在進行中」，模板對赴約型的
  指引是「我來了，我們開始吧」。
- 派送：`ProactiveDispatcher.deliver_pre_composed` 對 web thread 與綁定的通訊
  軟體同時 fan-out，不經過主動訊息的冷卻與 `_is_playing_a_scene` 暫停
  （該方法的 docstring 明說：延後應該由 follow-up dispatcher 自己的放行判斷
  負責，這裡擋下等於刪掉訊息）。
- 聊天回合看不到約定：`infrastructure/prompt/sections/` 沒有任何一段列出開啟中
  或到期的約定，角色在對話中只能靠對話歷史／記憶想起自己答應過什麼。
- 「現在不放行」的兩種既有寫法：(1) 原樣留在 queued 回 `False`（frozen、
  busy-defer 仍在忙）；(2) `PendingFollowUp.honesty_parked(retry_at=…)`，會把
  `scheduled_for` **往後改寫**，原約定時間就此遺失（沒有另一個欄位保存）。
- 託管環境的重試節奏：放行由到期事件 job 觸發
  （`pending_follow_up_release.py::PendingFollowUpReleaseEnqueuer`，
  `due_at == scheduled_for`）；job 回 `not_released` 後，下一次機會來自
  `PendingFollowUpReleaseReconciler`（約 15 分鐘一次）掃到「仍 queued 且已到期」
  的列再重新入列。
- 回合復原：回合開始時快照的是**該 conversation** 的開啟列
  （`list_open_for_conversation`），不是角色的全部開啟列。
- 同場聊天沒有獨立的 conversation：它是 web conversation 上帶
  `presence_frame.surface = web_stage` 的回合；`Message` 本身不記錄 surface。

**約定改期與提早履行時，哪些東西會動：**（查證於 `fe4910b`，2026-11-22）

- post-turn 的輸入有今日與未來幾天的行程、進行中的目標、story beat，**沒有開啟中
  的約定清單**。它不知道角色還欠著哪些約定，所以無法把舊約定收掉。
- 約定就地改期只有一條路：`ChatService._reconcile_message_promises`，條件是新的
  `message_promises` 帶 `commitment_key`，且該 key 恰好對到一列開啟中的約定。
  成立時改 `scheduled_for`／intent 並重算 `dedupe_key`、`delivery_slot_key`；
  之後 `_persist_message_promises` 的 `repo.add` 以 delivery slot 去重，不會多一列。
- **沒有任何 prompt 模板要求模型為約定產生 `commitment_key`**
  （`data/prompts/` 全目錄無此字樣；`processor.txt` 的輸出範例也沒有）。模型只會
  在渲染出的行程／目標行尾看到既有的 key（`llm_processor.py` 的行程與目標區塊）。
  所以 key 只在模型自發輸出時才存在。未帶 key 的改期：舊列原樣留著，新列另外
  建立，兩個時間各發一則。
- 改期後舊的到期事件 job 不會重排：`_reconcile_message_promises` 只 `repo.save`，
  沒有呼叫 `_maybe_enqueue_follow_up_release`。舊 job 觸發時因未到期而略過，
  新時間由 reconciler（約 15 分鐘）補入列。
- 行程側：`llm_processor.py` 的 adjustment 解析對 `remove`／`modify` 一律把
  `target_date_iso` 清成 `None`，`ScheduleService.apply_adjustments` 因此把它們
  歸到今日；指向未來日子活動的 `remove`／`modify` 即使 id 通過驗證（未來行程的
  id 在 `known_ids` 內）也找不到目標，等同沒做。唯一能碰未來日子活動的是
  `reconcile_commitment_adjustments`（僅帶 key 的 `modify`），但目標日期同樣已被
  清掉，只能在原日期內改時間，**不能跨日搬移**（見 `PENDING_FIXES.md` PF-10）。
- 提早到場：行程只在對話明說變動或互動跨越行程邊界時才被改寫（見
  [flows/chat-turn.md](flows/chat-turn.md) §3）。玩家比約定時間早出現、自然聊起來，
  兩者都不成立，約定的共同活動仍停在原時段。

**I-19 之後的約定流程：**（查證於 `fe4910b` 加上 I-19 的 source 改動，2026-11-22；
與上面兩段衝突時以本段為準——上面兩段保留的是改動前的機制與成因。）

- **post-turn 看得到約定**：`ChatService._do_post_turn` 透過
  `_load_open_promises_for_post_turn` 自己讀該角色 `queued` 的約定（排除
  `resolving` 與 honesty-repair 列），以 `open_promises` 傳給處理器（`_accepts_keyword`
  守衛，空清單不傳）。`llm_processor.py::_render_open_promise_section` 渲染到模板
  的 `${promise_section}`（與 `${boundary_section}` 同一行，無約定時為空字串）。
  模型看到的是 id 前 8 碼，最多列 8 筆。
- **`promise_updates`**：`_parse_promise_updates` 只接受清單內的 id（短碼需唯一），
  action 為 `fulfilled`／`cancelled`／`rescheduled`；含媒體交付的約定拒絕
  `fulfilled`；每筆約定只取第一個判定，最多 6 筆。媒體判斷是
  `pending_follow_up_dispatcher.py::promise_intent_has_media_obligation`
  （與派送端同一個 regex，屬關鍵字判斷）。
- **套用**：`ChatService._apply_promise_updates`，在 `message_promises` 落庫
  **之前**執行。逐列重讀，只在列仍是該角色 `queued` 的約定時寫入。`fulfilled` →
  `marked_resolved`，`resolved_message` 以
  `PROMISE_FULFILLED_IN_CONVERSATION_MARKER`（「在對話中履行」）開頭；`cancelled` →
  `cancelled`；`rescheduled` → `_rescheduled_promise`（與 `commitment_key` 路徑共用
  的重算）後 `_maybe_enqueue_follow_up_release`。release job 的 idempotency key 含
  時間窗，所以新時間會得到新 job，舊 job 觸發時因未到期而略過。
- **未來日子的 `remove`**：`_parse_adjustments` 對 id 屬於未來行程的 `remove`
  保留該活動所在日期（取自渲染出的行程，不取模型輸出），`apply_adjustments` 因此
  到那一天移除。`modify` 仍只能改今日（PF-10 第 2 點的跨日搬移未做）。
- **放行前的保留**：`_release_scheduled_promise` 在 `marked_resolving` 之前讀跨來源
  時間線（`_load_unified_timeline`，80 則），
  `ongoing_interaction.py::minutes_since_active_conversation` 非 `None` 就原樣留在
  `queued` 回 `False`。成立條件：15 分鐘內角色回過玩家，或最新一則 CHAT 是玩家
  發的且在 15 分鐘內。讀不到時間線視為不在對話。只套用於約定，`BUSY_DEFER`
  不變。下一次機會是 reconciler（約 15 分鐘）。
- **補發的組稿**：約定的摘要改讀跨來源時間線（`_safe_summarize(unified=True)`；
  busy-defer 仍讀單一 conversation）。
  `ScheduledPromiseComposeInput.conversation_minutes_at_scheduled` 是「在約定時刻
  當下是否正在對話」（同一函式以 `scheduled_for` 為 now 計算）；非 `None` 時遲到
  標記改為「約定時間到的時候你們正在對話中」並多一段「不算遲到」。當前活動帶
  `operator_confirmed_shared` 時行程區塊多一行。三者皆無時 prompt 不變。
- **聊天回合注入**：`ChatService._load_due_promises` 在忙碌延後短路**之後**讀已
  到期、`queued`、非媒體、非 honesty-repair 的約定，以 `due_promises` 傳到 prompt
  builder；`sections/schedule.py::_render_due_promises_block` 是 `SECTION_ORDER` 中
  `relationship_anchor` 之後的 `due_promises` 段，最多列 3 筆。聊天回合本身不結案，
  由該回合的 post-turn 判定。
- **回合復原**：journal 快照除了同一 conversation 的開啟列，另加該角色其他
  conversation 上的開啟約定。復原其他 conversation 的列時，只有現況是 `queued`、
  `cancelled`，或帶「在對話中履行」標記的 `resolved` 才寫回；已被 dispatcher 送出
  或處理中的列不動。

**必跑測試：** `tests/unit/test_pending_follow_up_entity.py`、
`test_pending_follow_up_scheduled_promise_entity.py`、
`test_pending_follow_up_dispatcher_promise.py`、
`test_llm_pending_follow_up_composer.py`、`test_llm_scheduled_promise_composer.py`、
`test_post_turn_promise_updates.py`、`test_promise_hold_and_compose.py`、
`test_chat_due_promises.py`、`test_turn_undo_follow_ups.py`。

---

## 7. Story arc 與 story event

**層：** `application` + `infrastructure/story`

**檔案：**
- `application/services/story_arc_service.py`（5 次）
- `application/services/story_event_service.py`（4 次）
- `infrastructure/story/`（18 個模組：arc / beat 適配、日期脈絡、YAML 模板庫）
- feature keys：`FEATURE_ARC_PLAN`、`FEATURE_ARC_ADAPT`、`FEATURE_ARC_SCENE_WRITE`、
  `FEATURE_ARC_BEAT_RECHECK`、`FEATURE_ARC_SEASON_DECIDE`、`FEATURE_ARC_COMPLETION_MEMORY`

**不可違反：**
- 每角色只能有一個 ACTIVE arc。
- 每 `(character, date, seed)` 與 `(character, date, arc_beat)` 各一個 story event。
- story realisation **不得**從 beat 文本或曆日推斷時間錨點（`story_event_service.py:572`）。
- 首次見面的 beat 在每個無人值守路徑中都是玩家必要項，即使
  `operator_position` 為 NULL，且維持 pending 直到連結的即時排程開始時間過去
  （`FIRST_MEETING_PREMATURE_COMPLETION_FIX_REFERENCE.md:18-21`）。

**必跑測試：** `tests/unit/test_story_arc_service.py`（28）、`_planner_context`(16)、
`_series`(6)、`_template`(6)，加上 `test_story_arc_routes.py`、
`test_story_arc_persistence_mapping.py`、`test_story_arc_retire_concurrency.py`、
`test_story_arc_beat_retry_budget.py`、`test_story_arc_cross_replica.py`。

相關參考：`CROSS_CHANNEL_ARC_PLANNER_REFERENCE.md`。

---

## 8. Feed 貼文／留言／反應

**層：** `application` + `infrastructure/feed`

**檔案：**
- `application/services/feed_composer_service.py`（5 次）
- `infrastructure/feed/llm_composer.py`、`llm_comment_reply.py`
- feature keys：`FEATURE_FEED_COMPOSE`、`FEATURE_FEED_COMMENT_REPLY`、
  `FEATURE_IMAGE_FEED`、`FEATURE_VIDEO_FEED`

**不可違反：**
- feed 貼文身分是 `(character_id, source)`；重播不得覆寫（`models.py:1673-1677`）。
- `audience=private` 的記憶永不成為公開貼文（`memory_item.py:153-158`）。
- 每個 feed slot 只有一個影片任務可以發布；CAS 就是去重機制。
- 失敗的非同步影片任務永不產出 artifact；`failed`/`dead` 是終態。

**必跑測試：** `tests/unit/test_feed_composer_service.py`（55）、
`test_llm_feed_composer_parse_robustness.py`（9）、`test_llm_feed_composer_video.py`（18）、
`test_feed_output_quality_gate.py`、`test_feed_routes.py`。

---

## 9. 對話檢查點與記憶整合

**層：** `application` + `infrastructure`

**檔案：**
- `application/services/dialogue_checkpoint/`（含 `updater.py`）
- `infrastructure/post_turn/llm_processor.py` — `LLMPostTurnProcessor` :101，`process()` :124
- `domain/entities/memory_item.py`
- `application/services/material_digest_precompute.py`

**重要結構事實：** `LLMPostTurnProcessor` 是**純 LLM→DTO 適配器**，
**不做持久化、不呼叫 repository**。副作用全部在上一層的
`ChatService._do_post_turn`（`chat_service.py:7379`，呼叫點 :7521），
那裡才跑 `ScheduleService`、`StoryArcService`、`GoalService`、
`MemoryRepositoryPort`。

**不可違反：**
- `content_mode` 不可由內容掃描回填（見 `invariants.md` §A）。
- `safe_summary` 在背景產生，回合不得阻塞。
- 記憶的 `player_knowledge` 在寫入站設定一次，之後不得猜測；`""` 保持 `""`。
- prompt material digest 攜帶產生時的 tolerance，讀取端拒絕在不同 tolerance 下渲染。

**必跑測試：** `tests/unit/dialogue_checkpoint/`（`test_llm_merger.py`、
`test_merge_concurrency.py`、`test_post_turn_hook.py`、
`test_prepare_prompt_dialogue_context.py`、`test_mirrored_window_agreement.py`）、
`tests/unit/test_post_turn_processor.py`、`test_material_digest_precompute.py`、
`test_prompt_material_digests_migration.py`。
eval：`tests/evals/fixtures/nsfw_born_safe_memory_continuity_01.yaml`。

---

## 10. 診斷匯出與可觀測性

**層：** `api` + `infrastructure/observability`

**檔案：**
- `api/routes/observability.py`（90 天內 **16 次，單檔最熱**）
- `infrastructure/observability/` — `diagnostic_buffer.py`、`persistent_diagnostics.py`、
  `diagnostic_export_sources.py`
- 前端：`frontend/src/pages/admin/ObservabilityAdminPage.vue`、
  `frontend/src/utils/api/observability.ts`

**注意：** 不存在 `application/services/observability.py`。這條路徑就是 route +
infrastructure，沒有 application 服務層。找錯地方會浪費時間。

**不可違反：**
- 診斷匯出預設不含 prompt 與訊息本文，除非明確開啟 `include_prompt` /
  `include_messages`。
- 背景任務 payload 不得帶 prompt、token 或聊天內容。
- 診斷 bundle 視為敏感資料，不得寫進 `UPDATE_PROGRESS_LOG.md` 或任何已提交文件。

**必跑測試：** `tests/unit/test_observability_routes.py`（17）、
`test_diagnostic_buffer.py`、`test_diagnostic_export_sources.py`、
`test_persistent_diagnostics.py`、`test_observability_subsystem_health_metrics.py`、
`test_execution_mode_metrics.py`、`test_metered_trace_correlation.py`。

相關參考：`DIAGNOSTIC_COMPLETENESS_IMPLEMENTATION_REFERENCE.md`。

---

## 11. Schema 變更與 migration

**層：** `infrastructure/persistence`

**檔案：**
- `infrastructure/persistence/models.py`（4,104 行，90 天內 11 次）
- `alembic/versions/`

**不可違反：**
- 禁止併發執行 Alembic；migration 只跑一次、在受控環境。
- 生產 migration 前必須讀 OVHcloud runbook、確認服務狀態、取得明確同意、
  建立並驗證 PostgreSQL custom-format 備份（`AGENTS.md`）。
- 新增 unique constraint 前先確認既有資料不會違反。

**測試現況 — 這是缺口：** `models.py` **沒有任何專屬測試檔**。它只被間接涵蓋：
`tests/conftest.py:28` 用 `Base` 建 schema，約 10 個 integration test 直接 import
個別 row class。**改 model 沒有直接的測試要更新**，安全網只有 migration 測試與
PG integration suite。

**必跑：** 相關的 `test_*_repository.py`、`test_*_migration.py`，以及
`tests/integration/` 中對應的 PG 測試。改動 schema 前後都要跑。

---

## 12. 服務接線與 DI 註冊

**層：** `bootstrap`

**檔案：**
- `bootstrap/container.py`（**7,112 行**，90 天內 14 次）
  - `ServiceContainer` :1103
  - `build_container(settings)` :2696
  - 36 個 `_build_*` 輔助函式
- `bootstrap/settings.py`（2,610 行）
- `api/app.py`（90 天內 13 次）— 路由註冊集中在 :756–865

**不可違反：**
- 新服務要加進 `ServiceContainer` 的欄位與 `build_container` 的組裝，
  否則 `getattr(container, "...", None)` 會拿到 `None` 並在 route 層變成 503。
- `CONFIG_ENCRYPTION_KEY` 必須跨部署穩定。
- 路由註冊集中在一處，不要在別的檔案 decorator-time 加入。

**測試現況：** 沒有專屬測試。改 container 之後跑全套 unit suite；
任何 `Depends(get_container)` 相關的 route 測試都會暴露漏接。

---

## 附註：前端聊天面板與 i18n

`frontend/src/components/ChatPanel.vue`（90 天內 11 次）與三個 locale bundle
（各 19 次，全專案最高）。結構單純、沒有專屬測試。改動時注意：

- i18n 三個語系必須同步新增 key，否則 `vue-i18n` 會回退到 key 字串。
- 專案沒有前端測試套件；驗證方式是 `npm run build` 加手動確認。

---

## 選題依據的說明

本頁以最近 90 天（2026-08-23 ~ 2026-11-21）的 commit 熱度選題。熱度只決定
**收了哪些列**，不寫進列內容。未被收錄但可能重要的區域（冷門但危險）：

- `contracts/` 那 4 個反向 import `application` 的檔案（見 `layers.md`）
- `scripts/check_clock_guard.py` 的失效（見 `invariants.md` §E）
- Telegram polling 的全域單一擁有者只存在於文件（見 `invariants.md` §H）

這三項本身就是 atlas 這次盤點出來的缺陷，已記入對應頁面的「已知缺口」。
