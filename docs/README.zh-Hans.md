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
python main.py
```

入口不接收命令行参数。路径、语言和版本在 [config.py](../config.py) 中设置。结果写入 `output/`。

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
graphic_preset.xlsx
skill_pool.json
```

`MHWS-in-json_<版本>.zip` 包含共享的源 JSON，与各语言工作簿分开打包。

## 工作簿说明

`MissionData.xlsx` 以 `app.user_data.QuestData` 为主体。每个完成条件占一行，其他任务字段纵向合并。任务类型保留原值；缺少对应语言文本时回退英语，所有语言都没有怪物名称时保留 `EM` 编号。StreamQuest 文本取自配套数据。缺少 `QuestData` 的 `MsData` 任务编号排在末尾，填入能找到的文本。

`WeaponActionValues.xlsx` 需要 `_format` 为 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。重新生成时，使用同一游戏版本的输入运行 `motlist-to-json action-map`；可通过 `MHWS_ACTION_MAP_PATH` 指定其他文件。每条动作或资源映射各占一行；未映射的 requestSet 保留在表中，`MappingName` 留空。`MappingConfidence` 是证据类别，不是概率。
