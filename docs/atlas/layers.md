---
doc: layers
tier: atlas
verified_at_commit: 3fc5836
verified_at: 2026-11-21
sources:
  - src/kokoro_link
  - src/kokoro_link/bootstrap/container.py
  - src/kokoro_link/api/app.py
  - scripts/check_clock_guard.py
symbols:
  - src/kokoro_link/bootstrap/container.py::ServiceContainer
  - src/kokoro_link/bootstrap/container.py::build_container
  - src/kokoro_link/api/app.py::create_app
  - src/kokoro_link/contracts/llm.py::ChatModelPort
  - src/kokoro_link/contracts/clock.py::ClockPort
---

# 分層

## 職責

`src/kokoro_link/` 下 10 個 Python 套件，加上兩個非 Python 目錄。規模：約 1,180 個
`.py` 模組。

| 套件 | 職責 | 模組數 | 代表檔 |
|---|---|---|---|
| `api/` | FastAPI delivery 層：app factory、認證依賴、HTTP 路由 | 80（其中 72 個 route 檔 / 69 個路由模組） | `app.py`, `dependencies.py`, `routes/chat.py` |
| `application/` | 用例服務與 DTO，協調 domain 與 ports | 352（253 個在 `services/`） | `services/chat_service.py`, `dto/character.py` |
| `bootstrap/` | 組裝根：設定、DI container、站台設定、啟動種子 | 16 | `container.py`, `settings.py` |
| `cli/` | 獨立維護入口 | 9 | `consolidate_memories.py`, `replay_turn.py` |
| `contracts/` | Port Protocol 定義（189 個 `*Port`） | 155 | `llm.py`, `repositories.py`, `clock.py` |
| `domain/` | 實體、值物件、純領域服務 | 99（55 個 entity） | `entities/character.py`, `value_objects/` |
| `infrastructure/` | 適配器：持久化、LLM provider、prompt、儲存、訊息、TTS/圖片/影片 | 483 | `persistence/engine.py`, `llm/anthropic.py`, `prompt/` |
| `llm_output/` | 純標準庫的 LLM 輸出解析工具 | 4 | `extract.py`, `diagnostics.py` |
| `storage_service/` | 獨立的物件儲存 ASGI app | 2 | `app.py` |
| `data/` | 非 Python 靜態資源 | 0 | `arc_templates/`, `prompts/`, `character_cards/` |
| `frontend/` | 建置後的靜態前端資產 | 0 | `dist/`, `static/` |

`llm_output/` 的 `__init__.py` 明確聲明自己「與 `contracts` 同等地位」：
不 import domain / application / infrastructure。

## 不屬於這一層的事

`layers.md` 不描述任何單一功能的行為。要看聊天怎麼跑請讀 `domains/chat.md`；
要看改動落點請讀 `change-map.md`。

## 實際依賴方向（重要：這不是嚴格 DAG）

**先講結論：分層是慣例，不是強制。** 沒有 `import-linter`、沒有 ruff 的
import 限制、沒有任何測試斷言依賴方向。`pyproject.toml` 只有 hatch 與 pytest
設定。

實測的跨層 import：

| 方向 | 數量 | 判定 |
|---|---|---|
| `domain → application` | 0 | 乾淨 |
| `domain → infrastructure` | 0 | 乾淨 |
| `domain → contracts` | 4 檔 | **向上**（見下） |
| `contracts → infrastructure` | 0 | 乾淨 |
| `contracts → application` | 4 檔 | **向上** |
| `application → infrastructure` | 153 處 / 78 檔 | **重**,佔 application 模組 22% |
| `application → api` | 0 | 乾淨 |
| `infrastructure → application` | 97 處 | **雙向耦合** |
| `api → infrastructure` | 53 處 / 約 19 檔 | **繞過 container** |

### 具體的例外邊

`domain → contracts`：
- `domain/entities/character.py:5-6` → `contracts.image_profile`, `contracts.video_profile`
- `domain/entities/durable_chat_command.py:3` → `contracts.durable_chat_commands`
- `domain/entities/story_scene_session.py:33` → `contracts.clock.ensure_utc`

`contracts → application`：
- `arc_series_continuation.py:8`
- `character_card_translator.py:14`
- `drama_to_arc.py:26`
- `fusion_to_arc.py:8`

`application → infrastructure` 最熱的目標：`prompt` (46)、`prompts` (14)、
`observability` (14)、`character_card` (13)、`localization` (11)。

`api → infrastructure` 直接引用的例子：`api/app.py:9-10,103,167,170-171`、
`api/routes/chat.py:68`、`api/routes/public_objects.py:35`、`api/routes/version.py`。

### 這代表什麼

- **不要假設「只需要動 application 就能保證安全」。** `application` 會直接吃
  `infrastructure` 的具體實作（尤其 prompt builder）。改 prompt 層會波及 application。
- **`contracts` 不是純淨的介面層**：它有 4 個檔案反向 import application 的服務與 DTO。
  擴充 `contracts` 時要先確認不會拉進循環。
- **API 層不是只透過 container 取得東西**。新增 route 時若直接 import
  infrastructure，會繞過 DI，讓測試替換變困難。這是既有債，不要擴大。

## 唯一被強制的規則

`scripts/check_clock_guard.py`：

- 掃描 `src/kokoro_link/application` 與 `src/kokoro_link/domain`
- 禁止直接使用 `datetime.now(`
- 既有例外必須列在 `scripts/clock_guard_allowlist.txt`
- 由 `tests/unit/test_clock_guard.py::test_clock_guard_blocks_new_direct_datetime_now_usage` 回歸驗證

理由：時間必須可注入，否則測試與時區行為不可控。新增程式碼請用 `ClockPort`
（`contracts/clock.py:9`）與 `ensure_utc`。

CI（`.github/workflows/publish-images.yml`）不跑 clock guard，只靠單元測試。

## 組裝根

`bootstrap/container.py` 共 **7,112 行**：

- `ServiceContainer` dataclass 在 `:1103`，是一組扁平的型別化服務屬性
- `build_container(settings)` 在 `:2696`
- 手工 DI，配 **36 個 `_build_*` 模組級輔助函式**（如 `_build_db_repositories:1596`、
  `_build_post_turn_processor:1723`、`_build_object_storage:2172`）
- 路由透過 `Depends(get_container)` 取得（`api/dependencies.py:30-31` 回傳
  `request.app.state.container`）
- container 在 `api/app.py:251` 建置
- 路由註冊集中在一處：`api/app.py:756-865`

`bootstrap/` 其餘檔案：`settings.py`（2,610 行，`AppSettings`）、
`site_settings_holder.py`（可變站台設定）、`app_runtime_settings_seed.py`
（啟動種子）、`process_roles.py`（process role 切換）、`runtime_config_wiring.py`。

## 新增程式碼該放哪

| 你要加的東西 | 放這裡 | 理由 |
|---|---|---|
| 純業務規則（無 I/O） | `domain/` | 不得 import application / infrastructure |
| 新 port 介面 | `contracts/<feature>.py` | 一 feature 一檔；不要集中塞 `repositories.py` |
| 用例編排 | `application/services/<name>_service.py` | 99 個 `*_service.py` 是主流慣例 |
| 外部系統適配 | `infrastructure/<capability>/` | 按能力分目錄，不按廠商 |
| HTTP 端點 | `api/routes/<resource>.py` | 在 `api/app.py:756-865` 註冊 |
| 一次性維護腳本 | `cli/` | 不是 `application/` |
| 靜態資源 | `data/` | 不要放進套件程式碼目錄 |

## `application/services/` 命名叢集

253 個模組，`*_service.py` 佔 99 個。其餘按前綴分群（供定位用，非分類體系）：

`character_*` 26、`story_*` 14、`cloud_*` 13、`feed_*` 9、`fusion_*` 9、
`chat_*` 6、`branching_*` 6、`persona_*` / `official_*` / `messaging_*` 各 5、
`proactive_*` / `memory_*` / `runtime_*` / `player_*` / `due_*` / `arc_*` 各 4，
其餘約 30 個是 1–3 個檔的孤島（`turn`, `tool`, `studio`, `schedule`, `rss`,
`relationship`, `pending`, `operator`, `external`, `experiment`, `durable`,
`tts`, `social`, `routing`…）。

## 不變式

- `domain/` 不得 import `application/` 或 `infrastructure/`（目前 0 例外，保持）。
- `application/` 不得 import `api/`（目前 0 例外，保持）。
- `application/` 與 `domain/` 不得直接 `datetime.now(`（clock guard 強制）。
- `llm_output/` 維持標準庫依賴，不 import 專案其他套件。
- 新增 repository 實作必須落在 `infrastructure/repositories/`，並實作
  `contracts/` 中對應的 Port。

## 相關 feature reference

無。分層本身沒有專屬設計文件；`AGENTS.md` 的「Deployment Boundaries」是唯一
相關的書面約束。

## 已知缺口

- **沒有機器強制的依賴方向。** `application ↔ infrastructure` 已雙向耦合
  （153 + 97 處）。若想收斂，最小成本是在 `pyproject.toml` 加入 `import-linter`
  的 `forbidden` contract，先只鎖 `domain → application/infrastructure` 與
  `application → api` 這兩條已經零例外的邊。
- **`contracts → application` 的 4 個反向邊** 是潛在循環風險，值得單獨清理。
- **`container.py` 7,112 行** 已是顯著的認知負擔。每次新增服務都要改，且它是
  90 天內第三熱的檔案（14 次）。拆分需要設計，不在本次範圍。
- **`api → infrastructure` 直連約 19 檔** 讓 API 層無法完全用假物件測試。
- **`application/services/` 253 個模組、99 個 `*_service.py`** 沒有統一的責任
  邊界規範，命名叢集只是觀察結果，不是設計。
