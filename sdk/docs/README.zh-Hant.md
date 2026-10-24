# SDK 使用說明

[English](../README.md) | [简体中文](README.zh-Hans.md) | 繁體中文

倉庫的 `sdk/` 目錄是讀取遊戲檔案的離線 SDK。`python -m sdk` 開啟它的[選單介面](#選單介面tui)；各項功能也可以在專案根目錄用 `python -m` 單獨執行。安裝腳本 `sdk/setup_env.ps1` 和相依清單 `sdk/requirements.txt` 由所有功能共用：

| 功能 | 用途 | 需要的外部檔案 |
|---|---|---|
| `sdk.enemy_logic_exporter` | 從遊戲 EXE、IL2CPP 中繼資料和資源匯出中提取魔物行動邏輯，產生網頁使用的行動圖 JSON | 遊戲 EXE、IL2CPP 中繼資料、`MHWS-in-json` 資源；部分命令還需要 Ghidra |
| `sdk.skill_effect_exporter` | 找出原生程式碼中使用每個技能的函式，按技能等級求值，產生技能效果鏈路 JSON（`SkillDetails.xlsx` 的資料來源） | 遊戲 EXE、IL2CPP 中繼資料、`MHWS-in-json` 資源 |

IL2CPP 中繼資料是 REFramework 匯出的 `il2cpp_dump.json`，必須與 EXE 同一遊戲版本。它和 EXE 一樣由使用者提供，倉庫和 Release 都不保存副本。各項功能尋找它的順序相同：`-i/--il2cpp` 參數、環境變數 `MHWS_IL2CPP`、EXE 同目錄的 `il2cpp_dump.json`。EXE 與 dump 的 SHA-256 只登記在 `sdk/game_versions.json`；提交的資料與模型只記錄遊戲版本號。

只想重新產生網頁或表格、不改動提取結果時，不需要 SDK：建置器只讀取倉庫中已提交的 JSON（見「[只建置網頁](#只建置網頁)」）。

## 通用參數

| 參數 | 說明 |
|---|---|
| `-e`, `--exe` | 遊戲 EXE；預設取環境變數 `MHWS_EXE`，其次在所有 Steam 庫中尋找 |
| `-i`, `--il2cpp` | 與 EXE 同版本的 `il2cpp_dump.json`；預設取環境變數 `MHWS_IL2CPP`，其次取 EXE 同目錄的檔案 |
| `-n`, `--natives` | 解包 JSON 的 `natives` 目錄，預設 `MHWS-in-json/natives` |
| `-o`, `--output` | 輸出位置 |
| `-m`, `--models` | 研究模型目錄（`sdk.enemy_logic_exporter`） |
| `-w`, `--work-dir` | 研究快取目錄，寫在子命令前（`sdk.enemy_logic_exporter`） |

## 建置環境（Windows）

1. 安裝 Python 3.13（勾選 `py` 啟動器）與 Git，複製倉庫。
2. 在專案根目錄執行安裝腳本。它在 `.agents/sdk-venv` 建立虛擬環境，安裝固定版本的相依套件（Capstone、PyGhidra、questionary），最後執行環境檢查：

   ```powershell
   powershell -ExecutionPolicy Bypass -File sdk/setup_env.ps1
   ```

3. 按檢查結果補齊缺失項，然後再檢查一次：

   ```powershell
   .agents/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env
   .agents/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env --verify   # 同時核對 EXE 與 dump 的版本摘要（較慢）
   ```

| 檢查項 | 怎樣補齊 |
|---|---|
| 遊戲 EXE | 預設在所有 Steam 庫中尋找；裝在別處時設環境變數 `MHWS_EXE`，或給命令加 `-e` |
| IL2CPP dump | 用 REFramework 匯出與 EXE 同版本的 `il2cpp_dump.json`，放在 EXE 同目錄；放在別處時設環境變數 `MHWS_IL2CPP` 或用 `-i` 指定 |
| 資源匯出 | 隨倉庫檢出的 `MHWS-in-json/natives`，或用 `-n` 指定 |
| 資源換行 | 資源檔案必須保持匯出時的 LF 位元組。報錯時刪除 `MHWS-in-json` 目錄，再執行 `git checkout -- MHWS-in-json` |
| 研究快取 `--index`、`--helpers`、`--inventory`、`--requests` | 從已有機器複製整個 `.agents/enemy-logic-exporter`，或按「[遊戲更新後](#遊戲更新後)」重新產生（需要 Ghidra） |
| 工作目錄 | 預設 `.agents/enemy-logic-exporter`；可用 `-w` 或環境變數 `MHWS_SDK_WORK_DIR` 修改，但必須位於專案 `.agents` 內。快取放在其他磁碟時，用目錄連接把 `.agents` 指過去 |
| `GHIDRA_INSTALL_DIR`、`JAVA_HOME` | 只有 `decompile`、`analyze` 需要：安裝 Ghidra 12.0.4 及其支援的 JDK 後設定這兩個環境變數 |

以下範例中的 `python` 指上面虛擬環境中的直譯器；所有命令都在專案根目錄執行。查看任一命令的完整參數：`python -m sdk.<工具> <命令> --help`。

## 選單介面（TUI）

`python -m sdk` 開啟常用工作的選單：環境檢查、技能效果提取（全部或指定技能）、重建 `SkillDetails.xlsx`、魔物提取與玩家視圖、未知條件統計、發布與建置行動邏輯網頁，以及 SDK 測試。用方向鍵和 Enter 選擇（選單文字為簡體中文）。每個操作先印出要執行的完整命令列再執行，同樣的步驟可以直接寫進腳本。EXE 與 IL2CPP dump 的尋找方式和命令列相同，「设置 EXE 与 il2cpp 路径」可在本次工作階段中修改。發布前會先確認，避免誤覆蓋已提交的模型。安裝腳本會把專案根目錄登記到虛擬環境中（`mhws_sdk.pth`），因此選單可以在任意目錄啟動；此前建立的環境需要重新執行一次安裝腳本。

```powershell
.agents/sdk-venv/Scripts/python.exe -m sdk
```

## 魔物行動邏輯 SDK（`sdk.enemy_logic_exporter`）

SDK 只讀取遊戲檔案，不執行遊戲、不注入。它從 EXE 的 x64 指令中還原每張行為表的控制流程，再結合資源參數和 IL2CPP 中繼資料，把判斷條件、動作和繼續位置寫成 JSON。完整研究模型保存在 `.agents/enemy-logic-exporter`，用 `publish` 精簡後寫入 `src/processed_data/enemy_battle_logic/models`，網頁由這些模型產生。

目前模型對應遊戲版本 **1.42.0.2**（`sdk/enemy_logic_exporter/data/profiles/`）。EXE 與 IL2CPP dump 必須與 `sdk/game_versions.json` 中該版本登記的摘要一致，否則提取命令會拒絕執行。

### 只建置網頁

不需要 SDK 相依套件和遊戲檔案：

```powershell
python -m src.processed_data.enemy_battle_logic                     # 正式建置，輸出到 output/processed_data
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
python -m src.processed_data.enemy_battle_logic --template <模型.json> --output .agents/one
```

開啟輸出目錄下的 `enemy_battle_logic/index.html` 瀏覽。頁面可離線使用。

### 修改程式碼後重新提取

`-e`、`-i` 和研究快取參數省略時使用預設位置。全量提取約 15 分鐘。

```powershell
$w = '.agents/enemy-logic-exporter/fix'
python -B -m sdk.enemy_logic_exporter extract --enemy EM0002_00_0 -o "$w/one"   # 試跑一隻魔物
python -B -m sdk.enemy_logic_exporter extract-all -o "$w/s1"                     # 全部 34 隻
python -B -m sdk.enemy_logic_exporter player-view -m "$w/s1" -o "$w/s1p"         # 產生玩家視圖
python -B -m sdk.enemy_logic_exporter census -m "$w/s1p"                         # 含未知部分的條件，按命令與原因分組
python -B -m sdk.enemy_logic_exporter uncertainty -m "$w/s1p"                    # 玩家戰鬥樹中輸入都已知後仍無法判定的條件
python -B -m sdk.enemy_logic_exporter publish -m "$w/s1p"                        # 寫入網頁模型目錄
python -B -m src.processed_data.enemy_battle_logic --output "$w/site"
python -B -m unittest discover -s tests/sdk -t .
```

每次改動前後都比較 `census` 的 `unknownConditions` 和 `uncertainty` 的 `total.uncertain`。`player-view` 只接受 `.agents` 中的完整模型，不接受已發佈的精簡模型。

### 遊戲更新後

需要新版本的 EXE、與之同版本的 IL2CPP dump、重新匯出的資源，以及 Ghidra。

```powershell
python -B -m sdk.enemy_logic_exporter check-env --verify
python -B -m sdk.enemy_logic_exporter resolve-symbols --version <新版本>       # 產生 data/profiles/<新版本>.json
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<新版本>.json           # 先看報告
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<新版本>.json --apply   # 遷移位元組未變的證據
python -B -m sdk.enemy_logic_exporter analyze --version <新版本> -o .agents/enemy-logic-exporter/full-run/result --cache-dir .agents/enemy-logic-exporter/full-run/native
python -B -m sdk.enemy_logic_exporter requests --index .agents/enemy-logic-exporter/full-run/native/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json -o .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter recover --index .agents/enemy-logic-exporter/full-run/native/index.json --helpers .agents/enemy-logic-exporter/per-monster/helpers/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --requests .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter scheduler-slots
python -B -m sdk.enemy_logic_exporter roster --write
python -B -m sdk.enemy_logic_exporter new-monster --enemy <新魔物ID>          # 名單新增的每隻魔物
```

之後把 `sdk/enemy_logic_exporter/shared/config.py` 中的 `ACTIVE_GAME_VERSION` 改為新版本，再按「修改程式碼後重新提取」跑一遍。`migrate-evidence` 列出的待複核項和 `resolve-symbols` 報告的 `changed` 項必須逐條核對原生程式碼，不能只替換版本號或摘要。遊戲版本不變、只換用另一份 IL2CPP dump 時的步驟，以及詳細的核對順序，見 [SDK 維護說明](../enemy_logic_exporter/AGENTS.md)（簡體中文）。

### 命令一覽

| 命令 | 作用 | 需要 |
|---|---|---|
| `check-env` | 檢查相依套件、遊戲檔案、研究快取和 Ghidra 設定 | — |
| `extract` / `extract-all` | 提取一隻或全部魔物的完整研究模型 | EXE、dump、資源、研究快取 |
| `player-view` | 為完整模型產生玩家視圖（網頁使用的條件與輸入） | 完整模型 |
| `census` | 統計含未知部分的條件，按命令和原因分組 | 完整模型 |
| `uncertainty` | 統計玩家戰鬥樹中無法判定的條件 | 帶玩家視圖的完整模型 |
| `publish` | 刪除研究欄位、共享重複值，寫入 `src/processed_data/enemy_battle_logic/models` | 帶玩家視圖的完整模型 |
| `resolve-symbols` | 為新版本產生符號位址 profile | EXE、dump |
| `migrate-evidence` | 遷移位元組未變的證據列，其餘列入人工複核 | EXE、dump、新 profile |
| `scheduler-slots` | 恢復 AI 狀態與中斷請求的行為表槽 | EXE、dump |
| `roster` / `new-monster` | 更新大型魔物名單；為新魔物產生入口模組 | 資源 |
| `analyze` | 全量資源與原生證據分析，產生研究快取 | EXE、dump、資源、Ghidra |
| `requests` / `recover` | 發現動作請求；逐魔物恢復參數與命令實作 | 研究快取、EXE |
| `manifest` / `decompile` / `verify` / `index` | 新版本研究：定位方法、反編譯、核對位元組、建立原生索引 | EXE、dump（`decompile` 需要 Ghidra） |

### 常見問題

- **「资源发现后行为表发生变化」**：資源檔案的位元組與研究快取不一致，通常是換行被 Git 改成了 CRLF。按上表「資源換行」一項處理。
- **「原生配方的 EXE 来源变化」或版本不符**：EXE 或 dump 不是 profile 記錄的版本。確認檔案來源；遊戲已更新時按「遊戲更新後」處理。
- **「缺少 il2cpp dump」**：沒有找到 `il2cpp_dump.json`。放到 EXE 同目錄，或用 `-i`、`MHWS_IL2CPP` 指定。
- **「缺少研究缓存」**：`.agents/enemy-logic-exporter` 中沒有標準位置的快取。執行 `check-env` 查看路徑，複製或重新產生。
- **只能輸出到 `.agents`**：研究輸出必須位於專案 `.agents` 內，這是為了不把大型證據快取提交到 Git。

## 技能效果 SDK（`sdk.skill_effect_exporter`）

遊戲沒有「技能 → 效果數值」的資料表：SkillData 的四個數值槽沒有名稱，`PlayerSkillParam` 等參數檔案裡的欄位也不帶技能 ID，二者只在原生程式碼中連接。這個工具先掃描 EXE，找出以技能 ID 呼叫技能讀取方法的全部函式；再在「只裝備該技能、取某一等級」的情境下，按真實指令執行這些函式（布林與列舉參數逐一列舉），記錄回傳值、執行期條件以及數值來自哪個 SkillData 槽位、參數檔案欄位或 EXE 常數。結果寫入 `src/processed_data/skill_details/data/skill_links/`（`index.json` 加按技能類別拆分的分片），建置 PROCESSED_DATA 時據此產生 `SkillDetails.xlsx`。

```powershell
python -B -m sdk.skill_effect_exporter extract                                     # 全部技能，約 20 分鐘，寫入正式位置
python -B -m sdk.skill_effect_exporter extract -e <EXE> -i <il2cpp_dump.json>      # 指定輸入
python -B -m sdk.skill_effect_exporter extract -s HunterSkill_019 -o .agents/skill-effects/try.json   # 除錯單個技能
python -m src.processed_data.skill_details                                         # 只重建 SkillDetails.xlsx
```

- `SkillDetails.xlsx` 的「技能效果」表每列是一個技能等級（`Lv.X`）的一個效果，列出遊戲內的技能說明與等級說明，以及適用的武器、彈種或動作（「【武器】彈種」）。表中只保留從遊戲參數讀取到的數值，優先採用技能自身的 `getSkill*` 取值函式，不採用組合多個來源的函式；只在未裝備技能或疊加餐點效果時出現的數值不列出。效果名稱由取值函式名翻譯而來（`src/processed_data/skill_details/labels.py`，名稱為簡體中文），最後一欄保留函式名。數值為「a / b」表示數值隨戰鬥狀態變化，例如連擊的命中段數。
- 表格不列出的函式位址、參數、執行期條件、資料來源、EXE 常數和未模擬的呼叫保留在鏈路 JSON 中。

- 相依套件與上面的虛擬環境相同（Capstone）。
- 讀取獵人裝備武器類型（`HunterCharacter._HunterComp.Prepare.<WeaponBuilder>k__BackingField._EquippedWeaponType`）或弩彈種類（`app.WeaponGunDef.SHELL_TYPE`、`SHELL_PARAM_TYPE`，包括由呼叫回傳或寫入 `out` 參數的情況）的函式，按每種取值分別求值，鏈路 JSON 把取值記為參數「武器」「弹种」「弹药参数类型」。清單是 `sdk/skill_effect_exporter/config.py` 中的 `DIMENSIONS`。
- 有些 `cHunterSkill` 取值函式只回傳等級或倍率，實際效果由呼叫它的函式決定，例如 `getSkillDodgeNoHitLv` 的呼叫方 `getDodgeNoHitTime` 給出各迴避動作的無敵時間。讀取的技能不超過 `MAX_ACCESSOR_SKILLS` 個的取值函式，其呼叫方也會求值，鏈路中的用法記為 `accessor`。
- 超過路徑或指令上限的函式，會只保留仍能走到技能讀取點的路徑重新求值，其他呼叫按不透明呼叫處理；這些路徑標記為 `focused`。「只追踪可能经过技能读取点的路径仍超限」表示技能可能在此處（該武器或彈種下）起作用，但數值仍不完整。
- 結果相同、條件只差一個條件及其否定的路徑會合併，不影響結果的條件不再列出。每個情形最多保留 `MAX_RECORDED_PATHS` 條路徑，條件少的優先，最後一列註明未列出的條數。
- 輸出只記錄遊戲版本，不保存解包檔案摘要；更新 `MHWS-in-json` 後要重新執行 `extract`。
- 彙總多個技能的函式（如攻擊力合計）依賴其他技能的計時器等執行期狀態，鏈路 JSON 中可能記為 `too_many_paths`；同一技能的精確數值通常由 `getSkill*` 讀取函式給出。
- 需要人工說明的技能寫在 `sdk/skill_effect_exporter/notes.py`；版本相關的佈局常數集中在 `sdk/skill_effect_exporter/config.py`。遊戲更新後的檢查步驟見 [技能效果 SDK 維護說明](../skill_effect_exporter/AGENTS.md)（簡體中文）。
