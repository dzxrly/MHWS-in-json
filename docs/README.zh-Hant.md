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

## 執行

```powershell
python -m pip install -r requirements.txt
python main.py
```

在 [config.py](../config.py) 中設定路徑、語言和版本。程式不接收命令列參數，結果寫入 `output/`；匯出失敗時保留上一次輸出。測試命令為 `python -B -m tests`。

## 程式碼結構

```text
src/
  database/        # 資料庫活頁簿
  processed_data/  # 後處理活頁簿、JSON 資料集和行動圖網頁
  shared/          # 來源資料、文字、RCOL、Excel 和日誌工具
  pipeline/        # 匯出、驗證、打包和發布
sdk/
  il2cpp/          # IL2CPP 上傳與下載工具
  enemy_logic_exporter/
    shared/        # Python：native、resources、logic、models、workflow
    data/          # JSON：evidence/、models/、rules.v1.json
    monster/       # 每個魔物和變種的獨立入口
tests/
```

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
graphic_preset.xlsx
skill_pool.json
enemy_battle_logic/index.html
enemy_battle_logic/EM0001_00_0.html
...
```

行動圖包含一個索引和 34 個魔物頁面。變種各有獨立頁面，不包含訓練靶。線上行動圖網站：[mhws-monsters-ai.eggtargaryen.com](https://mhws-monsters-ai.eggtargaryen.com/)。

`MHWS-in-json_<版本>.zip` 包含來源 JSON，與活頁簿分開打包。

## 專案工具

倉庫的 `sdk/` 目錄是讀取遊戲檔案的離線 SDK，`python -m sdk` 開啟它的選單。它包含以下功能：

- 魔物行動邏輯（`sdk.enemy_logic_exporter`）：從遊戲檔案中提取魔物行動邏輯，產生行動圖網頁使用的 JSON。`src/processed_data/enemy_battle_logic/models` 中的 34 份模型保留未知分支的標記。
- 技能效果（`sdk.skill_effect_exporter`）：找出原生程式碼中使用每個技能的函式並按等級求值，產生 `SkillDetails.xlsx` 使用的技能效果鏈路 JSON。

SDK 需要使用者提供從記憶體 dump 出的遊戲 EXE（如 `MonsterHunterWilds_dump.exe`）和 REFramework `il2cpp_dump.json`，不記錄遊戲版本。環境建立（`sdk/setup_env.ps1`）與用法見 [SDK 使用說明](../sdk/docs/README.zh-Hant.md)。只重新產生網頁或表格時不需要 SDK：

```powershell
python -m src.processed_data.enemy_battle_logic --preview-all --output .tmp/battle-preview
```

然後開啟 `.tmp/battle-preview/enemy_battle_logic/index.html`，頁面可離線使用。

`SkillDetails.xlsx` 中的技能效果數值也可以產生為單個離線網頁（簡體中文），資料來自同一份技能效果鏈路 JSON：

```powershell
python -m src.processed_data.skill_details.web --output .tmp/skill-web
```

開啟 `.tmp/skill-web/skill_details/index.html`。技能按類別列出，可按名稱、效果和武器搜尋；每個效果一張小表，欄是技能等級，列是適用的武器、彈種、動作或情形，旁邊給出數值含義（作用於、計算、條件、單位），程式碼依據可展開查看。

## 資料說明

- `SkillDetails.xlsx` 給出每個技能的效果數值。「技能效果」頁每列是一個技能在某一等級（`Lv.1`、`Lv.2`……）的一個效果，列出遊戲內的技能說明與等級說明、效果數值，以及適用的武器、彈種或動作（寫作「【武器】彈種」）。只列出從遊戲參數讀取到的數值，按「只裝備該技能」的情境求得。數值隨情形（如連續命中次數）不同時分列列出，情形寫在「条件」欄開頭；只在其他效果（飯技、狩獵笛旋律、武器自身狀態、其他技能的資料）生效時才出現的數值不列出；隨機判定寫作發動機率（如 80%）。只有程式碼中找不到區分條件時才保留「a / b」。「作用于」「计算」「条件」「单位」欄（數值作用於什麼、怎樣計算、何時生效、單位）來自 SDK 中每個技能的模組 `sdk/skill_effect_exporter/skills/hunterskill_<編號>.py` 裡人工整理的數值含義，由 SDK 寫進鏈路 JSON，依據程式碼中每個數值的用途寫出；`python -m src.processed_data.skill_details --meanings-report <檔案.md>` 列出每個效果的含義及其用途證據。「技能」頁合併 SkillCommonData 與 SkillData。名稱提供日文與簡體中文，說明和效果名稱只提供簡體中文。
- `MissionData.xlsx` 中每個任務完成條件佔一列，其餘任務欄位縱向合併。缺少對應語言文字時回退英文，無名稱的魔物保留 `EM` 編號。`SoloHealth` 列出可能的初始單人最大血量，計入任務難度、隨機血量檔位和`Legendary` 倍率；無法確定目標時留空。
- `WeaponActionValues.xlsx` 需要格式為 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。使用同版本輸入執行 `motlist-to-json action-map` 可重新產生，也可透過 `MHWS_ACTION_MAP_PATH` 指定其他檔案。每條對映各佔一列，未對映的 requestSet 保留，`MappingName` 留空。`MappingConfidence` 表示證據類別。日語以外的語言版本會在 `MappingName` 前增加日語名稱欄 `MappingNameJa`。
