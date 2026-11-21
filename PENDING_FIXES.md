# PENDING_FIXES — 已知缺陷待修清單

**建立：** 2026-11-21
**來源：** Architecture Atlas 首次盤點（commit `812ba78`）
**狀態：** 未修，僅記錄。本檔不是設計文件；每一項要動工前仍需自己的設計
reference 與 owner 確認。

這份清單只收「已經被驗證為事實」的缺陷。猜測性的改進想法屬於
`IDEAS_BACKLOG.md`，不在此列。

---

## 優先序說明

| 級別 | 定義 |
|---|---|
| P1 | 文件聲稱有保護，實際沒有。會讓人誤信安全性。 |
| P2 | 結構性風險，尚未造成事故。 |
| P3 | 維護成本或可測試性缺口。 |

---

## P1

### PF-01 — `check_clock_guard.py` 目前是失敗的

**證據（實測）：**
```
uv run python scripts/check_clock_guard.py  →  exit 1
61 個未列入 scripts/clock_guard_allowlist.txt 的檔案
```

**四層問題：**

1. **守護本身失敗。** 61 個違規未處理，allowlist 停在 74 筆。
2. **不在 CI。** `.github/workflows/publish-images.yml` 不含此檢查，只發布 image。
3. **測試不測真實程式碼。** `tests/unit/test_clock_guard.py` 用 `tmp_path`
   造樣本測 `find_violations`，從不掃描 repo 目錄。所以測試全綠不代表守護有效。
4. **範圍比文件窄。** 只匹配 `datetime.now(`（`check_clock_guard.py:14`）；
   `datetime.utcnow()`、`datetime.today()`、`time.time()`、別名 import 全部漏檢。
   也只掃 `application/` 與 `domain/`，不掃 `infrastructure/` 與 `api/`。

**文件與現實的落差：** `README.md:229` 寫「New domain/application files are
guarded by `scripts/check_clock_guard.py`」。目前不成立。

**建議修法（需設計）：**
- 短期：把 61 個檔案逐一判斷——是真正需要的例外（進 allowlist）還是應該改用
  `ClockPort`（改程式）。不要無腦全部加進 allowlist，那等於永久放棄。
- 中期：加一個測試掃真實目錄，讓失敗在 `make test` 就暴露。
- 長期：擴充 pattern 覆蓋 `utcnow`/`today`/`time.time`，並擴大掃描範圍。
- CI 要不要納入是獨立決定——目前 CI 只發布 image，不跑測試。

**風險：** 時間不可注入會讓測試與時區行為不可控；這是原始規則存在的理由。

---

### PF-02 — 「恰好一個 Telegram polling owner」只存在於文件

**證據：**
- `AGENTS.md` 規定全域「There must be exactly one Telegram polling owner」。
- 程式只實作**每帳號**租約：`sa_messaging_account_repository.py:110-140`
  對 `enabled AND platform=telegram AND delivery_mode=polling` 做條件式 UPDATE；
  由 `telegram_polling_service.py:231-255` 每輪取得／釋放。

**後果：**
- N 個程序可以各自擁有互斥的帳號子集並同時輪詢——這其實符合多 connector
  的設計意圖，但與「全域唯一」的措辭矛盾。
- 交接時租約是**釋放**而非**轉移**，兩個程序可能同時持有連線。
- 沒有任何機制阻止本地開發環境與 hosted 環境同時輪詢同一個 bot token。

**建議修法（需設計）：**
- 先決定語意：要「全域單一程序」還是「每帳號單一 owner」？兩者都合理，
  但目前文件寫 A、程式做 B。
- 若是後者：改 `AGENTS.md` 措辭，並補一個全域 bot token 唯一性檢查。
- 若是前者：需要一個全域 lease（`runtime_process_heartbeats` 目前明確
  **不**帶租約語意，`models.py:3455-3460`，不能拿來當租約用）。

**注意：** 這條與「本地開發不得同時跑 Telegram polling」的部署規則直接相關。
誤判會造成重複回覆或 bot API 衝突。

---

## P2

### PF-03 — 沒有機器強制的分層方向

**證據（`docs/atlas/layers.md`）：**

| 方向 | 數量 | 問題 |
|---|---|---|
| `application → infrastructure` | 153 處 / 78 檔 | 雙向耦合 |
| `infrastructure → application` | 97 處 | 同上 |
| `contracts → application` | 4 檔 | 反向依賴，潛在循環 |
| `api → infrastructure` | 53 處 / 約 19 檔 | 繞過 DI |

沒有 `import-linter`、沒有 ruff import 限制、沒有任何測試斷言依賴方向。
`pyproject.toml` 只有 hatch 與 pytest 設定。

**為什麼現在只列 P2：** 沒有造成已知事故，但它是「改了 A 層卻在 B 層壞掉」
這類 bug 的根源，也是新加入者最容易判斷錯的地方。

**建議修法（低風險起步）：**
只鎖**已經零例外**的三條邊，不要一開始就鎖全部：
```
domain → application      (目前 0)
domain → infrastructure   (目前 0)
application → api         (目前 0)
```
用 `import-linter` 的 forbidden contract，先當 warning，穩定後升 error。
不要一次鎖 `application ↔ infrastructure`——那是 250 處的債，不是一次能清的。

**反向依賴的 4 個 contracts 檔：**
`arc_series_continuation.py:8`、`character_card_translator.py:14`、
`drama_to_arc.py:26`、`fusion_to_arc.py:8`
全部指向 `application.services.arc_template_intake_service` /
`application.dto.character_card`。

---

### PF-04 — `api/` 直連 `infrastructure/` 約 19 檔

**證據：** `layers.md` §實際依賴方向。
例：`api/app.py:9-10,103,167,170-171`、`api/routes/chat.py:68`、
`api/routes/public_objects.py:35`、`api/routes/version.py`。

**後果：** API 層無法完全用假物件測試；改 infrastructure 的建構方式會波及 route。

**建議修法：** 逐步收斂到 `bootstrap/container.py` 或 `Depends()` 提供。
不要一次全改。新程式碼不要再走直連。

---

### PF-05 — `container.py` 7,112 行且持續成長

**事實：** 90 天內第三熱的檔案（14 次）。36 個 `_build_*` 輔助函式，
`ServiceContainer` 是扁平屬性集。

**後果：** 每個新服務都要改同一個檔案；合併上游時這裡是必衝區。

**建議修法：** 按能力域拆成多個 `wiring_*.py`，`build_container` 只負責呼叫。
需要設計，不是純機械重構。

**與 FORK_DELTA 的關係：** 這是最容易與上游衝突的檔案之一。見
`FORK_DELTA.md`。

---

## P3

### PF-06 — `persistence/models.py` 沒有專屬測試

**事實：** 4,104 行、90 天內 11 次改動，**沒有任何 `test_persistence_models.py`**。
只被間接涵蓋：`tests/conftest.py:28` 用 `Base` 建 schema，約 10 個 integration
test 直接 import 個別 row class。

**後果：** 改 model 沒有直接的測試要更新，安全網只有 migration 測試與 PG
integration suite。

**建議：** 不一定要為每個 model 寫測試，但至少補一組「所有 model 都能建表、
所有 constraint 名稱唯一」的 sanity test。

---

### PF-07 — 前端沒有測試套件

**事實：** `frontend/` 無測試框架設定。驗證方式是 `npm run build` 加手動確認。
（`.codex-round.md` 曾提到跑過「frontend suite 2136 passed」——那是
frontend 目錄下另一個測試設定，需確認是否仍存在並納入常規。）← **待查證**

**後果：** i18n key 缺漏、型別錯誤只有在 build 或執行時才發現。

**建議：** 至少加一個 i18n key 一致性檢查（三語系 key 集合相同）。

---

### PF-08 — NSFW 摘要失敗是靜默的

**事實：** `LLMNsfwSafeSummarizer.summarize` 失敗時回傳空字串
（`llm_safe_summary.py`），該訊息之後對 frontier 模型永久隱形。沒有指標、
沒有重試。

**後果：** 長期會讓 frontier 模型對某段關係的記憶出現斷層。
`tests/evals/fixtures/nsfw_born_safe_memory_continuity_01.yaml` 說明這是已知痛點。

**建議：** 記錄失敗計數到 diagnostic export，並考慮有限次重試。
**這是產品行為決定，需要 owner 明確批准後才能改。**

---

### PF-09 — NSFW 模式沒有年齡或同意閘門

**事實：** 唯一守門是「Admin 已先配置 target」。UI 層沒有任何確認步驟。

**這是刻意的設計還是遺漏，需要 owner 判斷。** 若是有意，應寫進
`docs/atlas/domains/nsfw.md`；若是遺漏，需要設計。

---

## 與 Atlas 的關係

上述每一項在 atlas 對應頁面的「已知缺口」章節都有一份描述：

| 項目 | Atlas 位置 |
|---|---|
| PF-01 | `docs/atlas/invariants.md` §E |
| PF-02 | `docs/atlas/invariants.md` §H |
| PF-03, PF-04, PF-05 | `docs/atlas/layers.md` §已知缺口 |
| PF-06, PF-07 | `docs/atlas/layers.md` §已知缺口 |
| PF-08, PF-09 | `docs/atlas/domains/nsfw.md` §已知缺口 |

本檔是**可執行**的版本（有優先序、有建議修法）；atlas 是**描述**的版本
（說明現況）。兩邊都要在同一個 commit 更新。

## 修完之後

- 從本檔移除該項。
- 更新對應 atlas 頁面的「已知缺口」與 `verified_at_commit`。
- 在 `UPDATE_PROGRESS_LOG.md` 補一筆。
