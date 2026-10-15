# 背景追蹤與建置版本補強方案（2026-10-15）

## 授權、問題及範圍

使用者要求先保存方案，再修正最新診斷包顯示的背景呼叫缺少角色／request
關聯及 build metadata 空白。基準為 local/customizations 的 f6b6fa8。
本次 source-only，不 commit/push、不部署、不改正式設定或歷史業務資料。

## 設計與實作順序

1. 建置時產生映像內版本檔，內容為 SHA、UTC 建置時間、可用 tag，優先採
   明確 build args；檢查現有 Zeabur 建置來源，僅採可驗證來源，無 SHA 時
   明確保留未知。runtime 環境變數優先、映像檔 fallback，不在啟動時執行 git。
   版本來源／缺少欄位需可診斷，不能把 source hash 說成 commit SHA。
2. 背景工作入口建立 trace/request context，保留 job/character；feature resolve
   與 provider 執行在同一 scope。子呼叫獨立 operation_id、parent_operation_id，
   重試保留 trace，attempt 維持既有識別。非同步串流延後消費需傳遞 context，
   取消／失敗／並行工作不得互相污染。
3. usage metering 沿用 trace 關聯與角色／conversation／turn，不以另一個隨機
   ID 假裝能自動串接。持久工作以既有 job ID 建立可重建 trace，重新執行保留
   job 關聯、operation 區分次數；不新增任意業務 payload 或 schema migration。
4. 日誌與事件附 process instance/build，安全欄位白名單新增 trace/operation/job。
   真正無角色的工作標 global；角色 work 不靠時間鄰近猜關聯。
5. 聚焦測試、整合檢查、更新 checkpoint 及結果。

## 非目標／不變規則

- 不修復背景 stale fencing 行為、不切換 provider、不修改對話或貼文。
- 不引入第二個 Telegram owner、不送通知、不讀／匯出秘密。
- 保留既有 request_id 與 API 相容；新增 trace/operation 欄位為 additive。
- 舊資料缺關聯／版本維持 unknown，不回填推測值。
- 不依賴 Zeabur Pro，不下載付費日誌；版本 fallback 有界、不可載入任意路徑。

## 驗收

- 同一背景 feature 路由、provider attempts、usage 可透過 trace/job 串接，
  角色正確；兩個並行角色互不污染。
- stream 延後執行與 task 建立仍保留關聯，例外／取消後 context 恢復。
- 缺 instrumentation 的舊呼叫仍可運作，診斷失敗不改業務結果。
- 無環境變數時讀取映像版本檔；明確 env 優先；缺／壞檔不阻止啟動。
- 建置來源無 git 時不產生假的 commit，仍提供可區分版本的 source digest。
- 不需 migration；測試禁止使用正式連線與外部 API。

## 執行狀態

- [x] 保存本方案；讀取後才開始程式修改。
- [x] 建置版本檔與 fallback。
- [x] trace/context、背景入口與 usage 關聯。
- [x] 驗證、diff review 與執行紀錄。
- 部署狀態：未部署。

## 實作結果與驗證

- Docker 於前端產物複製後產生固定 `build_metadata.json`；有界 4096-byte
  schema 驗證，env 有效值優先，缺檔／壞檔 fail-soft。GitHub 現有流程會傳 SHA；
  沒有可驗證的 Zeabur SHA 注入設定，所以保留 commit unknown，提供 UTC
  built_at、明確標為 `sha256:` 的 source_digest、metadata_source／missing_fields。
  API、ZIP、心跳 details 與持久事件均帶可用版本資訊，沒有新增 schema 欄位。
- 背景 job 使用可重建的 `job:<id>` trace，重試各自新 operation；角色 tick、
  warmup、maintenance、proactive 入口補 scope。encounter job 的 relationship ID
  不當成角色 ID。真正 global 工作不因子角色 scope 被向上污染。
- Metered model 捕捉 resolve 時的 context，執行／延後串流恢復相同 trace；
  usage.request_id 採 operation_id，metadata 加 trace/parent/job，明確既有 ID
  保持優先。SQL 匯出只抽取白名單 JSON 關聯欄位，不匯出任意 metadata。
- 修正取消／early stream close 被 usage 誤標 succeeded；仍原樣傳播例外。
  另修串流事件從 consumer context 混入無關角色/job 的問題。
- Persisted WARN/ERROR 繼承當前 context；事件加入 process instance、可用 SHA/digest。
  敏感訊息、prompt、headers、URL、聊天內容維持原有禁止／opt-in 規則。
- 主要回歸 292 passed；最後關聯／usage set 31 passed、日誌 set 12 passed、
  最後 scope/lifespan set 32 passed（各集合重疊，不能相加）。Build helper／reader
  14 項測試包含實際產生檔案與 runtime fallback。`git diff --check` 通過。
- 已知非本次問題：proactive suite 兩筆 cadence-hint 斷言與目前 prompt 行為不符；
  移除 evaluate decorator 後仍同樣失敗，未修改該業務行為。
- 未做完整 Docker image build、PostgreSQL 重演或正式網頁 smoke test；本次無
  migration，SQLite 匯出投影／檔案生成與服務整合測試已驗證。部署後仍須用
  新背景事件與新診斷包確認實際 build fallback 和 trace/job 關聯。

## 完整映像建置嘗試

使用者已授權本機完整 Docker build，只建置獨立標籤，不啟動 app。
2026-10-15 執行環境存取 Docker named pipe 被拒；申請 elevated build 時，
自動核准服務因 CC Switch gpt-5.6-luna HTTP 404 失敗，指令未執行。
這不是 Docker build failure，也不是安全性拒絕；不可繞過核准流程。

待執行：於 source checkout 執行
`docker build --file docker/app/Dockerfile --tag yuralume-local/diagnostic-trace:verify-20261015 --progress plain .`
不提供 build args，刻意驗證 Zeabur 缺少 SHA/time args 時的映像 metadata fallback。
建置後可 docker create（不 start）並 docker cp 映像的
`/app/src/kokoro_link/infrastructure/build_metadata.json`，驗證 built_at/source_digest，
再移除僅此次建立的停止中容器。尚未完成上述映像驗證；不得據此宣稱可部署。
