# 怪物行动逻辑提取与维护

本目录是离线研究 SDK，代码统一使用 Python。它读取游戏 EXE 和匹配的 IL2CPP JSON，提取原生方法证据，再用人工核实过的配方固化语义与控制流。公共分析代码位于 `shared/`，按原生证据、游戏资源、语义恢复、模型构建和离线流程分组；JSON 文件统一放在 `data/`。每个大型怪物（含独立变种，排除训练靶）在 `monster/<完整ID小写>.py` 有独立入口；名单本身是数据（`data/roster.v1.json`），由 `roster` 从 EnemyData 与 BTableList 生成。SDK 与 `src` 之间只通过 JSON 文件交接，双方禁止导入或调用对方的代码。网页构建器位于 `src/processed_data/enemy_battle_logic`，只读取已解析的图 JSON，不能读取游戏资源、IL2CPP 或 EXE。

## 维护边界

- 不运行游戏、EXE、注入或 Hook。Ghidra 只将 EXE 当作数据读取。
- 调试代码、反编译结果、Ghidra 项目、截图及测试输出统一放在项目根目录 `.agents`。默认工作目录是 `.agents/enemy-logic-exporter`。
- 不复制 EXE 或完整 IL2CPP dump 到 Git；不提交 `.agents` 中的证据缓存。
- EM166 的历史图与原始分析只能作为对照，不能作为其他怪物图的节点、连接或判断依据。
- 原生地址、参数索引、字段偏移、静态权重地址、方法名后缀均与游戏版本相关。更新后不能仅替换版本号或 SHA-256 以绕过检查。
- 保留用户已有暂存改动；本目录的迁移或维护不自动授权提交、推送或发布。

## 文件与职责

`shared/native` 负责只读 PE、元数据及原生证据；`shared/resources` 负责资源发现、参数和动作身份；`shared/logic` 负责已核实的条件、命令与机器追踪；`shared/models` 负责图构建、JSON 读写和覆盖校验；`shared/workflow` 负责 CLI 与离线批次调度。各组只保留具体实现，不提供旧路径兼容包装。`shared/config.py` 集中定义项目根目录、数据路径、来源 profile 以及全部版本相关常量（见“版本相关常量”），资源定位不依赖当前工作目录。

`data/evidence` 保存配方的 JSON 证据（含 `scheduler_slots.v1.json` 调度槽证据），`data/rules.v1.json` 保存已核实规则，`data/models` 保存待解析语义输入。`shared` 和 `monster` 只保存 Python 代码，研究运行生成的缓存继续放在项目根目录 `.agents`。

| 文件 | 职责 |
|---|---|
| `shared/config.py` | 集中保存路径、版本无关的符号定义（`SYMBOL_SPECS`）、结构偏移、IL2CPP 类型/方法/字段名、字段说明标签、规则整理表、调度槽标签与分组、发布时删除的研究字段；函数地址与核对常量从当前 `data/profiles/<版本>.json` 读取，不写字面地址。`shared` 中的模块只从这里取这些值 |
| `shared/native/symbols.py` | 把符号解析为当前构建的地址：IL2CPP 方法按类型、去掉数字后缀的方法名及参数类型定位；无名 helper 按屏蔽重定位后的开头字节特征定位，可再限定为具名锚点方法的直接被调方；全局与常量作为“人工核对”值随 profile 传递。为每个函数计算与重定位无关的规范化摘要 |
| `shared/workflow/version_update.py` | `resolve-symbols` 生成新版本 profile 并报告移动、代码变化与需复核项；`migrate-evidence` 按类型与方法名在新构建中重新定位全部证据行，只有规范化摘要不变的行才自动改写地址、范围、字节摘要与方法后缀 |
| `shared/models/roster.py` | 生成并比较大型怪物名单（含变种实际复用的 Combat 主人）；`new-monster` 为名单新增的怪物生成独立入口模块，不覆盖已有配方 |
| `shared/resources/variables.py` | 索引全部 BTableVariable 定义（计时器、浮点、布尔），模型以 `variableCatalog` 记录本怪物判断读取的变量及其初始值与来源 |
| `shared/models/uncertainty.py` | `uncertainty` 统计玩家战斗树中在全部玩家输入已知时仍无法判定的条件，按命令排序，作为后续规则工作的依据 |
| `shared/native/metadata.py` | 用 mmap 索引大体积 REFramework JSON，按需读取类型、继承字段和枚举 |
| `shared/native/pe.py` | 只读 PE64，依据异常目录及方法地址确定函数边界，保留同地址的方法别名并校验原生字节 |
| `shared/native/manifest.py` | 按怪物与方法类别从当前元数据重新生成提取清单 |
| `shared/native/evidence.py` | 去重原生字节身份、地址别名和类型字段，保留每个类型的方法及参数上下文 |
| `shared/workflow/batch.py` | 将 34 个怪物及共同调度器的方法定位保存为 `.agents` 研究索引 |
| `shared/native/decompile.py`、`shared/native/control_flow.py` | 通过官方 PyGhidra 接口提取伪 C、基本块、P-code、调用点和失败状态 |
| `shared/workflow/freeze.py` | 默认重新核对当前已维护的预览模型；`--all` 只在全部模型通过语义及覆盖检查后更新正式输入 |
| `shared/native/streaming.py` | 每份唯一原生代码保存一个压缩证据体；保留全部方法上下文，校验来源后支持续跑 |
| `shared/resources/inventory.py`、`shared/resources/requests.py` | 核对实际 BTableList、导入闭包、资源主人、原生请求位置、动作 GUID 与参数变体 |
| `shared/workflow/full_run.py`、`shared/workflow/extraction.py` | 通过独立怪物模块提取资源闭包、全部原生方法上下文和已维护语义图；只输出 JSON，不构建网页 |
| `shared/native/bindings.py`、`shared/workflow/semantic_recovery.py` | 从实际 x64 指令恢复调用参数、原生后继、比较、位置和状态写入；不使用丢失 SSA 身份的高层 P-code 偏移绑定参数 |
| `shared/logic/machine.py`、`shared/logic/common_conditions.py` | 按当前版本的真实指令追踪判断、动作让出、子表调用及准确恢复位置；同一调用指令按目标与参数槽保留独立节点，不同机器状态只有在隔离重放得到相同语义子图时才复用节点；公共条件只接受已核实的分类（任务等级、历战分类、目标为玩家/随从/怪物、目标玩家的异常状态与倒地/被击飞、状态信号、部位破坏、导航与遮挡等），缺少运行时输入保持未知 |
| `shared/logic/combat_position.py` | 恢复行为表中内联的 `Stack<POSITION>.Push` 返回位置保存；核对扩容 helper 字节，要求全部容量与引用标记路径得到相同的调用和继续位置，不按方法白名单限制 |
| `shared/logic/command_catalog.py`、`shared/logic/commands.py` | 保留全部命令实现，集中恢复窄范围字段比较、单项写入及参数注释；局部写入不能代表命令全部副作用。怪物专用命令若只是“自身 Extend 字段 与 参数/0 比较”（两种书写顺序、十六或十进制偏移均可），提取时由原生配方恢复为 `leafRules`，条件改写为该字段的比较 |
| `shared/logic/static_pools.py` | 从原始初始化指令提取常量；静态 key 与权重不能直接转换成出招概率 |
| `shared/logic/weights.py` | 校验整数权重、独立候选槽和调用目标，按已核实的取模与累积权重规则检查给定抽样值；不假设随机数生成器 |
| `shared/logic/expressions.py`、`shared/logic/values.py` | 集中构造、校验和求值条件表达式，读取标量及枚举；缺少运行时输入保持未知 |
| `shared/resources/action_names.py` | 绑定并校验准确的资源、动作 GUID、参数变体与说明名，保留 Shell 原名及来源 |
| `shared/models/player_view.py` | 将已核实条件编译成玩家树的 JSON 判断与分支说明，按 `schedulerSlots` 生成分组入口，把战斗中的有效性前提作为显式情境输入；保留动作身份、候选槽、调用和继续位置；只读取完整研究模型，不绘制 HTML |
| `shared/models/publish.py` | 从完整研究模型生成 Git 中的网页模型：删除研究字段、以 `sharedValues` 共享重复值并核对可完整还原（见“发布模型”） |
| `shared/models/catalog.py`、`shared/models/io.py`、`shared/models/validation.py` | 维护独立怪物范围、模型入口、大小限制与图结构校验；`io.py` 在读取时展开已发布模型的共享值 |
| `shared/logic/rules.py` | 固化通用条件及少数已核实的特殊条件 |
| `monster/em0001_00_0.py` | 雌火龙独立入口，保留局部与上游配方，模型输入位于 `data/models` |
| `monster/em0002_00_0.py` | 火龙独立原生配方，核对 Combat/CommonAttack 的方法、选择器及动作请求覆盖；整场入口和部分条件仍在核查 |
| `monster/em0166_00_0.py` | 独立入口与已核对的阶段应用分析；不能把其历史图用于其他怪物 |
| `shared/logic/scheduler_slots.py` | 扫描 `cEmAIState*`/`cEmAIInterrupt*`/控制器方法中对 `requestChangeBTable`、`requestJumpBTable`、`requestChangeBTableVerify` 的直接调用，只接受请求前、同方法内未跨调用的立即数槽参数；专用中断按 `EnemyDef..cctor` 的初始化字节映射 `UNIQUE_00/01`。结果写入 `data/evidence/scheduler_slots.v1.json`，模型以 `schedulerSlots` 记录每个槽由哪些状态请求 |
| `__main__.py`、`shared/workflow/cli.py` | 离线 CLI 入口 |

`manifest`、`decompile`、`verify` 可用于新版本研究。原生配方当前支持经过来源核对的 **1.42.0.2**（`config.ACTIVE_GAME_VERSION`）。34 个独立模块均可通过 `build_model` 提取自身实际 BTableList、导入闭包和原生方法，公共机器追踪器不提供预先编造的怪物行为。当前 34 份已解析图合计覆盖 7,763 个原生方法上下文、8,171 个子表、120,637 个节点和 4,988 个权重选择点；复用资源按其所在模型分别计数。仍保留 1,946 个未知流程节点、2,415 个含未知表达式的条件和 405 个选择器边界；玩家战斗树中在全部玩家输入已知时仍无法判定的条件为 1,183 个（`uncertainty` 统计），另有 316 个随机分支按概率展示；同一调用位置的不同机器状态只有在隔离重放得到相同语义子图时才复用节点，否则保留边界。原先 46 表、408 节点的雌火龙图保留为固定回归样本。动作说明名绑定到资源、请求 GUID 与参数变体；实例 GUID 和基础 GUID 分别保留。Shell 原名及注释按资源与 UID 保存，未核实触发关系时不绑定到具体动作。全局 Combat 事件保持 partial，不能把导出成功描述为完整战斗 AI 已恢复。

## 版本相关常量

`shared` 下的结构偏移和游戏内部类型/方法/字段名统一放在 `shared/config.py`；函数地址不再写成字面量，而是由 `SYMBOL_SPECS` 声明、按版本解析到 `data/profiles/<版本>.json`。`monster/<id>.py` 中只属于该怪物配方的地址与内部名放在文件头部的全局常量，游戏更新后需人工核对。只替换版本号或摘要不能证明常量仍然有效。

## 游戏更新与扩展

1. **地址变化**：`resolve-symbols --exe <新EXE> --metadata <新dump> --version <新版本>` 以当前 profile 为基线生成新 profile，报告 `moved`（地址移动）、`changed`（规范化代码变化，需复核语义）和 `review`（人工核对常量）。任何符号无法唯一定位都会失败，不会沿用旧地址。
2. **证据迁移**：`migrate-evidence --exe <新EXE> --metadata <新dump> --profile data/profiles/<新版本>.json` 先只报告；加 `--apply` 后，规范化摘要不变的证据行自动更新到新地址与方法后缀，并为新 profile 记录摘要；有任何待复核行的文件保持不动，命令以非零码退出。
3. 复核通过后把 `config.ACTIVE_GAME_VERSION` 改为新版本，重新生成 `scheduler-slots` 证据和 `roster`，再提取、对比与发布。
4. **新怪物/变种**：`roster --write` 更新名单并报告 `added`、`removed`、`ownerChanged` 与 `missingModules`；对每个新增 ID 运行 `new-monster --enemy <ID>` 生成入口，再提取。网页端名单由 `publish` 一并写入 `models/roster.json`，不需要改代码。
5. **已有怪物的新逻辑**：新子表、导入与动作请求随 BTableList 和原生索引自动纳入；形如“自身 Extend 字段比较”的新专用命令会被自动恢复为 `leafRules`；其他新命令先表现为未知条件或未知命令节点。用 `uncertainty --models <完整模型目录>` 找出影响最大的命令，再按“核实原生语义 → 写入规则/公共条件 → 在 `player_view.py` 编译为玩家输入”的顺序补充。新出现的行为表槽若不在 `SLOT_LABELS` 中，会以原始槽名归入“未分类行为表”组，提醒补充名称与分组。

## 环境与输入

在项目根目录运行模块。Python 3、Ghidra 12.0.4、Ghidra 支持的 JDK 和 PyGhidra 3.0.2、Capstone 5.0.6 已用于当前版本验证。JVM 是 Ghidra 自身的运行依赖，本项目不编写 Java 提取脚本。普通 JSON 构建无需安装这些研究依赖。

```powershell
python -m pip install -r sdk/enemy_logic_exporter/requirements.txt
$env:JAVA_HOME = '你的 JDK 安装目录'
$env:GHIDRA_INSTALL_DIR = '你的 Ghidra 安装目录'
$exe = '游戏安装目录/MonsterHunterWilds.exe'
$work = '.agents/enemy-logic-exporter'
```

输入包括与 EXE 同一游戏版本的 `src/data/il2cpp_dump.json` 和 `MHWS-in-json/natives` 下导出的资源 JSON。PFB 用于资源和组件引用；BTable 参数与工厂决定参数绑定；行动与 AI 状态资源提供外围约束；motlist 主要描述动作与运动资源。不要仅凭某类文件存在就推断它决定选招。

## 导出流程

1. **记录来源并重新定位。** 版本号由维护者确认，EXE/元数据摘要由命令计算。元数据中的方法地址只说明位置和签名，不等于分支语义。地址别名必须保留，泛型共享代码不能只凭第一个类型名归属。小函数没有异常目录时的边界属于暂定边界，需检查指令和调用关系。

```powershell
python -m sdk.enemy_logic_exporter --work-dir $work manifest --exe $exe --version 1.42.0.2 --enemy Em0001_00 --selection base --output "$work/base-manifest.json"
python -m sdk.enemy_logic_exporter --work-dir $work manifest --exe $exe --version 1.42.0.2 --enemy Em0001_00 --selection upstream --helper 0x140196660 --helper 0x143928820 --helper 0x145cbd510 --helper 0x145cc7880 --output "$work/upstream-manifest.json"
```

这些 helper 地址只适用于本配方的已核实版本。后续版本应从当前调用点重新定位 helper，再传入 `--helper`，不能原样照抄。其他怪物可指定如 `--enemy Em0022_00 --selection all`，其输出仍需人工核实，不能直接交给雌火龙配方。

   调度槽证据随版本更新重新生成，并检查 `boundaries` 中只剩转发参数的包装方法：

```powershell
python -m sdk.enemy_logic_exporter scheduler-slots --exe $exe
```

2. **选择性反编译。** 默认缓存项目以 EXE 摘要命名，且核对 Ghidra 内已导入程序的摘要；新版本应使用新缓存。不默认对整个游戏运行自动分析。失败行保留错误，退出码非零；不得把失败伪装成已导出逻辑。`--limit` 用于小范围诊断，不能将其结果当作完整清单。

```powershell
python -m sdk.enemy_logic_exporter --work-dir $work decompile --exe $exe --manifest "$work/base-manifest.json" --output "$work/decompiled.json"
python -m sdk.enemy_logic_exporter --work-dir $work decompile --exe $exe --manifest "$work/upstream-manifest.json" --output "$work/continued-python.json"
python -m sdk.enemy_logic_exporter verify --exe $exe --evidence "$work/continued-python.json"
```

每个方法证据保存类型、完整方法名、VA 起止、原生字节 SHA-256、参数与字段、地址别名、反编译状态和伪 C。schemaVersion=2 的研究索引将共同字节身份、地址别名和字段各保存一次，通过引用复用，但不能合并不同类型、参数布局或调用上下文。兼容旧行数组。基本块与 P-code 的状态为 `unreviewed_native_control_flow`，不能直接等同于动作图；固化前仍须逐个核实语义、来源 profile 与原生字节。

完整批次使用 `analyze`，扫描全部 34 个大型怪物（排除训练靶），按实际 BTableList 和导入关系确定资源范围。它提取各行为表的全部 `table_` 和 `updateTableInpl` 方法，以原生字节身份去重、压缩并保存到 `.agents`，不会向 Git 写入大型原生 JSON。缓存续跑仍会核对 EXE、元数据、方法范围、原生字节与压缩体摘要。

```powershell
python -m sdk.enemy_logic_exporter --work-dir $work analyze --exe $exe --version 1.42.0.2 --ghidra $env:GHIDRA_INSTALL_DIR --output "$work/full-run/result" --cache-dir "$work/full-run/native"
```

结果只包含离线 JSON、运行回执与相邻 ZIP：`inventory.json`、`monster-scopes.json`、`action-requests.json`、`run-result.json` 及 `semantic-graphs/`。大型原生缓存不打包。必须查看 `semanticRecovery`、`missingSemanticModels` 和 `releaseReady`，不能将完整批次退出成功写成全怪物语义恢复完成。历史研究绘图器保留在 `.agents/player-battle-trees/refactor/legacy-renderers`，不再由 SDK 调用。

3. **人工核实条件与状态机。** 阅读方法分支、状态编号和调用点，必要时对照反汇编。追踪 `_CommandArgArray` 字段偏移到资源参数索引、命令工厂类型、子表 GUID、动作 ID、参数变体、变量与计时器 GUID。参数数组顺序不能当作执行顺序。`table_<GUID>` 的编译状态与保存位置决定分支和继续执行的位置；动作请求与子表调用必须保存恢复位置。

可在已有全量原生索引、命令实现缓存、资源清单和动作请求证据上运行 `recover`，逐个生成 34 个怪物的条件参数、动作名称、跨表调用、位置记录、状态写入和实现详情。命令工厂按实际类型查询，既覆盖 `app.btable.Em…BTableCommand`，也覆盖 `app.Em…BTableCommand`。导入字段必须是实际导出表类型，不能用偏移相同的静态随机字段覆盖。调用参数的索引及资源类型匹配与命令语义核查分别记录；空工厂、参数未唯一恢复及字段类型冲突保留边界。

```powershell
python -m sdk.enemy_logic_exporter requests --exe $exe --index "$work/full-run/native/index.json" --inventory "$work/full-run/result/inventory.json" --output "$work/full-run/result/action-requests.json"
python -m sdk.enemy_logic_exporter recover --exe $exe --index "$work/full-run/native/index.json" --helpers "$work/per-monster/helpers/index.json" --inventory "$work/full-run/result/inventory.json" --requests "$work/full-run/result/action-requests.json" --output "$work/per-monster"
```

输出为 `commands/command-catalog.json`、按类型分片的命令实现 JSON，以及 `annotations/index.json` 和资源分片。每个怪物记录实际独立模块、资源闭包与原生方法上下文。命令与参数绑定、语义核查和整场战斗恢复分别记录。EM0166 阶段应用配方仍核对入口尾跳、Extend 方法、字节摘要与字段复制指令。结果中的 `semanticReviewComplete=false`、`releaseReady=false` 必须保留，不能将研究注释直接作为正式玩家图。

4. **核实随机与运行时限制。** 静态数组中的 key 含义若未知就保留未知。核实候选排除、空集合回退、整数权重、随机整数取模及候选目标的连接。当前疲劳判断先于怒判断；普通分支权重 25 的路径先调用吐息子表，返回后再检查远距条件，不能直接说成 25% 概率后空翻。非空跳过列表缺少运行时信息时必须返回未知。

5. **离线解析并核对玩家图。** SDK 的规则位于 `data/rules.v1.json`，未解析模型位于 `data/models`。`extract --enemy EM0001_00_0` 通过该怪物模块读取解包 JSON、IL2CPP 与 EXE，核对来源和最小原生证据，输出含条件、动作身份、名称、续招及恢复位置的已解析图 JSON。缺少已维护模型时明确拒绝，不能生成占位图。`freeze` 同样只输出解析后的图；`freeze --all` 仍要求 34 个模型全部通过语义与覆盖检查。

34 个怪物均可通过 `extract --index --helpers --inventory` 直接提取，无需在网页端绑定资源。索引、辅助实现和资源发现必须属于同一已核查版本；`--requests` 用独立动作请求清单检查覆盖。该方式仍保留未核实条件和 `semanticReviewComplete=false`，不能当作整场恢复完成。EM0160_50 的 BTableList 实际复用 Em0160_00 Combat，独立模块保留变种完整身份及其 Repel 资源；不能按编号前缀强求所有变种资源的主人。

```powershell
python -m sdk.enemy_logic_exporter extract --enemy EM0002_00_0 --exe $exe --index "$work/full-run/native/index.json" --helpers "$work/per-monster/helpers/index.json" --inventory "$work/full-run/result/inventory.json" --requests "$work/full-run/result/action-requests.json" --output "$work/extracted"
python -m src.processed_data.enemy_battle_logic --template "$work/extracted/em0002_00_0.v1.json" --output "$work/preview"

python -m sdk.enemy_logic_exporter extract-all --exe $exe --index "$work/full-run/native/index.json" --helpers "$work/per-monster/helpers/index.json" --inventory "$work/full-run/result/inventory.json" --requests "$work/full-run/result/action-requests.json" --output "$work/all-extracted"
python -m src.processed_data.enemy_battle_logic --models "$work/all-extracted" --preview-all --output "$work/all-preview"
```

```powershell
python -m sdk.enemy_logic_exporter --work-dir $work freeze --exe $exe
python -m src.processed_data.enemy_battle_logic --template "$work/frozen/em0001.upstream.v1.json" --output "$work/preview"
```

现有研究缓存可通过 `--work-dir .agents/enemy-action-tree` 复用。确认生成结果、版本身份和差异后，用 `publish` 把 `.agents` 中的完整研究模型写成网页模型并更新 `src/processed_data/enemy_battle_logic/models`（见下文“发布模型”）。该目录不保存待绑定模板或判断规则文件。预览结果位于 `$work/preview/enemy_battle_logic`。不要将伪 C、EXE 或 Ghidra 缓存作为正式构建依赖。

已提取的完整研究模型可独立更新玩家展示字段，无需重新提取原生代码。`player-view` 只接受 `.agents` 中的完整模型，拒绝已发布的精简模型：

```powershell
python -m sdk.enemy_logic_exporter player-view --models "$work/all-extracted" --output "$work/player-models"
python -m sdk.enemy_logic_exporter publish --models "$work/player-models"
python -m src.processed_data.enemy_battle_logic --output "$work/player-preview"
```

`playerView` 保存声明式条件、准确的分支与动作继续位置。情境（`scenario`）明确写出：单人或作为主机的玩家是当前目标，怪物处于战斗 AI 状态、没有待切换状态与覆盖普通姿态的专用状态，行为表动作请求未被屏蔽；这些都是可见的情境输入，不是隐含假设。计时器检查按 `variableCatalog` 的初始值作为“计时器到期”输入，布尔变量比较作为“行为表布尔变量”输入，`leafRules` 恢复的专用字段作为“专用状态 <字段>”输入（枚举字段显示枚举名），地形高低与遮挡判定作为单个布尔输入，随机余数分支标为“随机”类别并给出按均匀分布估算的比例（随机源分布未核实）。入口按 `schedulerSlots` 分组：普通战斗选招之外，每个行为表槽（受击、闪光、骑乘、状态提示等）都是独立入口并列出请求它的 AI 状态或中断；没有已证实上游的局部树单独归入“接入位置待核查”组，不伪造接入线。命令上下文、目标模块与目标玩家有效性在“目标是该玩家、正在战斗”的情境中作为显式情境输入，不再让每个条件都显示为未知。网页把整只怪物画成同一棵可交互树：怪物 → 分组 → 行为表 → 条件分支 → 动作，节点就地展开或收起，内部检查保留为小节点，相同判断状态只在首次出现处展开，其他位置显示“同前”并可跳转；顶部可搜索动作/条件、按距离角度和怒/疲劳等设定情境。SDK 与网页端继续只通过 JSON 交接。动作说明名来自已绑定动作类的解释，不代表官方招式名或游戏内验证。

正式流水线只交付 `enemy_battle_logic/index.html` 和各怪物的 `<enemyId>.html`，语义模型与图数据内嵌在离线页面中。Pages 和压缩包均使用这同一份输出，不另外发布研究索引、伪 C 或重复 JSON。同一怪物只能有一个正式模型；重复版本、来源冲突、断开的连接或图数据不一致会阻止发布。CI 只读取已解析的图 JSON，不读取资源、IL2CPP、EXE，也不运行或安装 SDK。网页显示离线提取时记录的来源核对状态；CI 的 JSON 校验不能证明之后的游戏原生代码没有变化。

正式范围是 EnemyData 中基础编号小于 1000 的完整 ID，排除训练靶 `EM0165_00_0`，当前为 34 个。全部怪物统一使用语义行动图；不得用资源清单或原生方法索引替代。默认构建校验 34 个模型、实际连接、方法/动作请求覆盖和 HTML 内容一致性；按用户已确认的发布范围保留 partial 图，不再以全部语义审核完成或完整 Combat 总入口作为网页发布前提。发现记录与摘要、版本必须一致。这些静态验收不代替人工语义审核或游戏内验证。

当前网页模型目录已有 34 份实际提取的 partial 图 JSON，均为 `publish` 生成的精简格式，未知分支和接入关系继续保留。显式 `--template` 或 `--preview-all` 可在 `.agents` 生成单个或部分怪物预览；默认全量构建仍要求全部 34 个身份及结构检查通过。`freeze --all（从工作目录 reviewed 读取）` 只接收完整、经审核的语义输入，不会自动将方法清单转换成完整战斗逻辑。图保留 Combat 进入、更新、BTable 切换、中断和恢复的实际已核实部分，异步请求只连接到等待调度的目标，不当作同步调用。未知命令的真实 void 调用方连续流可保留，但其副作用仍标未知；未恢复的 Boolean 不能伪造为 0 或整个命令的 opaque 运行时布尔输入。

方法覆盖、原生字节位置覆盖和资源/类型/方法/命令/参数上下文覆盖分别记录。同址方法别名不能只靠地址 set 视为恢复完成；相同子表 GUID 出现在不同资源时保留独立图身份和 nativeTableGuid。非 Combat 的空声明资源不编造入口。当前元数据确认返回 Void、当前原生入口第一条指令为 ret 的空调度函数存入 resourceNonDispatchEntries，不为它补造子表入口；其他未恢复入口继续保留边界。逐候选跳过列表按各自参数槽绑定；新候选的 id 为实际池槽 slot:<nativeCandidateIndex>，nodeId 指向已核实的调用节点。多个槽可以汇入相同上下文的调用节点，各自保留 key、权重和筛选参数，不编造 PC 或合并权重。相同原生调用地址若参数、调用目标或实际保存位置不同，须保留独立语义节点（节点名为 `<地址>-variant-N`），完整研究模型中的 nativeSite 仍指向原指令；不能以同址为由覆盖恢复 PC 或复用其他路径的条件。旧 JSON 没有 nodeId 时，其 id 仍表示调用节点。真实动作 ID 与参数类名不同不代表绑定无效：核对唯一 GUID、所属参数槽及当前原生选择代码，保留两种类型及应用边界。缺少 ActionInfo 的已确认请求保留请求位置、原始身份和保存的恢复位置，不借用近似 GUID。

本版以既有 EM0166 研究页的详细程度为目标，不继续扩展 Life 历史缓存、HIGH 物理命中或通用栈存储模拟。尚未核实的辅助方法、恢复位置和运行时条件保持未知；深入探索代码只留存在 .agents，不作为网页构建或正式 SDK 的依赖。

内联返回位置保存使用 `data/evidence/combat_position_push.v1.json` 中的版本、布局和扩容 helper 字节；其中的方法列表是最初人工核对的样本，不是白名单。证明只依赖匹配的指令前缀、固定 POSITION 写入、正常扩容返回及准确子表调用，不推断游戏中的栈容量、异常、回调或不同缓存上下文等价性。纯返回位置分支和仍不明确的调用继续保留边界；该配方不表示完整 Combat 或整场战斗已恢复。

### 发布模型

`publish`（`shared/models/publish.py`）从完整研究模型生成 Git 中的网页模型：删除 `config.py` 中 `RESEARCH_ONLY_NODE_FIELDS`、`RESEARCH_ONLY_MODEL_FIELDS` 所列的研究字段（原生位置、继续位置证明、请求位置、源指针及与节点重复的谓词字段等），再把出现两次以上、序列化后不少于 `SHARED_VALUE_MIN_BYTES` 字节的 JSON 值写入一次 `sharedValues`，原位置写成 `{"$": 索引}`，并以 `storage.format = "shared-values-v1"` 标记。发布时逐个核对展开结果与删减后的模型完全一致；网页与 SDK 的读取器在任何校验之前展开引用。新增网页或校验所需字段时，必须同步检查这两个删除列表。研究字段只保留在 `.agents` 的完整模型中。

原生研究索引只允许保存到 `.agents`。Git 中的正式模型只保留语义、资源绑定及最小原生证据，可以用 `evidenceCatalog` 复用共同证据，并通过带摘要的 `fragments` 拆分语义表。单个模型文件超过 10 MiB 提示审核，超过 25 MiB 拒绝读入（GitHub 单文件 50 MB 警告、100 MB 拒绝）；当前发布模型最大约 4.3 MB。缩小文件只能删除网页不读取的研究字段或共享重复值，不能删除条件、连接、动作身份等逻辑。旧的 34 个大型原生索引保存在 `.agents/enemy-logic-exporter/legacy-native-models`，不参与正式构建。

## 游戏更新后的维护顺序

1. 取得同版本的 EXE、IL2CPP dump 和资源导出，保存新 profile 与新证据，不覆盖旧证据。
2. 用通用 `manifest` 重新定位方法；核对大 JSON 格式是否仍符合索引器的假设。索引失败应修正索引器，不能读旧地址兜底。
3. 对通用条件、getter、随机算子、计时器更新及具体怪物子表分别比较。只迁移被当前字节、字段布局与资源绑定支持的结论。
4. 逐项核对 `shared/config.py` 与各 `monster/<id>.py` 文件头部的常量（地址、偏移、内部名、方法后缀、字节摘要），并重新生成 `scheduler-slots` 证据，确认 `boundaries` 只剩转发参数的包装方法。
5. 更新经过核实的配方和对应 profile；新怪物编写独立配方。部位、目标、阶段、中断和动作内部条件没有证据时仍输出未知，不补造完整树。
6. 在 `.agents` 中重新提取完整研究模型，与上一版逐项对比统计；纯重构必须得到逐字节一致的输出。确认后用 `publish` 更新网页模型。
7. 运行下面的回归检查与正式 JSON 构建。检查边界值、缺失状态、资源结构变化、版本拒绝、跨表调用和返回位置。重建 HTML 后用真实浏览器检查展开/收起、搜索定位、情境筛选、“同前”跳转、缩放、离线使用及 SVG 导出。

```powershell
python -m sdk.enemy_logic_exporter publish --models "$work/all-extracted"
python -B -m tests
python -m src.processed_data.enemy_battle_logic
```

当前计时器：ACTIVATE 重置并启用，DEACTIVATE 保留值并停用，REACTIVATE 保留值并启用；更新到零后停用。时间增量单位未核实。角度特殊 Option、全局调度、实际动作中断仍有边界；不要将静态检查通过写成游戏内验证通过。

## 玩家决策树绘制约定

每只怪物只有一棵树和一张画布，不拆分独立窗口：根节点为怪物，下一层按 `playerView.entries` 的 `group` 分组（与玩家战斗、与其他怪物、非战斗与生态、接入位置待核查的局部分支），再下一层是行为表入口，之后是条件、候选和动作。默认只展开普通战斗选招的前几层，其余就地展开。采用大纲式布局，父节点与第一分支对齐；SDK 标记为内部检查的条件画成小节点，不折叠进连线，以免未知检查使连线数量成倍增加。同一判断状态（节点、调用栈、动作后标记、情境输入与假设）只在首次出现处展开，其他位置画成虚线“同前”节点并可跳转。情境筛选只改变 `BattlePlayer` 引擎的输入，不修改 JSON。

## 技术图绘制约定

技术图由工具栏切换，用于核对原始子表。一个怪物的全部已恢复子表出现在同一张图中，以子表分组，共享子表只画一次。用固定版本的 elkjs 分层布局，先排列每个子表，再排列子表之间的调用关系；库与许可证嵌入单文件 HTML，不调用 CDN。跨表调用线从分组边框引出，标明实际调用节点和目标入口；精确节点 ID 仍保留在图数据中。普通实线为条件、调用与后续逻辑；虚线表示调用/动作保存的恢复位置。它是继续执行位置的说明，不是绕过被调用逻辑的执行边。不能将共享子表的所有结束节点连接到所有调用方，这会制造不存在的路径；实际返回由调用栈决定。
