# 約定訊息跟上對話 — 設計參考

**Status:** 第 2 版，owner 已批准（2026-11-22，含 Part 2）。source 已實作並通過指定測試；發布紀錄見 `UPDATE_PROGRESS_LOG.md`。真實模型下的表現待 owner 試玩確認。
**建立：** 2026-11-22 (by Claude)；同日依 owner 討論重寫（見 §12）
**Backlog：** `IDEAS_BACKLOG.md` I-19；缺陷 `PENDING_FIXES.md` PF-10
**前置：** `ONGOING_INTERACTION_HOLD_REFERENCE.md`（I-21 第一期的「互動中」推導）、
`ONGOING_INTERACTION_WRITEBACK_REFERENCE.md`（I-21 第二期的「和你一起」標記）
**Atlas 對應：** `docs/atlas/change-map.md` #6「約定訊息到期時怎麼放行」、
「約定改期與提早履行時，哪些東西會動」

---

## 1. 問題

角色答應「到某個時間找你／提醒你」之後，系統會存一則待發的約定訊息，到點就
發。這則訊息不知道在那之後對話裡發生了什麼：

| # | 情境 | 現在的結果 |
|---|---|---|
| 1 | 約 22:00 見面，你 21:55 先來，一路聊過 22:00 | 22:00 另外跳出「我來找你了」 |
| 2 | 約 10:00 見面，你 9:00 就到了，聊一會後沒再說話 | 10:00 照發「我來找你了」 |
| 3 | 約 10:00 叫你起床，你 9:00 說「我起了」 | 10:00 照樣叫你起床 |
| 4 | 約 23/11 10:00，之後改成 24/11 15:00 | 23/11 10:00 照發；24/11 15:00 再發一次 |
| 5 | 你說「不用叫我了」 | 照發 |
| 6 | 約 22:00 提醒吃藥，22:00 時正在聊 | 另外跳出一則提醒，和對話脫節 |

另外，情境 2 與 4 的行程也沒跟上：提早開始的約會在行程上仍停在原時段；改期後
舊日期的活動仍留著。

## 2. 調查結果

結構事實的常駐位置是 `docs/atlas/change-map.md` #6。本設計依賴的摘要：

| # | 事實 |
|---|---|
| 1 | 約定訊息到點就放行，只檢查角色是否存在、是否 frozen |
| 2 | post-turn（每回合結束後整理記憶／行程／新約定的那次模型呼叫）看不到開啟中的約定清單 |
| 3 | 就地改期只靠 `commitment_key`，但沒有任何 prompt 要求模型產生它 |
| 4 | 聊天回合的 prompt 不會列出到期的約定 |
| 5 | 組稿只讀「立約那條 conversation」的摘要，不知道對話是否正在進行，也看不到「和你一起」標記 |
| 6 | `remove`／`modify` 指向未來日子的活動時等同沒做；帶 key 的 `modify` 不能跨日 |
| 7 | 提早到場不會改寫行程（對話沒明說變動、也沒跨越行程邊界） |
| 8 | 把一列往後延的既有寫法會改寫 `scheduled_for`，原約定時間遺失 |
| 9 | 託管環境中，一列這次沒放行，下一次機會是約 15 分鐘一次的 reconciler |
| 10 | 回合復原只快照該 conversation 的開啟列 |

## 3. 設計原則

- **事情發生的那個回合就更新約定**，不等到發送前才回頭查。當下原話就在眼前；
  發送時只剩摘要。
- 判斷交給 LLM（專案的 LLM-first 原則），程式只提供清單與驗證 id。
- 沒有開啟中的約定時，所有 prompt 逐字不變。
- 約定不能無聲消失：每一次結案／取消／改期都記 log，且可由回合復原還原。
- 無 migration，不新增欄位。

## 4. 設計

### 4.1 Part 1 — post-turn 看得到約定，並能更新它（核心）

涵蓋情境 2、3、4、5，以及情境 1 的大部分。

**輸入**：post-turn 的 prompt 新增一個區塊，列出該角色開啟中（`queued`）的
`SCHEDULED_PROMISE`：短 id、約定時間（營運者時區）、`promise_intent`、是否含
媒體交付義務。沒有開啟中的約定時不輸出。

**輸出**：新增欄位 `promise_updates`，每筆 `{promise_id, action, ...}`：

| action | 意思 | 程式動作 |
|---|---|---|
| `fulfilled` | 這件事在對話中已經完成（已經見到面並開始了、已經提醒過、已經回報過） | 該列標 `resolved`，`resolved_message` 記「在對話中履行」與回合識別 |
| `cancelled` | 這件事不需要了（對方說不用了、前提已不存在，例如已經起床） | 該列標 `cancelled` |
| `rescheduled` | 同一件事改到另一個時間，附 `scheduled_for_iso` | 同一列改時間，重算 `dedupe_key`／`delivery_slot_key`，並重新入列到期事件 |

規則：

- `promise_id` 必須是清單裡的 id，否則整筆丟棄（與行程 id 的驗證方式相同）。
- 只在列仍是 `queued` 時寫入；dispatcher 已搶先處理的列不碰。
- 含媒體交付義務的列不接受 `fulfilled`（照片必須真的送出），只接受
  `cancelled`／`rescheduled`。
- `rescheduled` 的新時間必須在未來；同一輪的 `message_promises` 若產生落在
  同一 delivery slot 的新約定，既有的去重會擋下，不會多一列。
- prompt 指示：預設不動；**只有對話明確顯示**已完成、不需要或改期時才輸出。
  「提早見面」的判準是兩人已經實際開始約好的那件事，不是玩家單純傳了一句話。
- 既有的 `commitment_key` 改期路徑保留不動，兩者並存。

**行程對齊**（同一個區塊內的指示，走既有的 `schedule_adjustments`）：

- 見面型約定被判為 `fulfilled`，而今日行程裡有對應的共同活動：對該 id 輸出
  `modify`，把時段改成實際開始的時間。
- 行程上沒有對應活動：`add` 一筆從現在起的共同活動，
  `operator_involvement` 填 `operator_confirmed_shared`。

### 4.2 Part 2 — 未來日子的舊活動可以收掉

涵蓋情境 4 的行程側（PF-10 第 2 點）。

- adjustment 解析：`remove` 指向的 id 屬於未來日子的行程時，保留該活動所在的
  日期，讓 `apply_adjustments` 到那一天的行程去移除。只開放 `remove`，
  `modify` 的跨日搬移不在本次範圍。
- post-turn 的改期規則補一句：原本那天的活動在「未來行程」清單裡時，同樣
  輸出 `remove`。
- 已記憶化的活動不可移除（既有規則）。

### 4.3 Part 3 — 時間到了、約定還沒被結案、剛好正在聊

Part 1 之後，會走到這裡的主要是提醒類（情境 6），以及見面型約定剛好卡在
Part 1 尚未判定的那一兩輪（情境 1 的邊界）。

**3a. 先不另外發**（dispatcher）：`_release_scheduled_promise` 在組稿前判斷
「正在對話」——`resolve_ongoing_interaction` 非 `None`（15 分鐘內有來回），或
最新一則聊天訊息是玩家發的且在 15 分鐘內（回合生成中）。成立則原樣留在
`queued`，不改 `scheduled_for`。讀取失敗視為不在對話，照舊放行。

**3b. 你又說了一句 → 角色在回覆裡自己接上**（聊天回合）：組 prompt 前讀該角色
已到期且仍 `queued` 的約定，加一段「到期的約定」，指示不要另外開場，在這次
回覆裡自然地履行。**結案不在這裡做**，由該回合的 post-turn（Part 1）判斷是否
真的履行了。沒被接上的，下一輪繼續注入。忙碌延後短路的回合不注入。
含媒體交付義務的約定不注入。

**3c. 你沒再說話 → 對話結束後補發**（composer）：組稿多拿到三件事——

1. 對話摘要改讀跨來源統一時間線。
2. 「約定時間到的時候你們正在對話，最後一次來回在 N 分鐘前」：不算遲到，
   不要道歉、不要寫成剛到場。
3. 當前活動帶「和你一起」標記時多一行「這個時段是你們約好一起的活動」。

三者皆為空時，模板輸出與現在相同。補發時間：最後一次來回之後約 15–30 分鐘
（事實 9）。

## 5. 行為對照

| # | 情境 | 改後 |
|---|---|---|
| 1 | 21:55 先來，聊過 22:00 | 21:55 那幾輪就被判為提前履行並結案；22:00 不發。行程上的約會改成從實際開始的時間起算 |
| 2 | 9:00 到了，聊完沒再說話，約 10:00 | 9:00 結案；10:00 不發。行程同上 |
| 3 | 9:00 說「我起了」，約 10:00 叫起床 | 9:00 取消；10:00 不發 |
| 4 | 23/11 10:00 改成 24/11 15:00 | 同一則約定改到 24/11 15:00，只發一次；23/11 的舊活動移除，24/11 新增 |
| 5 | 「不用叫我了」 | 取消 |
| 6 | 22:00 提醒吃藥，正在聊 | 22:00 不另外發；你下一句的回覆裡提醒；提醒過後結案。你沒再說話則約 15–30 分鐘後補發 |
| — | 沒有任何對話 | 不變，準時發 |

## 6. 不做的事

- 不做「發送前再請模型檢查一次是否已履行」的第二道關卡。Part 1 判錯漏掉時，
  訊息會照舊發出（退回現況，不會更糟）。試玩後若漏判常見再加。
- 不處理一般主動訊息（非約定）在對話中發出的情況。
- 不改 15 分鐘保持時間；不改 reconciler 節奏。
- 不做 `modify` 的跨日搬移。
- 不回頭修既有的約定與行程資料。

## 7. 影響的元件

| 檔案 | 改動 |
|---|---|
| `contracts/post_turn.py` | `PromiseUpdate`、`PostTurnResult.promise_updates`、輸入的開啟約定清單 |
| `infrastructure/post_turn/llm_processor.py`、`data/prompts/post_turn/processor.txt` | 約定區塊、輸出欄位與解析、改期規則補句；Part 2 的 `remove` 日期保留 |
| `application/services/chat_service.py` | `_do_post_turn` 讀開啟約定並套用 `promise_updates`；3b 的讀取與注入（兩個入口）；journal 快照擴大到被更新的列 |
| `application/services/schedule_service.py` | Part 2：`apply_adjustments` 處理未來日子的 `remove` |
| `application/services/pending_follow_up_dispatcher.py` | 3a 的判斷；3c 的摘要來源與新輸入 |
| `application/services/ongoing_interaction.py` | 「玩家最新訊息在保持時間內」小函式 |
| `contracts/scheduled_promise_composer.py`、`infrastructure/busy/llm_scheduled_promise_composer.py`、`data/prompts/busy/scheduled_promise_composer.txt` | 3c |
| `infrastructure/prompt/sections/`、`sections/order.py` | 3b 的 prompt 段 |
| `application/services/turn_undo/steps/pending_follow_ups.py`、`turn_journal_snapshots.py` | 復原 |

文件：`docs/atlas/change-map.md` #5、#6、`docs/atlas/flows/chat-turn.md`、
`FEATURE_MANUAL.md`、`FORK_DELTA.md`（新 `F-xx`）、`PENDING_FIXES.md`（PF-10）、
`IDEAS_BACKLOG.md`。

## 8. 風險

- **誤判結案**：模型把還沒完成的約定判成 `fulfilled`／`cancelled`，訊息就不會
  發。緩解：prompt 預設不動、要求明確證據；每次更新記 INFO log（列 id、
  action、回合 id）；回合復原會還原；Admin 的 pending follow-up 頁可查。
- **漏判**：退回現況（訊息照發），3a 仍會擋住對話中途的那一種。
- **post-turn 在背景執行**：結案可能晚於下一回合幾秒。約定剛好在這幾秒內到期
  時，3a 會擋住。
- **回合復原**：post-turn 的更新發生在回合之後；快照必須涵蓋角色全部開啟的
  約定列，不只同一條 conversation（事實 10）。
- **補發延遲**：情境 6 的補發晚 15–30 分鐘。
- **Part 2 動到行程寫入**：只開放未來日子的 `remove`，且 id 必須通過既有驗證。

## 9. 測試

- post-turn 解析：未知 id 丟棄；三種 action；媒體約定拒絕 `fulfilled`；
  無開啟約定時 prompt 逐字不變。
- chat service：三種 action 的落庫；列已非 `queued` 時不寫；`rescheduled` 重算
  key 並重新入列；與同輪 `message_promises` 不產生重複列；worker 路徑
  （`run_post_turn_for_record`）同樣生效。
- 行程：未來日子的 `remove` 生效；已記憶化不可移除；今日行為不變。
- dispatcher：對話中不放行且列不變；玩家訊息未回覆時同上；讀取失敗照舊放行；
  `BUSY_DEFER` 不受影響；補發輸入帶新欄位。
- composer：新欄位皆空時 prompt 逐字不變。
- 聊天 prompt 段：有到期約定才出現；媒體約定不出現；延後短路的回合不注入。
- 回合復原：三種 action 各自還原，包含立約於另一條 conversation 的列。
- 跑 change-map #5、#6、#2 的必跑測試。

## 10. 部署

無 migration、無資料操作。app-only 發布，四個角色換同一個 digest。

## 11. 實作清單

1. Part 1：contract、post-turn 區塊與解析 + 測試。
2. Part 1：`_do_post_turn` 套用、journal 快照、回合復原 + 測試。
3. Part 1：行程對齊的 prompt 指示 + 測試。
4. Part 2：未來日子的 `remove` + 測試。
5. Part 3a：dispatcher 判斷 + 測試。
6. Part 3c：compose 輸入、摘要來源、模板 + 測試。
7. Part 3b：prompt 段與兩個入口 + 測試。
8. 必跑測試全跑。
9. 更新 atlas、`FEATURE_MANUAL.md`、`FORK_DELTA.md`、`PENDING_FIXES.md`、
   `IDEAS_BACKLOG.md`、`.codex-round.md`；`atlas-check`、`fork-delta-check`。
10. commit、push、發布、驗證、記入 `UPDATE_PROGRESS_LOG.md`。

## 12. 設計變更紀錄

- 2026-11-22 第 1 版：只有「對話中不發／回覆裡接上／對話後補發」，結案是
  確定性的（有注入就結案）。
- 2026-11-22 第 2 版（owner 討論後）：
  - owner 指出提早履行超過 15 分鐘的情境（本文件情境 2、3）第 1 版接不住，
    提議發送前檢查約定狀態。改為在事情發生的回合由 post-turn 更新約定
    （Part 1），並成為核心。
  - 結案改由 post-turn 判斷，取消確定性結案。
  - owner 問「和你一起」標記能否取代 15 分鐘判斷：不能（標記表示約好一起，
    不表示人在場；提醒類沒有標記），改為補發組稿的口吻輸入（3c 第 3 點）。
  - owner 同意把行程對齊併入（Part 1 的行程對齊）。
  - owner 問改期：查出 PF-10，約定側併入 Part 1 的 `rescheduled`；行程側為
    Part 2（owner 已確認併入）。
- 2026-11-22 owner 批准第 2 版全部內容，開始實作。
- 2026-11-22 實作完成。實作時的決定：模型看到的約定 id 是前 8 碼；開啟清單與到期
  注入都排除 `resolving` 與 honesty-repair 列；媒體約定以派送端既有的關鍵字 regex
  判斷；`apply_adjustments` 不需改動（本來就依日期分桶），Part 2 只改了解析；
  復原其他 conversation 的約定列時，已被 dispatcher 送出或處理中的不寫回。
