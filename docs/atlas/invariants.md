---
doc: invariants
tier: atlas
verified_at_commit: 3fc5836
verified_at: 2026-11-21
sources:
  - AGENTS.md
  - CLAUDE.md
  - src/kokoro_link/domain/entities/conversation.py
  - src/kokoro_link/domain/value_objects/content_flow.py
  - src/kokoro_link/contracts/background_jobs.py
  - src/kokoro_link/contracts/durable_chat_commands.py
  - src/kokoro_link/contracts/inbound_receipts.py
  - src/kokoro_link/infrastructure/persistence/models.py
  - src/kokoro_link/infrastructure/security/provider_secret_cipher.py
  - scripts/check_clock_guard.py
symbols:
  - src/kokoro_link/domain/entities/conversation.py::MessageContentMode
  - src/kokoro_link/domain/value_objects/content_flow.py::sanitize_messages_for_tolerance
  - src/kokoro_link/contracts/clock.py::ensure_utc
  - src/kokoro_link/infrastructure/security/provider_secret_cipher.py::ProviderSecretCipher
  - scripts/check_clock_guard.py::find_violations
---

# 不變式

違反以下任一條即為缺陷。標記說明：

- **HARD** — 由程式約束、資料庫約束或檢查腳本強制
- **CONVENTION** — 有明文規定，僅靠 review 把關
- **UNCLEAR** — 有規定但沒有明確的執行機制
- **BROKEN** — 有規定且**目前實際已被違反**

## A. 內容模式與資料不可變性

| 規則 | 級別 | 證據 |
|---|---|---|
| `content_mode` 是寫入時的事實，不得由文字推斷，不得由內容掃描回填 | HARD（僅 docstring） | `domain/entities/conversation.py:44-54` |
| 內容流輔助函式不得新增關鍵字偵測；tolerance 只讀標記 | HARD | `domain/value_objects/content_flow.py:1-5` |
| NSFW mode 的 tolerance 在構造上就是 `community` | HARD | `content_flow.py:41,46-53` |
| frontier prompt 必須用 `safe_summary` 替換受限訊息，或整則丟棄；永不外送原文 | HARD | `content_flow.py:66-90`；欄位契約 `models.py:575-582` |
| 沒有 `safe_summary` 的 NSFW 檢索必須改路由到社群模型，而不是被清洗掉 | HARD | `content_flow.py:97-116` |
| `image_profile_id = None` 表示「運營者關閉產圖」，永不 fallback 到正常 profile | HARD | `nsfw_mode.py:49-53`；`active_image_provider.py:109-121` |
| 正常路由的 reasoning posture 不得帶到 NSFW target | HARD | `nsfw_mode.py:54-58` |
| `Message.kind` 未知值降級為 `CHAT`，讀取不得失敗 | CONVENTION | `conversation.py:33-37` |
| `Message.created_at` 是跨來源時間軸的唯一真值；頻道討論串按它合併 | CONVENTION | `conversation.py:84-90` |
| `safe_summary` 在背景產生，回合不得阻塞等待 | HARD | `chat_service.py:1456-1480` |
| `audience=private` 的記憶永不成為公開 feed 貼文 | CONVENTION | `domain/entities/memory_item.py:153-158` |
| deferred intent 的 TTL 是資料列屬性，不是啟發式；過期列在注入前過濾 | CONVENTION | `domain/entities/deferred_intent.py:15-23` |
| `PendingFollowUp.delivery_slot_key` 是投遞窗口去重鍵，不得當成承諾身分 | CONVENTION | `COMMITMENT_RECONCILIATION_IMPLEMENTATION_REFERENCE.md:27-29` |

注意：`created_at` 允許回填到 migration 套用時間（`conversation.py:89-90`），
這與 `content_mode` 的禁回填不衝突——不可變規則只限 `content_mode` 與
`safe_summary` 的語意。

## B. 路由

| 規則 | 級別 | 證據 |
|---|---|---|
| provider 能力必須宣告，不得從適配器行為推斷 | CONVENTION | `contracts/async_video_job.py:25` |
| routing profile 快取在控制面不可用或快取過期時必須 fail closed | HARD | `application/services/cloud_routing_profile_cache.py:39,56` |
| 背景／影子 worker 除非能證明模式是 `distributed`，否則 fail closed 成 dry-run | HARD | `background_shadow_worker.py:106,217,328` |
| 影子執行中若擁有者變更，身分重載必須 fail closed | HARD | `background_shadow_worker.py:461-482` |
| 自動整合必須 fail closed：無法取得 slot 就代表不准執行 | HARD | `auto_consolidation_trigger.py:128` |
| 錯誤碼只讀結構化欄位，不得比對 provider 文字 | CONVENTION | `telegram_polling_service.py:97-104` |

## C. 安全與秘密

| 規則 | 級別 | 證據 |
|---|---|---|
| `CONFIG_ENCRYPTION_KEY` 必須跨部署穩定 | CONVENTION | `AGENTS.md` §Hosted Development |
| 沒有加密金鑰時必須拒絕寫入 provider secret，不得存明文 | HARD | `provider_secret_cipher.py:117-121` |
| 秘密只存於 Coolify 變數或 git-ignored env；不得 commit／log／貼出／印出 | CONVENTION | `AGENTS.md` §Safety Checks |
| 背景任務 payload 只帶 ID／日期／設定版本，不帶 prompt、token、聊天內容 | HARD | `contracts/background_jobs.py:33-37,57,97` |
| 診斷匯出預設不含 prompt 與訊息本文 | CONVENTION | `AGENTS.md` §Diagnostics are opt-in |
| 帶憑證的內部 API fail closed：未設定 → 503，不匹配 → 401 | HARD | `api/routes/external_chat.py:230-252` |
| 還原的媒體原始檔不得以 `text/html` 或非白名單型別供應 | HARD | `application/media_content_types.py:19-50` |
| 角色備份的 finaliser 不得把金鑰材料寫回已清洗的 payload | HARD | `contracts/character_backup_jobs.py:262-270` |

## D. 併發、所有權、冪等

| 規則 | 級別 | 證據 |
|---|---|---|
| 每個 `idempotency_key` 最多一個 active 背景任務；重複 `enqueue` 回 `None` 而非報錯 | HARD | `contracts/background_jobs.py:11-13`；`models.py:3276-3284` |
| worker 只能完成／失敗／延長自己仍持有且未過期的租約；過期租約必須重新取得，不得復活 | CONVENTION | `contracts/background_jobs.py:14-21` |
| `enqueue` 必須在同一交易、同列鎖下驗證 coordinator epoch | CONVENTION | `contracts/background_jobs.py:22-32` |
| `(owner_id, client_message_id)` 不可變且唯一；payload hash 拒絕同 id 不同內容 | HARD | `contracts/durable_chat_commands.py:8-15`；`models.py:2628-2650` |
| 訊息附加對 `(conversation_id, idempotency_key)` 冪等；NULL 鍵互不相同 | HARD | `models.py:576-594` |
| `position` 在每個 conversation 內唯一 | HARD | `models.py:586-589` |
| 每個回合副作用對 `(turn_id, effect_kind)` 唯一；非冪等工作前先 claim | HARD | `contracts/durable_chat_effects.py:78`；`models.py:2733-2741` |
| 入站平台訊息 at-most-once：在**嘗試**時 claim，重複呼叫者必須丟棄 | HARD | `contracts/inbound_receipts.py:1-50`；`models.py:1070-1077` |
| 例外：在任何寫入前被 conversation-busy 租約拒絕的回合，必須釋放 claim 讓平台重投 | CONVENTION | `contracts/inbound_receipts.py:44-50` |
| 每角色最多一個執行中的匯出，每運營者最多一個執行中的還原 | HARD | `contracts/character_backup_jobs.py:241-258` |
| 排程承諾冪等：對開啟中的承諾重試回傳既有列 | HARD | `contracts/pending_follow_up.py:29-35`；`models.py:1920-1936` |
| feed 貼文身分是 `(character_id, source)`；重播不得覆寫 | HARD | `models.py:1673-1677` |
| 可能重複計費的投遞／claim 一律偏向丟棄，不偏向重跑 | CONVENTION | `contracts/inbound_receipts.py:41-47` |
| 禁止併發執行 Alembic | CONVENTION | `AGENTS.md` §Hosted Development |

## E. 時間

| 規則 | 級別 | 證據 |
|---|---|---|
| `application/` 與 `domain/` 不得直接 `datetime.now(` | **BROKEN** | `scripts/check_clock_guard.py:9-14` — 見下方說明 |
| 所有持久化時間戳為 aware UTC；naive 輸入視為 UTC，不拒絕 | HARD | `contracts/clock.py:16-21` |
| 帶排程時間的實體拒絕 naive datetime | HARD | `album_item.py:67`、`pending_follow_up.py:84` |
| 事件日誌去重：相同 `last_activity_at` 的重複 expiration 不得重複附加 | HARD | `nsfw_mode.py:470-492,521-535` |
| story realisation 不得從 beat 文本或曆日推斷時間錨點 | CONVENTION | `story_event_service.py:572` |

### clock guard 的實際狀態 — 這是目前最明確的一條缺陷

- 文件（`README.md:229`）稱新檔案受 `check_clock_guard.py` 守護。
- **實測 `uv run python scripts/check_clock_guard.py` 回 exit 1，列出 61 個未列入
  allowlist 的檔案**，橫跨 application 與 domain（含 `nsfw_mode.py`、
  `chat_stream_relay.py`、`messaging_dispatcher.py`、`turn_undo_service.py`
  與數個 entity）。
- allowlist 目前 74 筆；守護沒有跟上程式碼成長。
- **不在 CI**：`.github/workflows/publish-images.yml` 不含此檢查。
- 唯一的測試 `tests/unit/test_clock_guard.py` 用 `tmp_path` 造樣本測
  `find_violations`，**從不掃真實目錄**。
- 範圍比文件描述窄：只匹配 `datetime.now(`；`datetime.utcnow()`、`time.time()`、
  `datetime.today()` 與別名 import 全部漏檢；也只掃 `application/` 與 `domain/`，
  不掃 `infrastructure/` 與 `api/`。

結論：這條規則名義上是 HARD，實務上是 **BROKEN**。任何新增程式碼仍應使用
`ClockPort`，但在守護修好之前，它不會替你攔住錯誤。

## F. 持久化的業務約束（DB 層）

| 規則 | 證據 |
|---|---|
| 一對角色關係只存在一次（無序 pair 唯一） | `models.py:761,794,390` |
| 每個 platform 每角色一個訊息帳號；`webhook_slug` 全域唯一 | `models.py:983-988` |
| 每個 `(account, chat)` 一個 channel binding | `models.py:1030-1032` |
| 每 `(character, date)` 一份日常排程 | `models.py:646-647` |
| 每 `(character, date, seed)` 與 `(character, date, arc_beat)` 各一個 story event；每角色僅一個 ACTIVE arc | `models.py:1236-1242` |
| 每角色一個開啟中的 story scene session | alembic inventory |
| 每 `(post, liker)` 一個反應 | `models.py:1746-1748` |
| 每 pair 每期間一個 self-reflection；每 `(character, kind, description)` 一個行為模式 | `models.py:2198-2200,2237-2239` |
| 每 `(pair, entry)` 一個 memoir pin | `models.py:3037-3039` |
| 每 `(caller, request)` 一個 external-chat receipt；channel 目前限 `line` | `models.py:3581-3584,3596-3599` |
| `process_role` ∈ {api, coordinator, worker, connector}；`health_state` ∈ {starting, healthy, degraded, stopping} | `models.py:3463-3470` |

## G. Prompt 組裝

| 規則 | 級別 | 證據 |
|---|---|---|
| 組裝只讀寫入時標記，不得檢查文字決定 tolerance | HARD | `content_flow.py:1-5` |
| prompt material digest 攜帶產生時的 tolerance；讀取端拒絕在不同 tolerance 下渲染 | CONVENTION | `contracts/prompt_material_digest.py:34-46` |
| 日曆／天氣 port 只回事實，不得告訴 LLM 該下什麼結論 | CONVENTION | `contracts/calendar_context.py:12-15` |
| 翻譯適配器 fail-soft，失敗回原文；結構欄位保持 byte-identical | CONVENTION | `contracts/arc_template_translator.py:6-15` |
| 玩家不得透過 prompt 自訂替換身分、事實脈絡、安全／角色邊界、工具指令、輸出契約、排程規則 | CONVENTION | `PROMPT_CUSTOMIZATION_IMPLEMENTATION_REFERENCE.md:12-15,39-42` |
| Playground 不得持久化任何測試輸入、輸出、prompt 文字或聊天列 | CONVENTION | `PROMPT_PLAYGROUND_IMPLEMENTATION_REFERENCE.md:26-27` |

## H. 已發現的規則衝突

### 1. Telegram polling 擁有者

`AGENTS.md:52-56` 規定「恰好一個 Telegram polling owner」，是全域性質。程式
實際只實作**每帳號**的 DB 租約（`sa_messaging_account_repository.py:110-140`，
由 `telegram_polling_service.py:231-255` 每輪取得／釋放）。

後果：N 個程序可以各自擁有互斥的帳號子集並同時輪詢；交接時租約是釋放而非轉移，
兩個程序可能同時持有連線。**全域單一 poller 是部署慣例，不是程式不變式。**

### 2. `AGENTS.md` 與 `CLAUDE.md` 的重複內容

兩份文件各自重述同一套 PowerShell 規則，措辭不同，獨立編輯。目前無語意衝突，
但屬於同步風險。

## 相關 feature reference

本頁彙整自 `AGENTS.md`、各 `contracts/` 檔頭與 `*_REFERENCE.md`。個別功能的
完整規則仍以各自的 reference 為準。

## 已知缺口

- clock guard 失效（見 E 節），是最該優先修的一條。
- 沒有 lint、型別檢查、import 方向檢查（見 `layers.md` §已知缺口）。
- 大量規則標為 CONVENTION，實際上只有 review 在把關；沒有違規偵測。
- `tests/unit/test_clock_guard.py` 不掃真實目錄，屬於「測了守護本身」而非
  「測了程式碼」。
