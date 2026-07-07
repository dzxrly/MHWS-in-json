# MHWS JSON to XLSX

[English](../README.md) | 简体中文 | [繁體中文](README.zh-Hant.md)

本项目用于把 Monster Hunter Wilds 的 JSON 数据库导出为 Excel 工作簿，并生成可直接发布的压缩包。

## 输出内容

执行 `python main.py` 后，所有文件都会写入 `output/`。

- `output/<语言>/*.xlsx`：对应语言的数据库工作簿。
- `output/DATABASE_<语言名称>_<版本号>.zip`：每种语言一个数据库包，包内包含该语言的 xlsx 文件和 `MHWS-in-json/` 源数据目录。
- `output/processed_data/`：额外转换器生成的语言无关处理结果。
- `output/PROCESSED_DATA_<版本号>.zip`：包含 `skill_pool.json`、`amulet_pool.json` 和 `graphic_preset.xlsx`。

压缩包统一使用 deflate 最大压缩率。
任一文本文件中语言索引为 `-1` 的语言会被跳过。

## 使用方式

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

入口不接收命令行参数。路径、语言、输出名和版本号等配置都在 [config.py](../config.py) 中修改。

## GitHub Release

[.github/workflows/release.yml](../.github/workflows/release.yml) 会在每次 push 时运行，也支持手动触发。版本号格式为 UTC 时间 `yyyyMMdd-HHmmss-<短 hash>`，并会把 `output/` 下生成的所有 zip 上传到 Release。

`.gitignore` 已忽略 Stage VoxelData 和 Enemy Constraint 这类超大 JSON。如果这些文件在添加忽略规则前已经进入提交历史，推送到 GitHub 前仍需要单独清理历史。

清理范围见 [Git Large File Cleanup](GIT_LARGE_FILE_CLEANUP.md)。
