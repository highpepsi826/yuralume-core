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
| I-09 | Improve character context memory in Telegram chats | Telegram / Memory | done (core) | 1 | `GENDER_AND_ADDRESS_SEPARATION_IMPLEMENTATION_REFERENCE.md`, `PLAYER_IDENTITY_AND_SETTINGS_PLACEMENT_REFERENCE.md` | 2026-10-24 |
| I-07 | Primary/secondary API rotation: fail over to another API on error, optional per feature | Providers | idea | 2 | - | 2026-10-21 |
| I-02 | TTS integration | Voice | idea | 3 | - | 2026-10-21 |
| I-03 | Voice messages in Telegram and web chat | Voice / Telegram / Web | idea | 4 | - | 2026-10-21 |
| I-12 | More detailed player profile fields to improve character interaction | Player profile | idea | 5 | - | 2026-10-21 |
| I-08 | Increase otome feel (乙女感) | Character / Prompt | idea | 6 | - | 2026-10-21 |
| I-13 | Strengthen character worldbuilding | Character / World | idea | 7 | - | 2026-10-21 |
| I-05 | Character can proactively talk during co-presence (同場); player must receive a notification | Co-presence / Notifications | idea | 8 | - | 2026-10-21 |
| I-06 | Co-presence chat usable on mobile | Co-presence / Mobile | idea | 8 | - | 2026-10-21 |
| I-10 | Connect local models besides Strata (e.g. SD/ComfyUI, local LLM); assist setup for language/voice/video and analyse where local models fit | Providers / Local | idea | 9 | - | 2026-10-24 |
| I-14 | Otome-game style interface game mode | Game UI | idea | 10 | - | 2026-10-21 |
| I-15 | Session/scene boundaries inside one continuous chat thread (場次) | Memory / Telegram | discussing | 1 | - | 2026-10-21 |
| I-01 | Real-time voice conversation | Voice | idea | 11 | - | 2026-10-21 |
| I-04 | Play games / read books / browse web pages together with a character in real time (gaming/reading companion) | Companion | idea | 12 | - | 2026-10-21 |
| I-11 | Real-time generated picture-book stories | Media / Story | idea | 13 | - | 2026-10-21 |
| I-16 | Improve image-generation prompt rules (wrong body features, extra objects) | Media / Prompt | idea | - | - | 2026-10-23 |
| I-18 | Investigate why chat lacks date/time awareness (weekday, upcoming holidays) | Chat / Prompt | idea | - | - | 2026-10-24 |
| I-19 | Scheduled promise messages still fire during an active co-presence chat, breaking immersion | Co-presence / Scheduling | in-progress | - | `PROMISE_DURING_CONVERSATION_REFERENCE.md` | 2026-11-22 |
| I-20 | Maximise existing messaging apps (Telegram/WhatsApp) with mode flags/prefixes before building an APP | Platform / Telegram | idea | - | - | 2026-10-25 |
| I-21 | Schedule slot changes override an ongoing interaction: shared co-presence activity forgotten, or active conversation abruptly ended ("busy, talk later") | Co-presence / Chat / Schedule | in-progress | - | `ONGOING_INTERACTION_HOLD_REFERENCE.md`, `ONGOING_INTERACTION_WRITEBACK_REFERENCE.md` | 2026-11-22 |
| I-23 | Interaction still feels thinner/degrades even with daily Telegram chat | Relationship / Emotion | idea | - | - | 2026-11-01 |
| I-24 | Hidden status bar (status values shown or hidden from the player) | Game UI | idea | - | - | 2026-11-01 |
| I-25 | Menstrual cycle tracking for characters | Character / Health | idea | - | - | 2026-11-01 |
| I-26 | Hypothetical topics drift into being treated as fact within two turns | Chat / Prompt / Memory | idea | - | - | 2026-11-01 |
| I-27 | Opt-in "玩家共同生活": the character lives a daily life with the player even when the player is absent (at least 1 activity/day) | Co-presence / Schedule / Proactive | idea | - | - | 2026-11-07 |
| I-28 | Full roleplay mode: long-form prose with scene description, expression/action beats and inner monologue, interactive | Chat / Prompt / Story | idea | - | - | 2026-11-07 |
| I-29 | Character travels abroad (leisure or business): temporary timezone and an out-of-town self-awareness | Schedule / Travel | idea | - | - | 2026-11-07 |
| I-30 | NSFW mode has no content-direction prompt: output stays restrained because the system prompt never learns the mode is on | NSFW / Prompt | done | - | `NSFW_INTIMACY_DIRECTION_REFERENCE.md` | 2026-11-21 |
| I-31 | NSFW mode reroutes every feature to the target, including structural tasks that do not need the transcript; give those a carve-out back to normal routing | NSFW / Routing | done | - | `NSFW_ROUTING_CARVE_OUT_REFERENCE.md` | 2026-11-22 |
| I-32 | Other NPCs present in a co-presence chat never speak, even when the player addresses them directly; improve without affecting memory | Co-presence / NPC / Prompt | idea | - | - | 2026-11-22 |

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
- Platform strategy (I-20 → I-05/I-06/I-14): try to exhaust Telegram/WhatsApp
  before committing to a separate APP; the mode-flag mechanism is also the
  cheapest form of I-15's scene marker.

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
  1. **玩家稱呼／性別錯亂** — 2026-10-23 已處理主因，見下方 2026-10-23 進度。
  2. **proactive 訊息辨識** — 時間錨已改善感知，但 `_render_recent_proactive_block`
     仍是反重複框架而非「你剛才問過」，且只取最近 3 條 SENT。
     可考慮加上與逐字稿一致的時間錨。
  3. **場次分界（I-15）** — 用戶決定先不做。

#### 進度（2026-10-23）

- **重大發現：Telegram 上玩家的人設被靜默關閉（8 月起至今）**
  - `persona_safe_for_account`（`persona_disclosure_gate.py:29-40`）只在
    `len(allowed_sender_refs) == 1` 時回 True。**空的 allowlist 對收訊是「接受任何人」，
    但在這裡被當成不安全**，於是 Telegram 每一輪都以 `operator_persona_enabled=False`
    送進 chat service（`messaging_dispatcher.py:244`）。
  - 後果（全部無錯誤、無日誌）：`_load_player_persona_note` 回空字串、
    `OperatorPersona` 整段不載入、地址解析不做。玩家的 279 字人設從未進過
    Telegram prompt。
  - 證據：10/19 三份 prompt 對 `157cm`、`杜桃桃`、`IT consultant`、`土生土長`、
    `演出授權`、`對方資料`、`代名詞` 全部 0 命中；只剩 seed 的「稱呼：桃桃」。
  - 人設功能本身 2026-08-23（`ce5bc09`）就上線，用戶已寫了約兩個月。
  - **這是預設設定缺陷**：只補性別欄位（下方 b 項）不會有幫助，因為整份人設被壓掉。
- **已定位並修復的另外三個成因**（用 diagnostic bundle `3fd36fce…`）：
  1. persona layer 1 的欄位字典**根本沒有 gender**，所以講幾次都學不到。
  2. `identity.py` 的「優先使用對方剛剛用的版本」讓模型把句尾的「男朋友」
     讀成玩家自稱，原樣回敬。
  3. 玩家的糾正「我是女的！是女朋友！」被 post-turn 解析成
     `address_changes` 的改名，寫進 seed 與改名記錄（「稱呼：女朋友」）。
- **已部署**（commit `e9339a7`，digest `sha256:7575f048…1769`，四個 app role）：
  - `gender` 成為可學習的 layer-1 欄位，要求 `operator_self` 歸屬
    （「我朋友是女的」不會誤記），同步鏡射到 consolidator 的第二份白名單，
    並渲染進 prompt 與玩家畫像投影；面板與三份 locale 加標籤。
  - 改名要求逐字引文：`source_text` 空白或不在玩家訊息中即丟棄。
  - prompt 新增規則 (f)：陳述／糾正身分屬於身分事實，不算改名。
  - **注意**：以上對 Telegram 的效果取決於 allowlist 修好沒有；allowlist 為空時
    學到的 gender 一樣進不了 prompt。
- **設計與已知限制**：`GENDER_AND_ADDRESS_SEPARATION_IMPLEMENTATION_REFERENCE.md`。
  採 B-lite：逐字引文無法擋住「引用真話但誤判意圖」的情況，靠學到的性別
  事實修正；若日後再發生，才考慮加窄範圍判斷器。
- **待辦（新 session）**：
  - **(0)** ✅ 已完成 2026-10-24：唯讀 SQL 確認 allowlist 為空；提出「讀取被擋、寫入
    未擋」的不對稱才是 10/19 改名真正成因（既非 (A) allowlist 曾填過，也非
    (B) 網頁那一輪）。使用者補上 `allowed_sender_refs=["7434175332"]`，
    `persona_safe_for_account` 恢復 True。
  - **(a)** ✅ 已完成（`32090f1`）：`PromptCustomizationSetting` 移到群組最後。
  - **(b)** ✅ 已完成（`32090f1`）：代名詞輸入寫入 `OperatorProfile.pronouns`。
  - **(c)** ⏸ 使用者決定延後：先看 (b) 上線後是否還需要全域
    `player_persona_note`。目前仍為 `(character_id, operator_id)`。
  - **(d2)** ✅ 已完成（`32090f1`）：`_apply_observed_address_changes` 接上
    `persona_enabled`，讀寫採用同一條規則。
  - **(d1)** ✅ 已完成（`32090f1` + `968a1bd`）：allowlist 單一 sender 提示與
    警告，且折疊卡片上就看得見。

#### I-09 結案（2026-10-24）

- 使用者實測確認：Telegram 上角色未經提示即知道偏好（熱檸檬茶），證明人設
  已進入 prompt，核心症狀解除。
- 剩餘非阻擋項已移至下方「I-09 遺留」。

- **觀察項**：`dialogue_checkpoints` 於 2026-10-23 唯讀查詢已見 1 行（先前為 0），
  鏈路確認接通，維持觀察即可。
- **NPC 上限**：`_MAX_COMPANIONS = 12`，Jc 已有 12 位（含墨墨）已滿。
  用戶將自行整理名單，之後再決定是否放寬上限。

### I-10 接駁本地模型

- 用戶想法：研究哪些本地模型適合跑來支援 Yuralume（SD/ComfyUI、local LLM 等）。
- 已有：Cloudflare domain routing、OVH 上自己的 domain。
- 限制：本地電腦不一定長開 → 需要與 I-07 的 fallback 配合（本地離線時自動轉線上）。
- 補充（2026-10-24，原 I-17 併入）：輔助設定和接駁本地模型（語言 / 聲音 / 影片），
  並分析本地模型可以用在 Yuralume 的什麼地方。
  - 待分析：哪些功能（聊天、記憶整理、出圖、TTS/語音、影片預覽等）適合改用本地模型；
    本機硬件能跑什麼；接駁方式（OpenAI 相容 API、ComfyUI 等）。
  - 相關：I-02/I-03（聲音）。

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

### I-16 改善出圖 prompt 規則

- 目標：改善現在出圖用的 prompt 規則。
- 原因：目前生成的圖有時會畫錯角色身體特徵，或出現多餘的東西。
- 待分析：現有出圖 prompt 的組成方式、角色外觀資料來源、negative prompt 的使用情況。

### I-18 對話缺乏日期時間感

- 目標：查清楚聊天中角色為什麼沒有日期時間感。
- 原因：雖然已設定玩家時區，每日行程也會按當地假日/公眾假期/節日生成，但聊天中
  角色好像連今天星期幾、明天是不是假期都不知道。
- 待分析：聊天 prompt 是否注入當地日期/星期/時間；行程生成用的假期資料是否有傳入
  聊天 context；相關：I-15 現象 1（逐字稿沒有時間錨）。

### I-19 同場聊天時排程訊息照發，打斷臨場感

- 問題：與角色同場聊天時，如果有排程中的等待回覆，系統仍會照發。
- 例子：角色說晚上 10 時找我，我在 21:55 已主動找角色開始聊天；到了 22:00，系統仍
  照傳「我來找你了，你想聊什麼？」之類的句子，打破臨場感。
- 待分析：排程/約定訊息發送前是否檢查當前是否正在對話中，或約定是否已被提前履行；
  相關：COMMITMENT_RECONCILIATION_IMPLEMENTATION_REFERENCE.md（約定同步）、I-05。
- 2026-11-22 調查（by Claude）：放行時不檢查是否正在對話；聊天回合也看不到到期的
  約定。結構事實見 `docs/atlas/change-map.md` #6，設計見
  `PROMISE_DURING_CONVERSATION_REFERENCE.md`（等待 owner 批准）。

### I-20 開發 APP 前先「用盡」現有大眾通訊 app

- 用戶想法：在考慮轉做 APP 之前，先試試用盡 Telegram（或 WhatsApp）這些現成 app 的
  能力。例如現在要區分「同場」或「電話聊天」，就在訊息前面加 flag 來分辨。
- 原因：做 APP 成本高，先驗證玩法；現成 app 已解決通知、語音、桌面/手機同步等問題。
- 待分析：
  - flag 的形式：文字前綴（例：`//同場`）、特殊符號、Telegram 指令（`/copresence`）、
    回覆某條錨定訊息、或按鈕/keyboard。
  - 模式狀態存哪裡：conversation 層的持久 mode，還是每條訊息即時判斷；如何自動離開。
  - WhatsApp 的可行性：官方 Business API 限制多（模板訊息、24 小時窗口），可能要
    第三方 bridge，成本與穩定性待評估。
  - Telegram 的限制：Bot API 不能主動撥號、語音通話不可用；只能靠語音檔交換（見 I-03）。
  - 與 I-05/I-06/I-14 的關係：若 flag 方案可行，可延後自建 APP 的決定；flag 亦是最
    輕量的場次標記（I-15）。
  - 待決定：新增（本項）還是併入 I-06 的「web-vs-app 決定」。

### I-21 行程切換凌駕正在進行的互動

- 共同根源：行程一切換，就蓋過了正在進行的互動。（原 I-22 已併入，I-22 不再使用）
- 現象 A（同場）：我在他的吃飯行程中跟他一起吃飯，但一旦他的行程跳到下一個，
  他就直接進行新活動，忘了正在跟我吃飯。
- 現象 B（同場或 Telegram）：一旦進入他忙碌的行程，明明上一句他還在問我問題挑起
  話題，下一句就回「我正在 xxx，等下再跟你聊這個話題」。
- 待分析：
  - 同場進行中的共同活動是否有被記錄成狀態；行程切換時 prompt 是否只看「當前行程」。
  - 忙碌行程的「延遲回覆/忙碌」規則是否沒有考慮對話正在熱烈進行。
  - 是否讓進行中的互動延長/暫緩行程，或加入過渡（先收尾話題、說明要去忙）。
- 相關：I-19、I-05、I-18（時間感）。
- 2026-11-22 補充（owner 重述，by Claude）：
  - 要保留的優點：玩家隨時出現或消失，角色都能接住，不追問「你去哪了」。
  - 現象 C（約會）：約會中玩家有事離開，角色照自己的行程走；玩家想回來繼續時，
    行程裡沒有玩家，角色當他「不在」。
  - 方向（owner 已同意）：不加玩家手動模式，改由「最近一次來回對話的時間」推導
    一個會自動過期的「互動中」狀態。互動中時行程不硬切；玩家沉默超過保持時間
    就失效，角色回到自己的行程。保持時間同場與 Telegram 共用一個值（預設 15 分鐘）。
  - 調查結果：
    - `_maybe_defer_reply`（`chat_service.py:3845`）沒有收到 `presence_frame`，
      同場回合也會進忙碌延後。只要 `busy_score` ≥ 0.7 就問判斷器。
    - 忙碌判斷器 prompt（`data/prompts/busy/decider.txt`）只收到較舊的對話摘要，
      不知道「上一則還在聊」，也不知道介面是同場。
    - 行程 prompt 段（`sections/schedule.py::_render_schedule_block`）把當前行程
      宣告為「唯一真實來源，衝突一律以本段為準」，行程一切換，上一個共同活動只剩
      一行「剛結束」（且只在當前為空檔時才顯示）。
    - owner 觀察到「系統偶爾會改下一個行程來配合進行中的活動」：那是 post-turn
      處理器的 `schedule_adjustments`（`post_turn/processor.txt:111` →
      `ScheduleService.apply_adjustments`）。偶爾才發生，是因為它只在對話明確
      表達行程變動時才動，預設不動。第二期應強化這條既有路徑，不必新建。
  - 分期：第一期只改判斷與 prompt，不寫行程、無 migration；第二期才讓共同活動
    寫回行程（與 I-27、I-19 一起考慮）。設計見
    `ONGOING_INTERACTION_HOLD_REFERENCE.md`。

### I-23 每天聊但互動仍然變少／降級

- 問題：明明每天在 Telegram 聊天，互動還是會少或降級。
- 初步判讀：與上下文無關（歷史抽取見 I-09 遺留第 7 項），較可能是關係／情緒狀態
  被衰減。`ExponentialDecayEmotionAggregator` 按半衰期把 `affection_delta` /
  `trust` 等事件衰減回基線，聊天密集但單次情緒事件強度不高時，累積會持續被稀釋。
- 待分析：衰減半衰期與基線的實際設定；每日聊天是否會產生任何情緒事件；是否應該
  有「持續互動」的保底或不同曲線；降級是指回覆品質、語氣，還是狀態數值。
- 相關：I-09（不同層：那是上下文，這是狀態）、I-08、I-12。

### I-24 隱藏狀態列

- 用戶想法：做隱藏狀態列。
- 待分析：隱藏的是哪些數值（好感／信任／情緒／行程）；是玩家可切換，還是預設隱藏；
  隱藏後是否仍影響回覆（應該仍然影響，只是不顯示）；與 I-14 乙遊介面的關係。
- 相關：I-14。

### I-25 記生理期

- 用戶想法：讓角色記錄生理期。
- 待分析：需要新的資料模型（週期起日、長度、症狀）；屬於敏感資料，需要明確的
  存取與匯出邊界；是否只對部分角色啟用；與行程（不適/休息）、情緒、prompt 的聯動。
- 現況：目前沒有任何週期資料模型；`health_care` prompt section 只是固定的關心語，
  與生理週期無關。
- 相關：I-12（玩家資料欄位）、I-13。

### I-26 假設性話題兩回合內被當成事實

- 問題：談論「假設」的話題很容易帶偏，聊到第二回合就已經偏成事實的走向，要使用者
  每回合都提醒這是「假設性話題」。
- 初步判讀：兩層都可能有關——對話層沒有標記「這是假設」，記憶抽取層
  （`LLMMemoryConsolidator` 的「融合事實」）也會把假設句寫成事實。
- 待分析：是否在對話中偵測假設語氣並加註；記憶寫入前是否要排除假設句；可參考
  I-09 的逐字引文守衛做法。
- 相關：I-09。

### I-27 玩家共同生活（off-screen 日常模擬）

- 用戶想法：可開啟「玩家共同生活」功能，就算玩家沒找角色，也用 AI 模擬角色跟玩家的日常
  （最低限度一日一個活動）。
- 與 I-05 的分別：I-05 是「同場時角色主動開口並通知玩家」，是單次事件；本項是一條持續的
  off-screen 生活線，玩家不在場也照樣發生，並且會累積成隔天可聊的近況。
- 現有基礎：
  - `ScheduleActivity.participant_refs` 已能標記「與玩家一起」的活動
    （`has_live_operator_commitment` / `has_expired_operator_commitment`）。
  - `proactive_scheduler` 的 tick 已能定時觸發評估；`CharacterLifeContextBuilder`
    已能提供「自己最近的生活」給角色引用。
  - `character_encounter_service` 已有角色之間的碰面模擬，機制可參考。
- 待分析：
  - 開關的粒度：全域／每角色；關閉後既有累積的活動記錄如何處理。
  - 每日最少一個活動是否寫回 schedule（會影響 I-21 的行程切換行為）。
  - 模擬出的活動要不要通知玩家（每日摘要？還是只在對話中被引用）。
  - 成本：每日一個 LLM 活動 × 角色數，與 I-10 本地模型/離線 fallback 的關係。
- 相關：I-05、I-21、I-23、I-04。

### I-28 正統 RP 模式

- 用戶想法：正統的 AIRP mode——長篇、有場景、表情動作、內心戲、互動。
- 現況：已有的相近能力是「起幕」story scene（`story_scene_service`，開場旁白＋
  場景畫面＋角色第一句，落地在一般對話串）與 `fusion_story`；但這是**事件式**的
  場景，不是一個常駐的敘事模式。
- 待分析：
  - 是「每一回合都用長篇敘事」，還是「進入場景後才用」（與現有 story scene 的差別）。
  - 分段規則：場景描寫／角色台詞／內心戲各佔多少；避免每回合都變長篇獨白。
  - 與 Telegram 的相容性：長篇文字在手機訊息介面是否可用（與 I-20 的 flag 構想相關）。
  - 與 I-14 乙遊介面的關係；是否與 I-08 乙女感共用 prompt 規則。
  - token 成本與 I-09 的窗口限制（8 則、3 則原文）是否足夠支撐長篇。
- 相關：I-11、I-14、I-08、I-09。

### I-29 角色旅行／出差的行程與時區

- 用戶想法：角色到國外旅行或工幹的行程——暫時改時區，並讓角色意識到自己 out of town。
- 現況（2026-11-07 調查）：
  - `ScheduleService._resolve_operator_timezone` 只從**玩家**的
    `operator_profile.timezone_id` 取時區（`schedule_service.py:997`），角色本身沒有
    時區／地點欄位；`Character` 也沒有 location 欄位。
  - 因此角色一旦「出國」，其行程、時間錨、問候時間都會維持玩家時區，說不通。
- 待分析：
  - 資料模型：是給角色加 `travel` 期間（目的地、時區、起迄日），還是給 schedule
    加 per-day 時區覆寫。
  - 誰決定旅行：玩家指定、行程 AI 自行產生，還是角色主動提及後由系統建立。
  - 影響面：行程生成、時間錨（I-18）、主動訊息時間（避免半夜傳訊）、
    問候語的「早晚」、航班/時差造成的疲倦。
  - 回程後如何收尾（旅行記憶寫入）。
- 相關：I-18（時間感）、I-13（世界觀）、I-27。

### I-32 同場時其他 NPC 不說話

- 用戶想法：同場聊天時，若有其他 NPC 在場，他們從不開口——即使玩家把話題直接引到
  他們身上也一樣。希望改善，但**不能影響記憶**。
- 「不影響記憶」的初步理解（待與用戶確認）：NPC 的台詞不應被寫成主角色的記憶事實、
  不應污染主角色的長期記憶／關係值，也不應讓 NPC 產生獨立的記憶寫入。
- 待分析：
  - 現況：聊天 prompt 已有 `companion_roster`（私人 NPC 名單，見 I-09 進度），但回覆
    是否被規定只能以主角色身分發言；NPC 在場資訊從哪裡來（排程／故事場景）。
  - 方案方向：A) 主角色回覆內允許轉述／帶出 NPC 台詞（敘事式，單一回覆）；
    B) NPC 以獨立訊息發言（需區分發言者、顯示名稱，及寫入歷史的標記）。
  - 記憶隔離：NPC 台詞在對話歷史中如何標記，讓記憶抽取跳過或只當背景。
  - 觸發條件：玩家點名／提問 NPC 時才發言，避免 NPC 搶話。
- 相關：I-05、I-28、I-09。

## Change Log

- 2026-10-21 Created backlog with I-01 to I-14. (by Claude)
- 2026-10-21 Added user's detailed notes for I-01 to I-14. (by Claude)
- 2026-10-21 Ranked I-01 to I-14 by priority; added I-15 (session boundaries)
  and recorded I-09 progress, the DH3 enable, and three located symptoms.
  (by Claude)
- 2026-10-23 I-09: main cause located from the 10/19 diagnostic bundle and
  fixed/deployed (`e9339a7`): learned `gender` layer-1 field, verbatim-evidence
  guard on address changes, prompt rule (f). Status set to in progress. Two
  follow-ups recorded for a new session: Playground placement in 設定 and the
  missing gender/pronoun input. (by Claude)
- 2026-10-23 I-09 part 2: found the larger cause — an EMPTY Telegram sender
  allowlist makes `persona_safe_for_account` false, so the whole player persona
  block (declared note + learned facts + address resolution) has been silently
  suppressed on Telegram since the feature shipped 2026-08-23. Fix order
  recorded: resolve the allowlist gate first, then (a) Playground placement,
  (b) gender/pronoun input, (c) persona-note scope. (by Claude)
- 2026-10-23 Added I-16 (improve image-generation prompt rules: wrong body
  features, extra objects). (by Claude)
- 2026-10-24 Added I-17 (assist local model setup/connection for language,
  voice, video; analyse where local models fit). (by Claude)
- 2026-10-24 Merged I-17 into I-10; I-17 removed. (by Claude)
- 2026-10-24 Added I-18 (investigate missing date/time and holiday
  awareness in chat). I-17 is retired (merged into I-10). (by Claude)
- 2026-10-24 Added I-19 (scheduled promise messages fire during an active
  co-presence chat). (by Claude)
- 2026-10-25 Added I-20 (maximise Telegram/WhatsApp with mode flags before
  building an APP). (by Claude)
- 2026-10-27 Added I-21 (co-presence activity forgotten on schedule switch)
  and I-22 (busy schedule slot abruptly ends an active conversation).
  (by Claude)
- 2026-10-27 Merged I-22 into I-21 (shared root cause: schedule switch
  overrides ongoing interaction). I-22 is retired and will not be reused.
  (by Claude)
- 2026-11-01 Added I-23 (interaction degrades despite daily chat), I-24
  (hidden status bar), I-25 (menstrual cycle tracking), I-26 (hypothetical
  topics drift into fact). Recorded the Telegram context-loading findings as
  I-09 legacy item 7 (DB-sourced unified window; 8-message window; 3 raw
  tail messages). (by Claude)
- 2026-11-07 Added I-27 (opt-in player co-living simulation), I-28 (full
  roleplay mode), I-29 (character travel with temporary timezone). Recorded
  that schedule timezone currently resolves from the player profile only.
  (by Claude)
- 2026-11-21 Added I-30 (NSFW mode has no content-direction prompt; output
  stays restrained because the system prompt never learns the mode is on).
  Design written to `NSFW_INTIMACY_DIRECTION_REFERENCE.md`, awaiting owner
  approval. (by Claude)
- 2026-11-21 Added I-31 (NSFW routing carve-out for structural features).
  Design written to `NSFW_ROUTING_CARVE_OUT_REFERENCE.md`, awaiting owner
  approval. Records that `content_tolerance_for_llm_provider` returns
  community whenever content_mode is NSFW regardless of provider, so the
  carve-out must fix tolerance derivation first. (by Claude)
- 2026-11-21 I-30 → `in-progress`: implemented `intimacy_directive`, the
  NSFW `互動界線` variant and the post-turn intimacy fact, plus the NSFW /
  NORMAL golden twins. NORMAL prompt verified byte-identical. Not deployed;
  `done` is decided by the main session after release. (by Claude)
- 2026-11-22 I-31 → `in-progress`: implemented the `structural_features`
  carve-out (11 allowlisted keys), `content_tolerance_for_route`, the shared
  `_nsfw_target_for` helper at all four NSFW branch points, the chat-turn
  tolerance by reached provider, the admin checkbox group + "apply
  recommended set", and the three locale bundles. Tests T1–T5, T7 green.
  Not deployed; `done` is decided by the main session after release.
  (by Claude)
- 2026-11-22 I-21 → `designing`: owner restated the problem (added the
  date-continuation case) and agreed on a derived, self-expiring "ongoing
  interaction" state instead of a player-facing mode. Investigation findings
  recorded in the I-21 note. Phase 1 design written to
  `ONGOING_INTERACTION_HOLD_REFERENCE.md`, awaiting owner approval.
  (by Claude)
- 2026-11-22 I-21 → `in-progress`: phase 1 implemented in source (derived
  15-minute ongoing-interaction state; stage turns skip busy-defer; decider
  receives conversation-state lines; schedule prompt yields to the
  conversation). Not committed, not deployed. Phase 2 (schedule write-back)
  not started. (by Claude)
- 2026-11-22 I-21 phase 1 released (`2aa978a`); awaiting owner playtest.
  Phase 2 design written to `ONGOING_INTERACTION_WRITEBACK_REFERENCE.md`,
  awaiting owner approval. New findings recorded in
  `docs/atlas/flows/chat-turn.md` §4–§6 (memorializer ignores the
  conversation; post-turn is rebuilt from the turn record; the chat prompt
  never shows that an activity is shared with the player). (by Claude)
- 2026-11-22 I-21 phase 2 Part B implemented in source (chat prompt shows
  one line when the current activity carries `operator_confirmed_shared`,
  two wordings by ongoing state). Not committed, not deployed; Part A not
  started. (by Claude)
- 2026-11-22 I-21 phase 2 Part A (post-turn re-derives the boundary crossing
  and asks for a schedule write-back) and Part C (schedule UI shows 和你一起)
  implemented in source. Not committed, not deployed. (by Claude)

### I-09 遺留（非阻擋，未排程）

1. **(c) 全域 `player_persona_note`** — 使用者決定延後。目前每個角色一份
   （`(character_id, operator_id)`，上限 500 字），已有一個「玩家身分卡」可
   快照複製，所以重打的成本比想像中低。若日後仍覺麻煩再開設計。
2. **proactive 訊息辨識** — `_render_recent_proactive_block` 仍是反重複框架，
   不是「你剛才問過」，且只取最近 3 條 SENT。時間錨已改善感知，但語意仍未
   對齊逐字稿。這是本來的第 2 項，與人設修復無關。
3. **`dialogue_checkpoints` 觀察** — 2026-10-23 唯讀查詢已見 1 行（先前為 0），
   確認鏈路接通，觀察即可。
4. **B-lite 殘留風險** — 逐字引文守衛擋不住「引用真話但誤判意圖」。目前靠
   學到的性別事實修正；若再發生才考慮加窄範圍判斷器。
5. **`PromptCustomizationSetting` 硬編碼中文字串** — 全檔零 `t()`，不跟隨語系。
   與 I-09 無關但同次發現，需獨立設計檔。
6. **`persona_safe_for_account` 不 trim 空白** — `["  "]` 會被當成一個 sender。
   玩家 UI 產不出這種值（`splitLines` 會 trim），但其他呼叫端可能可以。
7. **Telegram 上下文抽取現況與改善空間**（2026-11-01 調查）——先確認現況：
   - 同場與 Telegram 走同一個 `ChatService`，歷史都由
     `dialogue_window_loader.load_unified_recent_window` 從 DB（conversation
     repository）抽取，跨來源合併成一條時間線並先合併 fan-out 重複行；
     `messaging_dispatcher` 只負責綁定 conversation 與建立 `presence_frame`。
     所以不是由前端傳上下文，也沒有「手機一份、同場另一份」的分叉。
   - `_RECENT_MESSAGE_LIMIT = 8`（`chat_service.py:421`）：預設窗口只有 8 則；
     只有 DH3 checkpoint 啟用時才改用較寬的 `dialogue_checkpoint.window_limit`。
   - `PROMPT_RAW_TAIL_MESSAGES = 3`（`dialogue_checkpoint/window.py:36`）：prompt
     只保留最後 3 則原文，更早的會被壓成摘要。
   - 待分析：8 則對「每天聊」是否太窄；3 則原文是否讓話題在兩三回合內失去細節；
     window_limit 的實測值與 token 成本；是否要按對話密度自適應。
- 2026-11-22 Added I-32 (other NPCs present in a co-presence chat never speak,
  even when addressed; improve without affecting memory). (by Claude)
- 2026-11-22 I-19 → `designing`: investigated the scheduled-promise release
  path; design written to `PROMISE_DURING_CONVERSATION_REFERENCE.md`, awaiting
  owner approval. (by Claude)
- 2026-11-22 I-19 design rewritten (v2): post-turn sees open promises and can
  mark them fulfilled / cancelled / rescheduled; covers early arrival and
  rescheduling; PF-10 recorded. Still awaiting owner approval. (by Claude)
- 2026-11-22 I-19 → `in-progress`: owner approved design v2 including Part 2.
  (by Claude)
