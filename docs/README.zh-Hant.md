<div align="center">

# MHWS-in-json

[English](../README.md) | [简体中文](README.zh-Hans.md) | 繁體中文

</div>

MHWS 遊戲資料匯出工具，輸出形式與 [eigeen/mhws-data-dump-scripts](https://github.com/eigeen/mhws-data-dump-scripts) 和 [dtlnor/MHWs-in-json](https://github.com/dtlnor/MHWs-in-json) 相近。

<div align="center">

<a href="https://github.com/dzxrly/PyREUser3">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-dark.svg">
    <img alt="Powered by PyREUser3" src="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-light.svg">
  </picture>
</a>

</div>

## 輸出內容

執行 `python main.py` 後，所有檔案都會寫入 `output/`。

- `output/<語言>/*.xlsx`：對應語言的資料庫活頁簿。`FullText.xlsx` 使用單一工作表記錄全部訊息 GUID 及其本地化文字，並按實際內容、已拒絕文字、空白文字分組，各組內保留來源檔案讀取順序；已拒絕文字以 `[#Rejected#]` 開頭，未標記的空白文字維持空白。`AmuletCollection.xlsx` 包含正規化的護石、技能和孔位池，名稱依語言本地化，稀有度顯示為 `Rare.X`，武器與防具孔位分欄並使用 `Lv.X` 格式；其中 `SkillPool` 依技能點數橫向分池，每個池各占一欄，項目顯示為「技能名稱 `Lv.X`」。`WeaponActionValues.xlsx` 會為每種武器及彈藥分別建立 sheet，並將無法可靠對映的 RS 放在末尾的橙色 `[未映射]` 區塊。
- `output/DATABASE_<語言名稱>_<版本號>.zip`：每種語言一個發布資源包，僅包含該語言的 xlsx 檔案，不包含 `MHWS-in-json/`。
- `output/processed_data/`：額外轉換器產生的語言無關處理結果。
- `output/PROCESSED_DATA_<版本號>.zip`：語言無關的發布資源包，包含 `skill_pool.json`、`amulet_pool.json`、`graphic_preset.xlsx`、`Bowgun_Custom.xlsx`、`HeavyBowgun.xlsx` 和 `LightBowgun.xlsx`。
- `output/MHWS-in-json_<版本號>.zip`：共享來源資料庫 JSON 發布資源包，包含 `MHWS-in-json/` 目錄。

壓縮包統一使用 deflate 最大壓縮率。來源資料庫 JSON 沒有多語言語義，因此只單獨打包一次，不再重複放入每個語言包。
`PROCESSED_DATA` 中的弩槍工作簿固定只匯出簡體中文。
任一文字檔中語言索引為 `-1` 的語言會被跳過。
執行腳本時，終端會輸出詳細的載入、轉換、儲存和打包日誌。

### 動作值對映

動作對映只讀取可攜式靜態資料包 `MHWS-in-json/ActionMap.json`（`_format = mhws_static_action_request_set_map_v1`）。該檔案應在本機使用 `motlist-to-json action-map`，結合相同遊戲版本的 EXE dump、`il2cpp_dump.json`、motbank/motlist、PAK 檔案清單及 MHWS JSON 產生，因此 GitHub Action 不必上傳這些大型依賴。暫時測試其他位置的資料包時，可設定 `MHWS_ACTION_MAP_PATH`。

每條關係都必須精確命中目前 RCOL 的五元身分 `(scope, rcol, requestSetID, keyHash, sourceRequestSetOrdinal)`；過期或互相衝突的資料包會直接中止匯出。沒有真實訊息 GUID 的關係不會視為已命名動作，而會保留在末尾 `[未映射]` 區塊。真實多對多關係會保留；同一最終動作名稱內完全相同的 RS 會去重，相同的本地化動作名稱會合併。

每個動作值 sheet 的第一列彙總 RCOL 來源路徑，第二列為欄位標題；資料區不再重複顯示 `rcol` 路徑欄。

## 使用方式

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

入口不接收命令列參數。路徑、語言、輸出名稱和版本號等設定都在 [config.py](../config.py) 中修改。
