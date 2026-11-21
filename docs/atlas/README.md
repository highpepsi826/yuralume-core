---
doc: readme
tier: atlas
verified_at_commit: 3fc5836
verified_at: 2026-11-21
sources:
  - docs/atlas
  - scripts/atlas_check.py
  - AGENTS.md
symbols: []
---

# Architecture Atlas

## 這是什麼

`docs/atlas/` 是 Yuralume 程式碼**當前結構**的地圖：哪一層負責什麼、改動落在哪裡、哪些規則不能破、用到的專案詞彙是什麼意思。它回答的問題是「我想改 X，該動哪一層、哪些檔案、哪些測試、不能碰什麼」。

它**不是**：

- changelog——不看歷史，只看現在。
- feature 設計文件——「要加什麼功能」寫在根目錄的 `*_REFERENCE.md`。
- 使用者文件——面向玩家與營運者的行為說明在 `FEATURE_MANUAL.md`。
- 自動產生的 API reference——不做 AST 全量抽取，那在寫下的那一刻就過時了。
- 行為的真實來源——atlas 與程式碼衝突時**以程式碼為準**，atlas 是缺陷。

## 給誰看

- 任何接手工作的 assistant（Claude、Codex），特別是 context compaction 之後。
- owner 與未來的人工維護者。
- 任何需要在不掃 `src/` 的情況下定位改動落點的人。

## 使用順序

1. 先讀 `INDEX.md`——一頁全貌：分層圖、領域清單、現有 `*_REFERENCE.md` 的歸屬。
2. 再讀 `change-map.md`——用「我想改的東西」反查：主要層、相關檔案、不可違反的規則、必跑測試。
3. 只有當 change-map 的答案不夠時，才進 `domains/<domain>.md` 看該領域的職責與不變式，或進 `flows/<flow>.md` 看跨層的呼叫流程。
4. 詞義不確定時查 `glossary.md`。

命令列驗證：

```powershell
make atlas-check
```

## 與其他文件的關係

| 文件 | 位置 | 負責什麼 | 生命週期 |
|---|---|---|---|
| Live checkpoint | `.codex-round.md` | **當前這一個任務**：做到哪、下一步、卡在哪 | 任務完成後段落移到 `.codex-round-archive.md` |
| Architecture Atlas | `docs/atlas/` | **當前程式結構**的穩定描述 | **永不歸檔，原地更新** |
| Active reference | 根目錄 `*_REFERENCE.md` | **單一改動**的設計與實施紀錄 | 該改動完成且無人引用後 `git mv` 到 `docs/archive/` |
| Feature manual | `FEATURE_MANUAL.md` | 當前使用者可見行為 | 隨功能變更同步更新 |
| Archive | `docs/archive/` | 只讀歷史 | 不再修改 |

關鍵差別：`*_REFERENCE.md` 的工作做完就進 archive；atlas 頁面**不進 archive**，因為它描述的程式碼還在跑。頁面內容過時就原地改，並更新 `verified_at_commit`。

## 維護契約

**必須在同一個 commit 更新 atlas 的情況**：

- 改動改變了某領域的行為（`domains/<domain>.md` 的「職責」「關鍵流程」不再是事實）。
- 改動改變了分層或依賴方向（`layers.md`）。
- 改動新增、修改或移除了不變式（`invariants.md`）。
- 改動讓 `change-map.md` 的某一列指向錯誤的檔案、層或測試。
- 任何上述情況都必須同步更新該頁的 `verified_at_commit` 與 `verified_at`。

**不需要更新頁面內容的情況**：

- 純外觀或純重構改動，頁面裡的敘述依然成立。
- 這種情況**不需要**改 `verified_at_commit`。代價只是 freshness 分級會往前走，而分級設計就是要讓「驗證落後」看得見但不是缺陷。

**改動 atlas 時的規則**：

- 任何可以對照程式碼核實的敘述都要帶錨點：`file:line` 或 `file::Symbol`。
- 每個 domain 頁的「已知缺口」一節必填。真的沒有就明說「目前無已知缺口」，那本身是一個結論，不要用空話填滿。
- 新增 atlas 頁面時，frontmatter 的 `sources` 與 `symbols` 必須齊全，否則 `make atlas-check` 會報 error。

## Staleness 機制

每個 atlas 頁面檔頭有 YAML frontmatter，記錄它**最後一次被對照程式碼驗證**的位置。`scripts/atlas_check.py`（`make atlas-check`）讀這些欄位並檢查：

| 檢查 | 級別 | 說明 |
|---|---|---|
| 缺 frontmatter，或缺 `doc` / `tier` / `verified_at_commit` / `verified_at` / `sources` / `symbols` 任一鍵 | error | 頁面無法被追蹤 |
| `sources` 中的路徑不存在 | error | 頁面引用的檔案已被刪除或搬走 |
| `symbols` 格式不是 `path::Symbol`，或 path 不存在 | error | 錨點格式錯誤 |
| `symbols` 的 symbol 字串未出現在該檔內容中 | error | 錨點指向的符號已改名或刪除 |
| `verified_at_commit` 在 git 中不可達 | error | 記錄的 commit 不存在（例如 rebase 掉了） |
| freshness：`verified_at_commit..HEAD` 的 commit 數 | ok / warning | 見下表 |
| 無法執行 git | warning | 不讓整個檢查崩潰 |

Freshness 分級（commit 數，門檻暫定 30 / 100）：

| 距離 HEAD 的 commit 數 | 標籤 | 意義 |
|---|---|---|
| 0–30 | fresh | 近期驗證過 |
| 31–100 | due | 該排時間重新對照程式碼 |
| >100 | stale | 很可能已經與程式碼不符，優先重讀 |

結束碼：任何 error → 1；`--strict` 時任何 warning 也 → 1；否則 0。`--json` 輸出機器可讀結果。`--strict` 供 pre-release 檢查使用。

換句話說：檢查器**不會**阻止頁面變舊，只會讓「舊了多少」變成可查詢的事實。內容正確性仍由 review 保證。

## Frontmatter 格式

```markdown
---
doc: routing
tier: atlas
verified_at_commit: 3fc5836
verified_at: 2026-11-21
sources:
  - src/kokoro_link/application/services/active_llm_provider.py
  - src/kokoro_link/application/services/nsfw_mode.py
symbols:
  - src/kokoro_link/application/services/active_llm_provider.py::ActiveLLMProvider
  - src/kokoro_link/application/services/nsfw_mode.py::NsfwModeService
---
```

欄位說明：

| 欄位 | 必填 | 說明 |
|---|---|---|
| `doc` | 是 | 頁面識別碼，通常等於檔名（不含 `.md`） |
| `tier` | 是 | 固定為 `atlas` |
| `verified_at_commit` | 是 | 最後一次對照程式碼時的 short SHA |
| `verified_at` | 是 | 最後一次對照的日期（`YYYY-MM-DD`） |
| `sources` | 是 | 該頁描述的檔案路徑，相對 repo root。目錄也可以（用於整批檔案）。 |
| `symbols` | 是 | `path::Symbol` 錨點。沒有可錨定的 symbol 時寫 `symbols: []` 或留空列表。 |

格式限制：frontmatter 只支援扁平結構——`key: value` 純量，或 `key:` 後接縮排的 `  - item` 列表。不需要也不支援巢狀映射。路徑一律用相對 repo root 的正斜線形式，不要寫 `.\` 或絕對路徑。

## 禁止事項

- **不寫 secrets**：API key、token、`.env.container` 的任何內容、provider 憑證。
- **不寫訊息內容**：對話內文、角色回覆、prompt 全文。
- **不寫資料庫資料列**：真實的使用者資料、聊天紀錄、排程內容。
- **不宣稱程式碼以外的行為**：atlas 與程式碼衝突時以程式碼為準，atlas 即為缺陷，修 atlas 而不是改程式碼來遷就文件。
- **不把 atlas 當設計文件用**：要做新的設計，寫新的 `*_REFERENCE.md`，完成後讓 atlas 反映結果。
- **不手動刪除過時頁面來「清理」**：頁面描述的領域若還存在，就更新；領域若已整個移除，在刪頁面的同一個 commit 更新 `INDEX.md` 與 `change-map.md`。
