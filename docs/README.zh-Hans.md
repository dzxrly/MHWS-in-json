<div align="center">

# MHWS-in-json

[English](../README.md) | 简体中文 | [繁體中文](README.zh-Hant.md)

</div>

MHWS 游戏数据导出工具，输出形式与 [eigeen/mhws-data-dump-scripts](https://github.com/eigeen/mhws-data-dump-scripts) 和 [dtlnor/MHWs-in-json](https://github.com/dtlnor/MHWs-in-json) 相近。

<div align="center">

<a href="https://github.com/dzxrly/PyREUser3">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-dark.svg">
    <img alt="Powered by PyREUser3" src="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-light.svg">
  </picture>
</a>

</div>

## 输出内容

执行 `python main.py` 后，所有文件都会写入 `output/`。

- `output/<语言>/*.xlsx`：对应语言的数据库工作簿，其中 `FullText.xlsx` 使用单个工作表记录全部消息 GUID 及其本地化文本，并按实际内容、已拒绝文本、空文本分组，各组内保留源文件读取顺序；已拒绝文本以 `[#Rejected#]` 开头，未标记的空文本保持为空。
- `output/DATABASE_<语言名称>_<版本号>.zip`：每种语言一个发布资源包，仅包含该语言的 xlsx 文件，不包含 `MHWS-in-json/`。
- `output/processed_data/`：额外转换器生成的语言无关处理结果。
- `output/PROCESSED_DATA_<版本号>.zip`：语言无关的发布资源包，包含 `skill_pool.json`、`amulet_pool.json`、`graphic_preset.xlsx`、`Bowgun_Custom.xlsx`、`HeavyBowgun.xlsx` 和 `LightBowgun.xlsx`。
- `output/MHWS-in-json_<版本号>.zip`：共享源数据库 JSON 发布资源包，包含 `MHWS-in-json/` 目录。

压缩包统一使用 deflate 最大压缩率。源数据库 JSON 没有多语言语义，因此只单独打包一次，不再重复放入每个语言包。
`PROCESSED_DATA` 中的弩枪工作簿固定只导出简体中文。
任一文本文件中语言索引为 `-1` 的语言会被跳过。
运行脚本时，终端会输出详细的加载、转换、保存和打包日志。

## 使用方式

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

入口不接收命令行参数。路径、语言、输出名和版本号等配置都在 [config.py](../config.py) 中修改。
