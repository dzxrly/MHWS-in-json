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

在 [config.py](../config.py) 中设置路径、语言和版本。入口不接收命令行参数，结果写入 `output/`；导出失败时保留上一次输出。测试命令为 `python -B -m tests`。

## 代码结构

```text
src/
  database/        # 数据库工作簿
  processed_data/  # 后处理工作簿、JSON 数据集和行动图网页
  shared/          # 源数据、文本、RCOL、Excel 和日志工具
  pipeline/        # 导出、校验、打包和发布
sdk/
  il2cpp/          # IL2CPP 上传与下载工具
  enemy_logic_exporter/
    shared/        # Python：native、resources、logic、models、workflow
    data/          # JSON：evidence/、models/、rules.v1.json
    monster/       # 每个怪物和变种的独立入口
tests/
```

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

`PROCESSED_DATA_<版本>.zip` 包含后处理数据，仅提供简体中文版：

```text
Bowgun_Custom.xlsx
EnemyActionNames.xlsx
HeavyBowgun.xlsx
LightBowgun.xlsx
SkillDetails.xlsx
amulet_pool.json
graphic_preset.xlsx
skill_pool.json
enemy_battle_logic/index.html
enemy_battle_logic/EM0001_00_0.html
...
```

行动图包含一个索引和 34 个怪物页面。变种各有独立页面，不包含训练靶。在线行动图网站：[mhws-monsters-ai.eggtargaryen.com](https://mhws-monsters-ai.eggtargaryen.com/)。

`MHWS-in-json_<版本>.zip` 包含源 JSON，与工作簿分开打包。

## 项目工具

仓库的 `sdk/` 目录是读取游戏文件的离线 SDK，`python -m sdk` 打开它的菜单。它包含以下功能：

- 怪物行动逻辑（`sdk.enemy_logic_exporter`）：从游戏文件中提取怪物行动逻辑，生成行动图网页使用的 JSON。`src/processed_data/enemy_battle_logic/models` 中的 34 份模型保留未知分支的标记。
- 技能效果（`sdk.skill_effect_exporter`）：找出原生代码中使用每个技能的函数并按等级求值，生成 `SkillDetails.xlsx` 使用的技能效果链路 JSON。

SDK 需要使用者提供从内存 dump 出的游戏 EXE（如 `MonsterHunterWilds_dump.exe`）和 REFramework `il2cpp_dump.json`，不记录游戏版本。环境搭建（`sdk/setup_env.ps1`）与用法见 [SDK 使用说明](../sdk/docs/README.zh-Hans.md)。只重新生成网页或表格时不需要 SDK：

```powershell
python -m src.processed_data.enemy_battle_logic --preview-all --output .tmp/battle-preview
```

然后打开 `.tmp/battle-preview/enemy_battle_logic/index.html`，页面可离线使用。

`SkillDetails.xlsx` 中的技能效果数值也可以生成为单个离线网页（简体中文），数据来自同一份技能效果链路 JSON：

```powershell
python -m src.processed_data.skill_details.web --output .tmp/skill-web
```

打开 `.tmp/skill-web/skill_details/index.html`。技能按类别列出，可按名称、效果和武器搜索；每个效果一张小表，列是技能等级，行是适用的武器、弹种、动作或情形，旁边给出数值含义（作用于、计算、条件、单位），代码依据可展开查看。

## 数据说明

- `SkillDetails.xlsx` 给出每个技能的效果数值。“技能效果”页每行是一个技能在某一等级（`Lv.1`、`Lv.2`……）的一个效果，列出游戏内的技能说明与等级说明、效果数值，以及适用的武器、弹种或动作（写作“【武器】弹种”）。只列出从游戏参数读取到的数值，按“只装备该技能”的情境求得。数值随情形（如连续命中次数）不同时分行列出，情形写在“条件”列开头；只在其他效果（饭技、狩猎笛旋律、武器自身状态、其他技能的数据）生效时才出现的数值不列出；随机判定写作发动概率（如 80%）。只有代码中找不到区分条件时才保留“a / b”。“作用于”“计算”“条件”“单位”列（数值作用于什么、怎样计算、何时生效、单位）来自 SDK 中每个技能的模块 `sdk/skill_effect_exporter/skills/hunterskill_<编号>.py` 里人工整理的数值含义，由 SDK 写进链路 JSON，依据代码中每个数值的用途写出；`python -m src.processed_data.skill_details --meanings-report <文件.md>` 列出每个效果的含义及其用途证据。“技能”页合并 SkillCommonData 与 SkillData。名称提供日文与简体中文，说明和效果名称只提供简体中文。
- `MissionData.xlsx` 中每个任务完成条件占一行，其余任务字段纵向合并。缺少对应语言文本时回退英语，无名称的怪物保留 `EM` 编号。`SoloHealth` 列出可能的初始单人最大血量，计入任务难度、随机血量档位和`Legendary` 倍率；无法确定目标时留空。
- `WeaponActionValues.xlsx` 需要格式为 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。使用同版本输入运行 `motlist-to-json action-map` 可重新生成，也可通过 `MHWS_ACTION_MAP_PATH` 指定其他文件。每条映射各占一行，未映射的 requestSet 保留，`MappingName` 留空。`MappingConfidence` 表示证据类别。日语以外的语言版本会在 `MappingName` 前增加日语名称列 `MappingNameJa`。
