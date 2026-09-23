<div align="center">

# MHWS-in-json

[English](../README.md) | 简体中文 | [繁體中文](README.zh-Hant.md)

</div>

将仓库中的 MHWS JSON 数据转换为 Excel 工作簿和发布压缩包。JSON 目录结构参考 [eigeen/mhws-data-dump-scripts](https://github.com/eigeen/mhws-data-dump-scripts) 和 [dtlnor/MHWs-in-json](https://github.com/dtlnor/MHWs-in-json)。

<div align="center">

<a href="https://github.com/dzxrly/PyREUser3">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-dark.svg">
    <img alt="Powered by PyREUser3" src="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-light.svg">
  </picture>
</a>

</div>

## 运行

```powershell
python -m pip install -r requirements.txt
python -B -m tests
python main.py
```

入口不接收命令行参数。路径、语言和版本在 [config.py](../config.py) 中设置。输出路径须位于项目内，默认写入 `output/`。导出先在 `.agents/export-runs/` 中生成完整结果，检查工作簿和压缩包内容后再统一发布；生成失败时保留上一次输出。`output/manifest.json` 记录文件哈希、语言编号、输入表路径和各阶段耗时。

## 代码结构

```text
src/
  database/        # DATABASE 工作簿，每个功能独立子目录
  processed_data/  # 弩枪、怪物动作、伤害计算 JSON、画质预设、护石 JSON 池
  shared/          # 源数据缓存、文本引用、RCOL 解析、Excel 工具
  pipeline/        # 导出协调、打包、校验、发布
tests/
  database/  processed_data/  shared/  pipeline/  release/
```

公共源表在一次导出中只读取和标准化一次。数据库预处理保留明确的文本 GUID 引用，包括技能与材料组合文本，再按语言填入翻译；结构 GUID 保留为标识符。数据库和任务文本各自保留原有的清理与回退规则。动作值和任务工作簿复用已注册样式，全文本工作簿采用流式写出。

使用 `python -B -m tests` 运行回归测试，CI 在导出前执行同一套测试。测试临时文件位于 `.agents/`；`.github/scripts/` 中的发布说明脚本保持独立运行。

## 发布压缩包

`DATABASE_<语言>_<版本>.zip` 每种语言一份，包含该语言的数据库工作簿：

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

`PROCESSED_DATA_<版本>.zip` 包含经过后处理的非数据库数据。仅发布简体中文版，不提供其他语言版本：

```text
Bowgun_Custom.xlsx
EnemyActionNames.xlsx
HeavyBowgun.xlsx
LightBowgun.xlsx
amulet_pool.json
damage_calculator.zh-Hans.json
graphic_preset.xlsx
skill_pool.json
```

`damage_calculator.zh-Hans.json` 保留怪物部位和伤口 GUID、普通与替代肉质、源耐久，以及带完整 requestSet 标识的玩家动作记录。每条动作记录包含原始动作值、四项部位／伤口倍率，以及经精确关联并有中文文本的动作名称；另外导出已核对的攻击／属性技能等级与道具补正。源数据引用了缺失的替代肉质时明确写为 `null`。完整导出会在发布前校验该 JSON。若只需单独生成快照，可在项目根目录运行 `python -m src.processed_data.damage_calculator.exporter --output .agents/damage_calculator.zh-Hans.json`。

`MHWS-in-json_<版本>.zip` 包含共享的源 JSON，与各语言工作簿分开打包。

## 工作簿说明

`MissionData.xlsx` 以 `app.user_data.QuestData` 为主体。每个完成条件占一行，其他任务字段纵向合并。任务类型保留原值；缺少对应语言文本时回退英语，所有语言都没有怪物名称时保留 `EM` 编号。StreamQuest 文本取自配套数据。缺少 `QuestData` 的 `MsData` 任务编号排在末尾，填入能找到的文本。

`WeaponActionValues.xlsx` 需要 `_format` 为 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。重新生成时，使用同一游戏版本的输入运行 `motlist-to-json action-map`；可通过 `MHWS_ACTION_MAP_PATH` 指定其他文件。每条动作或资源映射各占一行；未映射的 requestSet 保留在表中，`MappingName` 留空。`MappingConfidence` 是证据类别，不是概率。
