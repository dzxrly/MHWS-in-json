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
  database/  processed_data/  shared/  pipeline/  release/  sdk/
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
skill_effects.zh-Hans.json
skill_pool.json
enemy_battle_logic/index.json
enemy_battle_logic/EM0001_00_0.json
enemy_battle_logic/EM0001_00_0.html
```

`enemy_battle_logic` 为 EnemyData 中全部 35 个大型怪物与训练对象 ID 各生成一份 JSON，训练对象单独标注。`logicStatus` 区分雌火龙已恢复的局部模型和其余 `not_recovered` 资源清单。清单保留 BTable 参数、去重后的动作参数定义、已绑定的通用判断及源文件哈希；参数槽位不能解释为执行顺序，也不表示完整行动树已经恢复。

默认分支的工作流同时将这些已校验文件发布到 GitHub Pages。首页支持按名称或 EM 编号查找、下载各怪物 JSON，以及打开已有局部控制流图。`.github/scripts/build_pages.py` 直接复制发布文件，不重新提取逻辑；Pages 发布来源需设置为 GitHub Actions。其他分支仍生成发布压缩包，但不部署公开站点。

`damage_calculator.zh-Hans.json` 保留怪物部位和伤口 GUID、普通与替代肉质、源耐久，以及带完整 requestSet 标识的玩家动作记录。每条动作记录包含原始动作值、是否使用玩家攻击／属性、动作属性倍率、斩味和会心适用标记、四项部位／伤口倍率，以及经精确关联并有中文文本的动作名称；另从怪物共通参数导出七档斩味的物理／属性倍率，并保留道具补正。技能数值只由 `skill_effects.zh-Hans.json` 导出。源数据引用了缺失的替代肉质时明确写为 `null`。完整导出会在发布前校验两个 JSON。若只需单独生成快照，可在项目根目录运行 `python -m src.processed_data.damage_calculator.exporter --output .agents/damage_calculator.zh-Hans.json` 和 `python -m src.processed_data.skill_effects.exporter --output .agents/skill_effects.zh-Hans.json`。

技能 JSON 保留源技能 ID、中文名称和描述、各等级原始数值、核验状态及源文件哈希。已核验的伤害效果另标明结算阶段、武器和属性范围，以及可选的生效档位。消费端以前提“勾选的技能已经触发、会心率恒为 100%”计算；此处不处理触发条件、持续时间、会心率加值、餐点技能或异常积蓄。未核实数值作用的技能仍可供追查，但不得当作零加成参与计算。

`MHWS-in-json_<版本>.zip` 包含共享的源 JSON，与各语言工作簿分开打包。

## 项目工具

项目维护工具位于 `sdk`。使用 `python -m sdk.il2cpp upload --dry-run` 准备 IL2CPP 构建数据，或用 `python -m sdk.il2cpp download` 获取数据；GitHub 操作沿用已有 `gh` 登录状态，临时文件存放在 `.agents/il2cpp`。

怪物行动逻辑的离线研究工具入口是 `python -m sdk.enemy_logic_exporter --help`。[维护说明](../sdk/enemy_logic_exporter/AGENTS.md) 记录了版本核对、原生方法提取、人工核实和固化流程。审核后的正式输入放在 `src/processed_data/enemy_battle_logic/models`，包含规则和当前上游模型两个 JSON，需随代码保留。最初的 4 子表模型仅作为 SDK 的内存中间结果，不再单独保存为正式模型。

`python main.py` 及 GitHub Actions 已接入行动图生成、校验和打包。结果位于 `processed_data/enemy_battle_logic`，包含模型目录索引、各怪物的 JSON 和 HTML，并纳入 `PROCESSED_DATA` 压缩包。单独运行 `python -m src.processed_data.enemy_battle_logic` 使用同一导出器。每个 HTML 将同一怪物全部已恢复子表放在一张大图中，内嵌 ELK 自动布局，支持拖动、缩放、节点证据查看和 SVG 导出。目前只有雌火龙的局部模型，包含 11 个子表、79 个节点，仍有未知分支，不代表全部怪物或完整战斗 AI。

正式生成只读取固化模型和资源 JSON，不读取 EXE，不依赖 Ghidra 或 SDK。CI 校验模型与规则的版本一致性以及资源结构；未提供 IL2CPP 元数据时记录为 `not_supplied`。仅修改原生代码的游戏更新不能靠这些检查自动发现，更新后仍需通过 SDK 重新核实并维护固化模型。

## 工作簿说明

`MissionData.xlsx` 以 `app.user_data.QuestData` 为主体。每个完成条件占一行，其他任务字段纵向合并。任务类型保留原值；缺少对应语言文本时回退英语，所有语言都没有怪物名称时保留 `EM` 编号。StreamQuest 文本取自配套数据。缺少 `QuestData` 的 `MsData` 任务编号排在末尾，填入能找到的文本。

`WeaponActionValues.xlsx` 需要 `_format` 为 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。重新生成时，使用同一游戏版本的输入运行 `motlist-to-json action-map`；可通过 `MHWS_ACTION_MAP_PATH` 指定其他文件。每条动作或资源映射各占一行；未映射的 requestSet 保留在表中，`MappingName` 留空。`MappingConfidence` 是证据类别，不是概率。
