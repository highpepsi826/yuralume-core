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

這些結構事實的常駐位置是 `docs/atlas/flows/chat-turn.md`「行程如何影響一個
回合」；下表是本設計依賴的摘要。

| # | 事實 | 位置 |
|---|---|---|
| 1 | 忙碌延後不知道介面。`_maybe_defer_reply` 沒有 `presence_frame` 參數，同場回合一樣會被延後 | `chat_service.py:3845`，呼叫點 `:2338`、`:2939` 附近 |
| 2 | 只要當前行程 `busy_score` ≥ 0.7 就會問判斷器 | `chat_service.py:3916`、`busy_defer_policy.py:9` |
| 3 | 判斷器只收到較舊的對話摘要（`older_dialogue_summary`），不知道幾分鐘前還在一來一往 | `infrastructure/busy/llm_decider.py::_build_prompt`、`data/prompts/busy/decider.txt` |
| 4 | 同場 prompt 本來就寫了「洗澡這類時段用演出設界，不是拒絕互動」，但忙碌延後在組 prompt 之前就短路了，這段指引根本沒機會生效 | `sections/dialogue.py:238` `_STAGE_PRESENCE_GUIDANCE` |
| 5 | 行程 prompt 段把當前行程宣告為「唯一真實來源，衝突一律以本段為準」；上一個活動只在當前是空檔時才以「剛結束」顯示一行 | `sections/schedule.py::_render_schedule_block` |
| 6 | 同場是每回合由玩家宣告的，不是持續狀態；沒有任何東西記得「我們正在一起」 | `domain/value_objects/presence_frame.py:8` |
| 7 | **行程已經有一條「跟著對話改」的路徑**：每回合結束後背景執行的 post-turn 處理器可輸出 `schedule_adjustments`（add／remove／modify），由 `ScheduleService.apply_adjustments` 寫回今日行程；新時段與既有時段重疊時，既有時段的開始時間會被往後推 | `data/prompts/post_turn/processor.txt:111`、`chat_service.py:7678`、`schedule_service.py:1472` |
| 8 | 這條路徑的觸發條件是「**僅當使用者或角色明確表達行程變動時**」「不確定就不要提」，預設為空陣列。所以只有對話裡有人明說（「晚點再去洗」「再看一集」），行程才會改；默默繼續原本的活動不會觸發。它也不知道有一段互動正跨越行程邊界 | 同上 `:112-113`、`:140` |
| 9 | 已記憶化（`memorialized`）的活動不會被 modify／remove | `schedule_service.py:1505` 說明、`:1693` |

第 4 點是現象 B 在同場的直接成因：設計意圖早就是「在劇情內處理」，只是被
忙碌延後搶先了。

第 7、8 點解釋了 owner 觀察到的「系統偶爾會改下一個行程來配合正在進行的
活動」：那是 post-turn 的 `schedule_adjustments`，偶爾才發生是因為它只在對話
明說行程變動時才動。

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
    streak_started_at: datetime     # 這段連續互動的起點
    activity_started_during_streak: bool  # 當前行程在 streak_started_at 之後才開始

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

**連續互動的起點（`streak_started_at`）**：從最後一次來回往回走，只要相鄰兩則
`CHAT` 訊息的間隔不超過 `hold`，就屬於同一段；第一個超過 `hold` 的間隔之後那則
訊息就是起點。

為什麼不用「行程是否在上一次來回之後才開始」：那個條件只在切換後的第一回合
成立，角色回一句之後就失效，prompt 又變回「正在洗澡」，瞬移只是晚一回合發生
（owner 2026-11-22 提出的「前一秒還在懷中」案例）。用整段互動的起點，過渡才能
維持到互動結束。

預設聊天窗口只有 8 則訊息，一段長互動的起點會落在窗口之外。若整個窗口都連續，
需要另外讀取更早訊息的**時間戳**（只讀 `created_at` 與 `kind`，不讀內容）來找
起點；實作第 1 步先確認 repository 是否已有合適的查詢，沒有就新增一個唯讀方法。
回溯設上限（建議 6 小時），超過就以上限為起點。

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
- 你目前的活動是在這段對話開始之後才輪到的。  ← activity_started_during_streak 為真時
```

`decider.txt` 增加一條判斷原則：

> 如果下方有『對話狀態』，代表對方不是突然來打擾，而是你們本來就聊到一半。
> 這種情況通常傾向『立即』。真的要去忙，也應該在正常回覆裡把話題收尾、
> 交代要去做什麼，而不是把這一則晾著。只有真的碰不了手機的活動才選『延後』。

上一則回覆的引文：只在該訊息 `content_mode` 為 NORMAL 時附上（截 80 字）；
NSFW 訊息只給時間事實，不給文字，避免把原文送進未必走 NSFW 路由的判斷器。

### 4.3 主 prompt：連續互動期間，場景以對話為準

原則：**連續互動期間，場景以對話為準，行程只是計畫。** 行程段不得把一個在
互動開始之後才輪到的活動寫成「正在做」。

`ScheduleContext` 新增 `ongoing_interaction: OngoingInteraction | None = None`。
為 `None` 時輸出逐字不變，既有 golden prompt 不受影響。

**情況一：互動中，當前行程在互動開始之前就已經在進行。**
行程段維持原樣，只追加一行：

```
互動狀態：你和對方約 N 分鐘前還在對話，這是同一段互動的延續，不是對方重新出現。
```

「忙碌程度」0.6 以上的措辭（「回覆保持簡潔」「之後再詳聊」）改為中性版本：
「手邊有事要做，但你們正聊到一半，依你的性格決定怎麼兼顧」。

**情況二：互動中，當前行程是在互動開始之後才輪到的
（`activity_started_during_streak`）。**
整段互動期間每一回合都這樣渲染，不只第一回合：

- 不輸出「目前活動：… 正在「{當前活動}」」與「忙碌程度」兩行。
- 改為：

```
互動狀態：你和對方從 {streak 起點時間} 起一直在互動，當時你正在「{互動開始時的活動}」。
行程上原定 {時段} 要「{當前活動}」，但這只是計畫——你有沒有動身去做，以你們的
對話內容為準；對話裡沒有發生過的事，就還沒發生。
你此刻身在何處、正在做什麼，延續對話裡最後的場景，不要自行跳到新的地點或活動。
要不要去、何時去，依你的性格和當下氣氛決定：可以再待一下、邀對方一起、
或把話收尾後動身；動身要在對話裡演出來，不能略過。
```

- 行程段表頭的「唯一真實來源」在此情況改為「以下是你今天的計畫；你此刻的
  實際處境見『互動狀態』」。
- 同場時，`_STAGE_PRESENCE_GUIDANCE` 的私密時段那一點（「迴避、請他稍等、
  隔著門說話」）不輸出，因為它預設角色已經獨自在那個私密場景裡。其餘三點保留。
  這需要把 `ongoing_interaction` 也傳進 `DialogueContext`（或由 presence 段讀
  `ctx.schedule`）。

「互動開始時的活動」＝ `streak_started_at` 當下的行程活動，由行程資料按時間
查出（純讀取）。互動跨了多個行程時段時，只提起點那一個與當前這一個，中間的
不列。

角色在對話裡真的動身之後，下一回合 prompt 仍是情況二，但因為指示是「延續
對話裡最後的場景」，他會接著在洗澡。行程與對話在這裡一致，不需要額外狀態。

**例外：當前行程本身就是與玩家的共同活動。** 若當前活動帶有玩家參與的
`participant_refs`（`has_live_operator_commitment` 為真，例如 post-turn 剛寫入的
「一起看電影」），它就是對話談出來的結果，不是與對話衝突的計畫。此時按情況一
渲染（照常寫「正在」），不套用情況二。

### 4.4 與既有 post-turn 行程調整的關係

第一期**不改** post-turn 處理器，但兩者會自然配合：

- 情況二要求角色把去留「在對話裡演出來」（「再五分鐘才去洗」「一起去吧」）。
  這正是 post-turn 的觸發條件——有人明確表達行程變動。所以第一期上線後，
  行程被改寫來配合互動的頻率預期會上升，§11 的「對話與行程落差」會比原先估計
  的小。這是預期，不是保證，上線後以實際行程變動紀錄驗證。
- post-turn 把洗澡往後推之後，下一回合「當前行程」就不再是洗澡，情況二自然
  不成立，prompt 與行程重新一致。
- post-turn 新增了共同活動時，適用上面的例外。

post-turn 是背景執行的，可能晚於下一回合才生效；情況二在這段空窗內提供保護。

### 4.5 玩家消失時

沒有新增任何行為。超過保持時間後 `resolve_ongoing_interaction` 回 `None`，
一切回到現在的樣子：角色走自己的行程，玩家再出現時照現有規則接住，不追問。
這正是要保留的優點。

### 4.6 三個現象各自怎麼被解決

| 現象 | 第一期結果 |
|---|---|
| A 同場共同活動被忘記 | §4.3 情況二 + §4.2(a) |
| A′ 前一秒還在懷中，下一秒隔著浴室門說話 | §4.3 情況二：整段互動期間不把新行程寫成「正在做」，並拿掉「隔著門」指引 |
| B 聊到一半變「等下再回」 | 同場：§4.2(a) 直接消除。Telegram：§4.2(b) + §4.3 |
| C 約會中短暫離開再回來 | 15 分鐘內回來：§4.3 視為同一段互動。超過 15 分鐘：**第一期不處理**，屬第二期 |

## 5. 受影響的元件

| 檔案 | 改動 |
|---|---|
| `application/services/ongoing_interaction.py`（新） | 純函式與常數 |
| `application/services/chat_service.py` | 兩個入口計算 `ongoing_interaction`；傳入 `_maybe_defer_reply` 與 prompt context |
| `contracts/busy_reply_decider.py` | `decide` 新增可選參數 |
| `infrastructure/busy/llm_decider.py` | 渲染「對話狀態」區塊 |
| `data/prompts/busy/decider.txt` | 一條判斷原則 + `${ongoing_interaction_block}` |
| `infrastructure/prompt/sections/context.py` | `ScheduleContext.ongoing_interaction`；presence 段可讀到同一個值 |
| `infrastructure/prompt/sections/schedule.py` | `_render_schedule_block` 的情況一／情況二 |
| `infrastructure/prompt/sections/dialogue.py` | 情況二時不輸出同場指引的私密時段一點 |
| `application/services/schedule_service.py` | 新增唯讀方法：查某一時刻的行程活動（不改 `resolve_current` 簽名） |
| conversation repository（視第 1 步確認結果） | 唯讀：讀取較早訊息的時間戳以找出互動起點 |

不動：domain entity、persistence、migration、前端、pending follow-up 派送。

## 6. 明確非目標

- 不新增任何行程寫入，也不改 post-turn 處理器的 prompt 或觸發條件（第二期）。
  既有的 post-turn 行程調整照常運作。
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
| T2 | `streak_started_at`：連續訊息往回串到第一個超過 `hold` 的間隔；回溯上限。`activity_started_during_streak` 在切換後第二、第三回合仍為真 | 同上 |
| T2b | 起點落在 8 則窗口之外時，能靠時間戳查詢找到 | 同上 |
| T3 | 同場回合 + `busy_score` 0.9 → 不呼叫判斷器、不建延後列、走正常回覆 | `test_chat_service_busy_defer.py` |
| T4 | 同場回合仍會取消既有的延後列 | 同上 |
| T5 | Telegram 回合 + 互動中 → 判斷器收到 `ongoing_interaction_lines`；非互動中 → 空 tuple | 同上 |
| T6 | 判斷器 prompt：有／無「對話狀態」區塊；NSFW 訊息不附引文 | `test_llm_busy_decider.py` |
| T7 | 行程段：`ongoing_interaction=None` 輸出逐字不變；情況一追加一行；情況二不含「正在「{當前活動}」」與「忙碌程度」 | `test_prompt_builder_schedule.py` |
| T7b | 同場 + 情況二：prompt 不含「隔著門」那一點，其餘同場指引仍在 | `test_prompt_builder_presence_frame.py` |
| T7c | 當前活動帶玩家 `participant_refs` 時，即使在互動期間才開始，也按情況一渲染 | `test_prompt_builder_schedule.py` |
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
4. 行程的時刻查詢方法；`ScheduleContext`、行程段與同場指引渲染（§4.3）+ T7、T7b、T8。
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

## 10. 設計變更紀錄

- 2026-11-22（by Claude）：owner 指出「前一秒還在懷中，下一秒隔著浴室門說話」
  更奇怪。確認原設計有兩個缺陷：(1) 行程段仍寫「正在洗澡」，同場指引又鼓勵
  隔著門說話；(2) `activity_changed_since` 只在切換後第一回合成立。改為以整段
  連續互動的起點為基準（`streak_started_at`），並改寫 §4.1、§4.3 及對應測試。

- 2026-11-22（by Claude）：owner 指出系統偶爾會自己改下一個行程來配合進行中
  的活動，要求查證。查明是 post-turn 的 `schedule_adjustments`（§2 第 7–9 點）。
  新增 §4.3 的共同活動例外與 §4.4；第二期的範圍因此改為「讓既有路徑在跨行程
  互動時可靠觸發」，不是新建寫回機制（§12）。owner 同日確認接受第一期的
  對話／行程落差。

## 11. 風險

- **角色永遠不去忙**：玩家一直聊，行程就一直被延後。第一期不寫行程，行程本身
  照常推進，只是角色在對話中「晚一點再去」；長時間後敘事與行程會脫節。可接受，
  第二期處理。
- **prompt 與行程表面上矛盾**：情況二時行程說該洗澡、prompt 說還沒去。其他讀
  行程的功能（主動訊息、feed、行程記憶化）仍會把那個時段當成已發生，事後可能
  出現「我剛洗完澡」而對話裡他其實沒去。第一期接受這個落差，第二期寫回行程時
  一併解決。
- **起點查詢的成本**：只在整個窗口都連續時才多一次唯讀查詢。
- **判斷器多一段輸入**：token 成本略增，只在 `busy_score` ≥ 0.7 且互動中時發生。
- **同場不延後後的私密時段**：完全交給主 prompt 的同場指引演出設界。模型若演得
  太配合（洗澡中仍長談），需要調 `_STAGE_PRESENCE_GUIDANCE`，不在本期範圍。

## 12. 第二期方向（未設計，僅記錄）

寫回行程的機制已經存在（§2 第 7 點），第二期不需要新建，只需要讓它在跨行程
互動時可靠觸發，而不是偶爾：

- 把「互動正跨越行程邊界」這個事實（§4.1 的 `OngoingInteraction`）交給 post-turn
  處理器，讓它在角色沒有明說的情況下，也能判斷是否該把下一個行程延後或把
  進行中的共同活動延長。
- 互動自然結束（超過保持時間）時，把這段時間補記成與玩家的共同活動，供行程
  記憶化使用。
- 需要另外處理：已記憶化活動不可改（§2 第 9 點）、與 I-19、I-27 的關係、
  超過保持時間後回來的約會延續（現象 C）。

第二期會寫行程資料，需要獨立的設計文件與 owner 批准。
