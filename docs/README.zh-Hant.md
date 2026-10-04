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

目前完整匯出會在魔物行動圖審核檢查處停止。研究圖可用下方的預覽命令查看。

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

暫存檔案和研究快取放在 `.agents/`。

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
amulet_pool.json
damage_calculator.zh-Hans.json
graphic_preset.xlsx
skill_effects.zh-Hans.json
skill_pool.json
enemy_battle_logic/index.html
enemy_battle_logic/EM0001_00_0.html
...
```

行動圖包含一個索引和 34 個魔物頁面。變種各有獨立頁面，不包含訓練靶。通過審核的頁面也會由預設分支發布到 GitHub Pages。

`MHWS-in-json_<版本>.zip` 包含來源 JSON，與活頁簿分開打包。

## 專案工具

使用 `python -m sdk.il2cpp upload --dry-run` 準備 IL2CPP 上傳，或用 `python -m sdk.il2cpp download` 取得建置資料。兩者沿用既有的 `gh` 登入狀態。

魔物 SDK 讀取遊戲資源、同版本 EXE 和 IL2CPP 中繼資料，產生行動圖 JSON；網頁建置器只讀取這些 JSON。提取和維護步驟見 [SDK 說明](../sdk/enemy_logic_exporter/AGENTS.md)。

`src/processed_data/enemy_battle_logic/models` 中的 34 份模型對應遊戲 **1.42.0.2**。模型仍有未知分支，語義審核尚未完成，目前僅供研究預覽。

```powershell
python -m sdk.enemy_logic_exporter --help
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
```

開啟 `.agents/battle-preview/enemy_battle_logic/index.html` 瀏覽行動圖。頁面可離線使用，支援縮放、節點搜尋和 SVG 匯出。預覽單個模型時，將 `--preview-all` 替換為 `--template <graph.json>`。

## 資料說明

- `damage_calculator.zh-Hans.json` 包含魔物肉質、部位與傷口、玩家動作記錄、斬味倍率和道具補正。缺失的替代肉質保留為 `null`。
- `skill_effects.zh-Hans.json` 包含技能等級和已核實的傷害效果，標明結算階段、武器與屬性範圍以及生效檔位。使用時假定勾選技能已生效，並選擇目前命中是否會心；資料不處理觸發過程、持續時間、會心率加值、餐點技能和異常積蓄，未核實效果不參與計算。
- `MissionData.xlsx` 中每個任務完成條件佔一列，其餘任務欄位縱向合併。缺少對應語言文字時回退英文，無名稱的魔物保留 `EM` 編號。`SoloHealth` 列出可能的初始單人最大血量，計入任務難度、隨機血量檔位和`Legendary` 倍率；無法確定目標時留空。
- `WeaponActionValues.xlsx` 需要格式為 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。使用同版本輸入執行 `motlist-to-json action-map` 可重新產生，也可透過 `MHWS_ACTION_MAP_PATH` 指定其他檔案。每條對映各佔一列，未對映的 requestSet 保留，`MappingName` 留空。`MappingConfidence` 表示證據類別。
