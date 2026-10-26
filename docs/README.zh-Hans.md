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

## 网站

[mhws-info.eggtargaryen.com](https://mhws-info.eggtargaryen.com/)（只提供简体中文）：

- 怪物行动逻辑：每只怪物的出招决策树，可按距离、角度和状态筛选。共 34 只怪物，变种各有独立页面。
- 技能效果数值：每个技能在各等级下的效果数值与生效条件。

## 运行

```powershell
python -m pip install -r requirements.txt
python main.py
```

在 [config.py](../config.py) 中设置路径、语言和版本。入口不接收命令行参数，结果写入 `output/`；导出失败时保留上一次输出。测试命令为 `python -B -m tests`。

## 代码结构

```text
main.py, config.py           # 入口与设置
MHWS-in-json/                # 源 JSON
src/
  database/                  # 数据库工作簿
  processed_data/            # 后处理工作簿与 JSON；怪物行动模型
  shared/                    # 源数据、文本、RCOL、Excel 和日志工具
  pipeline/                  # 导出、校验、打包和发布
  site_data/                 # 网站数据；生成的 data/ 已提交
sdk/                         # 读取游戏文件的离线 SDK
  enemy_logic_exporter/      # 怪物行动逻辑
    shared/  data/  monster/ #   公共代码、规则与证据、每只怪物一个模块
  skill_effect_exporter/     # 技能效果数值
    shared/  skills/         #   原生代码模拟与流程、每个技能一个模块
web/                         # 网站（Vite + Vue）；src/sites/ 中每个信息站一个目录
tests/
```

怪物模型或技能效果变化后，运行 `python -m src.site_data` 重新生成网站数据并提交；数据过期时测试会失败。构建网站只需要 Node.js 22 或更新版本：先 `npm --prefix web ci`，再 `npm --prefix web run build`。

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
enemy_battle_logic.json
graphic_preset.xlsx
skill_details.json
skill_pool.json
```

`enemy_battle_logic.json` 和 `skill_details.json` 是[网站](#网站)背后的完整数据。

`MHWS-in-json_<版本>.zip` 包含源 JSON，与工作簿分开打包。

## 项目工具

仓库的 `sdk/` 目录是读取游戏文件的离线 SDK，`python -m sdk` 打开它的菜单。它包含以下功能：

- 怪物行动逻辑（`sdk.enemy_logic_exporter`）：从游戏文件中提取怪物行动逻辑，生成行动图网页使用的 JSON。`src/processed_data/enemy_battle_logic/models` 中的 34 份模型保留未知分支的标记。
- 技能效果（`sdk.skill_effect_exporter`）：找出原生代码中使用每个技能的函数并按等级求值，生成 `SkillDetails.xlsx` 使用的技能效果链路 JSON。

SDK 需要使用者提供从内存 dump 出的游戏 EXE（如 `MonsterHunterWilds_dump.exe`）和 REFramework `il2cpp_dump.json`，不记录游戏版本。环境搭建（`sdk/setup_env.ps1`）与用法见 [SDK 使用说明](../sdk/docs/README.zh-Hans.md)。只重新生成网站或表格时不需要 SDK。

## 数据说明

- `SkillDetails.xlsx`：每行是一个技能在某一等级的一个效果，列出数值、作用对象、计算方式、生效条件和单位。数值按“只装备该技能”求得；随情形变化的数值按情形分行列出。
- `MissionData.xlsx`：每个任务完成条件占一行。`SoloHealth` 列出可能的初始单人最大血量，计入任务难度、随机血量档位和 Legendary 倍率。
- `WeaponActionValues.xlsx` 需要 `MHWS-in-json/ActionMap.json`，可使用同版本输入运行 `motlist-to-json action-map` 重新生成，或通过 `MHWS_ACTION_MAP_PATH` 指定其他文件。未匹配到的动作 `MappingName` 留空。
