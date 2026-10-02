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
EnemyActionLogic.html
HeavyBowgun.xlsx
LightBowgun.xlsx
amulet_pool.json
damage_calculator.zh-Hans.json
graphic_preset.xlsx
skill_effects.zh-Hans.json
skill_pool.json
```

`damage_calculator.zh-Hans.json` 保留怪物部位和伤口 GUID、普通与替代肉质、源耐久，以及带完整 requestSet 标识的玩家动作记录。每条动作记录包含原始动作值、是否使用玩家攻击／属性、动作属性倍率、斩味和会心适用标记、四项部位／伤口倍率，以及经精确关联并有中文文本的动作名称；另从怪物共通参数导出七档斩味的物理／属性倍率，并保留道具补正。技能数值只由 `skill_effects.zh-Hans.json` 导出。源数据引用了缺失的替代肉质时明确写为 `null`。完整导出会在发布前校验两个 JSON。若只需单独生成快照，可在项目根目录运行 `python -m src.processed_data.damage_calculator.exporter --output .agents/damage_calculator.zh-Hans.json` 和 `python -m src.processed_data.skill_effects.exporter --output .agents/skill_effects.zh-Hans.json`。

技能 JSON 保留源技能 ID、中文名称和描述、各等级原始数值、核验状态及源文件哈希。已核验的伤害效果另标明结算阶段、武器和属性范围，以及可选的生效档位。消费端以前提“勾选的技能已经触发、会心率恒为 100%”计算；此处不处理触发条件、持续时间、会心率加值、餐点技能或异常积蓄。未核实数值作用的技能仍可供追查，但不得当作零加成参与计算。

`MHWS-in-json_<版本>.zip` 包含共享的源 JSON，与各语言工作簿分开打包。

## 怪物行动逻辑流程图

`EnemyActionLogic.html` 是一个可离线打开的单文件。通过怪物和阶段选择器查看流程图，主图从玩家距离和怪物状态出发，显示具体动作名称、类型、参数版本及所属路径的后续。每个已发现的阶段只有一张连通图。原生图保留状态和距离分支；同一动作的不同分支参数、请求位置和返回上下文分别展示，不把候选列表当作固定连招。HTML 内嵌图形、数据和查看工具，支持缩放、搜索，以及点击节点追踪上游条件、动作内部过程和正常后续。原始编号与地址放在折叠详情中。

范围为 EnemyData 中 EM 基础编号小于 1000 的完整 ID；EM0165 标记为训练对象。动作类型从战斗行为表的 ActionID 引用解析，中文名称是类型名的释义。未发现阶段配置时显示“战斗阶段未解析”。仅凭参数 JSON 无法确定选招分支、执行顺序和每个阶段的适用动作；这些关系保留为未知。

阶段识别优先读取有效的 `_PhaseList`；少数专用结构由 `enemy_action_logic/phases.py` 中的固定 EM 配置兼容，并与实际阶段命令核对。当前分开显示巨戟龙 EM0078 的 3 个阶段、冻峰龙 EM0162 的 4 个任务阶段、白炽龙 EM0164 和游星欧米茄 EM0166 各 4 个阶段。海龙 EM0046 的游泳战斗有 3 个内部阶段，另保留常规战斗入口。愤怒状态、可反复切换的模式、音乐阶段和动作内部阶段不直接当作整体战斗阶段。EM164/166 枚举中未被有效阶段列表使用的 PHASE_5 不生成额外图。没有原生流程证据的怪物仍显示阶段动作归属未恢复，不能把分图理解为已经筛出了各阶段的全部动作。

```powershell
python -m src.processed_data.enemy_action_logic.exporter --output output/processed_data/EnemyActionLogic.html
python -m src.processed_data.enemy_action_logic.exporter --enemy EM0166_00_0 --output output/processed_data/EM0166ActionLogic.html --evidence path/to/evidence.json
```

`--enemy` 可重复指定。`--evidence` 可读取外部原生图 JSON 或保留原生图证据的既有导出 HTML；HTML 的 `nativeEvidence` 与展示图分开保存，可直接复用。只有合并候选而没有原生图的旧版 HTML 需要原始证据 JSON。完整流水线也生成这个 HTML，并将其纳入 `PROCESSED_DATA` 压缩包；环境变量 `MHWS_ENEMY_LOGIC_EVIDENCE` 可指定证据文件。导出本身不生成 PDF 或单独的 ZIP。

原生证据 JSON 使用 `{"schemaVersion": 1, "enemies": {"EM0166_00_0": {...}}}`。每个怪物包含 `sourceFiles`（相对 natives 路径到 SHA256 的映射，覆盖本次读取的资源）、`nativeSnapshot.exeSha256` 和 `graphs`。图含 `id/title/entry/nodes/edges`；节点为 `id/label/kind/evidence/detail`，边为 `from/to/label/evidence/back`。`kind` 为 `process/decision/action/unknown/end`，`evidence` 为 `resource/native/unresolved/context`。原生分支直接保留。动作模板可用 `detail.actionType/requestSites/continuation/executionFlow` 表达请求位置、续执行目标及动作内部流程；请求位置必须匹配源表参数、动作和分支 GUID。动作版本同时关联 ActionParam 中的循环计时、动画过滤器及完整参数。`decisionCases` 仅是辅助证据，不再按距离合并其中的状态或动作集合；其 `distanceBasis` 必须区分 `command` 命令距离与 `player` 玩家距离。布局可以随证据提供，只有布局签名与当前展示图一致时才复用。

导出检查源哈希、阶段一致性、图的连通和返回路径、布局范围，以及 HTML 内嵌数据和图形的一致性。这一版可复用已有 EM166 原生分析，还不能自动恢复所有怪物的完整运行时状态机，也没有进行游戏内验证。

## 工作簿说明

`MissionData.xlsx` 以 `app.user_data.QuestData` 为主体。每个完成条件占一行，其他任务字段纵向合并。任务类型保留原值；缺少对应语言文本时回退英语，所有语言都没有怪物名称时保留 `EM` 编号。StreamQuest 文本取自配套数据。缺少 `QuestData` 的 `MsData` 任务编号排在末尾，填入能找到的文本。

`WeaponActionValues.xlsx` 需要 `_format` 为 `mhws_static_action_request_set_map_v2` 的 `MHWS-in-json/ActionMap.json`。重新生成时，使用同一游戏版本的输入运行 `motlist-to-json action-map`；可通过 `MHWS_ACTION_MAP_PATH` 指定其他文件。每条动作或资源映射各占一行；未映射的 requestSet 保留在表中，`MappingName` 留空。`MappingConfidence` 是证据类别，不是概率。
