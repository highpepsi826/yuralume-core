# Prompt Playground 中文方案

## 目的

提供一個給管理員與玩家測試 Prompt Studio 修改效果的獨立 Playground。兩種角色都能建立自己的 Draft、選擇現有角色、帶入目前遊玩進度的唯讀快照，輸入測試訊息並比較目前有效版本與 Draft 版本的角色回覆。

這個功能的定位是「預覽一次可能的模型輸出」，不是另一個正式聊天入口。它不得寫入正式遊戲資料，也不得觸發任何角色自主行為。

## 使用情境

玩家修改「聊天回覆語氣」模板後，選擇自己的角色，帶入目前進度，輸入一段測試訊息，例如「今天有點累」，立即比較角色回覆是否符合期待。

管理員可在 Prompt Studio 編輯核心模板草稿後，以同一角色和同一份快照比較已發布版本與草稿版本的結果，不必每次微調都先影響所有玩家。玩家也可對可編輯的五份 style template 建立私人草稿，在不改變既有覆寫前先比較效果。

## 首版範圍

首版只測試「聊天文字回覆」。不在首版加入圖片、短影片、LumeGram 發文、留言、主動訊息、工具呼叫或故事寫作。

原因是聊天測試可以完整驗證最常調整的角色語氣與上下文，且能清楚保證沒有副作用。媒體和主動行為有額外成本、非同步工作、外部 provider 與狀態判斷，應在聊天 Playground 穩定後另行設計。

## 介面方案

入口放在 Prompt Studio：

- 玩家設定頁：在五個可改風格模板區塊上方加入「開啟測試場」與 Draft 狀態。
- 管理員 Prompt Studio：頁首加入「開啟 Playground」。

頁面採雙欄或上下兩區，避免需要反覆捲動：

1. 上方固定為測試設定與輸入：角色、是否帶入目前進度、測試訊息、模板來源。
2. 下方為角色回覆結果與本次套用資訊。

控制項：

- 角色選擇器：僅列出玩家擁有的角色；管理員可選全部角色。
- 「帶入目前進度」開關：預設開啟。
- 測試訊息輸入框：上限建議 2,000 字元。
- 模板來源：
  - 目前有效版本：目前 DB 中已套用給此玩家的管理員／玩家有效覆寫。
  - Draft 版本：目前登入者在 Prompt Studio 儲存、但尚未發布的私有草稿；只用於比較，不套用給任何其他人。
- 執行測試按鈕。
- 清除本頁測試紀錄按鈕。

結果顯示：

- 已發布版本與 Draft 版本的角色回覆文字，左右並排顯示。
- 角色、執行時間、模型／provider 名稱、有效 Prompt hash 的短版識別。
- 「帶入內容」摘要，例如：角色卡、最近 12 則正式對話、目前活動、近期行程、故事線、長期記憶數量。摘要只列類別與筆數，不顯示完整私密 Prompt。
- 測試失敗時顯示一般化錯誤，不顯示 provider key、原始 request 或完整內部 prompt。

本頁的對話氣泡只存在瀏覽器記憶體。重新整理或離開頁面即清除；首版不提供保存、匯出或分享測試紀錄。

## Draft 與發布流程

Draft 是登入者私有資料；每位玩家或管理員、每個允許編輯的模板各有一份 Draft。Draft 存在 DB 的獨立草稿記錄中，但不是有效覆寫，不會被各服務每 10 秒的有效覆寫同步機制讀取，也不會改變任何人「還原目前預設」的目標。

Draft 的操作只放在 Prompt Studio。切換「載入 Draft」或「檢視目前有效版本」只改變編輯器正在顯示的內容，不能隱含儲存、發布或捨棄任何 Draft。沒有 Draft 時，編輯器先載入目前有效版本；首次按「儲存 Draft」才以目前文字建立私人 Draft。

管理員頁每個模板必須提供以下明確控制：

- `儲存 Draft`：更新該管理員自己尚未發布的草稿。
- `載入 Draft`：將已存 Draft 載入編輯器，繼續修改；有 Draft 時選取模板預設載入它。
- `檢視已發布版本`：將目前全站有效版本載入編輯器作檢視與比較，不改變 Draft。
- `查看差異`：清楚比較目前全站已發布版本與該管理員的 Draft。
- `捨棄 Draft`：刪除 Draft，編輯器回到目前全站已發布版本。
- `正式發布 Draft`：將 Draft 寫成全站有效覆寫；發布成功後清除 Draft 或標示它已發布。

玩家頁每份可編輯 style template 提供同一組完整操作，但名稱與影響範圍改為：

- `儲存 Draft`：更新該玩家自己尚未發布的草稿。
- `載入 Draft`：將已存 Draft 載入編輯器繼續修改；有 Draft 時選取模板預設載入它。
- `檢視目前有效版本`：將該玩家目前實際會使用的有效版本載入編輯器作檢視與比較，不改變 Draft。
- `查看差異`：清楚比較目前有效版本與該玩家的 Draft。
- `捨棄 Draft`：刪除 Draft，編輯器回到目前有效版本。
- `發布 Draft`：只寫入該玩家自己的有效覆寫，絕不改變全站設定。

「查看差異」只可讀取目前有效內容與私人 Draft；若尚無 Draft，按鈕顯示不可比較的原因，不能把兩份相同的有效版本當作差異結果。

發布語意依權限不同：

| 操作者 | 可建立 Draft 的模板 | 「發布 Draft」的結果 |
| --- | --- | --- |
| 玩家 | 五份可編輯 style template | 寫入該玩家自己的有效覆寫；只影響該玩家後續生成。 |
| 管理員 | 所有已登錄模板 | 寫入全站已發布覆寫；各角色服務約 10 秒內套用。 |

管理員發布後，玩家「還原目前預設」會回到新的管理員已發布版本。玩家發布後，只有該玩家的有效覆寫更新；其他玩家和管理員已發布版本均不變。

Playground 不提供正式發布按鈕。它可以顯示「回到 Prompt Studio 發布」連結，但不應讓測試頁直接改變有效 Prompt，避免把評估與變更混在同一個操作面。

發佈後，下次進入 Playground：

- 左側「目前有效版本」是剛剛發布後該登入者實際會使用的新版本。
- 右側「Draft 版本」是該登入者其後新建立、尚未發布的草稿。
- 若沒有新 Draft，右側明確顯示「尚無 Draft 可比較」，不再執行第二次模型呼叫，也不以兩個相同的已發布版本冒充比較結果。

建立新 Draft 時，預設從當下「目前有效版本」複製。對玩家而言，這個基礎已包含自己的已發布覆寫、管理員已發布覆寫與內建模板；對管理員而言，這個基礎是全站已發布覆寫與內建模板。若日後需要比較歷史版本，應另做版本歷史／回復功能，不與 Draft 混用。

## 唯讀快照

「帶入目前進度」不是把所有資料永遠複製一份，而是在每次按測試時建立一次唯讀快照。建議帶入：

- 人物卡：名稱、摘要、個性、說話風格、外觀、關係、界線、角色狀態。
- 玩家相關資料：玩家輪廓、玩家自述、稱呼偏好、初始關係設定。
- 當前遊玩進度：目前活動、今日與近期行程、近期完成活動、故事線／場景／節拍、世界事件。
- 對話上下文：正式聊天室最近訊息與較早對話摘要。
- 已允許的長期記憶：沿用正式聊天的排名、長度上限、敏感內容處理與知識邊界。

不帶入：

- 其他玩家的資料、聊天室、記憶或個人覆寫。
- provider secret、管理員帳密、原始加密設定、診斷輸出。
- 尚未送出的正式聊天草稿與未完成 durable command。

玩家只能讀取自己擁有角色的快照。管理員可讀所有角色，但應沿用現有 admin 權限與操作紀錄模式。

## 絕對禁止的副作用

Playground 呼叫不得：

- 新增、更新或刪除 `messages`、`conversations`、記憶、角色狀態、目標、行程、故事、承諾、玩家輪廓或稱呼資料。
- 執行正式聊天的 post-turn 流程，包括記憶萃取、記憶整併、人格抽取、狀態建議、目標審查、承諾同步、重複表達紀錄與摘要檢查點推進。
- 建立 durable chat command、用量帳務列、聊天室 turn record 或玩家可見通知。
- 呼叫工具、生圖、短影片、TTS、RSS、網頁搜尋、Telegram、Discord、WhatsApp 或任何外部訊息連接器。
- 啟動／影響 scheduler、coordinator、worker 或 connector。

模型呼叫本身仍可能依 provider 計費，因此 UI 應明確寫「測試會使用目前聊天模型，可能消耗 provider 額度」。首版可沿用正式聊天模型路由與 content tolerance，但使用新的 source surface `prompt_playground`，讓診斷與成本分析能區分測試與正式對話。

## Prompt 與覆寫規則

Playground 使用與正式聊天相同的 `DefaultPromptContextBuilder`、角色資料與 request-scoped template override 機制，確保測試具有代表性。

目前有效版本的模板優先序：

1. 玩家自己的風格覆寫，只適用玩家可編輯的五份 style template。
2. 管理員 DB 全站已發布覆寫。
3. 版本內建 `.txt` 模板。

Draft 版本以目前有效版本為基礎，只覆蓋登入者尚未發布的 Draft 模板。Draft 同樣執行 placeholder、長度、控制字元與模板語法驗證。玩家 Draft 只能涵蓋五份 style template；管理員 Draft 可涵蓋所有模板。

雙版本比較必須在同一次 API request 中先凍結一份唯讀資料快照，再以相同快照、相同測試訊息、相同模型路由與相同內容容許度分別呼叫已發布與 Draft 版本。兩次模型呼叫仍可能因模型隨機性而有差異；若 provider 支援固定 seed，比較模式應固定同一 seed，否則 UI 要標示輸出存在隨機性。兩次呼叫都可能計費。

## 後端方案

新增獨立的 `PromptPlaygroundService`，不得呼叫 `ChatService.send_message()` 或其 post-turn／持久化路徑。

服務職責：

1. 驗證角色擁有權或管理員權限。
2. 平行讀取唯讀快照。
3. 凍結一次唯讀快照，分別以已發布覆寫與 Draft 覆寫呼叫 `DefaultPromptContextBuilder.build()`。
4. 使用 `ModelResolver` 的聊天 feature route 取得模型。
5. 每個可比較版本直接呼叫模型一次，禁止工具 descriptors、tool outcomes、forced image、stream persistence 與 retry 寫入。
6. 回傳兩份純文字回覆與受限 metadata；沒有 Draft 時只呼叫已發布版本一次。

可重用 `ChatAssistService` 的唯讀載入概念：角色／玩家資料、行程、故事、最近對話與世界事件。需要額外抽出共用 read-only snapshot builder，避免 Playground 與正式聊天各自維護一份上下文規則。

新 API 建議：

```text
POST /api/v1/characters/{character_id}/prompt-playground/runs
```

Request：

```json
{
  "message": "今天有點累。",
  "include_current_progress": true
}
```

此 API 不接受 Draft 正文、任意 user id 或 template override。後端只依登入者、選取角色與已儲存在 DB 的私有 Draft 解析比較來源，避免前端草稿逸出 Prompt Studio 的私有範圍。

Response：

```json
{
  "published_reply": "那先別硬撐，坐一下也好。",
  "draft_reply": "今天先別逼自己太緊，好嗎？",
  "model_id": "...",
  "prompt_hash": "short-hash",
  "snapshot_summary": {
    "recent_message_count": 12,
    "memory_count": 8,
    "has_current_activity": true,
    "has_story_arc": false
  }
}
```

後端不保存 request／response 正文。若既有 observability 必須記錄 generation，僅記錄 `source_surface=prompt_playground`、耗時、模型、token／成本數值與 hash；正文預設不入診斷資料。

## 前端方案

新增 `PromptPlaygroundPage.vue` 與 API client，使用既有角色選擇、UI textarea、聊天氣泡、登入權限與錯誤提示元件。

管理員與玩家頁都可從 Prompt Studio 開啟 Playground，並帶入目前選中的模板名稱。Draft 已由 Prompt Studio 儲存為登入者私有資料，因此 Playground 只讀取 Draft，不把草稿正文放入 router state、localStorage 或 URL query。

玩家頁不顯示 core template 草稿控制，且不可指定 admin-only template 名稱。玩家列表應標示每份可編輯模板的「有 Draft」狀態；管理員列表同樣標示每份模板的 Draft 狀態。

## 安全與容量限制

- 每位使用者限制併發 1 次測試；超過時回傳可重試狀態。
- 建議初始限制每分鐘 6 次、每小時 30 次，設定值由 admin runtime setting 管理。
- 每次只允許一則輸入、一次模型回覆，無 multi-turn session。
- 回覆上限建議 1,200 字元；逾限截斷並標示。
- 禁止附件與圖片 URL，首版只接受純文字。
- 以正式聊天相同的內容容許度、角色邊界與 provider 路由執行。

## 測試驗收

必須新增：

1. 擁有者可測試自己的角色；其他玩家取得 404；管理員可測試任意角色。
2. 測試讀到角色卡、正式近期對話、行程、故事與記憶，但任何 repository write method 均未被呼叫。
3. 不啟動 post-turn、scheduler、connector、tool 或媒體流程。
4. 玩家覆寫、管理員已發布覆寫、內建模板、玩家 Draft 與管理員 Draft 的優先序正確。
5. Draft 不會成為有效覆寫；發布前玩家還原目前預設不會使用任何 Draft。
6. 玩家發布 Draft 僅改變自己的有效覆寫；管理員發布 Draft 才改變全站已發布版本。
7. 發布 Draft 後，新的目前有效版本生效，而無新 Draft 的 Playground 不進行雙重模型呼叫。
8. 玩家無法建立／讀取／發布 core template Draft，也無法讀取其他玩家或管理員的 Draft。
9. 回應 metadata 不含 prompt 全文、私密資料或 provider secret。
10. 限流、輸入上限、並發限制及模型失敗的錯誤行為正確。
11. 前端切換角色、執行、清除、錯誤與 loading 狀態正確；離開頁面後測試記錄消失。

## 分階段實作

1. 先完成 read-only snapshot builder 與 service unit tests，證明零寫入。
2. 加 API、權限、草稿驗證、用量／observability 標記。
3. 在 Prompt Studio 加入玩家／管理員 Draft 儲存、載入、差異檢視、捨棄與發布流程。
4. 建立玩家與管理員 Playground UI，提供目前有效版本／Draft 雙版本比較。
5. 觀察成本與使用方式後，再決定是否支援 LumeGram／短影片／主動訊息專用 Playground。

## 待確認事項

1. Draft 保存期限：預設建議不自動過期；日後可加入版本歷史與手動清理。
2. 「目前遊玩進度」是否預設帶入正式對話？本方案預設帶入，並提供關閉開關，以便測純角色卡情境。
3. 是否要顯示 token／預估費用？本方案首版只留後端觀測資料，UI 暫不顯示金額，避免把 provider 細節塞入測試流程。
