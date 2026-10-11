# SDK 使用說明

[English](sdk.md) | [简体中文](sdk.zh-Hans.md) | 繁體中文

儲存庫的 `sdk/` 目錄中有兩個命令列工具，都在專案根目錄用 `python -m` 執行：

| 工具 | 用途 | 需要的外部檔案 |
|---|---|---|
| `sdk.il2cpp` | 在 GitHub Release 與本機之間上傳或下載 IL2CPP 中繼資料（`il2cpp_dump.json`） | 已登入的 GitHub CLI（`gh`） |
| `sdk.enemy_logic_exporter` | 從遊戲 EXE、IL2CPP 中繼資料和資源匯出中提取魔物行動邏輯，產生網頁使用的行動圖 JSON | 遊戲 EXE、IL2CPP 中繼資料、`MHWS-in-json` 資源；部分命令還需要 Ghidra |

只想重新產生網頁、不改動行動邏輯時，兩個工具都不需要：網頁建置器只讀取儲存庫中已發布的模型（見「[只建置網頁](#只建置網頁)」）。

## IL2CPP 資料工具（`sdk.il2cpp`）

IL2CPP 中繼資料約 1.6 GB，不進入 Git，而是以壓縮檔形式保存在儲存庫的 `build-data` Release 中。自動建置和本機行動邏輯提取都從這裡取得。

### 下載

```powershell
gh auth login                      # 首次使用時登入
python -m sdk.il2cpp download
```

- 預設保存到 `src/data/il2cpp_dump.json`；用 `--output <路徑>` 指定其他位置。
- 先下載 `il2cpp_dump.json.gz` 及其 `.sha256` 校驗檔，校驗通過後再解壓並替換目標檔案。任何一步失敗都保留原有檔案。
- 暫存檔在 `.agents/il2cpp`（可用 `--work-dir` 修改）。

### 上傳（維護者）

遊戲更新後，用新版本的 REFramework dump 替換 Release 中的資料：

```powershell
python -m sdk.il2cpp upload --dump "D:/path/il2cpp_dump.json" --dry-run   # 只壓縮並計算校驗值
python -m sdk.il2cpp upload --dump "D:/path/il2cpp_dump.json"
```

- 上傳覆蓋同名附件；`build-data` 不會被設為最新正式 Release。
- `--compresslevel 1-9` 控制 gzip 壓縮等級（預設 9）。`--release-title`、`--release-notes` 修改 Release 的標題和說明。

### 通用參數

| 參數 | 說明 |
|---|---|
| `--repo owner/name` | 目標儲存庫；預設依序取環境變數 `GITHUB_REPOSITORY`、`origin` 遠端和 `gh repo view` |
| `--tag` | Release 標籤，預設 `build-data` |
| `--asset` | 壓縮檔附件名稱，預設 `<dump 檔名>.gz` |

## 魔物行動邏輯 SDK（`sdk.enemy_logic_exporter`）

SDK 只讀取遊戲檔案，不執行遊戲、不注入。它從 EXE 的 x64 指令中還原每張行為表的控制流程，再結合資源參數和 IL2CPP 中繼資料，把判斷條件、動作和繼續位置寫成 JSON。完整研究模型保存在 `.agents/enemy-logic-exporter`，用 `publish` 精簡後寫入 `src/processed_data/enemy_battle_logic/models`，網頁由這些模型產生。

目前模型對應遊戲版本 **1.42.0.2**（`sdk/enemy_logic_exporter/data/profiles/`）。EXE 或中繼資料與該版本不符時，提取命令會拒絕執行。

### 建立環境（Windows）

1. 安裝 Python 3.13（勾選 `py` 啟動器）與 Git，複製儲存庫。
2. 在專案根目錄執行安裝腳本。它在 `.agents/sdk-venv` 建立虛擬環境，安裝固定版本的相依套件（Capstone、PyGhidra），最後執行環境檢查：

   ```powershell
   powershell -ExecutionPolicy Bypass -File sdk/enemy_logic_exporter/setup_env.ps1
   ```

3. 依檢查結果補齊缺少的項目，然後再檢查一次：

   ```powershell
   .agents/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env
   .agents/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env --verify   # 同時核對 EXE 與 dump 的版本摘要（較慢）
   ```

| 檢查項目 | 如何補齊 |
|---|---|
| 遊戲 EXE | 預設在所有 Steam 收藏庫中尋找；安裝在其他位置時設定環境變數 `MHWS_EXE`，或在命令加上 `--exe` |
| IL2CPP dump | `python -m sdk.il2cpp download`，或用 `--metadata` 指定 |
| 資源匯出 | 隨儲存庫取出的 `MHWS-in-json/natives`，或用 `--natives` 指定 |
| 資源換行 | 資源檔必須保持匯出時的 LF 位元組。報錯時刪除 `MHWS-in-json` 目錄，再執行 `git checkout -- MHWS-in-json` |
| 研究快取 `--index`、`--helpers`、`--inventory`、`--requests` | 從既有機器複製整個 `.agents/enemy-logic-exporter`，或依「[遊戲更新後](#遊戲更新後)」重新產生（需要 Ghidra） |
| 工作目錄 | 預設 `.agents/enemy-logic-exporter`；可用 `--work-dir` 或環境變數 `MHWS_SDK_WORK_DIR` 修改，但必須位於專案 `.agents` 內。快取放在其他磁碟時，用目錄連結把 `.agents` 指過去 |
| `GHIDRA_INSTALL_DIR`、`JAVA_HOME` | 只有 `decompile`、`analyze` 需要：安裝 Ghidra 12.0.4 及其支援的 JDK 後設定這兩個環境變數 |

以下範例中的 `python` 指上面虛擬環境中的直譯器；所有命令都在專案根目錄執行。查看任一命令的完整參數：`python -m sdk.enemy_logic_exporter <命令> --help`。

### 只建置網頁

不需要 SDK 相依套件和遊戲檔案：

```powershell
python -m src.processed_data.enemy_battle_logic                     # 正式建置，輸出到 output/processed_data
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
python -m src.processed_data.enemy_battle_logic --template <模型.json> --output .agents/one
```

開啟輸出目錄下的 `enemy_battle_logic/index.html` 瀏覽。頁面可離線使用。

### 修改程式碼後重新提取

`--exe` 和研究快取參數省略時使用預設位置。完整提取約 15 分鐘。

```powershell
$w = '.agents/enemy-logic-exporter/fix'
python -B -m sdk.enemy_logic_exporter extract --enemy EM0002_00_0 --output "$w/one"   # 試跑一隻魔物
python -B -m sdk.enemy_logic_exporter extract-all --output "$w/s1"                     # 全部 34 隻
python -B -m sdk.enemy_logic_exporter player-view --models "$w/s1" --output "$w/s1p"  # 產生玩家視圖
python -B -m sdk.enemy_logic_exporter census --models "$w/s1p"                         # 含未知部分的條件，依命令與原因分組
python -B -m sdk.enemy_logic_exporter uncertainty --models "$w/s1p"                    # 玩家戰鬥樹中輸入都已知後仍無法判定的條件
python -B -m sdk.enemy_logic_exporter publish --models "$w/s1p"                        # 寫入網頁模型目錄
python -B -m src.processed_data.enemy_battle_logic --output "$w/site"
python -B -m unittest discover -s tests/sdk -t .
```

每次改動前後都比較 `census` 的 `unknownConditions` 和 `uncertainty` 的 `total.uncertain`。`player-view` 只接受 `.agents` 中的完整模型，不接受已發布的精簡模型。

### 遊戲更新後

需要新版本的 EXE、IL2CPP dump（用 `sdk.il2cpp upload` 上傳後，其他機器即可下載）和重新匯出的資源，以及 Ghidra。

```powershell
python -B -m sdk.enemy_logic_exporter check-env --verify
python -B -m sdk.enemy_logic_exporter resolve-symbols --version <新版本>       # 產生 data/profiles/<新版本>.json
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<新版本>.json           # 先看報告
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<新版本>.json --apply   # 遷移位元組未變的證據
python -B -m sdk.enemy_logic_exporter analyze --version <新版本> --output .agents/enemy-logic-exporter/full-run/result --cache-dir .agents/enemy-logic-exporter/full-run/native
python -B -m sdk.enemy_logic_exporter requests --index .agents/enemy-logic-exporter/full-run/native/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --output .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter recover --index .agents/enemy-logic-exporter/full-run/native/index.json --helpers .agents/enemy-logic-exporter/per-monster/helpers/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --requests .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter scheduler-slots
python -B -m sdk.enemy_logic_exporter roster --write
python -B -m sdk.enemy_logic_exporter new-monster --enemy <新魔物ID>          # 名單新增的每隻魔物
```

之後把 `sdk/enemy_logic_exporter/shared/config.py` 中的 `ACTIVE_GAME_VERSION` 改為新版本，再依「修改程式碼後重新提取」執行一遍。`migrate-evidence` 列出的待複核項目和 `resolve-symbols` 報告的 `changed` 項目必須逐條核對原生程式碼，不能只替換版本號或摘要。詳細的核對順序見 [SDK 維護說明](../sdk/enemy_logic_exporter/AGENTS.md)（簡體中文）。

### 命令一覽

| 命令 | 作用 | 需要 |
|---|---|---|
| `check-env` | 檢查相依套件、遊戲檔案、研究快取和 Ghidra 設定 | — |
| `extract` / `extract-all` | 提取一隻或全部魔物的完整研究模型 | EXE、dump、資源、研究快取 |
| `player-view` | 為完整模型產生玩家視圖（網頁使用的條件與輸入） | 完整模型 |
| `census` | 統計含未知部分的條件，依命令和原因分組 | 完整模型 |
| `uncertainty` | 統計玩家戰鬥樹中無法判定的條件 | 含玩家視圖的完整模型 |
| `publish` | 刪除研究欄位、共享重複值，寫入 `src/processed_data/enemy_battle_logic/models` | 含玩家視圖的完整模型 |
| `resolve-symbols` | 為新版本產生符號位址 profile | EXE、dump |
| `migrate-evidence` | 遷移位元組未變的證據行，其餘列入人工複核 | EXE、dump、新 profile |
| `scheduler-slots` | 還原 AI 狀態與中斷請求的行為表槽 | EXE、dump |
| `roster` / `new-monster` | 更新大型魔物名單；為新魔物產生入口模組 | 資源 |
| `analyze` | 完整的資源與原生證據分析，產生研究快取 | EXE、dump、資源、Ghidra |
| `requests` / `recover` | 找出動作請求；逐隻魔物還原參數與命令實作 | 研究快取、EXE |
| `manifest` / `decompile` / `verify` / `index` | 新版本研究：定位方法、反編譯、核對位元組、建立原生索引 | EXE、dump（`decompile` 需要 Ghidra） |

### 常見問題

- **「资源发现后行为表发生变化」**：資源檔的位元組與研究快取不一致，通常是換行被 Git 改成了 CRLF。依上表「資源換行」一項處理。
- **「原生配方的 EXE 来源变化」或版本不符**：EXE 或 dump 不是 profile 記錄的版本。確認檔案來源；遊戲已更新時依「遊戲更新後」處理。
- **「缺少研究缓存」**：`.agents/enemy-logic-exporter` 中沒有標準位置的快取。執行 `check-env` 查看路徑，複製或重新產生。
- **只能輸出到 `.agents`**：研究輸出必須位於專案 `.agents` 內，這是為了不把大型證據快取提交到 Git。
