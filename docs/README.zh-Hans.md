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

当前完整导出会在怪物行动图审核检查处停止。研究图可用下方的预览命令查看。

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

临时文件和研究缓存放在 `.agents/`。

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
amulet_pool.json
damage_calculator.zh-Hans.json
graphic_preset.xlsx
skill_effects.zh-Hans.json
skill_pool.json
enemy_battle_logic/index.html
enemy_battle_logic/EM0001_00_0.html
...
```

行动图包含一个索引和 34 个怪物页面。变种各有独立页面，不包含训练靶。通过审核的页面也会由默认分支发布到 GitHub Pages。

`MHWS-in-json_<版本>.zip` 包含源 JSON，与工作簿分开打包。

## 项目工具

使用 `python -m sdk.il2cpp upload --dry-run` 准备 IL2CPP 上传，或用 `python -m sdk.il2cpp download` 获取构建数据。两者沿用已有的 `gh` 登录状态。

怪物 SDK 读取游戏资源、同版本 EXE 和 IL2CPP 元数据，生成行动图 JSON；网页构建器只读取这些 JSON。提取和维护步骤见 [SDK 说明](../sdk/enemy_logic_exporter/AGENTS.md)。

`src/processed_data/enemy_battle_logic/models` 中的 34 份模型对应游戏 **1.42.0.2**。模型仍有未知分支，语义审核尚未完成，目前仅供研究预览。

```powershell
python -m sdk.enemy_logic_exporter --help
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
```

打开 `.agents/battle-preview/enemy_battle_logic/index.html` 浏览行动图。页面可离线使用，支持缩放、节点查找和 SVG 导出。预览单个模型时，将 `--preview-all` 替换为 `--template <graph.json>`。

## 数据说明

- `damage_calculator.zh-Hans.json` 包含怪物肉质、部位与伤口、玩家动作记录、斩味倍率和道具补正。缺失的替代肉质保留为 `null`。
- `skill_effects.zh-Hans.json` 包含技能等级和已核实的伤害效果，标明结算阶段、武器与属性范围以及生效档位。使用时假定勾选技能已生效，并选择当前命中是否会心；数据不处理触发过程、持续时间、会心率加值、餐点技能和异常积蓄，未核实效果不参与计算。
- `MissionData.xlsx` 中每个任务完成条件占一行，其余任务字段纵向合并。缺少对应语言文本时回退英语，无名称的怪物保留 `EM` 编号。`SoloHealth` 列出可能的初始单人最大血量，计入任务难度、随机血量档位和`Legendary` 倍率；无法确定目标时留空。
- `WeaponActionValues.xlsx` 需要格式为 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。使用同版本输入运行 `motlist-to-json action-map` 可重新生成，也可通过 `MHWS_ACTION_MAP_PATH` 指定其他文件。每条映射各占一行，未映射的 requestSet 保留，`MappingName` 留空。`MappingConfidence` 表示证据类别。
