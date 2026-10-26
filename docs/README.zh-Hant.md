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
  processed_data/  # 後處理活頁簿與 JSON 資料集；行動圖模型
  shared/          # 來源資料、文字、RCOL、Excel 和日誌工具
  pipeline/        # 匯出、驗證、打包和發布
  site_data/       # 網站讀取的 JSON（與 web/ 的唯一介面）
sdk/
  il2cpp/          # IL2CPP 上傳與下載工具
  enemy_logic_exporter/
    shared/        # Python：native、resources、logic、models、workflow
    data/          # JSON：evidence/、models/、rules.v1.json
    monster/       # 每個魔物和變種的獨立入口
web/               # Vite + Vue 網站，只讀取 src/site_data 產生的 JSON
tests/
```

## 網站

[mhws-info.eggtargaryen.com](https://mhws-info.eggtargaryen.com/) 匯集各資訊站，只提供簡體中文：魔物行動邏輯（34 隻魔物，變種各有獨立頁面，不包含訓練靶）和技能效果數值（與 `SkillDetails.xlsx` 使用同一份技能效果鏈路 JSON）。

`sdk/`、`src/` 與 `web/` 互不匯入程式碼，只透過 JSON 傳遞資料。`python -m src.site_data` 把網站讀取的 JSON 寫入 `src/site_data/data/`（不提交到 Git），網站建置時把這個目錄複製到站點的 `data/`。發布匯出把同樣的檔案寫入 PROCESSED_DATA 的 `website/`：

```text
site.json                          部署日期、提交、是否為預覽
enemy_battle_logic/index.json      魔物列表
enemy_battle_logic/<enemyId>.json  單隻魔物的行動圖與技術圖資料
skill_details/skills.json          技能效果數值及其含義
```

`web/` 是 Vite + Vue 應用程式，首頁和每個資訊站各占一個路由（`/enemy_battle_logic/`、`/skill_details/`）。建置需要 Node.js 22 或更新版本，不需要 SDK。建置全站，輸出到 `web/dist`：

```powershell
python -m src.site_data && npm --prefix web ci && npm --prefix web run build
npm --prefix web run preview         # 在本機開啟 http://localhost:4173
```

修改頁面時用 `npm --prefix web run dev`，讀取同一份 JSON。`MHWS_SITE_DATA` 可讓建置改用其他資料目錄，例如發布包中的 `website/`。`python -m src.site_data --enemy-models <模型目錄> --preview` 可寫入 SDK 尚未發布的模型。

新增資訊站時，在 `src/site_data` 中寫出它的 JSON（由 `export_site_data` 呼叫），再在 `web/src/sites/<站點>/index.js` 中宣告標題、首頁卡片和路由，並加入 `web/src/sites.js`。

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
website/site.json
website/enemy_battle_logic/index.json
website/enemy_battle_logic/EM0001_00_0.json
...
website/skill_details/skills.json
```

`website/` 是[網站](#網站)讀取的 JSON；發布包不含網頁本身。

`MHWS-in-json_<版本>.zip` 包含來源 JSON，與活頁簿分開打包。

## 專案工具

倉庫的 `sdk/` 目錄是讀取遊戲檔案的離線 SDK，`python -m sdk` 開啟它的選單。它包含以下功能：

- 魔物行動邏輯（`sdk.enemy_logic_exporter`）：從遊戲檔案中提取魔物行動邏輯，產生行動圖網頁使用的 JSON。`src/processed_data/enemy_battle_logic/models` 中的 34 份模型保留未知分支的標記。
- 技能效果（`sdk.skill_effect_exporter`）：找出原生程式碼中使用每個技能的函式並按等級求值，產生 `SkillDetails.xlsx` 使用的技能效果鏈路 JSON。

SDK 需要使用者提供從記憶體 dump 出的遊戲 EXE（如 `MonsterHunterWilds_dump.exe`）和 REFramework `il2cpp_dump.json`，不記錄遊戲版本。環境建立（`sdk/setup_env.ps1`）與用法見 [SDK 使用說明](../sdk/docs/README.zh-Hant.md)。只重新產生[網站](#網站)或表格時不需要 SDK。

## 資料說明

- `SkillDetails.xlsx` 給出每個技能的效果數值。「技能效果」頁每列是一個技能在某一等級（`Lv.1`、`Lv.2`……）的一個效果，列出遊戲內的技能說明與等級說明、效果數值，以及適用的武器、彈種或動作（寫作「【武器】彈種」）。只列出從遊戲參數讀取到的數值，按「只裝備該技能」的情境求得。數值隨情形（如連續命中次數）不同時分列列出，情形寫在「条件」欄開頭；只在其他效果（飯技、狩獵笛旋律、武器自身狀態、其他技能的資料）生效時才出現的數值不列出；隨機判定寫作發動機率（如 80%）。只有程式碼中找不到區分條件時才保留「a / b」。「作用于」「计算」「条件」「单位」欄（數值作用於什麼、怎樣計算、何時生效、單位）來自 SDK 中每個技能的模組 `sdk/skill_effect_exporter/skills/hunterskill_<編號>.py` 裡人工整理的數值含義，由 SDK 寫進鏈路 JSON，依據程式碼中每個數值的用途寫出；`python -m src.processed_data.skill_details --meanings-report <檔案.md>` 列出每個效果的含義及其用途證據。「技能」頁合併 SkillCommonData 與 SkillData。名稱提供日文與簡體中文，說明和效果名稱只提供簡體中文。
- `MissionData.xlsx` 中每個任務完成條件佔一列，其餘任務欄位縱向合併。缺少對應語言文字時回退英文，無名稱的魔物保留 `EM` 編號。`SoloHealth` 列出可能的初始單人最大血量，計入任務難度、隨機血量檔位和`Legendary` 倍率；無法確定目標時留空。
- `WeaponActionValues.xlsx` 需要格式為 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。使用同版本輸入執行 `motlist-to-json action-map` 可重新產生，也可透過 `MHWS_ACTION_MAP_PATH` 指定其他檔案。每條對映各佔一列，未對映的 requestSet 保留，`MappingName` 留空。`MappingConfidence` 表示證據類別。日語以外的語言版本會在 `MappingName` 前增加日語名稱欄 `MappingNameJa`。
