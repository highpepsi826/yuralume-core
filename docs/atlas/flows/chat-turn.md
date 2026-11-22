---
doc: flow-chat-turn
tier: atlas
verified_at_commit: a803ef8
verified_at: 2026-11-22
sources:
  - src/kokoro_link/application/services/chat_service.py
  - src/kokoro_link/application/services/active_llm_provider.py
  - src/kokoro_link/infrastructure/prompt
  - src/kokoro_link/infrastructure/post_turn/llm_processor.py
  - src/kokoro_link/application/services/busy_defer_policy.py
  - src/kokoro_link/application/services/schedule_service.py
  - src/kokoro_link/infrastructure/busy/llm_decider.py
  - src/kokoro_link/infrastructure/prompt/sections/schedule.py
  - src/kokoro_link/infrastructure/prompt/sections/dialogue.py
  - src/kokoro_link/domain/value_objects/presence_frame.py
  - src/kokoro_link/application/services/ongoing_interaction.py
  - src/kokoro_link/domain/value_objects/ongoing_interaction.py
  - src/kokoro_link/data/prompts/busy/decider.txt
  - src/kokoro_link/data/prompts/post_turn/processor.txt
symbols:
  - src/kokoro_link/application/services/chat_service.py::send_message
  - src/kokoro_link/application/services/chat_service.py::send_message_stream
  - src/kokoro_link/application/services/chat_service.py::_send_message_turn
  - src/kokoro_link/application/services/chat_service.py::_run_post_turn
  - src/kokoro_link/application/services/chat_service.py::_generate_reply_with_tools
  - src/kokoro_link/application/services/chat_service.py::_maybe_defer_reply
  - src/kokoro_link/application/services/chat_service.py::_load_current_schedule
  - src/kokoro_link/application/services/busy_defer_policy.py::BUSY_REPLY_DECIDER_INVOKE_FLOOR
  - src/kokoro_link/application/services/schedule_service.py::apply_adjustments
  - src/kokoro_link/application/services/schedule_service.py::resolve_current
  - src/kokoro_link/infrastructure/busy/llm_decider.py::_build_prompt
  - src/kokoro_link/infrastructure/prompt/sections/schedule.py::_render_schedule_block
  - src/kokoro_link/infrastructure/prompt/sections/dialogue.py::_STAGE_PRESENCE_GUIDANCE
  - src/kokoro_link/domain/value_objects/presence_frame.py::PresenceFrame
  - src/kokoro_link/application/services/ongoing_interaction.py::resolve_ongoing_interaction
  - src/kokoro_link/domain/value_objects/ongoing_interaction.py::OngoingInteraction
  - src/kokoro_link/domain/value_objects/ongoing_interaction.py::schedule_yields_to_conversation
  - src/kokoro_link/application/services/chat_service.py::_resolve_ongoing_interaction
  - src/kokoro_link/application/services/schedule_service.py::resolve_activity_at
---

# 流程：聊天回合

`chat_service.py` 有 10,000 行。不要通讀，按這條主線找。

## 兩個入口

| 入口 | 行 | 回傳 |
|---|---|---|
| `send_message` | 2113 | `ChatReplyResponse` |
| `send_message_stream` | 2718 | `(token_stream, StreamFinalizer)` |

兩者共用同一段前置流程，然後分岔。串流路徑把持久化與 post-turn 交給
`StreamFinalizer`。

## 前置流程（兩個入口共用）

```mermaid
sequenceDiagram
    participant R as route
    participant CS as ChatService
    participant NS as NsfwModeService
    participant LLM as ActiveLLMProvider

    R->>CS: send_message / send_message_stream
    CS->>CS: _begin_turn (1985)
    CS->>CS: _admit_turn (2096) drain 閘門，拒絕或計數
    CS->>CS: _resolve_turn_prelude (2025)
    CS->>CS: 擁有者檢查 (2040-2044)
    CS->>CS: 訂閱守衛 / 解凍 / 載入 operator
    CS->>NS: _content_mode_for_character (1363)
    NS-->>CS: normal | nsfw
    CS->>CS: _load_conversation (4395)
    CS->>LLM: 稍後 _resolve_main_chat_model
```

| 步驟 | 方法 | 行 |
|---|---|---|
| 1 | `_begin_turn` — 對 drain gauge 准入，失敗釋放 handle | 1985 |
| 2 | `_admit_turn` — 原子地拒絕或計數 | 2096 |
| 3 | `_resolve_turn_prelude` — 載入角色、擁有者檢查、訂閱守衛、解凍、載入 operator、綁定 cloud actor、解析 `presence_frame`、決定 content mode、載入 conversation、message session 檢查 | 2025 |
| 4 | `_content_mode_for_character` — 問 `NsfwModeService`，NSFW 時順便續命 | 1363 |
| 5 | `_ensure_runtime_message_session_available` | 5496 |
| 6 | `_acquire_turn_lease`（非串流路徑） | 2087 |

## 非串流主線 `_send_message_turn` (2160)

**上下文組裝（步驟 1–17，全部在 LLM 呼叫之前）：**

| # | 方法 | 行 | 產出 |
|---|---|---|---|
| 1 | `_load_unified_recent_messages` | 2177 | 按時間合併聊天／feed／主動訊息歷史 |
| 2 | `_prepare_prompt_dialogue_context` | 2180 | 視窗化 + 舊對話摘要 |
| 3 | `_memorialize_feed_reactions` | 2192 | 未讀的讚與留言轉成記憶 |
| 4 | `_select_memories` | 2193 | 語意 + 近因檢索 |
| 5 | `_load_active_goals` | 2200 | 角色目標 |
| 6 | `_load_current_schedule` | 2207 | 當前／即將／剛結束／已完成／待邀請活動 |
| 7 | `_ensure_story_events` | 2210 | 當日 story event |
| 8 | `_describe_calendar` | 2212 | 日曆脈絡 |
| 9 | `_describe_weather` | 2213 | 天氣脈絡 |
| 10 | `_load_world_event_context` | 2214 | 世界事件 |
| 11 | `_load_world_event_recall` | 2217 | 回憶起的世界事件 |
| 12 | `_load_upcoming_day_schedules` | 2220 | 多日展望 |
| 13 | `_ensure_story_arc` | 2223 | arc 與到期 beat（可能建立或推進） |
| 14 | `_load_open_scene_session` | 2227 | 進行中的起幕 |
| 15 | `_load_recent_proactive_messages` | 2230 | 最近由角色發起的訊息 |
| 16 | `_load_recent_feed_posts` | 2233 | 最近的 LumeGram 貼文 |
| 17 | `_read_self_repetition_hint` | 2236 | 反覆自我重複的欄位 |

中間兩步不屬於上下文組裝：

- `_resolve_image_trigger` (2253) + `StageNudgeTurn.resolve` (2260) — 剝掉 `/pic`
  標記、解析 stage nudge
- `_maybe_apply_idle_drift` (2274) — 長期未互動的心情漂移（LLM key `idle_drift`）

**狀態與短路（18–23）：**

| # | 方法 | 行 | 注意 |
|---|---|---|---|
| 18 | `_load_recent_emotion_events` | 2282 | |
| 19 | `_overlay_emotion_on_state` | 2285 | |
| 20 | `_build_pre_turn_journal` | 2291 | undo 快照，**在任何短路之前** |
| 21 | `_maybe_defer_reply` | 2321 | 忙碌延後短路 → 在 2347 提前返回。細節見「行程如何影響一個回合」 |
| 22 | `_conversation_repository.save` | 2364 | **先存使用者訊息，再呼叫 LLM** |

**模型解析與生成（23–25）：**

| # | 方法 | 行 | 注意 |
|---|---|---|---|
| 23 | `_resolve_main_chat_model` | 2369（本體 1546） | NSFW 開啟時忽略 payload 的 provider/model；否則走 `active_llm_provider` |
| 24 | `_generate_reply_with_tools` | 2375（本體 4470） | **prompt 組裝 + LLM 呼叫 + tool loop** |

`_generate_reply_with_tools` 是唯一同時碰到 prompt 層與 provider 層的地方。改
prompt 或改 tool 行為都會落在這裡。

**收尾（26–39）：**

| # | 方法 | 行 | 注意 |
|---|---|---|---|
| 26 | state engine `on_assistant_reply` | 2443 | |
| 27 | `_track` | 2445 | 軌跡／指標 |
| 28 | `_character_repository.save` / `_conversation_repository.save` | 2477–2479 | 外部聊天路徑用 CAS append (2483) |
| 29 | `_schedule_nsfw_safe_summary_generation` | 2486 | **背景**，回合不等待 |
| 30 | `_touch_memories` | 2500 | |
| 31 | `_maybe_schedule_tts_pregeneration` | 2501 | |
| 32 | `_run_post_turn` | 2557（本體 7087） | 見下 |
| 33 | `_schedule_outcome_claim_audit` | 2606 | 對外聲明一致性稽核 |
| 34 | `_maybe_schedule_goal_review` | 2619 | |
| 35 | `_maybe_schedule_repetition_check` | 2623 | |
| 36 | `_persist_journal` | 2627 | |
| 37 | `_record_turn_safely` | 2629 | |
| 38 | `_record_llm_usage_safely` | 2681 | |
| 39 | `_finish_scene_turn` | 2697（本體 5788） | 場景收尾判定 + action chips |

## Post-turn 的邊界

```mermaid
flowchart LR
    A["_run_post_turn<br/>chat_service.py:7087"] --> B["_maybe_enqueue_post_turn<br/>:7164"]
    A --> C["_do_post_turn<br/>:7379"]
    C --> D["LLMPostTurnProcessor<br/>post_turn/llm_processor.py:101"]
    D -->|"一次 LLM 呼叫"| E["PostTurnResult"]
    E --> F["ScheduleService"]
    E --> G["StoryArcService"]
    E --> H["GoalService"]
    E --> I["MemoryRepositoryPort"]
    C --> J["_apply_state_suggestion :8299"]
```

**關鍵結構事實：** `LLMPostTurnProcessor` 是純 LLM→DTO 適配器。它
**不做持久化、不呼叫任何 repository**。所有副作用都在 `_do_post_turn` 裡發生，
也就是往上一層。找「為什麼記憶被寫入」時不要停在 processor。

`_do_post_turn` 後續還會跑：`_run_persona_extraction` (7925)、
`_apply_observed_address_changes` (7972)、`_persist_peer_meet_intents` (8051)、
`_persist_message_promises` (8124)、`_maybe_schedule_goal_review` (8348)、
`_maybe_schedule_repetition_check` (8483)。

## 行程如何影響一個回合

行程在一個回合裡有三個作用點，順序固定。找「為什麼角色突然說在忙」「為什麼
行程被改了」時從這裡開始。（查證於 `d066b3e`，2026-11-22；I-21 第一期的改動
已併入下文，未 commit 時以 source 為準。）

```mermaid
flowchart LR
    A["_load_current_schedule<br/>當前／即將／剛結束<br/>+ _resolve_ongoing_interaction"] --> B["_maybe_defer_reply<br/>忙碌延後短路"]
    B -->|"延後"| X["短回覆 + PendingFollowUp<br/>不組 prompt、不跑 post-turn"]
    B -->|"不延後"| C["prompt 行程段<br/>_render_schedule_block"]
    C --> D["LLM 回覆"]
    D --> E["post-turn<br/>schedule_adjustments"]
    E -->|"apply_adjustments"| F["今日行程被改寫"]
```

### 1. 忙碌延後短路（`_maybe_defer_reply`）

- 發生在 **prompt 組裝之前**。一旦延後，本回合只回一句短確認並排一列
  `PendingFollowUp`，主 prompt 的任何指引都不會執行。
- 判斷順序：port 未接線 → 先取消既有的延後列（有則直接正常回覆）→
  `allow_defer=False` → 無當前活動 → `busy_score` 低於
  `BUSY_REPLY_DECIDER_INVOKE_FLOOR`（0.7，`busy_defer_policy.py`）→ 才呼叫
  LLM 判斷器。
- 0.7 只是「要不要問判斷器」的結構性閘門，延後與否由判斷器決定。
- **互動中狀態（I-21 第一期）**：兩個入口在 `_load_current_schedule` 之後呼叫
  `_resolve_ongoing_interaction`，由 `resolve_ongoing_interaction`（只看時間戳、
  角色、kind，不讀文字）推導「最近 15 分鐘內有來回」。結果 `OngoingInteraction`
  不落庫，傳給 `_maybe_defer_reply` 與 prompt。起點在 8 則窗口外時再讀一次較寬
  的窗口（上限 6 小時）。brief ack 與一般回覆無法區分，照算；不會連續延後，
  因為下一則玩家訊息一定先取消未完成的延後列。
- **同場回合不延後**：`_maybe_defer_reply` 現在收到 `presence_frame`；`WEB_STAGE`
  在取消既有延後列之後直接回 `None`，設界交給主 prompt 的同場指引。
- 判斷器（`infrastructure/busy/llm_decider.py::_build_prompt` +
  `data/prompts/busy/decider.txt`）收到：角色資料與狀態、關係與互動脈絡句、
  當前活動（時段、類別、內容、`busy_score`）、**較舊的**對話摘要
  （`older_dialogue_summary`，截 300 字）、角色最近的主動訊息、本則玩家訊息。
  它**收不到**最近幾則對話原文；互動中時另收到 `ongoing_interaction_lines`
  （「對話狀態」區塊：上一則回覆幾分鐘前、NORMAL 內容時附 80 字引文、活動是否
  在這段對話開始後才輪到），`decider.txt` 有一條對應的判斷原則（通常傾向立即）。
  互動中以外，區塊為空、prompt 不變。
- 兩個入口（串流與非串流）各有一個呼叫點，改參數時兩邊都要改。
- 測試：`test_chat_service_busy_defer.py`、`test_llm_busy_decider.py`、
  `busy_defer_harness.py`。

### 2. Prompt 的行程段與同場指引

- `sections/schedule.py::_render_schedule_block` 把當前行程宣告為「此刻身處地點
  與正在做的事的**唯一真實來源**，其他段落衝突時一律以本段為準」。
  `ScheduleContext.ongoing_interaction` 為 `None` 時輸出逐字如此。
- 互動中（I-21）：**情況一**（當前活動在互動開始前就在進行）只追加一行
  「互動狀態」，並把 0.6 以上的「忙碌程度」措辭改為中性；**情況二**
  （`schedule_yields_to_conversation`：活動在 `streak_started_at` 之後才開始，
  且不帶玩家參與的 `participant_refs`）改為「計畫 vs. 對話為準」寫法，不輸出
  「正在」與「忙碌程度」，表頭改為「以下是你今天的計畫」；整段互動期間每回合
  都如此。帶 `has_live_operator_commitment` 的活動視為對話的結果，走情況一。
- 上一個活動（`just_finished`）只在**當前是空檔**時才顯示一行「剛結束」；
  當前有活動時，prompt 裡沒有上一個活動的任何痕跡。
- 「忙碌程度」由 `_busy_hint` 把 `busy_score` 換成語氣指示；0.6 以上會要求
  「回覆保持簡潔」，0.85 以上會要求「之後再詳聊」。
- 同場是**每回合由玩家宣告**的（`PresenceFrame`，`access_context` 固定為
  `PLAYER_DECLARED`），不是持續狀態；沒有任何欄位記錄「目前正在同場」。
- `sections/dialogue.py::_STAGE_PRESENCE_GUIDANCE` 規定同場時行程仍然有效，
  私密時段（洗澡等）由角色在劇情內設界。同場回合現在不會被延後，所以這段一定
  會生效；唯獨情況二時略過「洗澡…隔著門說話」那一點（它預設角色已獨處），
  其餘三點保留。

### 3. Post-turn 會改寫行程（`schedule_adjustments`）

- post-turn 處理器的輸出含 `schedule_adjustments`（add／remove／modify），在
  `_do_post_turn` 內依序交給 `ScheduleService.reconcile_commitment_adjustments`
  與 `apply_adjustments` 寫回。聊天對話要改寫行程，走的就是這條路徑（手動行程
  API 以 `manual=True` 呼叫同一個方法）。
- 觸發條件寫在 `data/prompts/post_turn/processor.txt` 的 `schedule_adjustments`
  欄位規則：預設空陣列，**僅當使用者或角色明確表達行程變動時**才產出，
  「不確定就不要提」。對話沒有明說，行程就不會動。
- 處理器看到的是今日全部活動的 id 清單與未來幾天的行程，沒有「哪一個是當前
  活動」或「互動正在跨越行程邊界」的標記。
- `apply_adjustments` 的規則：新增或修改的時段與既有時段重疊時，把既有時段的
  **開始時間往後推**；已記憶化（`memorialized`）的活動不可 modify／remove；
  remove／modify 只能針對今日既有活動，add 可以帶 `target_date_iso` 指向未來
  日子（該日無行程時建立 `is_planned=False` 的種子）。
- post-turn 在背景執行，改寫可能晚於下一個回合才生效。

### 已知缺口

- I-21 第一期已解決「互動中被忙碌延後」與「prompt 把新活動寫成正在做」。
  **仍未解決（第二期）**：行程本身不會因互動而改寫，其他讀行程的功能（主動訊息、
  feed、記憶化）仍把該時段當成已發生；超過 15 分鐘後回來的約會延續不處理。
  設計見 `ONGOING_INTERACTION_HOLD_REFERENCE.md`。
- 排程中的約定訊息在聊天進行中仍會照發（I-19）。
- 本頁其他段落的行號是 `3fc5836` 時的值，`chat_service.py` 之後有變動，行號
  已漂移（例如 `_maybe_defer_reply` 的呼叫點、`_run_post_turn` 本體）。以
  symbol 名稱搜尋為準；整頁重新對照時一併修正。

## 串流路徑的差異

`_start_message_stream` (2783) 重複前置與步驟 1–24，然後：

- `_describe_tools` (2982) + `asyncio.create_task(_generate_reply_with_tools(...))` (3003)
- 額外跑 `_load_prompt_template_overrides` (3127)、`_overlay_emotion_on_state` (3144)、
  `_fetch_address_preference` (3148)、`_resolve_experiment_overlay` (3152)、
  `_resolve_addresses` (3157)、`_load_address_change_lines` (3161)
- 品質閘門：`_reply_quality_gate_required` (3277) → `_review_chat_draft` (3290)
- 持久化與 post-turn 交給回傳的 `StreamFinalizer`

## 不可違反

- 使用者訊息在 LLM 呼叫**之前**就持久化（2364）。這是崩潰恢復的基礎，不要改成
  生成後才寫。
- `_build_pre_turn_journal` 必須在任何短路之前（2291），否則 undo 會缺快照。
- `_schedule_nsfw_safe_summary_generation` 是背景工作，回合不得等待（見
  `invariants.md` §A）。
- 送往 frontier 的歷史必須經 `sanitize_messages_for_tolerance`。
- 每個副作用對 `(turn_id, effect_kind)` 唯一，非冪等工作前先 claim。

## 測試

`chat_service.py` **沒有單一綜合測試檔**。覆蓋刻意拆成約 80 個檔案：

- 模組層：`tests/unit/test_chat_service.py`（31）、`test_chat_service_busy_defer.py`（19）
- harness：`busy_defer_harness.py`、`chat_stream_route_harness.py`、
  `external_chat_turn_harness.py`、`_messaging_harness.py`
- 行為層：`test_chat_tool_use.py`、`test_chat_vision_input.py`、
  `test_chat_turn_lease.py`、`test_chat_drain_gating.py`、`test_chat_idle_drift.py`、
  `test_chat_stage_nudge.py`、`test_chat_reply_quality_gate.py`、
  `test_chat_action_billing.py`、`test_chat_prompt_mirror_dedup.py`、
  `test_chat_world_event_recall.py`、`test_turn_undo*.py`、`test_story_scene_*_turn.py`
- 整合：`tests/integration/test_chat_user_isolation.py`（5）、
  `test_external_chat_turn_route_pg.py`（3）

改一個 turn-path 行為，預期要動「模組檔 + 該行為檔 + 可能一個 harness」。
