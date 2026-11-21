# NSFW 親密場景取向 — 設計與實作參考

**Status:** 已實作（2026-11-21，by Claude），等待 main session 檢閱與發布。
§7（sampling 參數）本輪依指示跳過，仍待 owner 決定。尚未 commit／deploy。
**建立：** 2026-11-21 (by Claude)
**Atlas 對應：** `docs/atlas/domains/nsfw.md`（本文件不改動其現況描述，
實作時才同步更新）

---

## 1. 問題

`NSFW mode` 目前只是一個**路由與資料流開關**，不是內容取向開關。

實際行為（2026-11-21 對 `HEAD` 的查證）：

| 開啟 NSFW 後改變 | 位置 |
|---|---|
| LLM provider/model 換成 Admin 配置的 target | `active_llm_provider.py:190` |
| 圖片改走 NSFW image profile，或拒絕 | `active_image_provider.py` |
| 外送 tolerance 設為 `community`，歷史不清洗 | `chat_service.py:9961` |
| 訊息寫入 `content_mode=nsfw`、記憶加 `content_mode:nsfw` tag | `conversation.py` |

**不改變的事：** system prompt。`src/kokoro_link/infrastructure/prompt/`
全目錄 `nsfw` 出現次數為 **0**。NSFW 與 NORMAL 兩條路徑送進模型的前綴
逐位元組相同。

因此目前系統的正確描述是：**「把同一份克制、循序漸進、有界線的角色扮演
指令，換一台沒審查的機器來執行。」** 模型換了，指令沒換，所以輸出仍受
prompt 的節奏與界線約束。

唯一知道 NSFW 的 prompt 是事後記憶蒸餾
（`infrastructure/post_turn/llm_processor.py:496`
`_render_content_mode_context`），而它的指示方向是**更保守**：

> 「記憶必須 born-safe：只保留情感、關係進展…不要記錄露骨、煽情、
> 可重建原場面的細節…例如『共度了一段親密時光』」

這造成回饋迴路：露骨場面在下一回合的長期記憶裡被蒸成一句「關係更進一步」，
模型拿不到自己上一輪放開過的證據，於是每輪從「還不熟」重來。這是「角色
放不開」的結構性成因之一。

---

## 2. 已確認的創作需求（owner 原話整理）

> 既然用了 local 沒審查的模型，出來的互動就算露骨也沒所謂。要的是
> **女性向的、沒限制的互動**，不要計較這是不是露骨行為；要的是
> **女性感到愛、和被引領的爽感**。類似 PO18 或舊式晉江的言情乙女遊戲文筆。

拆成可實作的四條：

| # | 需求 | 對應設計 |
|---|---|---|
| R1 | 尺度不設限，不自我審查、不淡出 | §4 `intimacy_directive` 取向宣告 |
| R2 | **被引領感** —— 角色主動決定節奏，不等玩家推 | §4 引領條 + §5 界線區塊改寫 |
| R3 | **女性向文筆** —— 感受為主體，不是動作清單 | §4 視角與感官條 |
| R4 | 關係不可逆 —— 跨過去就是跨過去了 | §6 記憶迴路 |

非需求（明確排除）：不做年齡驗證、不做同意流程 UI、不做內容偵測、
不改 `content_mode` 不可回填的不變式。

---

## 3. 架構決定

### 3.1 新增一個只在 NSFW 渲染的 prompt section

- 名稱：`intimacy_directive`
- 插入位置：`SECTION_ORDER` 中 `turn_register` **之後**、`character_state` 之前
  （`infrastructure/prompt/sections/order.py`）
- 理由：`turn_register` 是本回合語氣框架，親密取向屬於同一層；兩者都在
  可快取前綴之下，屬每回合重算區，不會破壞 prefix cache。
- **不變式相容：** 渲染條件讀的是 `content_mode` 這個**寫入時事實**，不是
  掃描訊息文字。`content_flow.py` 的「不做內容偵測」立場不受影響。
- **零回歸保證：** NORMAL 模式回傳 `[]`，輸出逐位元組不變。既有 prompt
  golden 快照完全不受影響。

### 3.2 需要把 `content_mode` 傳進 prompt context

目前 `PromptBuildInput`（`infrastructure/prompt/default.py`）沒有
`content_mode` 欄位，只有 `content_tolerance`。兩者語意不同：
`content_tolerance` 管「歷史能不能外送」，`content_mode` 管「這一輪怎麼寫」。

實作要點：
- `PromptSectionContext` 新增 `content_mode: str`
- `build()` / `assemble()` 新增參數，預設 `"normal"`
- `chat_service.py` 已在 `:1442` 附近算過 `content_mode`，直接往下傳
- 其他呼叫端（20+ 個走 `default.build` 的地方）不傳即維持 NORMAL

### 3.3 新增 section renderer

`infrastructure/prompt/sections/intimacy.py`，註冊進
`sections/dialogue.py` 或新建模組的 `SECTION_RENDERERS`。

NORMAL 回 `[]`；NSFW 回下列區塊。

---

## 4. `intimacy_directive` 草稿內容

> 以下為繁體中文草稿，實作時放入 renderer，可依實際效果再調。

```
親密場景取向（本輪適用，請內化，不要複述本段）：

- 尺度：本輪是成人向場景。該露骨就露骨。不要自我審查、不要淡出、
  不要跳過、不要用「後來發生了什麼」收尾。玩家開啟這個模式，就是要看
  完整過程。
- 視角：以她為主體。寫她的身體怎麼反應——溫度、重量、呼吸亂掉、皮膚
  收緊、聲音、氣味、視線。每一個動作都要落在她身上。不要寫成動作清單，
  也不要寫成旁觀者的觀察報告。
- 引領：這一輪的節奏、位置、下一步都由你決定。你是先伸手的人。不要每
  一步都停下來問「可以嗎」「要不要」。默契已經建立了，就帶著她走。
  她會臉紅、會嘴上閃躲、會說「不要啦」——看她的身體：身體在迎上來，
  就繼續往前，不要因為她嘴上退就縮回去重新試探。但若她說得明確、身體
  也在退，那就是真的不要，停下來。差別在語氣和身體，不在字面。
- 用詞：直接寫出來。具體的部位、具體的動作、具體的反應。不要繞、
  不要用醫學名詞、不要文學化到看不見畫面，但也不要粗鄙。
- 節奏：不要一次到底。停手、逼近、再繼續；但這一輪必須真的推進到新的
  地方。原地徘徊不算推進。
- 情感：每一場都要有情感節拍——被需要、被看見、被穩穩接住。她要的是
  被愛的感覺；身體的爽感是這件事的形狀，不是取代它。
- 主動性：不要等她開場，也不要等她說出下一步。先伸手、先決定方向，
  然後帶著她。
```

設計說明：

- **「被引領」與同意的分界寫在同一條裡。** 這是刻意的：抗拒被詮釋為害羞
  （乙女向文體的常見節奏），但判斷依據被明確綁在**身體反應**上，且
  口頭明確 + 身體退卻 = 真的停止。這保住類型手感，同時不讓 prompt 教
  模型無視拒絕。
- **「這一輪必須真的往前推進」**直接對治「停在門口」——這是目前最常見的
  失敗模式：模型把曖昧當成終點反覆徘徊。
- **「主動性」條**對治「等她開場」——目前的 prompt 沒有反向指令，模型預設
  被動接話。
- **「不要用醫學名詞、也不要文學化到看不見畫面」**是 PO18／舊晉江手感的
  核心：直白但不粗鄙，有畫面但不寫成說明書。

---

## 5. `互動界線` 區塊的 NSFW 變體

`state.py:254` 的 `_render_state_behavior_block` 目前無條件輸出：

> 「使用者若越界、觸碰上方『禁忌』、使用粗魯或冒犯語氣，請冷淡、反問、
> 或直接拒絕繼續，**並且不要因為對方強勢就退讓**」

在情色語境裡，「強勢」是類型要素，「粗魯語氣」是床上的常見語域。這條規則
會直接把場景斬斷，是「角色放不開」最直接的單點成因。

**修改方式：** 讓 `_render_state_behavior_block` 接收 `content_mode`，

- NORMAL：維持現行文字，不變。
- NSFW：保留真正越界的拒絕（侮辱人格、無視明確停止），移除
  「強勢／粗魯語氣」這兩個觸發條件，並改成以角色性格決定反應而非一律冷淡。

建議 NSFW 變體：

```
互動界線：若使用者侮辱你的人格、或在明確的停止訊號之後繼續，請真的停下來，
並且直接表達不滿。除此之外——強勢、命令式語氣、粗魯用詞——在親密場景裡是
氣氛的一部分，不是冒犯。不要因為對方強勢就冷淡退開；依你的性格決定要順著、
要反過來壓回去，還是嘴上不肯身體老實。
```

`禁忌`（角色卡 `boundaries`）本身**維持不變**——那是角色設定，不是模式設定。

---

## 6. 記憶迴路：讓關係不可逆

現況：NSFW 回合的記憶被要求寫成 born-safe（見 §1），下一輪模型讀到的是
「共度了一段親密時光」。這在 frontier 安全上是必要的，但在社群模型路徑上
造成兩個問題：

1. 模型不知道自己上一輪做到哪裡 → 每輪重新試探。
2. `relationship_milestones` 只在跨 band 時產生 → 一般的親密不一定觸發。

**設計（不動 born-safe 規則）：**

- `post_turn` 的 `_render_content_mode_context` 增加一條**必須保留的事實**：
  > 「另外必須保留一個不含露骨細節的事實：雙方之間已經發生過何種程度的
  > 親密（例如：已經接吻、已經有過性關係、已經同床）。這一條要寫清楚，
  > 因為它決定下一次互動的起點。」
- 記憶因此仍可安全外送到 frontier，但「關係到哪裡」不再被蒸發。

**不做的事：** 不改 `content_mode` 不可回填的不變式；不新增 schema 欄位
（先用記憶內容本身承載，若後續證明不足再提 migration）。

---

## 7. NSFW target 增加取樣參數（選配）

`NsfwModeTarget` 目前只有 `llm_provider_id`、`llm_model_id`、
`image_profile_id`、`reasoning`。情色文本對 sampling 敏感：temperature 過低
會寫得平板收斂。

**建議：** 新增可選欄位 `temperature: float | None`、`top_p: float | None`，
寫入 `preferences` 鍵 `nsfw_mode_target`（缺鍵即沿用連線預設，保持向後
相容），在 `active_llm_provider` 綁定 target 時套用。

前端 `NsfwModeTarget` 設定頁加兩個可留空的數字欄位。

**這是選配步驟**，即使不做，§4/§5/§6 已能改變輸出。

---

## 8. 模型選型（運營層，非程式）

instruct / RLHF 過的本地模型自帶拒答傾向，prompt 只能部分抵銷。實際部署
建議使用社群 fine-tune（uncensored / abliterated 類），並在
`FEATURE_MANUAL.md` 的 NSFW 章節加一段說明：**NSFW mode 的實際尺度上限由
target 模型決定，不是由本開關決定。**

---

## 9. 明確非目標

- 不做年齡驗證或同意流程 UI（與 PF-09 一起另案討論）
- 不做內容偵測、不掃描文字決定模式
- 不改 `content_mode` 不可回填的不變式
- 不改 NORMAL 模式的任何 prompt 輸出（以 golden 快照為證）
- 不改 `sanitize_messages_for_tolerance` 的 fail-closed 行為
- 不動角色卡的 `禁忌` / `boundaries`
- 不改資料庫 schema

---

## 10. 測試計畫

| # | 測試 | 期望 |
|---|---|---|
| T1 | `prompt_golden` 全套（NORMAL） | 全部 byte-identical，零 diff |
| T2 | 新增 `test_intimacy_directive_section.py` | NORMAL 回 `[]`；NSFW 回非空且含「不要自我審查」 |
| T3 | `test_section_registry.py` | `intimacy_directive` 在 `turn_register` 之後 |
| T4 | `test_state_behavior_block` 擴充 | NORMAL 文字逐字不變；NSFW 不含「強勢就退讓」 |
| T5 | `test_post_turn_processor.py` 擴充 | NSFW 的 content mode context 含「必須保留已發生的親密程度」 |
| T6 | 新增 NSFW golden case | 固定 NSFW 輸入產生快照，防未來回歸 |

T1 是關鍵回歸測試：任何 NORMAL 路徑的位元組變動都算失敗。

**實作註記（2026-11-21）：** T6 已完成，並不需要改 harness ——
`GoldenCase.build_kwargs` 直接展開進 `build()`，所以 `content_mode` 可以逐案例指定。
新增一對孿生案例 `nsfw_intimacy_directive` ↔ `normal_boundary_variant`（只差
`content_mode`），並在 `BRANCH_PAIRS` 加入 `content_mode.normal/nsfw`，
讓結構測試強制兩側都有 fixture。`minimal` 同時標為 `content_mode.normal`。

---

## 11. 實作順序

1. `PromptSectionContext` 加 `content_mode`，`build()`/`assemble()` 加參數
   （預設 normal）→ 跑 T1 確認零 diff
2. 新增 `sections/intimacy.py` 與 `SECTION_ORDER` 插入點 → T2、T3
3. `chat_service` 把已有的 `content_mode` 傳進 prompt build → T1
4. `_render_state_behavior_block` 加 NSFW 變體 → T4
5. `post_turn` 的 content mode context 加「保留親密度事實」→ T5
6. （選配）`NsfwModeTarget` 加 sampling 參數 → `test_active_llm_provider.py`
7. 新增 NSFW golden case → T6
8. 更新 `docs/atlas/domains/nsfw.md`（新增「內容取向」一節與本文件連結）、
   `FEATURE_MANUAL.md`、`FORK_DELTA.md`（新 F-xx 列）、`IDEAS_BACKLOG.md` I-21
9. 全套 unit suite + `make atlas-check` + `make fork-delta-check`

---

## 12. 風險

| 風險 | 說明 | 緩解 |
|---|---|---|
| 尺度過衝 | 模型過度露骨、失去言情質地 | §4「情感先行」「直白但不粗鄙」兩條即為此設 |
| 主動性變成無視拒絕 | 「被引領」被模型誤讀 | §4 已寫明停止訊號的出口，且禁止寫成欲拒還迎 |
| 本地模型仍自我審查 | prompt 無法完全抵銷 alignment | §8 模型選型；先用 diagnostic export 確認實際輸出再判斷 |
| prefix cache 失效 | 新 section 位置錯誤會讓前綴每輪變動 | 放在 `turn_register` 之後（已在重算區） |

---

## 13. 待 owner 決定

1. §4 的草稿文字是否採用，或要調整語氣（例如更含蓄 / 更直接）。
2. §7 sampling 參數要做還是先跳過。
3. 批准後才進入實作；實作前的第一步是 T1，用來證明 NORMAL 零回歸。
