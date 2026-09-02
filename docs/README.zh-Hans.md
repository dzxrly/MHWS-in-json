<div align="center">

# MHWS-in-json

[English](../README.md) | 简体中文 | [繁體中文](README.zh-Hant.md)

</div>

将 MHWS 游戏数据导出为 JSON 和 Excel，目录结构参考 [eigeen/mhws-data-dump-scripts](https://github.com/eigeen/mhws-data-dump-scripts) 和 [dtlnor/MHWs-in-json](https://github.com/dtlnor/MHWs-in-json)。

<div align="center">

<a href="https://github.com/dzxrly/PyREUser3">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-dark.svg">
    <img alt="Powered by PyREUser3" src="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-light.svg">
  </picture>
</a>

</div>

## 输出内容

执行 `python main.py` 后，以下文件会写入 `output/`：

- `output/<语言>/*.xlsx`：对应语言的数据库工作簿。
- `output/<语言>/FullText.xlsx`：消息 GUID 和本地化文本依次分为正常文本、已拒绝文本和空文本，每组内保留源文件顺序。已拒绝文本以 `[#Rejected#]` 开头，未标记的空文本保持空白。
- `output/<语言>/AmuletCollection.xlsx`：规范化的护石、技能和孔位池。名称按语言本地化，稀有度使用 `Rare.X`，武器与防具孔位分列，孔位等级使用 `Lv.X`。`SkillPool` 中每个技能点数池单独占一列，条目格式为“技能名 `Lv.X`”。
- `output/<语言>/WeaponActionValues.xlsx`：每种武器一个 sheet，另有 `Ammo` sheet。动作映射与资源映射会明确区分；两者都不存在的 requestSet 放在末尾，`MappingName` 保持空白并使用橙色底纹。
- `output/DATABASE_<语言名称>_<版本号>.zip`：每种语言一个发布资源包，仅包含该语言的 xlsx 文件，不包含 `MHWS-in-json/`。
- `output/processed_data/`：额外转换器生成的语言无关处理结果。
- `output/PROCESSED_DATA_<版本号>.zip`：语言无关的发布资源包，包含 `skill_pool.json`、`amulet_pool.json`、`graphic_preset.xlsx`、`Bowgun_Custom.xlsx`、`HeavyBowgun.xlsx` 和 `LightBowgun.xlsx`。
- `output/MHWS-in-json_<版本号>.zip`：共享源数据库 JSON 发布资源包，包含 `MHWS-in-json/` 目录。

压缩包使用 deflate 最高压缩级别。源 JSON 只打包一次，不重复放入每个语言包。
`PROCESSED_DATA` 中的弩枪工作簿固定只导出简体中文。
如果某种语言在任一消息文件中的文本索引为 `-1`，则跳过该语言。
加载、转换、保存和打包进度会输出到终端。

### 动作值映射

`WeaponActionValues.xlsx` 只读取 `MHWS-in-json/ActionMap.json`（`_format = mhws_static_action_request_set_map_v2`）。该文件需在本地使用 `motlist-to-json action-map` 生成，输入必须来自同一游戏版本：EXE dump、`il2cpp_dump.json`、motbank/motlist、PAK 文件列表和 MHWS JSON。不再接受 v1。测试其他路径的文件时，设置 `MHWS_ACTION_MAP_PATH`。CI 直接读取仓库中的数据包，不需要上述生成依赖。

只导出玩家攻击动作值 requestSet。嵌套值展开为叶子字段列；每条动作或资源映射边都会输出一行，同一 RS 因此可以重复。`MappingKind`、稳定身份、内部名、名称来源、资源角色、置信级别、条件和证据来源等列会明确说明映射性质。

`actionRelations` 与 `resourceRelations` 是两个独立数组。每条边都指向精确标识 `(scope, rcol, requestSetID, keyHash, sourceRequestSetOrdinal)`；目标过期或同一边冲突时，导出立即失败。缺少本地化 GUID 时自动使用内部名或资源名，不需要人工补映射。即使本地化显示文本相同，不同映射身份也不会合并。资源关系包含精确的 ShellList/PFB/RCOL 证据、自动推导的变体，以及显式标记的 RCOL 结构兜底。

每个 sheet 的第一行列出 RCOL 来源路径，第二行为表头。数据行不重复显示 `rcol` 路径。

## 使用方式

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

入口不接收命令行参数。路径、语言、输出名和版本号等配置都在 [config.py](../config.py) 中修改。
