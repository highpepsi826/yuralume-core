---
doc: glossary
tier: atlas
verified_at_commit: 3fc5836
verified_at: 2026-11-21
sources:
  - src/kokoro_link/domain/entities
  - src/kokoro_link/application/services/feature_keys.py
  - src/kokoro_link/domain/value_objects/content_flow.py
  - src/kokoro_link/application/services/nsfw_mode.py
  - src/kokoro_link/contracts/durable_chat_commands.py
symbols: []
---

# Glossary — 專案詞彙

收錄的是「不查程式碼就看不懂」的專案特有詞彙。一般英文詞（user、message、schedule 的字面意思）不在此列。每條標明它實際出現在哪個檔案；程式識別碼保持英文原文。

本頁只記錄**程式碼中實際存在**的實體與概念。設計文件提到但程式碼沒有的東西會明確標註，不會為了對齊描述而虛構。

---

## 角色與身分

### Character

角色本身。`src/kokoro_link/domain/entities/character.py`（class `Character`）。欄位很多（約 60 個）：人格、興趣、說話風格、狀態、目標、世界觀、身體狀態、disposition 等。同檔另有 `FeatureModelOverride`（單一 feature key 的角色層級 LLM 覆寫，空值回退到全域）與 `CharacterLora`（生圖用的 LoRA 權重參照）。

### OperatorProfile

操作這個 Yuralume 的真人，即「聊天視窗另一側的人」。`src/kokoro_link/domain/entities/operator_profile.py`。目前實質上是 singleton——`DEFAULT_OPERATOR_ID` 指向多數安裝共用的那一列，但 entity 仍保留 `id` 供未來多 operator 部署使用。含 email / password_hash / is_admin 等認證狀態。

### PlayerIdentityCard

玩家身分卡：角色建立向導答案的**可重用範本**。`src/kokoro_link/domain/entities/player_identity_card.py`。每個 (operator, name) 一列。玩家填一次，下個角色可以重複使用。刻意**不屬於角色資料**，它屬於 operator。

### PlayerPersonaNote

玩家宣告的 persona 設定，每個 (character_id, operator_id) 一列。`src/kokoro_link/domain/entities/player_persona_note.py`。定位是「演出授權」：要求角色把它當成既成事實並據此行動。程式碼的 docstring 特別解釋它為何不是 `OperatorPersona` 的一層。

四者關係：`OperatorProfile` 是真人；`PlayerIdentityCard` 是真人給角色的設定範本；`PlayerPersonaNote` 是真人對某個角色宣告的 persona；`Character` 是角色。前三個掛在 operator 下，只有 `Character` 是角色資料。

### OperatorPersona

角色觀察到的 operator 事實累積層。`src/kokoro_link/domain/entities/operator_persona.py`。與 `PlayerPersonaNote`（玩家自述）和 `PersonaCuriosityAttempt`（探索紀錄）刻意分開：這一層是「角色學到的」。

---

## 對話與回合

### Conversation / Message

`src/kokoro_link/domain/entities/conversation.py`。`Conversation` 持有 `messages` 與 `source`（web / telegram / line 等），代表跨來源統一時間軸中的一段。`Message` 是一則訊息，含 `role`、`kind`、`content_mode`、`safe_summary`。同檔的 `MessageKind` 是 LLM context 的過濾分類：`CHAT`、`TOOL_ONLY`（只含工具 payload，從 schedule / arc / proactive context 濾除）、`SCENE_NARRATION`（第三人稱旁白）。

### MessageContentMode

寫入時記錄的內容流標記，`NORMAL` / `NSFW`。`src/kokoro_link/domain/entities/conversation.py`。docstring 明言：**由使用者當下選定的模式決定，不從文字推斷，也不可事後由內容掃描回填**。相關 helper 在 `src/kokoro_link/domain/value_objects/content_flow.py`，該檔開頭也重申「不得長出關鍵字偵測」。

### safe_summary

NSFW 訊息的「安全摘要」欄位。`src/kokoro_link/domain/entities/conversation.py`（`Message.safe_summary`）。用於 hosted 匯入時折疊（D5）：`content_mode='nsfw'` 的訊息若帶 `safe_summary`，匯入時以摘要取代原文；沒有 `safe_summary` 的整列略過。統計與邏輯見 `src/kokoro_link/application/dto/character_backup/manifest.py`（`BackupNsfwCollapseStats`）。

### TurnRecord

單次 LLM turn 的稽核紀錄。`src/kokoro_link/domain/entities/turn_record.py`。記錄 turn **期間發生的事**：完整組裝後的 prompt、原始模型輸出、延遲、token 用量、副作用引用、失敗碼。無論成功失敗都會寫。

### TurnJournal

單次 turn 的**回滾紀錄**。`src/kokoro_link/domain/entities/turn_journal.py`。每個成功的聊天 turn 寫一筆，保存 turn 可能改動的子系統的**turn 前快照**（角色狀態、目標、進行中的 arc、當日排程等），讓 operator 之後能 undo。

### UndoneTurn

undo 之後留下的墓碑。`src/kokoro_link/domain/entities/undone_turn.py`。存在的原因：post-turn 抽取（記憶、情緒事件、promise、狀態建議）在回覆之後才非同步執行，undo 可能在它還在飛的時候落地。這筆紀錄讓後續處理知道這個 turn 已被撤銷。

### TurnRecord / TurnJournal / UndoneTurn 的差別

`TurnJournal` 是 undo 用的**事前快照**；`TurnRecord` 是**過程中**的稽核；`UndoneTurn` 是撤銷之後的**墓碑**。三者共用 `turn_record_id` 串聯。

### DialogueCheckpoint

比原始對話尾段更早的部分的累積摘要。`src/kokoro_link/domain/entities/dialogue_checkpoint.py`。每個 (character_id, operator_id) 一列——正是跨來源統一時間軸用的鍵，因為角色在 web / Telegram / LINE 上是同一個人。表達的是「這個配對的滾動對話摘要，以及它覆蓋到哪裡」。

---

## 記憶與反思

### MemoryItem

長期記憶的單位。`src/kokoro_link/domain/entities/memory_item.py`。domain 層的視圖，儲存 schema 與抽取器輸出都映射到這個形狀。含 kind、salience、tags、embedding、participants、audience、player_knowledge 等。

### Memoir / MemoirEntry / MemoirChapter / MemoirView

玩家可見的回憶頁視圖模型。`src/kokoro_link/domain/entities/memoir.py`。本身不存資料，而是聚合三個既有來源：高 salience 的 `MemoryItem`（含 `relationship_milestone` 錨點）、`SelfReflection` 章節、以及高強度的 `EmotionEvent`。不會為了產生回憶而另開 LLM job；玩家可釘選影響排序，但不能編輯或刪除。`MemoirView` 由 `MemoirService.build_view` 產生，最多兩章（最近一週 + 一月）。

### MemoirPin

玩家對回憶條目的釘選。`src/kokoro_link/domain/entities/memoir_pin.py`。釘選**不改動**底層的 `MemoryItem` / `EmotionEvent` / `SelfReflection`，而是在這張側表存一個指標（source row id + entry kind 判別欄）。

### SelfReflection

自我敘事反思。`src/kokoro_link/domain/entities/self_reflection.py`。dream pass 定期要求 LLM 閱讀高 salience 記憶與近期情緒事件（7 或 30 日窗口），寫成第一人稱短敘事，之後成為 fact-layer prompt block。

### DispositionDriftRecord

`CharacterDisposition` 區間位移的稽核列。`src/kokoro_link/domain/entities/disposition_drift_record.py`。drift judge 在 dream pass 中依冷卻窗口（預設每個維度 30 天）執行，記錄 from_band → to_band、理由與證據引文。

### StateSnapshot

角色狀態每次變更時的快照。`src/kokoro_link/domain/entities/state_snapshot.py`。觸發源可能是 heuristic、LLM 修正、休息回復或手動編輯；記錄情緒、好感、疲勞、信任、能量與 trigger。

### PersonaCuriosity / PersonaCuriosityAttempt

角色對 operator 的好奇探索帳本。`src/kokoro_link/domain/entities/persona_curiosity.py`（class 名為 `PersonaCuriosityAttempt`）。記錄「角色嘗試了解 operator 某件事」這個**過程事件**。刻意與 `OperatorPersona` 分開：嘗試是稽核事實，不是角色記得的關於人的事實。

---

## 未實現的承諾與主動訊息

### DeferredIntent

主動訊息的「動機半衰期」紀錄。`src/kokoro_link/domain/entities/deferred_intent.py`。當 intention_judge 擋下某次 tick（便宜 gate 已通過），judge 識別出的內在動機不會就此消失——以 TTL（預設 24h）持久化，之後以 fact-layer block 重新浮現。

### PendingFollowUp

延遲回覆紀錄。`src/kokoro_link/domain/entities/pending_follow_up.py`。當角色太忙（高 `busy_score`）無法寫完整回覆，ChatService 走兩步路：先給一句簡短的 in-character 確認，再排延遲的完整回覆。`brief_reply` 是玩家已看到的確認，確保延遲回覆不會與它矛盾。

同檔的 `PendingFollowUpKind` 區分兩種存在原因：

- `BUSY_DEFER`——忙完之後欠一個回覆。
- `SCHEDULED_PROMISE`——使用者在未來時刻要求訊息（例如「早上10點叫我起床」）。

### ScheduledPromise

**不是獨立的 entity。** 程式碼中相關的是 `pending_follow_up.py` 裡的兩個類別：

- `ScheduledPromiseObligation`——共享同一個可見排程交付的其中一個承諾。保留個別 promise，使得重複抽取產生一次回呼時，不會丟掉彼此不同的義務。
- `PendingFollowUpKind.SCHEDULED_PROMISE`——上面提到的 kind 列舉值。
- `ScheduledPromiseDuplicateGroup`——共享同一交付時段的 open promise 的唯讀分組（最舊者為 canonical）。**只用於回報**，不代表刪除、取消或合併。

另外有 `ScheduledPromiseComposeInput` / `ScheduledPromiseComposerPort` 在 `src/kokoro_link/application/services/pending_follow_up_dispatcher.py`，那是 composer 的輸入與埠，也不是 entity。

### ProactiveAttempt / proactive dispatcher

`ProactiveAttempt`：單次主動訊息評估的稽核紀錄。`src/kokoro_link/domain/entities/proactive_attempt.py`。dispatcher 每次看一個角色、決定是否發未受催促的訊息，就寫一列；連 no-op 決策（gate 擋下、decider 跳過）也記。

proactive dispatcher：`src/kokoro_link/application/services/proactive_dispatcher.py`。對單一角色協調一次評估：opt-out 短路 → 收集便宜訊號交 gate → 找 eligible binding → 交 decider → 執行決策要求的工具 → 過 outbound honesty gate（宣稱做了工具沒做的外部動作會被扣下）→ 寫入對話並推送。**每一條退出路徑都寫一個 `ProactiveAttempt`**，讓 operator 能回答「為什麼它沒密我」。

### PendingFollowUp vs DeferredIntent

兩者都在「現在不發、以後再說」的空間裡，但不是同一層：`PendingFollowUp` 是**使用者已經收到確認、具體欠一次回覆**的承諾；`DeferredIntent` 是**judge 判斷時機不對而暫時擱置的動機**。

---

## 故事

### StoryArc / StoryArcBeat

多週的故事弧。`src/kokoro_link/domain/entities/story_arc.py`。位於 `CharacterGoal`（使用者輸入的待辦、開放式）與 `StoryEvent`（單日、原子）之間，是驅動角色世界數週的敘事骨幹。有 title / premise / theme 與有序的 beats；beats 在 pending 期間可自由前後移動。

### ArcSeries

已編寫的多模板故事系列。`src/kokoro_link/domain/entities/arc_series.py`（`ArcSeries`、`ArcSeriesMember`、`CharacterSeriesProgress`）。是編寫與執行期的橋：編寫者選一組有序的既有 `ArcTemplate` id，執行期仍然一次只實例化一個正常的 `StoryArc`。

### ArcTemplate

故事弧的藍圖。`src/kokoro_link/domain/entities/arc_template.py`（`ArcTemplate`、`ArcTemplateBeat`、`ArcTemplateBinding`）。純值，以 YAML 編寫於 `src/kokoro_link/data/arc_templates/`；service 層按需把模板實例化為新的弧。`ArcTemplateBinding` 是適合哪些角色的寬鬆提示（空欄位代表不限），用於 picker 的健全檢查，不強制執行。

### StoryEvent

單一角色／單日抽中並展開的故事事件。`src/kokoro_link/domain/entities/story_event.py`。是 gacha 流程的產物：`StoryGachaService.roll` 依世界觀 + 冷卻 + 權重挑 seed，`StoryEventExpander` 請 LLM 展開成 2–3 句的 in-voice 敘事。

### StorySceneSession

玩家拉起的「起幕」場景，從開場到收尾。`src/kokoro_link/domain/entities/story_scene_session.py`。這個 session 開啟期間，一段普通聊天串就被框成場景——角色處於一齣被框定框架中的演出。

### StoryArc / ArcTemplate / ArcSeries 的差別

`ArcTemplate` 是 YAML 藍圖；`ArcSeries` 是模板的有序清單；`StoryArc` 是執行期真正跑著的那一個弧。`StoryEvent` 是弧的單日產物，`StorySceneSession` 是玩家手動拉起的單場演出。

---

## 動態牆與角色社交

### FeedPost / FeedComment / FeedReaction

角色動態牆（Instagram 風格）。`src/kokoro_link/domain/entities/feed_post.py` / `feed_comment.py` / `feed_reaction.py`。`FeedPost` 是角色在 `ProactiveScheduler` tick 中自主發佈的貼文，含一段第一人稱文字、可選圖片，以及指向啟發它的 domain 物件的出處指標。`FeedComment` 是使用者對貼文的留言（Phase A2 只做 user → character）。`FeedReaction` 按讚（Phase A1 只做 likes）。

### CharacterPeerProfile

一個角色對另一個角色的**方向性**穩定知識。`src/kokoro_link/domain/entities/character_peer_profile.py`。以觀察者角色的視角記錄對 peer 的事實。

### CharacterRelationship

operator 核准的**無方向**角色配對關係。`src/kokoro_link/domain/entities/character_relationship.py`（另有 `CharacterRelationshipPerspective`）。`character_a_id` / `character_b_id` 以 canonical 順序儲存，但仍保留方向性欄位，讓 A 看 B 和 B 看 A 可以不同。

`CharacterPeerProfile` 是單向的觀察知識；`CharacterRelationship` 是被核准的成對關係，內含兩個方向的視角。

### CharacterEventInbox / CharacterEventInboxItem

每角色的世界事件收件匣。`src/kokoro_link/domain/entities/character_event_inbox.py`，類別名為 `CharacterEventInboxItem`（模組 docstring 簡稱 InboxItem）。是 curator 把全域 `WorldEvent` 與角色興趣向量比對後的結果。**不是記憶**——餵進 prompt 不會讓角色「記得」這件事。

---

## 路由與模型選擇

### FeatureKey / feature routing

LLM 路由用的 canonical feature key。`src/kokoro_link/application/services/feature_keys.py`。每個輔助 LLM 服務在 container 接線時標上一個 key（例如 `FEATURE_CHAT = "chat"`、`FEATURE_IMAGE_RECOGNITION = "image_recognition"`）。刻意用字串而非 enum，讓 JSON preference 保持可移植；未知 key 視同「無覆寫」，拼錯會安靜降級。

路由解析在 `src/kokoro_link/application/services/active_llm_provider.py`，三層偏好，優先序高的在前：

1. 角色層級 `character.feature_models[key]`——只有呼叫端傳入 character 時才看。
2. 全域 `feature_models`——逐 feature 覆寫。
3. 全域 `active_model`——主模型 picker 寫入。

最後回退到 container 的預設 provider。

### routing_source

解析結果上標記「這次是用哪條路徑選出來的」。`src/kokoro_link/application/services/active_llm_provider.py`（`ROUTING_SOURCE_NSFW_MODE = "nsfw_mode"`、`ROUTING_SOURCE_NSFW_CONTENT = "nsfw_content"`）。其他來源值由 `resolve_routing_source` 產生。用途之一是決定 content tolerance：`src/kokoro_link/domain/value_objects/content_flow.py` 會對這兩個值回傳 `community`。

### content_tolerance（frontier vs community）

prompt 組裝時對訊息內容的容忍度，兩個值：`CONTENT_TOLERANCE_FRONTIER = "frontier"`、`CONTENT_TOLERANCE_COMMUNITY = "community"`。`src/kokoro_link/domain/value_objects/content_flow.py`。預設依 provider 判定：已知 frontier provider（`anthropic`、`gemini`、`google_gemini`、`openai`、`openrouter`、`xai`）為 frontier，其餘（本機／自訂／自架）預設 community。NSFW 模式的內容模式或 `routing_source` 為 `nsfw_mode` / `nsfw_content` 時一律 community。

---

## NSFW 與內容模式

### NSFW mode / NSFW target

使用者範圍的暫時 NSFW 模式。`src/kokoro_link/application/services/nsfw_mode.py`（`NsfwModeService`、`NsfwModeTarget`、`NsfwModeStatus`）。由使用者手動開啟，靠閒置 TTL 惰性過期（預設 30 分鐘）。程式碼定位很清楚：這是**路由與資料流事實，不是內容偵測**。

- NSFW target 是安裝層級的 Admin 設定（community 路由目標），而**啟用狀態**是每位使用者各自的。
- 啟用期間，`ActiveLLMProvider` 會優先走 target，並要求該 provider 已註冊；NSFW 內容需要已設定的 community LLM target，否則報錯而不是 fallback。
- 寫入時的 `content_mode_for_write` 決定 `MessageContentMode`。

---

## 部署與能力

### Cloud mode

`src/kokoro_link/bootstrap/settings.py`（`CloudSettings.enabled`，container 中以 `cloud_mode` 傳遞）。Yuralume Cloud hosted-core 整合總開關。Phase A 只暴露模式與設定，並鎖定自架專屬的本機登入／provider 介面；後續階段才使用 URL 與 token 做聯邦登入與資源路由。許多策略在 `cloud_mode` 為 false 時是 no-op（例如 `src/kokoro_link/domain/services/story_tone_policy.py`），因此自架行為不受影響。`CloudSubscriptionState`（`src/kokoro_link/domain/entities/cloud_subscription.py`）記錄每個 tenant 的訂閱存取狀態與鎖定。

### Durable chat command

前景聊天 turn 的「持久接受」契約。模組 `src/kokoro_link/domain/entities/durable_chat_command.py` 只是 re-export，真正定義在 `src/kokoro_link/contracts/durable_chat_commands.py`（`ChatTurnCommand`、`ChatTurnPhase`、`ChatTurnCommandState`、`DurableChatCommandRepositoryPort` 等）。

重點：契約**只保證收到（acceptance）**，不保證 LLM 已開始或回覆一定會來——直到前景 worker claim 才會。這讓客戶端在請求立刻斷線時仍能拿到誠實的 ACK。`(owner_id, client_message_id)` 唯一且不可變；canonical payload hash 拒絕同 id 不同內容；每個對話只有一個 active command；terminal 列仍可查詢。記憶體 adapter 只供單元測試與本機 harness，不能取代 hosted 部署的 PostgreSQL migration。

---

## 查證結果：不存在或與設計描述不同的詞

- **`ScheduledPromise`**——程式中沒有以此命名的 entity。實際存在的是 `PendingFollowUpKind.SCHEDULED_PROMISE` 列舉值、`ScheduledPromiseObligation`、`ScheduledPromiseDuplicateGroup`，以及 dispatcher 層的 `ScheduledPromiseComposeInput` / `ScheduledPromiseComposerPort`。全部在 `pending_follow_up.py` 與 `pending_follow_up_dispatcher.py`。
- **`InboxItem`**——`character_event_inbox.py` 的模組 docstring 用這個簡稱，但實際 class 名是 `CharacterEventInboxItem`。
- **`PersonaCuriosity`**——entity 檔名是 `persona_curiosity.py`，但 class 名是 `PersonaCuriosityAttempt`。
- **`Memoir`**——沒有名為 `Memoir` 的 class；是 `MemoirEntry` / `MemoirChapter` / `MemoirView` 三個視圖實體。
- **`FeatureKey`**——沒有名為 `FeatureKey` 的 class 或 enum。是一組 `FEATURE_*` 字串常數，見 `feature_keys.py`。
- **`nsfw_target`** 作為值物件欄位名——程式中的型別叫 `NsfwModeTarget`，偏好鍵叫 `nsfw_mode_target`。
- **`MessageContentMode`** 只有 `NORMAL` / `NSFW` 兩個值，沒有第三種或「未設定」狀態；`Message.content_mode` 的欄位預設值是 `MessageContentMode.NORMAL`（`conversation.py`）。
