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
- `output/<語言>/WeaponActionValues.xlsx`：每種武器一個 sheet，另有 `Ammo` sheet。沒有可靠動作名稱的記錄放在末尾，`ActionName` 保持空白並使用橙色底紋。
- `output/DATABASE_<語言名稱>_<版本號>.zip`：每種語言一個發布資源包，僅包含該語言的 xlsx 檔案，不包含 `MHWS-in-json/`。
- `output/processed_data/`：額外轉換器產生的語言無關處理結果。
- `output/PROCESSED_DATA_<版本號>.zip`：語言無關的發布資源包，包含 `skill_pool.json`、`amulet_pool.json`、`graphic_preset.xlsx`、`Bowgun_Custom.xlsx`、`HeavyBowgun.xlsx` 和 `LightBowgun.xlsx`。
- `output/MHWS-in-json_<版本號>.zip`：共享來源資料庫 JSON 發布資源包，包含 `MHWS-in-json/` 目錄。

壓縮包使用 deflate 最高壓縮級別。來源 JSON 只打包一次，不重複放入每個語言包。
`PROCESSED_DATA` 中的弩槍工作簿固定只匯出簡體中文。
如果某種語言在任一訊息檔案中的文字索引為 `-1`，則跳過該語言。
載入、轉換、儲存和打包進度會輸出到終端。

### 動作值對映

`WeaponActionValues.xlsx` 只讀取 `MHWS-in-json/ActionMap.json`（`_format = mhws_static_action_request_set_map_v1`）。該檔案需在本機使用 `motlist-to-json action-map` 產生，輸入必須來自同一遊戲版本：EXE dump、`il2cpp_dump.json`、motbank/motlist、PAK 檔案清單和 MHWS JSON。測試其他路徑的檔案時，設定 `MHWS_ACTION_MAP_PATH`。CI 直接讀取儲存庫中的資料包，不需要上述產生依賴。

只匯出玩家攻擊動作值 requestSet。嵌套值展開為葉節點欄位；同一 RS 對映到多個顯示動作名稱時，會對應輸出多列。

每條關係以 `(scope, rcol, requestSetID, keyHash, sourceRequestSetOrdinal)` 為鍵。鍵無法匹配目前 RCOL 資料或關係之間存在衝突時，匯出立即失敗。`actionNameGuid` 為空的關係不產生動作名稱；它們在末尾橙色區塊中的 `ActionName` 保持空白。保留多對多關係；同一顯示動作名稱下重複的 RS 列會去重，本地化後同名的動作會合併。

每個 sheet 的第一列列出 RCOL 來源路徑，第二列為欄位標題。資料列不重複顯示 `rcol` 路徑。

## 使用方式

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

入口不接收命令列參數。路徑、語言、輸出名稱和版本號等設定都在 [config.py](../config.py) 中修改。
