# MHWS JSON to XLSX

[English](../README.md) | [简体中文](README.zh-Hans.md) | 繁體中文

本專案用於將 Monster Hunter Wilds 的 JSON 資料庫匯出為 Excel 活頁簿，並產生可直接發布的壓縮包。

## 輸出內容

執行 `python main.py` 後，所有檔案都會寫入 `output/`。

- `output/<語言>/*.xlsx`：對應語言的資料庫活頁簿。
- `output/DATABASE_<語言名稱>_<版本號>.zip`：每種語言一個資料庫包，包內包含該語言的 xlsx 檔案和 `MHWS-in-json/` 原始資料目錄。
- `output/processed_data/`：額外轉換器產生的語言無關處理結果。
- `output/PROCESSED_DATA_<版本號>.zip`：包含 `skill_pool.json`、`amulet_pool.json` 和 `graphic_preset.xlsx`。

壓縮包統一使用 deflate 最大壓縮率。
任一文字檔中語言索引為 `-1` 的語言會被跳過。

## 使用方式

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

入口不接收命令列參數。路徑、語言、輸出名稱和版本號等設定都在 [config.py](../config.py) 中修改。

## GitHub Release

[.github/workflows/release.yml](../.github/workflows/release.yml) 會在每次 push 時執行，也支援手動觸發。版本號格式為 UTC 時間 `yyyyMMdd-HHmmss-<短 hash>`，並會把 `output/` 下產生的所有 zip 上傳到 Release。

`.gitignore` 已忽略 Stage VoxelData 和 Enemy Constraint 這類超大型 JSON。如果這些檔案在加入忽略規則前已經進入提交歷史，推送到 GitHub 前仍需要另外清理歷史。

清理範圍見 [Git Large File Cleanup](GIT_LARGE_FILE_CLEANUP.md)。
