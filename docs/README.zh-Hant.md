# MHWS-in-json

[English](../README.md) | [简体中文](README.zh-Hans.md) | 繁體中文

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

- `output/<語言>/*.xlsx`：對應語言的資料庫活頁簿。
- `output/DATABASE_<語言名稱>_<版本號>.zip`：每種語言一個發布資源包，僅包含該語言的 xlsx 檔案，不包含 `MHWS-in-json/`。
- `output/processed_data/`：額外轉換器產生的語言無關處理結果。
- `output/PROCESSED_DATA_<版本號>.zip`：語言無關的發布資源包，包含 `skill_pool.json`、`amulet_pool.json`、`graphic_preset.xlsx`、`弩枪客制零件信息.xlsx`、`HeavyBowgun.xlsx` 和 `LightBowgun.xlsx`。
- `output/MHWS-in-json_<版本號>.zip`：共享來源資料庫 JSON 發布資源包，包含 `MHWS-in-json/` 目錄。

壓縮包統一使用 deflate 最大壓縮率。來源資料庫 JSON 沒有多語言語義，因此只單獨打包一次，不再重複放入每個語言包。
`PROCESSED_DATA` 中的弩槍工作簿固定只匯出簡體中文。
任一文字檔中語言索引為 `-1` 的語言會被跳過。
執行腳本時，終端會輸出詳細的載入、轉換、儲存和打包日誌。

## 使用方式

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

入口不接收命令列參數。路徑、語言、輸出名稱和版本號等設定都在 [config.py](../config.py) 中修改。
