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

- `output/<语言>/*.xlsx`：对应语言的数据库工作簿。`FullText.xlsx` 使用单个工作表记录全部消息 GUID 及其本地化文本，并按实际内容、已拒绝文本、空文本分组，各组内保留源文件读取顺序；已拒绝文本以 `[#Rejected#]` 开头，未标记的空文本保持为空。`AmuletCollection.xlsx` 包含规范化的护石、技能和孔位池，名称按语言本地化，稀有度显示为 `Rare.X`，武器与防具孔位分列并使用 `Lv.X` 格式；其中 `SkillPool` 按技能点数横向分池，每个池独占一列，条目显示为“技能名 `Lv.X`”。`WeaponActionValues.xlsx` 为每种武器及弹药分别建立 sheet，并将无法可靠映射的 RS 放在末尾的橙色 `[未映射]` 区块。
- `output/DATABASE_<语言名称>_<版本号>.zip`：每种语言一个发布资源包，仅包含该语言的 xlsx 文件，不包含 `MHWS-in-json/`。
- `output/processed_data/`：额外转换器生成的语言无关处理结果。
- `output/PROCESSED_DATA_<版本号>.zip`：语言无关的发布资源包，包含 `skill_pool.json`、`amulet_pool.json`、`graphic_preset.xlsx`、`Bowgun_Custom.xlsx`、`HeavyBowgun.xlsx` 和 `LightBowgun.xlsx`。
- `output/MHWS-in-json_<版本号>.zip`：共享源数据库 JSON 发布资源包，包含 `MHWS-in-json/` 目录。

压缩包统一使用 deflate 最大压缩率。源数据库 JSON 没有多语言语义，因此只单独打包一次，不再重复放入每个语言包。
`PROCESSED_DATA` 中的弩枪工作簿固定只导出简体中文。
任一文本文件中语言索引为 `-1` 的语言会被跳过。
运行脚本时，终端会输出详细的加载、转换、保存和打包日志。

### 动作值映射

动作映射只消费可移植的静态数据包 `MHWS-in-json/ActionMap.json`（`_format = mhws_static_action_request_set_map_v1`）。该文件应在本地使用 `motlist-to-json action-map`，结合对应游戏版本的 EXE dump、`il2cpp_dump.json`、motbank/motlist、PAK 文件列表及 MHWS JSON 生成，因此 GitHub Action 不需要上传这些超大依赖。临时测试其他位置的数据包时，可设置 `MHWS_ACTION_MAP_PATH`。

每条关系必须精确命中当前 RCOL 中的五元身份 `(scope, rcol, requestSetID, keyHash, sourceRequestSetOrdinal)`；过期或互相冲突的数据包会直接中止导出。没有真实消息 GUID 的关系不会被当作已命名动作，而会留在末尾 `[未映射]` 区块。真实多对多关系会保留；同一最终动作名内完全相同的 RS 会去重，相同的本地化动作名会合并。

每个动作值 sheet 的第一行汇总 RCOL 来源地址，第二行为字段表头；数据区不再重复显示 `rcol` 地址列。

## 使用方式

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

入口不接收命令行参数。路径、语言、输出名和版本号等配置都在 [config.py](../config.py) 中修改。
