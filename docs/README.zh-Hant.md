<div align="center">

# MHWS-in-json

[English](../README.md) | [简体中文](README.zh-Hans.md) | 繁體中文

</div>

將儲存庫中的 MHWS JSON 資料轉換為 Excel 活頁簿和發布壓縮檔。JSON 目錄結構參考 [eigeen/mhws-data-dump-scripts](https://github.com/eigeen/mhws-data-dump-scripts) 和 [dtlnor/MHWs-in-json](https://github.com/dtlnor/MHWs-in-json)。

<div align="center">

<a href="https://github.com/dzxrly/PyREUser3">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-dark.svg">
    <img alt="Powered by PyREUser3" src="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-light.svg">
  </picture>
</a>

</div>

## 網站

[mhws-info.eggtargaryen.com](https://mhws-info.eggtargaryen.com/)（只提供簡體中文）：

- 魔物行動邏輯：每隻魔物的出招決策樹，可按距離、角度和狀態篩選。共 34 隻魔物，變種各有獨立頁面。
- 技能效果數值：每個技能在各等級下的效果數值與生效條件。

## 執行

```powershell
python -m pip install -r requirements.txt
python main.py
```

在 [config.py](../config.py) 中設定路徑、語言和版本。程式不接收命令列參數，結果寫入 `output/`；匯出失敗時保留上一次輸出。測試命令為 `python -B -m tests`。

## 程式碼結構

```text
main.py, config.py           # 入口與設定
MHWS-in-json/                # 來源 JSON
src/
  database/                  # 資料庫活頁簿
  processed_data/            # 後處理活頁簿與 JSON；魔物行動模型
  shared/                    # 來源資料、文字、RCOL、Excel 和日誌工具
  pipeline/                  # 匯出、驗證、打包和發布
  site_data/                 # 網站資料；產生的 data/ 已提交
sdk/                         # 讀取遊戲檔案的離線 SDK
  enemy_logic_exporter/      # 魔物行動邏輯
    shared/  data/  monster/ #   共用程式碼、規則與證據、每隻魔物一個模組
  skill_effect_exporter/     # 技能效果數值
  action_map_exporter/       # ActionMap v2
    shared/  skills/         #   原生程式碼模擬與流程、每個技能一個模組
web/                         # 網站（Vite + Vue）；src/sites/ 中每個資訊站一個目錄
tests/
```

魔物模型或技能效果變化後，執行 `python -m src.site_data` 重新產生網站資料並提交；資料過期時測試會失敗。建置網站只需要 Node.js 22 或更新版本：先 `npm --prefix web ci`，再 `npm --prefix web run build`。

## 發布壓縮檔

`DATABASE_<語言>_<版本>.zip` 每種語言一份，包含該語言的資料庫活頁簿：

```text
AmuletCollection.xlsx
EquipCollection.xlsx
EquipRecipeCollection.xlsx
FullText.xlsx
ItemDataCollection.xlsx
MissionData.xlsx
SkillCollection.xlsx
WeaponActionValues.xlsx
```

`PROCESSED_DATA_<版本>.zip` 包含後處理資料，僅提供簡體中文版：

```text
Bowgun_Custom.xlsx
EnemyActionNames.xlsx
HeavyBowgun.xlsx
LightBowgun.xlsx
SkillDetails.xlsx
amulet_pool.json
enemy_battle_logic.json
graphic_preset.xlsx
skill_details.json
skill_pool.json
```

`enemy_battle_logic.json` 和 `skill_details.json` 是[網站](#網站)背後的完整資料。

`MHWS-in-json_<版本>.zip` 包含來源 JSON，與活頁簿分開打包。

## 專案工具

倉庫的 `sdk/` 目錄是讀取遊戲檔案的離線 SDK，`python -m sdk` 開啟它的選單。它包含以下功能：

- 魔物行動邏輯（`sdk.enemy_logic_exporter`）：從遊戲檔案中提取魔物行動邏輯，產生行動圖網頁使用的 JSON。`src/processed_data/enemy_battle_logic/models` 中的 34 份模型保留未知分支的標記。
- 技能效果（`sdk.skill_effect_exporter`）：找出原生程式碼中使用每個技能的函式並按等級求值，產生 `SkillDetails.xlsx` 使用的技能效果鏈路 JSON。
- 武器動作對映（`sdk.action_map_exporter`）：用匹配的 dump 和轉換後的 JSON 產生 `MHWS-in-json/ActionMap.json`，為 `WeaponActionValues.xlsx` 提供動作名稱。

SDK 需要使用者提供從記憶體 dump 出的遊戲 EXE（如 `MonsterHunterWilds_dump.exe`）和 REFramework `il2cpp_dump.json`，不記錄遊戲版本。環境建立（`sdk/setup_env.ps1`）與用法見 [SDK 使用說明](../sdk/docs/README.zh-Hant.md)。只重新產生網站或表格時不需要 SDK。

## 資料說明

- `SkillDetails.xlsx`：每列是一個技能在某一等級的一個效果，列出數值、作用對象、計算方式、生效條件和單位。數值按「只裝備該技能」求得；隨情形變化的數值按情形分列列出。
- `MissionData.xlsx`：每個任務完成條件佔一列。`SoloHealth` 列出可能的初始單人最大血量，計入任務難度、隨機血量檔位和 Legendary 倍率。
- `WeaponActionValues.xlsx` 需要 `MHWS-in-json/ActionMap.json`，可使用同版本輸入執行 `python -m sdk.action_map_exporter extract` 重新產生，或透過 `MHWS_ACTION_MAP_PATH` 指定其他檔案。未對映到的動作 `MappingName` 留空。
