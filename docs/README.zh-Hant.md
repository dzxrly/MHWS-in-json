<div align="center">

# MHWS-in-json

[English](../README.md) | [简体中文](README.zh-Hans.md) | 繁體中文

</div>

將 MHWS 遊戲資料匯出為 JSON 和 Excel，目錄結構參考 [eigeen/mhws-data-dump-scripts](https://github.com/eigeen/mhws-data-dump-scripts) 和 [dtlnor/MHWs-in-json](https://github.com/dtlnor/MHWs-in-json)。

<div align="center">

<a href="https://github.com/dzxrly/PyREUser3">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-dark.svg">
    <img alt="Powered by PyREUser3" src="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-light.svg">
  </picture>
</a>

</div>

## 輸出內容

執行 `python main.py` 後，以下檔案會寫入 `output/`：

- `output/<語言>/*.xlsx`：對應語言的資料庫活頁簿。
- `output/<語言>/FullText.xlsx`：訊息 GUID 和本地化文字依次分為正常文字、已拒絕文字和空白文字，每組內保留來源檔案順序。已拒絕文字以 `[#Rejected#]` 開頭，未標記的空白文字保持空白。
- `output/<語言>/AmuletCollection.xlsx`：正規化的護石、技能和孔位池。名稱依語言本地化，稀有度使用 `Rare.X`，武器與防具孔位分欄，孔位等級使用 `Lv.X`。`SkillPool` 中每個技能點數池單獨佔一欄，項目格式為「技能名稱 `Lv.X`」。
- `output/<語言>/WeaponActionValues.xlsx`：每種武器一個 sheet，另有 `Ammo` sheet。動作對映與資源對映會明確區分；兩者都不存在的 requestSet 放在末尾，`MappingName` 保持空白並使用橙色底紋。
- `output/DATABASE_<語言名稱>_<版本號>.zip`：每種語言一個發布資源包，僅包含該語言的 xlsx 檔案，不包含 `MHWS-in-json/`。
- `output/processed_data/`：額外轉換器產生的語言無關處理結果。
- `output/PROCESSED_DATA_<版本號>.zip`：語言無關的發布資源包，包含 `skill_pool.json`、`amulet_pool.json`、`graphic_preset.xlsx`、`Bowgun_Custom.xlsx`、`HeavyBowgun.xlsx` 和 `LightBowgun.xlsx`。
- `output/MHWS-in-json_<版本號>.zip`：共享來源資料庫 JSON 發布資源包，包含 `MHWS-in-json/` 目錄。

壓縮包使用 deflate 最高壓縮級別。來源 JSON 只打包一次，不重複放入每個語言包。
`PROCESSED_DATA` 中的弩槍工作簿固定只匯出簡體中文。
如果某種語言在任一訊息檔案中的文字索引為 `-1`，則跳過該語言。
載入、轉換、儲存和打包進度會輸出到終端。

### 動作值對映

`WeaponActionValues.xlsx` 只讀取 `MHWS-in-json/ActionMap.json`（`_format = mhws_static_action_request_set_map_v2`）。該檔案需在本機使用 `motlist-to-json action-map` 產生，輸入必須來自同一遊戲版本：EXE dump、`il2cpp_dump.json`、motbank/motlist、PAK 檔案清單和 MHWS JSON。不再接受 v1。測試其他路徑的檔案時，設定 `MHWS_ACTION_MAP_PATH`。CI 直接讀取儲存庫中的資料包，不需要上述產生依賴。

只匯出玩家攻擊動作值 requestSet。嵌套值展開為葉節點欄位；每條動作或資源對映邊都會輸出一列，同一 RS 因此可以重複。`MappingKind`、穩定身分、內部名稱、名稱來源、資源角色、信賴級別、條件和證據來源等欄位會明確說明對映性質。

`actionRelations` 與 `resourceRelations` 是兩個獨立陣列。每條邊都指向精確識別 `(scope, rcol, requestSetID, keyHash, sourceRequestSetOrdinal)`；目標過期或同一條邊衝突時，匯出立即失敗。缺少本地化 GUID 時自動使用內部名稱或資源名稱，不需要人工補對映。即使本地化顯示文字相同，不同對映身分也不會合併。資源關係包含精確的 ShellList/PFB/RCOL 證據、自動推導的變體，以及明確標記的 RCOL 結構備援。

每個 sheet 的第一列列出 RCOL 來源路徑，第二列為欄位標題。資料列不重複顯示 `rcol` 路徑。

## 使用方式

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

入口不接收命令列參數。路徑、語言、輸出名稱和版本號等設定都在 [config.py](../config.py) 中修改。
