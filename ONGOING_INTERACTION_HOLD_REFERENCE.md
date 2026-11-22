# 互動保持（行程切換不凌駕進行中的互動）— 第一期設計參考

**Status:** 設計完成，**等待 owner 批准**。尚未動任何 source。
**建立：** 2026-11-22 (by Claude)
**Backlog：** `IDEAS_BACKLOG.md` I-21
**Atlas 對應：** `docs/atlas/flows/chat-turn.md`、`docs/atlas/change-map.md` #2、#6

---

## 1. 問題

Yuralume 的設定是：玩家隨時出現或消失，角色都能接住，不會追問。這一點要保留。
但行程一切換，就會蓋過正在進行的互動：

- **現象 A（同場）**：正在一起吃飯，行程跳到下一個，角色直接進行新活動，
  忘了正在一起。
- **現象 B（同場或 Telegram）**：上一句還在聊，行程切到忙碌時段（例如洗澡），
  下一句就變成「我正在洗澡，等下再回你」。
- **現象 C（約會）**：約會中玩家短暫離開再回來，行程裡沒有玩家，角色當他不在。

## 2. 調查結果（2026-11-22）

| # | 事實 | 位置 |
|---|---|---|
| 1 | 忙碌延後不知道介面。`_maybe_defer_reply` 沒有 `presence_frame` 參數，同場回合一樣會被延後 | `chat_service.py:3845`，呼叫點 `:2338`、`:2939` 附近 |
| 2 | 只要當前行程 `busy_score` ≥ 0.7 就會問判斷器 | `chat_service.py:3916`、`busy_defer_policy.py:9` |
| 3 | 判斷器只收到較舊的對話摘要（`older_dialogue_summary`），不知道幾分鐘前還在一來一往 | `infrastructure/busy/llm_decider.py::_build_prompt`、`data/prompts/busy/decider.txt` |
| 4 | 同場 prompt 本來就寫了「洗澡這類時段用演出設界，不是拒絕互動」，但忙碌延後在組 prompt 之前就短路了，這段指引根本沒機會生效 | `sections/dialogue.py:238` `_STAGE_PRESENCE_GUIDANCE` |
| 5 | 行程 prompt 段把當前行程宣告為「唯一真實來源，衝突一律以本段為準」；上一個活動只在當前是空檔時才以「剛結束」顯示一行 | `sections/schedule.py::_render_schedule_block` |
| 6 | 同場是每回合由玩家宣告的，不是持續狀態；沒有任何東西記得「我們正在一起」 | `domain/value_objects/presence_frame.py:8` |

第 4 點是現象 B 在同場的直接成因：設計意圖早就是「在劇情內處理」，只是被
忙碌延後搶先了。

## 3. 已確認的方向（owner 2026-11-22）

- 不加玩家手動模式切換。
- 由「最近一次來回對話的時間」推導一個會自動過期的「互動中」狀態。
- 保持時間同場與 Telegram **共用一個值**，預設 15 分鐘。兩個介面的差別在
  「互動中時做什麼」，不在時間長短。
- 分兩期。本文件只涵蓋第一期。

## 4. 核心設計

### 4.1 「互動中」的定義（推導，不落庫）

新增純函式（建議放 `application/services/ongoing_interaction.py`）：

```python
ONGOING_INTERACTION_HOLD = timedelta(minutes=15)

@dataclass(frozen=True, slots=True)
class OngoingInteraction:
    last_exchange_at: datetime      # 上一次角色回覆玩家的時間
    minutes_since: int
    activity_changed_since: bool    # 當前行程是在 last_exchange_at 之後才開始的

def resolve_ongoing_interaction(
    *, recent_messages, current_activity, now, hold=ONGOING_INTERACTION_HOLD,
) -> OngoingInteraction | None: ...
```

成立條件（全部為結構化時間戳比較，不讀訊息文字）：

1. 排除本回合剛寫入的玩家訊息後，窗口內存在一則玩家 `CHAT` 訊息，其後有一則
   角色 `CHAT` 回覆（即至少完成過一次來回）。
2. 該角色回覆的 `created_at` 距 `now` 不超過 `hold`。

來源是既有的跨介面統一窗口（`load_unified_recent_window`），所以 Telegram 聊到
一半轉同場也算連續。主動訊息、`TOOL_ONLY`、`SCENE_NARRATION` 不算來回。
被延後的短回覆（brief ack）**不算**角色回覆，否則一次延後會自己續命。

不成立時回傳 `None`，所有下游行為與現在完全相同。

### 4.2 忙碌延後的兩個改動

`_maybe_defer_reply` 新增 `presence_frame` 與 `ongoing_interaction` 兩個參數，
兩個聊天入口都要傳（串流與非串流）。

**(a) 同場回合不再開新的延後。**
`presence_frame.surface is ChatSurface.WEB_STAGE` 時，在「取消既有延後列」之後
直接回 `None`，走正常回覆。理由是調查第 4 點：同場的設界本來就該在劇情內演出，
而「等下再回你」這種延後訊息在面對面的框架裡不成立。

這一條**不看是否互動中**——玩家剛出現、角色正在洗澡時，也是由主 prompt 的
同場指引處理（隔著門說話、請他稍等）。這比原先討論的範圍略寬，列在 §9 請
owner 確認。

**(b) 文字介面：把「對話正在進行」交給判斷器。**
不加硬規則（專案的 LLM-first 原則）。`BusyReplyDeciderPort.decide` 新增可選參數
`ongoing_interaction_lines: tuple[str, ...] = ()`，由 application 層組好事實句：

```
對話狀態：
- 你們正在一來一往地對話，你上一則回覆在約 3 分鐘前。
- 你當時說的是：「……」          ← 僅在可安全引用時才附，見下
- 你目前的活動是在那之後才開始的。  ← activity_changed_since 為真時
```

`decider.txt` 增加一條判斷原則：

> 如果下方有『對話狀態』，代表對方不是突然來打擾，而是你們本來就聊到一半。
> 這種情況通常傾向『立即』。真的要去忙，也應該在正常回覆裡把話題收尾、
> 交代要去做什麼，而不是把這一則晾著。只有真的碰不了手機的活動才選『延後』。

上一則回覆的引文：只在該訊息 `content_mode` 為 NORMAL 時附上（截 80 字）；
NSFW 訊息只給時間事實，不給文字，避免把原文送進未必走 NSFW 路由的判斷器。

### 4.3 主 prompt：行程切換時的過渡指引

`ScheduleContext` 新增 `ongoing_interaction: OngoingInteraction | None = None`，
`_render_schedule_block` 在它存在時追加幾行（放在行程段內，緊接「忙碌程度」）。
為 `None` 時輸出逐字不變，既有 golden prompt 不受影響。

**互動中、行程沒變：**

```
互動狀態：你和對方約 N 分鐘前還在對話，這是同一段互動的延續，不是對方重新出現。
```

同時，互動中時「忙碌程度」那行的 0.6 以上措辭（「回覆保持簡潔」「之後再詳聊」）
改為中性版本：「手邊有事要做，但你們正聊到一半，依你的性格決定怎麼兼顧」。

**互動中、行程在上次來回之後才切換（`activity_changed_since`）：**

```
互動狀態：你和對方約 N 分鐘前還在對話，當時你正在「{上一個活動}」。
行程上現在輪到「{當前活動}」，但這是原定計畫，不代表你已經丟下對方去做了。
依你的性格和當下氣氛自然過渡：可以晚一點再去、邀對方一起、或先把話收尾再動身；
不要當作對方已經不在，也不要沒有交代就直接變成在做新的事。
```

上一個活動取 `just_finished_activity`（目前只在當前為空檔時才帶入，需要讓
`resolve_current` 在有當前活動時也回傳它——純讀取，不改行程資料）。

這段文字與行程段表頭的「唯一真實來源」並列時，以這段為準；表頭在互動中時
加半句「（下方『互動狀態』另有說明時依其說明）」。

### 4.4 玩家消失時

沒有新增任何行為。超過保持時間後 `resolve_ongoing_interaction` 回 `None`，
一切回到現在的樣子：角色走自己的行程，玩家再出現時照現有規則接住，不追問。
這正是要保留的優點。

### 4.5 三個現象各自怎麼被解決

| 現象 | 第一期結果 |
|---|---|
| A 同場共同活動被忘記 | §4.3 過渡指引 + §4.2(a) |
| B 聊到一半變「等下再回」 | 同場：§4.2(a) 直接消除。Telegram：§4.2(b) + §4.3 |
| C 約會中短暫離開再回來 | 15 分鐘內回來：§4.3 視為延續。超過 15 分鐘：**第一期不處理**，屬第二期 |

## 5. 受影響的元件

| 檔案 | 改動 |
|---|---|
| `application/services/ongoing_interaction.py`（新） | 純函式與常數 |
| `application/services/chat_service.py` | 兩個入口計算 `ongoing_interaction`；傳入 `_maybe_defer_reply` 與 prompt context |
| `contracts/busy_reply_decider.py` | `decide` 新增可選參數 |
| `infrastructure/busy/llm_decider.py` | 渲染「對話狀態」區塊 |
| `data/prompts/busy/decider.txt` | 一條判斷原則 + `${ongoing_interaction_block}` |
| `infrastructure/prompt/sections/context.py` | `ScheduleContext.ongoing_interaction` |
| `infrastructure/prompt/sections/schedule.py` | `_render_schedule_block` 追加行 |
| `application/services/schedule_service.py` | `resolve_current` 在有當前活動時也回傳剛結束的活動（需先確認現有呼叫端） |

不動：domain entity、persistence、migration、前端、pending follow-up 派送。

## 6. 明確非目標

- 不寫入、不延長、不插入任何行程活動（第二期）。
- 不處理超過保持時間後回來的約會延續（第二期，與 I-27 一起考慮）。
- 不處理 I-19（同場聊天時排程約定訊息照發）。`resolve_ongoing_interaction`
  之後可被它重用，但本期不接。
- 不加 Admin 設定頁或玩家可見開關（見 §9）。
- 不改既有延後列的取消邏輯與 `BUSY_FOLLOW_UP_RELEASE_CEILING`。
- 不動任何既有角色、聊天記錄、行程、延後列資料。

## 7. 測試計畫

| # | 測試 | 檔案 |
|---|---|---|
| T1 | `resolve_ongoing_interaction`：窗口內有來回且在保持時間內 → 成立；超時 → `None`；只有主動訊息 → `None`；只有 brief ack → `None`；本回合的玩家訊息不算 | 新 `test_ongoing_interaction.py` |
| T2 | `activity_changed_since`：當前活動 `start_at` 在上次來回之後 → 真 | 同上 |
| T3 | 同場回合 + `busy_score` 0.9 → 不呼叫判斷器、不建延後列、走正常回覆 | `test_chat_service_busy_defer.py` |
| T4 | 同場回合仍會取消既有的延後列 | 同上 |
| T5 | Telegram 回合 + 互動中 → 判斷器收到 `ongoing_interaction_lines`；非互動中 → 空 tuple | 同上 |
| T6 | 判斷器 prompt：有／無「對話狀態」區塊；NSFW 訊息不附引文 | `test_llm_busy_decider.py` |
| T7 | 行程段：`ongoing_interaction=None` 輸出逐字不變；互動中兩種變體的文字 | `test_prompt_builder_schedule.py` |
| T8 | 既有 golden prompt 逐字不變 | `tests/unit/prompt_golden/` |
| T9 | 串流與非串流兩個入口都傳了新參數 | `chat_stream_route_harness.py` 相關測試 |

必跑：`test_chat_service.py`、`test_chat_service_busy_defer.py`、
`test_llm_busy_decider.py`、`test_prompt_builder_schedule.py`、
`test_prompt_builder_presence_frame.py`、`prompt_golden/`、`prompt_sections/`，
以及 `make atlas-check`、`make fork-delta-check`。

## 8. 實作順序

1. `ongoing_interaction.py` + T1、T2。
2. `_maybe_defer_reply` 的同場短路（§4.2a）+ T3、T4。
3. 判斷器 port／adapter／template（§4.2b）+ T5、T6。
4. `resolve_current` 回傳剛結束活動；`ScheduleContext` 與行程段渲染（§4.3）+ T7、T8。
5. 兩個入口接線 + T9。
6. 同 commit 更新：`docs/atlas/flows/chat-turn.md`、`FORK_DELTA.md`（新 `F-16`）、
   `FEATURE_MANUAL.md`、`IDEAS_BACKLOG.md` I-21 狀態、本文件 Status。
7. 發布：app-only，無 migration、無資料寫入。

## 9. 待 owner 決定

1. **同場一律不延後（§4.2a）**。建議採用：範圍比「只在互動中才不延後」略寬，
   但與同場 prompt 既有的設計意圖一致，也更簡單。替代方案是只在互動中才跳過，
   這樣玩家剛出現、角色在洗澡時仍會收到「等下再回」。
2. **保持時間先寫成程式常數（15 分鐘）**。先前我說過做成 Admin 可調；建議先用
   常數試玩，數值確定有調整需要再加設定頁，避免為一個還沒驗證的數字做 UI。
3. **互動中是否也放寬 0.6 以上的「忙碌程度」措辭（§4.3）**。建議採用，否則
   Telegram 上角色仍會被「回覆保持簡潔、之後再詳聊」這句推向收尾。

## 10. 風險

- **角色永遠不去忙**：玩家一直聊，行程就一直被延後。第一期不寫行程，行程本身
  照常推進，只是角色在對話中「晚一點再去」；長時間後敘事與行程會脫節。可接受，
  第二期處理。
- **`resolve_current` 回傳值變動**影響其他呼叫端（proactive、feed 等）。實作第 4
  步先列出所有呼叫端；若有風險，改為新增獨立的讀取方法而不改既有簽名。
- **判斷器多一段輸入**：token 成本略增，只在 `busy_score` ≥ 0.7 且互動中時發生。
- **同場不延後後的私密時段**：完全交給主 prompt 的同場指引演出設界。模型若演得
  太配合（洗澡中仍長談），需要調 `_STAGE_PRESENCE_GUIDANCE`，不在本期範圍。
