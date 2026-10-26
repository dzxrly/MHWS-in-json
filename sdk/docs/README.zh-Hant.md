# SDK 使用說明

[English](../README.md) | [简体中文](README.zh-Hans.md) | 繁體中文

倉庫的 `sdk/` 目錄是讀取遊戲檔案的離線 SDK。`python -m sdk` 開啟它的[選單介面](#選單介面tui)；各項功能也可以在專案根目錄用 `python -m` 單獨執行。安裝腳本 `sdk/setup_env.ps1` 和相依清單 `sdk/requirements.txt` 由所有功能共用：

| 功能 | 用途 | 需要的外部檔案 |
|---|---|---|
| `sdk.enemy_logic_exporter` | 從 dump 出的遊戲 EXE、IL2CPP 中繼資料和資源匯出中提取魔物行動邏輯，產生網頁使用的行動圖 JSON | dump 出的 EXE、IL2CPP 中繼資料、`MHWS-in-json` 資源；部分命令還需要 Ghidra |
| `sdk.skill_effect_exporter` | 找出原生程式碼中使用每個技能的函式，按技能等級求值，產生技能效果鏈路 JSON（`SkillDetails.xlsx` 的資料來源） | dump 出的 EXE、IL2CPP 中繼資料、`MHWS-in-json` 資源 |

兩項功能讀取的都是從記憶體 dump 出的遊戲 EXE（例如 `MonsterHunterWilds_dump.exe`），產生 REFramework 的 `il2cpp_dump.json` 之前本來就會得到它；不使用原版 `MonsterHunterWilds.exe`。這兩個檔案都由使用者提供，倉庫和 Release 都不保存副本，SDK 也不猜測路徑：用 `-e/--exe`、`-i/--il2cpp` 指定，或設環境變數 `MHWS_EXE`、`MHWS_IL2CPP`。SDK 不記錄遊戲版本或檔案摘要；遊戲更新後，程式碼或資料對不上的地方會直接報錯（符號無法定位、原生位元組不一致等），按「[遊戲更新後](#遊戲更新後)」處理。

只想重新產生網頁或表格、不改動提取結果時，不需要 SDK：建置器只讀取倉庫中已提交的 JSON（見「[只建置網頁](#只建置網頁)」）。

## 通用參數

| 參數 | 說明 |
|---|---|
| `-e`, `--exe` | dump 出的遊戲 EXE；未設環境變數 `MHWS_EXE` 時必須指定 |
| `-i`, `--il2cpp` | REFramework 匯出的 `il2cpp_dump.json`；未設環境變數 `MHWS_IL2CPP` 時必須指定 |
| `-n`, `--natives` | 解包 JSON 的 `natives` 目錄，預設 `MHWS-in-json/natives` |
| `-o`, `--output` | 輸出位置 |
| `-m`, `--models` | 研究模型目錄（`sdk.enemy_logic_exporter`） |
| `-w`, `--work-dir` | 研究快取目錄，寫在子命令前（`sdk.enemy_logic_exporter`） |

## 建置環境（Windows）

1. 安裝 Python 3.13（勾選 `py` 啟動器）與 Git，複製倉庫。
2. 在專案根目錄執行安裝腳本。它在 `.tmp/sdk-venv` 建立虛擬環境，安裝固定版本的相依套件（Capstone、PyGhidra、questionary、rich），最後執行環境檢查：

   ```powershell
   powershell -ExecutionPolicy Bypass -File sdk/setup_env.ps1 -Exe <dump 出的 EXE> -Il2cpp <il2cpp_dump.json>
   ```

3. 按檢查結果補齊缺失項，然後再檢查一次：

   ```powershell
   .tmp/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env -e <dump 出的 EXE> -i <il2cpp_dump.json>
   ```

| 檢查項 | 怎樣補齊 |
|---|---|
| dump 出的 EXE | 從執行中的遊戲 dump 出的 EXE（如 `MonsterHunterWilds_dump.exe`）；用 `-e` 指定或設環境變數 `MHWS_EXE` |
| IL2CPP dump | REFramework 對同一遊戲匯出的 `il2cpp_dump.json`；用 `-i` 指定或設環境變數 `MHWS_IL2CPP` |
| 資源匯出 | 隨倉庫檢出的 `MHWS-in-json/natives`，或用 `-n` 指定 |
| 資源換行 | 資源檔案必須保持匯出時的 LF 位元組。報錯時刪除 `MHWS-in-json` 目錄，再執行 `git checkout -- MHWS-in-json` |
| 研究快取 `--index`、`--helpers`、`--inventory`、`--requests` | 從已有機器複製整個 `.tmp/enemy-logic-exporter`，或按「[遊戲更新後](#遊戲更新後)」重新產生（需要 Ghidra） |
| 工作目錄 | 預設 `.tmp/enemy-logic-exporter`；可用 `-w` 或環境變數 `MHWS_SDK_WORK_DIR` 修改，但必須位於專案 `.tmp` 內。快取放在其他磁碟時，用目錄連接把 `.tmp` 指過去 |
| `GHIDRA_INSTALL_DIR`、`JAVA_HOME` | 只有 `decompile`、`analyze` 需要：安裝 Ghidra 12.0.4 及其支援的 JDK 後設定這兩個環境變數 |

以下範例中的 `python` 指上面虛擬環境中的直譯器；所有命令都在專案根目錄執行，並已設定 `MHWS_EXE`、`MHWS_IL2CPP`（否則加上 `-e`、`-i`）。查看任一命令的完整參數：`python -m sdk.<工具> <命令> --help`。

## 選單介面（TUI）

`python -m sdk` 開啟常用工作的選單：環境檢查、技能效果提取（全部或指定技能）、重建 `SkillDetails.xlsx`、魔物提取與玩家視圖、未知條件統計、發布與建置行動邏輯網頁，以及 SDK 測試。用方向鍵和 Enter 選擇（選單文字為簡體中文）。每個操作先印出要執行的完整命令列再執行，同樣的步驟可以直接寫進腳本。選單啟動時讀取 `MHWS_EXE`、`MHWS_IL2CPP`；未設定時先詢問 dump 出的 EXE 與 IL2CPP dump 的路徑，「设置 EXE 与 il2cpp 路径」可在本次工作階段中修改。發布前會先確認，避免誤覆蓋已提交的模型。耗時的步驟（技能提取、`extract-all`、`player-view`、`publish`）會顯示進度條，給出已完成數量、用時與預計剩餘時間，選單和命令列中都會顯示（`sdk/progress.py`）。安裝腳本會把專案根目錄登記到虛擬環境中（`mhws_sdk.pth`），因此選單可以在任意目錄啟動；此前建立的環境需要重新執行一次安裝腳本。

```powershell
.tmp/sdk-venv/Scripts/python.exe -m sdk
```

## 魔物行動邏輯 SDK（`sdk.enemy_logic_exporter`）

SDK 只讀取遊戲檔案，不執行遊戲、不注入。它從 EXE 的 x64 指令中還原每張行為表的控制流程，再結合資源參數和 IL2CPP 中繼資料，把判斷條件、動作和繼續位置寫成 JSON。完整研究模型保存在 `.tmp/enemy-logic-exporter`，用 `publish` 精簡後寫入 `src/processed_data/enemy_battle_logic/models`，網頁由這些模型產生。

函式位址取自 `sdk/enemy_logic_exporter/data/profile.json`，由 `resolve-symbols` 按目前 dump 出的 EXE 與 IL2CPP dump 重新產生。

### 只建置網頁

不需要 SDK 相依套件和遊戲檔案：

```powershell
python -m src.site_data                                         # 正式資料，全部 34 個魔物
python -m src.site_data --enemy-models <目錄> --preview --output .tmp/site-preview   # 部分魔物，如剛提取的模型
python -m src.site_data --enemy-template <模型.json> --output .tmp/site-preview      # 單個魔物
$env:MHWS_SITE_DATA = (Resolve-Path .tmp/site-preview)        # 網站改為顯示預覽資料
npm --prefix web run dev                                       # 在 http://localhost:5173 瀏覽
```

不帶 `--output` 時重寫已提交的 `src/site_data/data/`，`publish` 之後一併提交；預覽必須寫到其他目錄。網站命令見[網站](../../docs/README.zh-Hant.md#網站)。

### 修改程式碼後重新提取

`-e`、`-i` 和研究快取參數省略時使用預設位置。全量提取約 15 分鐘。

```powershell
$w = '.tmp/enemy-logic-exporter/fix'
python -B -m sdk.enemy_logic_exporter extract --enemy EM0002_00_0 -o "$w/one"   # 試跑一隻魔物
python -B -m sdk.enemy_logic_exporter extract-all -o "$w/s1"                     # 全部 34 隻
python -B -m sdk.enemy_logic_exporter player-view -m "$w/s1" -o "$w/s1p"         # 產生玩家視圖
python -B -m sdk.enemy_logic_exporter census -m "$w/s1p"                         # 含未知部分的條件，按命令與原因分組
python -B -m sdk.enemy_logic_exporter uncertainty -m "$w/s1p"                    # 玩家戰鬥樹中輸入都已知後仍無法判定的條件
python -B -m sdk.enemy_logic_exporter publish -m "$w/s1p"                        # 寫入網頁模型目錄
python -B -m src.site_data                                                       # 網站 JSON，提交 src/site_data/data
python -B -m unittest discover -s tests/sdk -t .
```

每次改動前後都比較 `census` 的 `unknownConditions` 和 `uncertainty` 的 `total.uncertain`。`player-view` 只接受 `.tmp` 中的完整模型，不接受已發佈的精簡模型。

### 遊戲更新後

需要新的 dump 出的 EXE、對應的 IL2CPP dump、重新匯出的資源，以及 Ghidra。

```powershell
python -B -m sdk.enemy_logic_exporter check-env
python -B -m sdk.enemy_logic_exporter resolve-symbols -o .tmp/enemy-logic-exporter/new-profile.json   # 報告移動、變化的符號
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile .tmp/enemy-logic-exporter/new-profile.json           # 先看報告
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile .tmp/enemy-logic-exporter/new-profile.json --apply   # 遷移程式碼未變的證據
Copy-Item .tmp/enemy-logic-exporter/new-profile.json sdk/enemy_logic_exporter/data/profile.json
python -B -m sdk.enemy_logic_exporter analyze -o .tmp/enemy-logic-exporter/full-run/result --cache-dir .tmp/enemy-logic-exporter/full-run/native
python -B -m sdk.enemy_logic_exporter requests --index .tmp/enemy-logic-exporter/full-run/native/index.json --inventory .tmp/enemy-logic-exporter/full-run/result/inventory.json -o .tmp/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter recover --index .tmp/enemy-logic-exporter/full-run/native/index.json --helpers .tmp/enemy-logic-exporter/per-monster/helpers/index.json --inventory .tmp/enemy-logic-exporter/full-run/result/inventory.json --requests .tmp/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter scheduler-slots
python -B -m sdk.enemy_logic_exporter roster --write
python -B -m sdk.enemy_logic_exporter new-monster --enemy <新魔物ID>          # 名單新增的每隻魔物
```

之後按「修改程式碼後重新提取」跑一遍。`migrate-evidence` 列出的待複核項和 `resolve-symbols` 報告的 `changed` 項必須逐條核對原生程式碼。詳細的核對順序見 [SDK 維護說明](../enemy_logic_exporter/AGENTS.md)（簡體中文）。

### 命令一覽

| 命令 | 作用 | 需要 |
|---|---|---|
| `check-env` | 檢查相依套件、遊戲檔案、研究快取和 Ghidra 設定 | — |
| `extract` / `extract-all` | 提取一隻或全部魔物的完整研究模型 | EXE、dump、資源、研究快取 |
| `player-view` | 為完整模型產生玩家視圖（網頁使用的條件與輸入） | 完整模型 |
| `census` | 統計含未知部分的條件，按命令和原因分組 | 完整模型 |
| `uncertainty` | 統計玩家戰鬥樹中無法判定的條件 | 帶玩家視圖的完整模型 |
| `publish` | 刪除研究欄位、共享重複值，寫入 `src/processed_data/enemy_battle_logic/models` | 帶玩家視圖的完整模型 |
| `resolve-symbols` | 按目前 EXE 重新產生符號位址 profile（預設寫入 `data/profile.json`） | EXE、dump |
| `migrate-evidence` | 遷移程式碼未變的證據列，其餘列入人工複核 | EXE、dump、新 profile |
| `scheduler-slots` | 恢復 AI 狀態與中斷請求的行為表槽 | EXE、dump |
| `roster` / `new-monster` | 更新大型魔物名單；為新魔物產生入口模組 | 資源 |
| `analyze` | 全量資源與原生證據分析，產生研究快取 | EXE、dump、資源、Ghidra |
| `requests` / `recover` | 發現動作請求；逐魔物恢復參數與命令實作 | 研究快取、EXE |
| `manifest` / `decompile` / `verify` / `index` | 新建置研究：定位方法、反編譯、核對位元組、建立原生索引 | EXE、dump（`decompile` 需要 Ghidra） |

### 常見問題

- **「资源发现后行为表发生变化」**：資源檔案的位元組與研究快取不一致，通常是換行被 Git 改成了 CRLF。按上表「資源換行」一項處理。
- **「原生字节不匹配」/「Native evidence mismatch」或「辅助函数特征不唯一或失效」**：EXE 的程式碼與 profile、研究快取所依據的不同——遊戲已更新，或傳入的是原版 EXE 而不是 dump 出的 EXE。先檢查 `-e`；遊戲已更新時按「遊戲更新後」處理。
- **「the following arguments are required: -e/--exe」或「-i/--il2cpp」**：指定 dump 出的 EXE 和 IL2CPP dump，或設環境變數 `MHWS_EXE`、`MHWS_IL2CPP`。
- **「缺少研究缓存」**：`.tmp/enemy-logic-exporter` 中沒有標準位置的快取。執行 `check-env` 查看路徑，複製或重新產生。
- **只能輸出到 `.tmp`**：研究輸出必須位於專案 `.tmp` 內，這是為了不把大型證據快取提交到 Git。

## 技能效果 SDK（`sdk.skill_effect_exporter`）

遊戲沒有「技能 → 效果數值」的資料表：SkillData 的四個數值槽沒有名稱，`PlayerSkillParam` 等參數檔案裡的欄位也不帶技能 ID，二者只在原生程式碼中連接。這個工具先掃描 EXE，找出以技能 ID 呼叫技能讀取方法的全部函式；再在「只裝備該技能、取某一等級」的情境下，按真實指令執行這些函式（布林與列舉參數逐一列舉），記錄回傳值、執行期條件以及數值來自哪個 SkillData 槽位、參數檔案欄位或 EXE 常數。結果寫入 `src/processed_data/skill_details/data/skill_links/`（`index.json` 加按技能類別拆分的分片），建置 PROCESSED_DATA 時據此產生 `SkillDetails.xlsx`。

```powershell
python -B -m sdk.skill_effect_exporter extract -e <dump 出的 EXE> -i <il2cpp_dump.json>   # 全部技能，約 30 分鐘，寫入正式位置
python -B -m sdk.skill_effect_exporter extract -s HunterSkill_019 -o .tmp/skill-effects/try.json   # 除錯單個技能
python -B -m sdk.skill_effect_exporter extract --all-links -o .tmp/skill-effects/all   # 也求值技能模組跳過的函式（遊戲更新後核對）
python -B -m sdk.skill_effect_exporter annotate                                    # 只把技能模組的數值含義與說明寫進 index.json，不重新求值
python -B -m sdk.skill_effect_exporter new-skill -s HunterSkill_250                # 為技能表新增的技能產生空模組
python -m src.processed_data.skill_details                                         # 只重建 SkillDetails.xlsx
```

- `SkillDetails.xlsx` 的「技能效果」表每列是一個技能等級（`Lv.X`）的一個效果，列出遊戲內的技能說明與等級說明，以及適用的武器、彈種或動作（「【武器】彈種」）。表中只保留從遊戲參數讀取到的數值，優先採用技能自身的 `getSkill*` 取值函式，不採用組合多個來源的函式；只在未裝備技能或疊加餐點效果時出現的數值不列出。每個技能在 `sdk/skill_effect_exporter/skills/hunterskill_<編號>.py` 有獨立模組，寫明它每個顯示效果的數值含義（`MEANINGS`：名稱、作用於、計算、條件、單位、依據，以及數值所隨情形的名稱）和已核實的說明（`NOTES`）；`extract` 把它們寫進 `index.json`，修改模組後用 `annotate` 單獨更新。沒有寫含義的效果按取值函式名翻譯命名（`src/processed_data/skill_details/labels.py`，名稱為簡體中文），最後一欄保留函式名。數值隨情形（如連擊的命中次數）變化時按情形分列；只有程式碼中找不到區分條件時才保留「a / b」。
- 表格不列出的函式位址、參數、執行期條件、資料來源、EXE 常數和未模擬的呼叫保留在鏈路 JSON 中。

- 相依套件與上面的虛擬環境相同（Capstone）。
- 讀取獵人裝備武器類型（`HunterCharacter._HunterComp.Prepare.<WeaponBuilder>k__BackingField._EquippedWeaponType`）或弩彈種類（`app.WeaponGunDef.SHELL_TYPE`、`SHELL_PARAM_TYPE`，包括由呼叫回傳或寫入 `out` 參數的情況）的函式，按每種取值分別求值，鏈路 JSON 把取值記為參數「武器」「弹种」「弹药参数类型」。清單是 `sdk/skill_effect_exporter/config.py` 中的 `DIMENSIONS`。
- 有些 `cHunterSkill` 取值函式只回傳等級或倍率，實際效果由呼叫它的函式決定，例如 `getSkillDodgeNoHitLv` 的呼叫方 `getDodgeNoHitTime` 給出各迴避動作的無敵時間。讀取的技能不超過 `MAX_ACCESSOR_SKILLS` 個的取值函式，其呼叫方也會求值，鏈路中的用法記為 `accessor`。
- 超過路徑或指令上限的函式，會只保留仍能走到技能讀取點的路徑重新求值，其他呼叫按不透明呼叫處理；這些路徑標記為 `focused`。「只追踪可能经过技能读取点的路径仍超限」表示技能可能在此處（該武器或彈種下）起作用，但數值仍不完整。傳入技能參數（參數塊或從中讀出的值）的呼叫仍按真實程式碼執行。聚焦求值仍超限時改為窄聚焦：到達讀取點之前，兩個分支都能到達讀取點時只走更近的一個，即只沿一種先前執行時條件的組合追蹤（路徑標記 `narrow`，仍超限時詳情為「只沿最近分支追踪到技能读取点仍超限」）。`cHunterSkill.update` 這類逐幀處理的大函式按這種方式求值。
- 結果相同、條件只差一個條件及其否定的路徑會合併，不影響結果的條件不再列出。每個情形最多保留 `MAX_RECORDED_PATHS` 條路徑，條件少的優先，最後一列註明未列出的條數。
- 用途追蹤：除 `getSkill*`/`isSkill*` 取值函式本身外，每條鏈路在最高等級再求值一次，把技能讀取呼叫（`getSkillValue`、`getSkillLevelCore`、`checkSkillActive` 或被呼叫的取值函式）換成有名稱的未知量，例如 `技能等级〈HunterSkill_019〉()`。鏈路的 `usage` 欄位說明技能數值在什麼條件下與什麼比較、相乘、寫入哪裡；數值本身仍在 `results` 中。
- 沒有任何已求值路徑從中取值的參數欄位（靜態掃描經 `PlayerGlobalParam` 單例讀取的指令得到），會在讀取它且使用技能的函式中、以讀取指令為聚焦點再求值一次，鏈路的用法記為 `param`。例如彈道強化 Lv3 在會心距離命中時攻擊力 +5，是在弩砲和弓的命中處理函式裡讀取的。若這類呼叫方讀取了取值函式沒有讀到的資料，技能效果表也會列出它，並按這些資料命名效果。只被本身不使用技能的函式讀取的欄位（如 `cHunterSkillParamInfo.beginKnight`、`cHunterSkill.beginRyunyu`），經兩層以內呼叫它的、使用技能的函式求值，以這些呼叫為聚焦點，數值歸到呼叫方檢查的技能。
- 分叉條件比較了來自遊戲資料的值時（如心眼的肉質閾值 `_Shingan_MeatThreshold`），路徑在 `compared` 中列出它。
- `index.json` 中有 `coverage`：按技能參數檔案（`PlayerSkillParam`、`PlayerMealSkillParam` 等 `PlayerGlobalParam` 中型別名稱以 `SkillParam` 結尾的欄位）列出每個欄位的讀取函式，以及哪些技能的路徑傳回了它（`value`）、把它寫入執行時狀態（`write`）或在條件中比較了它（`compare`）；按技能列出非零的 SkillData 槽位和以這三種方式用到的槽位。三種用法都沒有的，就是表格可能仍然漏掉的效果。
- 技能效果表也會列出處理函式寫入執行時狀態的數值（如技能發動時寫入的持續時間，效果名以「写入」開頭並保留欄位名），以及只在取值函式之外讀到的數值。兩者都只在該資料項還沒有列出、且沒有其他技能的鏈路用到它時才列出，避免彙總多個技能的函式把其他技能的資料算進來。
- 輸出不記錄遊戲版本或摘要；遊戲或 `MHWS-in-json` 更新後要重新執行 `extract`。
- 彙總多個技能的函式（如攻擊力合計）依賴其他技能的計時器等執行期狀態，鏈路 JSON 中可能記為 `too_many_paths`；同一技能的精確數值通常由 `getSkill*` 讀取函式給出。
- 與敵人邏輯 SDK 相同，共通程式碼在 `sdk/skill_effect_exporter/shared/`，每個技能在 `skills/` 有獨立模組：它的提取步驟（`extract`，以及所有技能的鏈路求完後執行的 `extract_parameters`；多數只是呼叫共通步驟的薄入口，只屬於這個技能的特殊處理寫在這裡，如掃描無法對應到技能的函式及核對依據 `DECLARED_METHODS`，以及得不到本技能可顯示數值、只記錄鏈路不求值的函式 `SKIPPED_FUNCTIONS`）、顯示效果的數值含義和說明。對所有技能成立的說明寫在 `notes.py`，版本相關的佈局常數集中在 `config.py`，二者都在 `sdk/skill_effect_exporter/` 根部。遊戲更新後的檢查步驟見 [技能效果 SDK 維護說明](../skill_effect_exporter/AGENTS.md)（簡體中文）。
