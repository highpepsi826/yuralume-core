# NSFW 路由分流（結構性任務不跟隨 NSFW target）— 設計與實作參考

**Status:** 已撰寫，等待 owner 批准。**尚未實作任何 source 改動。**
**建立：** 2026-11-21 (by Claude)
**前置：** `NSFW_INTIMACY_DIRECTION_REFERENCE.md`（已發布 `055580b`）
**Atlas 對應：** `docs/atlas/domains/nsfw.md`

---

## 1. 問題

`active_llm_provider.py` 的 NSFW 分支是**無條件**的：只要模式開啟，任何
`feature_key` 都改用 NSFW target。

```python
nsfw_target = await self._read_nsfw_target(character=character)
if nsfw_target is not None:
    self._require_registered_nsfw_provider(nsfw_target.llm_provider_id)
    return selected(nsfw_target.llm_model_id, "nsfw_mode")
```

後果：模式期間**背景任務也全部改用本地模型**，包括排程規劃、story arc
規劃、feed 生成等完全不需要對話原文、但需要穩定結構化輸出的任務。本地模型
若不擅長照格式吐 JSON，這些任務會安靜地變差。

目標：讓「結構性、不吃對話原文」的任務留在正常路由，其餘仍走 NSFW target。

---

## 2. 一個必須先處理的安全事實

`content_tolerance_for_llm_provider`（`content_flow.py:46`）目前是：

```python
if _content_mode_value(current_content_mode) == MessageContentMode.NSFW.value:
    return CONTENT_TOLERANCE_COMMUNITY
if routing_source in {"nsfw_mode", "nsfw_content"}:
    return CONTENT_TOLERANCE_COMMUNITY
normalized = (provider_id or "").strip().lower()
if normalized in _FRONTIER_LLM_PROVIDER_IDS:
    return CONTENT_TOLERANCE_FRONTIER
return CONTENT_TOLERANCE_COMMUNITY
```

**只要 `content_mode` 是 NSFW，就回 community——不管 provider 是誰。**

因此在做分流之前，若某個被 cut-out 的任務路由到 frontier 模型，而呼叫端用
`_content_tolerance_for_model(model, content_mode=NSFW)` 算 tolerance，它會
拿到 community，**未清洗的露骨原文就會送到 frontier provider**。

這是本設計的**第一順位約束**：分流與 tolerance 計算必須同時改，不能只改路由。

---

## 3. 已確認的需求

| # | 需求 | 對應 |
|---|---|---|
| R1 | 結構性任務在 NSFW 期間走正常路由 | §5 allowlist |
| R2 | 不能因分流而把露骨原文送到 frontier | §4 tolerance 由實際 provider 決定 |
| R3 | 未列入 allowlist 的 feature（含未來新增）一律留在 NSFW target | fail-closed 預設 |
| R4 | 不改變現行預設行為 | 空 allowlist = 與現在完全相同 |

---

## 4. 核心設計

### 4.1 tolerance 改為「由實際路由到的 provider 決定」

新增一個判斷：**這一呼叫是否真的走了 NSFW target**。只有是，才套 community
覆寫；否則回到既有的 provider 判定。

```python
# 概念示意，非最終簽名
def content_tolerance_for_route(
    provider_id: str | None,
    *,
    routed_to_nsfw_target: bool,
) -> str:
    if routed_to_nsfw_target:
        return CONTENT_TOLERANCE_COMMUNITY
    return (
        CONTENT_TOLERANCE_FRONTIER
        if (provider_id or "").strip().lower() in _FRONTIER_LLM_PROVIDER_IDS
        else CONTENT_TOLERANCE_COMMUNITY
    )
```

`content_tolerance_for_llm_provider` 保留現有簽名與行為（其他 20+ 個呼叫端
不動），只在 `active_llm_provider` 這條路徑改用新函式。

**這是 fail-closed 的方向**：認不得的 provider 仍是 community，只有明确在
frontier 名單內的才會被判為 frontier。

### 4.2 allowlist

`NsfwModeTarget` 新增一個欄位：

```python
structural_features: tuple[str, ...] = ()
```

- 空 tuple（預設）= 與現行行為完全相同，所有 feature 走 NSFW target。
- 有值時，列出的 `feature_key` 跳過 NSFW 分支，走正常路由。

存放：`preferences` 鍵 `nsfw_mode_target` 內新增 `structural_features` 陣列。
缺鍵即空 tuple，向後相容（舊 target 設定不需遷移）。

### 4.3 三個判斷點必須一致

NSFW 分支目前出現在**三處**，分流必須三處同步，否則同一回合的 model 與
reasoning 會來自不同 provider：

| 位置 | 函式 | 行 |
|---|---|---|
| 1 | `resolve_model_id` | ~192 |
| 2 | `_read_preferred_provider` | ~598 |
| 3 | `_maybe_bind_reasoning` | ~359 |

作法：抽出單一 helper

```python
async def _nsfw_target_for(
    self, *, feature_key: str | None, character: Character | None,
) -> NsfwModeTarget | None:
    target = await self._read_nsfw_target(character=character)
    if target is None:
        return None
    if feature_key and feature_key in target.structural_features:
        return None
    return target
```

三處都改呼叫它。`_maybe_bind_vision`（~455）不需改：它只是問「是否 NSFW
路由中」，改用同一 helper 即可保持語意一致。

---

## 5. Feature 分類

### A. 必須走 NSFW target（吃對話原文）

| Feature | 理由 |
|---|---|
| `chat` | 回合本身 |
| `post_turn` | 記憶蒸餾；餵摘要會產出「摘要的摘要」 |
| `nsfw_safe_summary` | 本身就是原文→安全摘要的轉換器 |
| `dialogue_summary` | 對話檢查點摘要 |
| `novelty_gate` | 逐字比對最近台詞 |
| `prompt_material_digest` | 直接讀 recent messages |
| `proactive_intention`、`proactive_message` | 依最近對話判斷與接話 |
| `busy_reply_decide`、`busy_follow_up` | 對當下對話反應 |
| `scheduled_promise` | Rule B 已強制社群模型 |
| `chat_repetition_check` | 逐字比對 |
| `register_profile` | 從本回合文字推語氣 |
| `image_chat_tool` | 從對話生成圖片 prompt |

### B. 可分流（結構性，不吃原文）— 本次 allowlist 預設候選

| Feature | 理由 |
|---|---|
| `schedule_plan`、`schedule_weather_drift` | 只看行程與偏好 |
| `arc_plan`、`arc_adapt`、`arc_season_decide`、`arc_beat_recheck`、`arc_completion_memory` | 用 born-safe 記憶與 beat 標記 |
| `feed_compose`、`feed_comment_reply` | 公開貼文；`audience=private` 不會變成公開貼文 |
| `memory_consolidate` | 對已 born-safe 的記憶做整合 |
| `goal_review` | 不讀對話原文 |

**建議第一批只放這 12 個。** 它們都通過同一個判準：不讀 `recent_messages`，
或只讀已 born-safe 的記憶。

### C. 灰區 — 預設**不**放入 allowlist

| Feature | 疑慮 |
|---|---|
| 翻譯類（`tts_translate`、`card_translate`、`arc_template_translate`、`story_seed_translate`、`showcase_translate`、`official_card_translate`、`memoir_localize`） | 同一個 key 可能翻角色卡（安全）也可能翻剛生成的露骨台詞（需原文）。現行架構無法區分 |
| `arc_scene_write`、`story_scene_close`、`story_scene_side_story`、`story_scene_open` | 場景寫作，NSFW 期間可能直接要寫情色場景 |
| `chat_assist`、`prompt_rewrite` | 改寫玩家輸入，輸入可能是露骨內容 |
| `outcome_claim_judge`、`player_knowledge_disclosure` | 判斷類，吃摘要精度會掉 |
| `image_feed`、`image_portrait`、`video_feed`、`video_storyboard` | 非對話生成，但涉尺度判斷 |

灰區的處理方式：**先留著，用 diagnostic export 觀察實際輸入**，確認不含
原文後再逐個加入 allowlist。不靠推測放行。

---

## 6. 前端

`NsfwModeTarget` 設定頁新增一組 checkbox，標題「NSFW 模式期間仍使用一般路由的
任務」。預設全部不勾（= 現行行為）。提供一個「套用建議組合」按鈕，勾選 §5 B 類
的 12 項。

需要同步三個 locale bundle：`en-US.ts`、`ja-JP.ts`、`zh-TW.ts`。

---

## 7. 明確非目標

- 不改 NSFW mode 的 TTL、開關、事件記錄
- 不改 §5 A 類任何 feature 的行為
- 不改 `sanitize_messages_for_tolerance` 本身
- 不改 `content_mode` 不可回填的不變式
- 不動角色卡的 `禁忌`
- 不改資料庫 schema（沿用 `preferences` JSON）
- 不自動放行灰區 feature

---

## 8. 測試計畫

| # | 測試 | 期望 |
|---|---|---|
| T1 | 空 allowlist：NSFW 開啟時所有 feature 走 target | 與現行逐項相同（回歸） |
| T2 | allowlist 含 `schedule_plan`：該 feature 走正常路由，`chat` 仍走 target | `routing_source` 分別為正常值與 `nsfw_mode` |
| T3 | 同一回合的 model 與 reasoning 來自同一 provider | `_maybe_bind_reasoning` 與 `resolve_model_id` 一致 |
| T4 | **安全測試**：allowlist 含某 feature 且正常路由解析到 `anthropic`，`content_mode=NSFW` | tolerance 必須是 `frontier`，NSFW 訊息被清洗 |
| T5 | 未列入 allowlist 的未知 feature | 走 NSFW target（fail-closed） |
| T6 | allowlist 含 A 類 feature（錯誤配置） | 文件標明不支援；測試確認仍可運作但不保證品質 |
| T7 | 舊格式 target（無 `structural_features` 鍵） | 解析為空 tuple，行為不變 |

T4 是本設計的關鍵測試，必須先寫、先紅。

必跑：`tests/unit/test_active_llm_provider.py`（62）、
`tests/unit/test_cloud_active_llm_provider.py`（19）、
`tests/unit/test_nsfw_mode_service.py`、路由相關的 route 測試。

---

## 9. 實作順序

1. 先寫 T4（安全測試），確認在現行碼上失敗
2. 新增 `content_tolerance_for_route`（§4.1）並讓 T4 通過
3. `NsfwModeTarget.structural_features` + 解析／寫入（§4.2）
4. 抽出 `_nsfw_target_for` helper，三處改用（§4.3）
5. T1、T2、T3、T5、T7
6. 前端 checkbox + 三個 locale bundle
7. `docs/atlas/domains/nsfw.md` 的「路由優先序」表更新、`FEATURE_MANUAL.md`、
   `FORK_DELTA.md`（新 F-xx 列）、`IDEAS_BACKLOG.md`（新 I-xx 列）
8. 全套 unit + `atlas_check` + `fork_delta_check`

---

## 10. 風險

| 風險 | 緩解 |
|---|---|
| 分流後露骨原文外流 | §4.1 為第一順位；T4 先寫先紅 |
| 三處分支不一致導致 model/reasoning 混搭 | 單一 helper（§4.3）＋ T3 |
| 誤把 A 類放進 allowlist | 前端標示為進階設定；文件列明後果（記憶變薄） |
| 灰區誤判 | 預設不放行，需實測證據 |
| 舊 target 設定不相容 | 缺鍵即空 tuple，T7 把關 |

---

## 11. 待 owner 決定

1. allowlist 第一批是否就是 §5 B 類的 12 項。
2. 前端是否要提供「套用建議組合」按鈕。
3. 批准後才進入實作；第一步是 T4。
