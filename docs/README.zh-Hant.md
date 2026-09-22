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
python -B -m tests
python main.py
```

程式不接收命令列參數。路徑、語言和版本在 [config.py](../config.py) 中設定。輸出路徑須位於專案內，預設寫入 `output/`。匯出先在 `.agents/export-runs/` 中產生完整結果，檢查活頁簿與壓縮檔內容後再統一發布；產生失敗時保留上一次輸出。`output/manifest.json` 記錄檔案雜湊、語言編號、輸入表路徑與各階段耗時。

## 程式碼結構

```text
src/
  database/        # DATABASE 活頁簿，每個功能獨立子目錄
  processed_data/  # 弩槍、魔物動作、畫質預設、護石 JSON 池
  shared/          # 來源資料快取、文字引用、裝備規則、Excel 工具
  pipeline/        # 匯出協調、打包、驗證、發布
tests/
  database/  processed_data/  shared/  pipeline/  release/
```

共用來源表在一次匯出中只讀取與標準化一次。資料庫預處理保留明確的文字 GUID 引用，包括技能與素材組合文字，再依語言填入翻譯；結構 GUID 保留為識別碼。資料庫與任務文字各自保留原有的清理與回退規則。動作值與任務活頁簿重複使用已註冊樣式，全文本活頁簿採用串流寫出。

使用 `python -B -m tests` 執行迴歸測試，CI 在匯出前執行同一套測試。測試暫存檔位於 `.agents/`；`.github/scripts/` 中的發布說明指令碼保持獨立執行。

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

`PROCESSED_DATA_<版本>.zip` 包含經過後處理的非資料庫資料。僅發布簡體中文版，不提供其他語言版本：

```text
Bowgun_Custom.xlsx
EnemyActionNames.xlsx
HeavyBowgun.xlsx
LightBowgun.xlsx
amulet_pool.json
graphic_preset.xlsx
skill_pool.json
```

`MHWS-in-json_<版本>.zip` 包含共用的來源 JSON，與各語言活頁簿分開打包。

## 活頁簿說明

`MissionData.xlsx` 以 `app.user_data.QuestData` 為主體。每個完成條件佔一列，其他任務欄位縱向合併。任務類型保留原值；缺少對應語言文字時回退英文，所有語言都沒有魔物名稱時保留 `EM` 編號。StreamQuest 文字取自配套資料。缺少 `QuestData` 的 `MsData` 任務編號排在末尾，填入能找到的文字。

`WeaponActionValues.xlsx` 需要 `_format` 為 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。重新產生時，使用同一遊戲版本的輸入執行 `motlist-to-json action-map`；可透過 `MHWS_ACTION_MAP_PATH` 指定其他檔案。每條動作或資源對映各佔一列；未對映的 requestSet 保留在表中，`MappingName` 留空。`MappingConfidence` 是證據類別，不是機率。
