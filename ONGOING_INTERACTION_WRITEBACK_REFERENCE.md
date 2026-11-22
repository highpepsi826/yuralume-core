# 互動保持・第二期：讓行程跟上對話 — 設計參考

**Status:** owner 已批准（2026-11-22，§9 三點全採用建議）。Part B 實作中；Part A 待 Part B 發布後進行。
**建立：** 2026-11-22 (by Claude)
**Backlog：** `IDEAS_BACKLOG.md` I-21
**前置：** `ONGOING_INTERACTION_HOLD_REFERENCE.md`（第一期，已發布 `2aa978a`）
**Atlas 對應：** `docs/atlas/flows/chat-turn.md`「行程如何影響一個回合」§3–§6

---

## 1. 問題

第一期讓「對話」在互動期間不被行程切換打斷，但行程資料本身沒有跟上。留下
三個落差：

- **落差 A（假記憶）**：對話裡角色沒去洗澡，行程上那段洗澡照樣結束，事後被
  寫成「洗過澡」的記憶，角色之後可能說「我剛洗完澡」。
- **落差 B（共同時光沒有紀錄）**：跨行程一起度過的那段時間，行程上沒有任何
  「和玩家一起」的活動，之後的近況、記憶都不知道那段時間是一起過的。
- **落差 C（離開後回來）**：約會中離開超過 15 分鐘再回來，角色當玩家不在。

## 2. 調查結果

結構事實的常駐位置是 `docs/atlas/flows/chat-turn.md` §3–§6。本設計依賴的摘要：

| # | 事實 | 造成 |
|---|---|---|
| 1 | 行程記憶化不讀對話：活動的結束時間一過就寫成「做過了」，之後不可再改 | 落差 A |
| 2 | 對話改寫行程的既有路徑（post-turn `schedule_adjustments`）只在對話明說行程變動時才動，且不知道互動正跨越行程邊界 | 落差 A、B |
| 3 | 聊天 prompt 的行程段不顯示玩家參與：即使當前活動是玩家答應過的共同活動，prompt 也沒有一句說明是和對方一起 | 落差 C |
| 4 | post-turn 在託管環境由 worker 依回合紀錄重建，回合當下的狀態帶不過去 | 實作限制 |
| 5 | 新增活動與既有活動重疊時，後開始的那個會被往後擠短或擠掉 | 可利用 |
| 6 | 「是否與玩家一起」的記憶判斷只看玩家最後一次活躍時間是否落在活動時段內 | 落差 B 的邊界 |

落差 C 的成因比第一期時以為的單純：不是行程裡沒有玩家，而是**就算有，聊天
prompt 也看不到**。

## 3. 設計原則

- 不新建寫回機制，沿用既有的 post-turn `schedule_adjustments` 路徑。
- 判斷交給 LLM（專案的 LLM-first 原則）：程式只提供結構化事實與明確的提問，
  不用關鍵字或硬規則決定「角色去了沒」。
- 沒有跨越行程邊界的回合，所有 prompt 逐字不變。
- 不做 migration，不新增欄位。

## 4. 核心設計

### 4.1 Part A — 跨越行程邊界時，明確要求 post-turn 處理行程

**觸發條件**（結構化，與第一期情況二相同）：本回合處於互動中，且當前行程是在
這段互動開始之後才輪到的，且當前行程不是與玩家的共同活動。

因為 post-turn 可能在 worker 裡執行（§2 第 4 點），這個條件在 `_do_post_turn`
內**重新推導**：用先前訊息加本輪兩則訊息、回合時間與當日行程，呼叫第一期的
`resolve_ongoing_interaction` 與 `schedule_yields_to_conversation`。不改 job
payload。

**成立時**，post-turn prompt 的行程段後面多一個區塊（不成立時不輸出）：

```
互動跨越行程邊界：
- 你們從 {HH:MM} 起一直在互動，當時的活動是「{起點活動}」。
- 行程上原定 {HH:MM}–{HH:MM} 要「{當前活動}」（id={activity_id}），現在是 {HH:MM}。
請依對話內容判斷並用 schedule_adjustments 反映實際情況：
- 角色還沒去做原定活動、仍和對方在一起：
  新增一筆 add，時段從 {當前活動開始時間} 到你估計這段共處會持續到的時間
  （不確定就估到現在之後 30 分鐘），描述你們實際在做的事，
  operator_involvement 填 "operator_confirmed_shared"；
  原定活動若只是延後，對它輸出 modify 改到之後的時段；若這次不做了，輸出 remove。
- 角色已經在對話裡動身去做原定活動：不需要調整，給空陣列。
- 對方一起加入了原定活動：對該 id 輸出 modify，把 operator_involvement 填成
  "operator_confirmed_shared"。
- 看不出來：不要調整。
```

`processor.txt` 的 `schedule_adjustments` 規則另加一句，讓這個區塊成為「僅當
明確表達行程變動時才調整」的例外。

**寫回之後會自然收斂**：新增的共同活動帶玩家參與，第一期的例外條款使下一回合
不再是情況二，prompt 與行程重新一致，這個區塊也不再出現。共同活動到了估計的
結束時間而兩人還在聊，條件會再次成立，post-turn 再延長一次。

**落差 A**：原定活動被 modify 到之後或被 remove，就不會在原時段被記成「做過」。
**落差 B**：新增的共同活動結束後，由既有的記憶化流程寫成共同記憶。

### 4.2 Part B — 聊天 prompt 顯示「這是和對方一起的活動」

`_render_schedule_block` 在當前活動帶有玩家已答應的參與（`operator_confirmed_shared`）
時，於「目前活動」之後加一行。其他情況不輸出，prompt 逐字不變。

依第一期的互動狀態分兩種措辭：

- **互動中**：
  `這個時段是你和對方一起的活動，對方此刻就在你身邊。`
- **不在互動中**（玩家離開一陣子後回來，或約好了現在才出現）：
  `這個時段是你和對方約好一起的活動。對方中途可能離開過，現在出現了——`
  `自然地接續你們正在做的事，不必追問他剛才去了哪裡，也不要當作他是臨時跑來的。`

這直接解決落差 C：只要行程上那段是共同活動（事先約好的約會，或 Part A 寫入
的），玩家離開多久再回來，角色都知道「我們本來就在一起做這件事」。

未答應的邀請（`operator_invite_pending`）與單方面的念頭（`operator_wish`）
**不**顯示這一行，避免把沒約成的事說成一起。

### 4.3 這一期刻意不做的事

- **不回頭改已記憶化的活動**（§2 第 1 點）。互動「開始時」的那個活動通常已經
  記憶化，無法補上「和玩家一起」。Part A 只從當前活動的開始時間往後記。
- **玩家離開後不自動收尾**。共同活動估計到幾點就是幾點；玩家提早消失，行程上
  那段仍算共同活動，直到結束時間。記憶化時由既有的證據判斷決定能否說成一起
  完成。
- **不處理 I-19**（聊天中排程訊息照發）與 **I-27**（玩家不在時的共同生活）。

## 5. 受影響的元件

| 檔案 | 改動 |
|---|---|
| `application/services/chat_service.py` | `_do_post_turn` 內推導跨越狀態並傳給處理器 |
| `contracts/post_turn.py` | `process` 新增可選參數（跨越事實） |
| `infrastructure/post_turn/llm_processor.py` | 渲染「互動跨越行程邊界」區塊 |
| `data/prompts/post_turn/processor.txt` | 新區塊的佔位與一句例外說明 |
| `infrastructure/prompt/sections/schedule.py` | Part B 的一行 |
| `domain/value_objects/ongoing_interaction.py` | 視需要補一個小的結構化型別 |

不動：persistence、migration、`ScheduleService.apply_adjustments` 的規則、
記憶化流程、前端。

## 6. 資料影響（需要 owner 明確同意）

第二期會讓系統**更常寫入角色的今日行程**（新增共同活動、延後或移除原定
活動）。寫入走的是現在就在運作的同一條路徑與同一套規則，沒有新的寫入方式，
也不會動到已記憶化的活動、聊天記錄或角色資料。回合復原（undo）已涵蓋行程
快照，實作時要確認這條路徑的寫入同樣被涵蓋。

## 7. 測試計畫

| # | 測試 |
|---|---|
| T1 | `_do_post_turn` 在跨越條件成立時把事實傳給處理器；不成立時不傳 |
| T2 | worker 入口（`run_post_turn_for_record`）也能推導出相同結果 |
| T3 | post-turn prompt：不成立時逐字不變；成立時含區塊、正確的時間與 activity id |
| T4 | 當前活動已是共同活動時不輸出區塊（收斂） |
| T5 | 處理器回傳 add + modify 時，`apply_adjustments` 的結果：共同活動存在、原定活動被延後；回傳 add + remove 時原定活動消失 |
| T6 | Part B：`operator_confirmed_shared` 時輸出一行，互動中／不在互動中兩種措辭；`invite_pending`、`wish`、無玩家時逐字不變 |
| T7 | 既有 golden prompt 逐字不變 |
| T8 | 回合復原後，本回合由 post-turn 寫入的行程變動被還原 |

必跑：`tests/unit/test_post_turn_processor.py`、`tests/unit/dialogue_checkpoint/`、
`test_schedule_service*.py`、`test_prompt_builder_schedule.py`、`prompt_golden/`、
`prompt_sections/`、`test_chat_service.py`、`test_turn_undo*.py`、
`test_ongoing_interaction.py`，以及兩個檢查器。

## 8. 實作順序

1. Part B（獨立、風險最低）+ T6、T7。
2. `_do_post_turn` 推導跨越狀態 + T1、T2。
3. 處理器 port／adapter／template + T3、T4。
4. 端到端的寫回行為與 undo + T5、T8。
5. 同 commit 更新：atlas `flows/chat-turn.md`、`FORK_DELTA.md`（更新 F-16）、
   `FEATURE_MANUAL.md`、`IDEAS_BACKLOG.md`、本文件 Status。
6. 發布：app-only，無 migration。

## 9. owner 決定（2026-11-22 全部採用建議）

三點皆已批准：同意更常寫入今日行程；Part B 先單獨發布；預設 30 分鐘。

1. **同意第二期讓系統更常寫入今日行程（§6）**。這是本期的核心，不同意就只能
   做 Part B。
2. **Part B 是否先單獨發布**。建議是：它不寫任何資料、只加一行 prompt，卻直接
   解決落差 C，可以先上線試玩，再做 Part A。
3. **共處時間估不出來時的預設**。建議「現在之後 30 分鐘」。太短會頻繁延長
   （每次都是一次寫入），太長則玩家離開後行程上會殘留一段共同活動。

## 10. 風險

- **模型算錯時間或選錯活動**：id 由程式驗證（不在清單內的會被忽略），時間由
  既有規則處理重疊；最壞情況是一筆不理想的今日行程調整，可在行程頁手動改。
- **原定活動被擠掉**：新增的共同活動若蓋過整段原定活動，原定活動會被丟棄
  （§2 第 5 點）。prompt 已要求明確選擇 modify 或 remove，降低意外發生。
- **玩家提早離開**：行程上殘留一段共同活動（§4.3）。影響範圍是之後的近況
  描述，不影響對話。
- **成本**：不增加 LLM 呼叫次數，只在跨越時讓 post-turn prompt 多幾行。
- **第一期尚未試玩確認**：第二期建立在第一期的互動判斷上；第一期若要調整
  （例如保持時間），本期一併受影響。
