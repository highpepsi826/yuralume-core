# Yuralume Ideas Backlog

This file collects brainstormed ideas and development notes for this local
fork. It is shared by Claude Code and Codex.

## Purpose and Rules

- This is a **backlog, not an approved design**. An entry here does not
  authorize implementation.
- Before implementing an idea, follow `AGENTS.md`: write a dedicated design /
  implementation reference Markdown file, get explicit user approval, then
  implement. Link that file in the idea's `Ref` column and update its status.
- Add new ideas at the bottom of the table with the next ID. Never reuse an ID.
- When changing an entry, update `Status` and `Updated`, and add a line to the
  Change Log marked `(by Claude)` or `(by Codex)`.
- Keep entries short and non-sensitive. Put details in the idea's notes section
  or in its design file.

### Status values

| Status | Meaning |
|---|---|
| `idea` | Raw brainstorm, not yet discussed |
| `discussing` | Scope being discussed with the user |
| `designed` | Design file written, awaiting approval |
| `approved` | Design approved, ready to implement |
| `in-progress` | Being implemented |
| `done` | Implemented, deployed, and verified |
| `parked` | Postponed or rejected (keep the reason) |

### Priority values

Use a rank number (`1` = do first) once priorities are agreed; otherwise `-`.

Rank 1-4 is the near-term set, 5-9 is next, 10-13 is later. See "Priority
Rationale" below. This is a working suggestion, not an approval.

## Backlog

| ID | Idea | Area | Status | Priority | Ref | Updated |
|---|---|---|---|---|---|---|
| I-09 | Improve character context memory in Telegram chats | Telegram / Memory | idea | 1 | - | 2026-10-21 |
| I-07 | Primary/secondary API rotation: fail over to another API on error, optional per feature | Providers | idea | 2 | - | 2026-10-21 |
| I-02 | TTS integration | Voice | idea | 3 | - | 2026-10-21 |
| I-03 | Voice messages in Telegram and web chat | Voice / Telegram / Web | idea | 4 | - | 2026-10-21 |
| I-12 | More detailed player profile fields to improve character interaction | Player profile | idea | 5 | - | 2026-10-21 |
| I-08 | Increase otome feel (乙女感) | Character / Prompt | idea | 6 | - | 2026-10-21 |
| I-13 | Strengthen character worldbuilding | Character / World | idea | 7 | - | 2026-10-21 |
| I-05 | Character can proactively talk during co-presence (同場); player must receive a notification | Co-presence / Notifications | idea | 8 | - | 2026-10-21 |
| I-06 | Co-presence chat usable on mobile | Co-presence / Mobile | idea | 8 | - | 2026-10-21 |
| I-10 | Connect local models besides Strata (e.g. SD/ComfyUI, local LLM) | Providers / Local | idea | 9 | - | 2026-10-21 |
| I-14 | Otome-game style interface game mode | Game UI | idea | 10 | - | 2026-10-21 |
| I-15 | Session/scene boundaries inside one continuous chat thread (場次) | Memory / Telegram | discussing | 1 | - | 2026-10-21 |
| I-01 | Real-time voice conversation | Voice | idea | 11 | - | 2026-10-21 |
| I-04 | Play games / read books / browse web pages together with a character in real time (gaming/reading companion) | Companion | idea | 12 | - | 2026-10-21 |
| I-11 | Real-time generated picture-book stories | Media / Story | idea | 13 | - | 2026-10-21 |

## Priority Rationale

- **1 I-09 memory**: current pain, likely a logic/context-assembly bug rather
  than a model limit. No new dependency. Also blocks I-12 and I-08.
- **2 I-07 API rotation**: provider outages affect every feature; needed as a
  foundation before I-10 (local model with cloud fallback).
- **3-4 I-02 → I-03 TTS then voice messages**: each builds on the previous.
- **5 I-12 player profile**: feeds I-09's name/gender bugs and image
  consistency.
- **6-7 I-08 / I-13**: prompt-content work; most valuable once I-09 stops
  losing context.
- **8 I-05 / I-06 co-presence + mobile**: blocked on the web-vs-app decision;
  needs research first.
- **9 I-10 local models**: depends on I-07 and on the machine being online.
- **10 I-14 otome UI**: depends on I-05/I-06's platform decision.
- **11 I-01 real-time voice**: depends on I-02.
- **12-13 I-04 / I-11**: largest new subsystems, lowest certainty.

## Idea Notes

Add a section per idea when there are details worth keeping
(open questions, constraints, dependencies, related ideas).

Group notes:

- Voice (I-01/I-02/I-03): likely order TTS (I-02) → voice messages (I-03) →
  real-time voice (I-01).
- Co-presence (I-05/I-06): notification channel undecided (web push,
  Telegram, PWA). Must respect the single Telegram polling owner rule.
- Providers (I-07/I-10): both touch provider configuration; consider
  designing together.

### I-01 即時語音對話

- 用戶想法：網上有新 project 可讓 AI 生成實時聊天（例：VivixA1）。想知道用不同的
  AI 組合能否做到差不多的效果。
- 待分析：參考 project 的做法；可用的 AI 組合（STT + LLM + TTS 串流，或原生語音模型）；
  延遲與成本。

### I-02 接駁 TTS

- 用戶想法：為角色們生成各自的聲音。目前只有 ElevenLabs（免費版）和 Sonix。
- 待分析：用線上服務（訓練/複製聲音）還是本地 TTS 模型節省成本；免費額度限制。

### I-03 語音留言

- 用戶想法：Telegram 角色 bot 由 BotFather 建立，現在只有文字和圖片互傳，想加入
  語音互傳。網頁版是否已有此功能有待了解。
- 待分析：現有 Telegram connector 與網頁聊天對語音/附件的支援；依賴 I-02（TTS）和 STT。

### I-04 遊戲/閱讀搭子

- 用戶想法：可跟角色即時玩遊戲、看書、看網頁。方向包括：
  - 參考現有 AI 遊戲搭子（用戶未用過）。
  - 在 Yuralume 內做簡單遊戲（小遊戲、超小型 MMORPG 等）。
  - 後台子程式「陪」玩外部遊戲（限制遊戲類型，AI 要能讀懂畫面並快速回覆）。
- 待分析：三個方向分開評估；外部遊戲需要螢幕擷取 + 視覺模型，延遲與成本是關鍵。

### I-05 同場時角色主動對話

- 痛點：同場聊天在網頁版，關掉頁面就收不到任何消息，角色也不能主動聯絡，失去臨場
  生活感。
- 用戶想過做成 APP，但限制多（用戶用 Apple 手機）。仍在找不同方案。
- 待分析：PWA + Web Push（iOS 16.4+ 加到主畫面後支援）、經 Telegram 通知、原生 APP 的成本比較。

### I-06 手機同場聊天

- 與 I-05 相關。問題：
  - 角色主動對話時，手機能否收到消息？還是只能收到通知後回 APP/網頁回應？
  - 時間停滯感如何解決（玩家不在時，角色的時間/生活是否繼續推進）？
- 仍在找不同方案。

### I-07 主副 API 輪換

- 痛點：現在的 API 經常不穩、斷線。既然已設定多個 API，應可輪換。
- 待設計的問題：
  - 如何判定真的不會再回應（timeout/重試次數），避免重覆回覆？
  - 主 API 掛了，下一個用哪個（優先順序/fallback 鏈）？
  - 不同 API 的功能（例：vision、tool call、上下文長度）是否對得上？
- 功能需可選擇性開啟。需仔細分析設計。

### I-08 增加乙女感（女性向特調）

- 背景：原作者是男生，很多設計偏男性向。已得到允許，在不商用的前提下可隨意修改。
- 用戶想法：在 prompt、語言風格、陪伴功能等各方面改成女性向特調。
- 待分析：盤點現有 prompt / 預設角色 / 功能中的男性向假設；與 I-13、I-14 相關。

### I-09 Telegram 上下文記憶

- 痛點：在 Telegram 多聊幾段後，角色會忘記人設、事件、當前場景、本來在做的事；
  幻覺多（例：玩家稱他「男朋友」，他就一直稱玩家「男朋友」），無視性別。
- 背景：Yuralume 原意是讓玩家可扮演不同角色（他/她/牠/它），但 OOC 和遺忘上下文太嚴重。
- 用戶想法：找機會詳細排查相關 logic。
- 待分析：Telegram 路徑的 context 組裝（歷史長度、摘要、人設/玩家性別注入）；
  可用 diagnostic export 取得實例。

#### 進度（2026-10-21）

- **已定位主因**：`chat_service._RECENT_MESSAGE_LIMIT = 8`，其中最新 3 則保留原文，
  第 4-8 則每輪壓成 ≤600 字摘要，第 9 則以前完全不進 prompt。這是成本控制，
  與模型上下文大小無關（1M 上下文也幫不上）。
- **已啟用 DH3 checkpoint**（2026-10-21，production）：`ENABLED=true`,
  `WINDOW_MESSAGES=30`, `PROMPT_BUDGET_TOKENS=2400`, `BACKLOG_TRIGGER_TOKENS=400`，
  四個 application role 均已生效，六個服務 healthy。無 migration。
  回滾備份：`dh3-enable-backup-20261021.json`。
- **已澄清的誤解**：
  - 記憶本來就是跨平台統一的（網頁 / Telegram / WhatsApp 合併成一條時間線）；
  - DH3 checkpoint 的鍵是 `(character_id, operator_id)`，不是 conversation，
    所以累積摘要是「角色 × 玩家」整體，不是單一平台。
- **待觀察**：`dialogue_checkpoints` 目前 0 行。需 backlog ≥ 400 tokens
  （約 10-20 則）或窗口壓力才會觸發。用戶選擇自然累積，不主動灌訊息。
- **待設計**：是否要在同一條對話線內標記「場次」，見下方 I-15。

#### 進度（2026-10-22）

- **已完成並部署**：
  - **逐行時間錨**（commit `a4951f0`，digest `sha256:7187e024…`）：逐字稿每一行
    超過 30 分鐘就帶 `（約 N 天前）`，用與長期記憶相同的格式化函式。
    解決「昨天的事當成今天的事」「6 小時門檻以下的間隔完全無標記」。
  - **私人 NPC 進入聊天 prompt**（commit `5372ae9`，digest `sha256:22c623fd…`）：
    新增 `companion_roster` 段落，位於 `peer_roster` 之後，渲染
    `Character.companions` 的名稱／關係／描述／性格／關係片段，上限 1200 字。
    之前 companions 只到排程規劃與故事場景，聊天完全看不到。
  - 兩次發佈均驗證：六個服務 healthy、health `status=ok`、schema 未變、
    Telegram 單一 lease 無錯誤、代表性媒體可讀、四個 role log 零錯誤。
- **仍未處理**（下次繼續）：
  1. **玩家稱呼／性別錯亂** — 完全未動。機制為 `OperatorPersona` 自動推斷，
     信心值 < 0.7 的欄位不進 prompt；`player_persona_note` 需玩家手填。
     需先看實際 prompt（diagnostic export 的 `include_prompt`，或本地假資料重現）
     才能判斷是「機制寫錯」還是「資料不足」。
  2. **proactive 訊息辨識** — 時間錨已改善感知，但 `_render_recent_proactive_block`
     仍是反重複框架而非「你剛才問過」，且只取最近 3 條 SENT。
     可考慮加上與逐字稿一致的時間錨。
  3. **場次分界（I-15）** — 用戶決定先不做。
- **觀察項**：`dialogue_checkpoints` 仍為 0 行，屬預期（未達觸發量）。
  若一兩週後仍為 0，需查鏈路是否真的接通。
- **NPC 上限**：`_MAX_COMPANIONS = 12`，Jc 已有 12 位（含墨墨）已滿。
  用戶將自行整理名單，之後再決定是否放寬上限。

### I-10 接駁本地模型

- 用戶想法：研究哪些本地模型適合跑來支援 Yuralume（SD/ComfyUI、local LLM 等）。
- 已有：Cloudflare domain routing、OVH 上自己的 domain。
- 限制：本地電腦不一定長開 → 需要與 I-07 的 fallback 配合（本地離線時自動轉線上）。

### I-11 即時繪本故事

- 用戶想法：參考其他 AI 遊戲項目，隨故事發展即時生成配圖。開一個新 session 讓玩家和
  角色以接龍方式共同創作「繪本故事」。
- 待設計：什麼內容寫進長期記憶？全部、選擇性，還是 summary 後寫入？需再細想。

### I-12 玩家具體設定欄位

- 痛點：現在的玩家設定太單薄。
- 用戶想法：
  - 增加更多玩家設定欄位。
  - 生成圖片時玩家有固定形象，增加代入感。
- 背景：原作者設計是讓角色在聊天中慢慢「了解」玩家、補完「玩家檔案」，但用戶覺得不足夠。
- 待分析：現有玩家檔案結構；手動欄位與自動補完如何並存；與 I-09（性別/稱呼錯誤）相關。

### I-13 強化角色世界觀

- 痛點：現在沒有特別世界觀設定（原因是避免插入太多 token），對想玩特殊世界觀的玩家不友好。
- 用戶想法：至少提供一些常見的特殊世界觀選項（例：西幻、ABO、哨向等），或允許玩家自行補完。
- 待設計：平衡 token 插入與取捨（例：精簡核心設定常駐，細節按需注入）。

### I-14 乙遊介面

- 用戶想法：做另一個類乙遊的 Yuralume 介面與功能，將現有功能重新排版；初期未完善時
  可切回現有介面。逐步把 Yuralume 做成類乙遊的 AI 陪伴遊戲。
- 未決定：留在網頁版還是做 APP（與 I-05/I-06 的決定相關）。

### I-15 場次（session / scene）分界

- 背景：Telegram 每個 chat 只有一條 conversation，永久接續，沒有 `/new`。
  這是刻意的設計（`messaging_dispatcher._ensure_conversation` 綁定後永久重用），
  不是 Telegram 限制。
- 用戶觀察：偶爾早上說一句「早」，下次聊別的話題時角色仍「接著」聊，分不出斷點。
- 已澄清：跨平台跳躍（Telegram → 網頁 → Telegram）本來就是同一條統一時間線，
  不會斷開、不會重複。這是設計本意。
- 待討論的核心權衡：
  - 「場次」是**標記**還是**真的開新對話**？開新對話會讓歷史被切斷，風險高。
  - 是否需要前端入口（例：/new、或 UI 按鈕）讓玩家主動標記？
  - 是否可自動判斷（時間間隔、話題轉換）還是必須玩家手動？
  - 與時間停滯感設計的關係：現有 idle-drift（2 小時）只改情緒，不推劇情。
- 相關：I-09（DH3 checkpoint 已啟用，可能已緩解一部分）。

#### 已定位的三個具體現象（2026-10-21）

1. **昨天的事當成今天的事**
   - `sections/dialogue.py::_format_history_line` 只輸出 `角色：內容`，**逐字稿每一行都沒有時間**。
   - 只有超過 6 小時才插入 `——（中間隔了X）——` 標記。4-5 小時的間隔完全無標記。
   - 對比：長期記憶行有 `memory_time_tag`（「約 2 天前」），但對話逐字稿沒有。

2. **每日小事件隔 4-5 小時回覆就「有這事嗎」**
   - proactive 訊息會寫進 `source="web"` 的 conversation，理論上在統一窗口內。
   - 但 `_render_recent_proactive_block` 的框架是**反重複**（「這些已經送出，不要重問」），
     不是「提醒你剛才說過什麼」。
   - `_load_recent_proactive_messages` 只取最近 3 條 SENT；超過就被擠掉。
   - 待確認：4-5 小時後該訊息是否仍在 30 則窗口內。

3. **伙伴角色（例：甜品店的糰子）被完全忘記**
   - `character_social_knowledge_service._eligible_roster_rows` 會**靜默跳過**：
     - `peer_profile is None` → 跳過
     - `not profile.has_prompt_material()` → 跳過（summary / occupation / haunts /
       habits / relationship_note 全空）
   - 名冊上限 `_ROSTER_TOP_N = 6`、`_ROSTER_MAX_CHARS = 1400`，
     排序 = (最後互動時間, 好感+信任平均)。
   - profile 由 `LLMPeerKnowledgeConsolidator` 從「關係記憶」生成；沒有相關記憶
     就沒有 profile，該伙伴**永遠不會出現在 prompt**。
   - 沒有「玩家在訊息中提到某伙伴 → 按名稱檢索」的機制。

#### 可考慮的修法（未定案）

- **逐字稿加逐行時間錨**：在 `_format_history_line` 前綴相對時間（重用
  `timing_utils.format_relative_past_label`），一次解決現象 1 和 2。
  成本：30 則 × 約 5-8 字。風險：既有 prompt 文字測試需更新。
- **把 6 小時門檻降低**（3-4 小時），只在間隔標記層面。
- **proactive 改為中性框架**：保留反重複，但加上「這是 X 前你主動說的」時間錨。
- **伙伴角色按需檢索**：玩家訊息提到名冊外的名字時，用模糊/語意比對拉出對應
  profile；或取消 `has_prompt_material` 的硬性跳過，改為列出名字 + 關係標籤。
- **取消名冊 6 人上限**（或提高），配合 `_ROSTER_MAX_CHARS` 控制 token。

## Change Log

- 2026-10-21 Created backlog with I-01 to I-14. (by Claude)
- 2026-10-21 Added user's detailed notes for I-01 to I-14. (by Claude)
- 2026-10-21 Ranked I-01 to I-14 by priority; added I-15 (session boundaries)
  and recorded I-09 progress, the DH3 enable, and three located symptoms.
  (by Claude)
