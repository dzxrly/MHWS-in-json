# 怪物行动逻辑提取与维护

本目录是离线研究 SDK，代码统一使用 Python。它读取游戏 EXE 和匹配的 IL2CPP JSON，提取原生方法证据，再用人工核实过的配方固化语义与控制流。公共分析代码位于 `shared/`，按原生证据、游戏资源、语义恢复、模型构建和离线流程分组；JSON 文件统一放在 `data/`。每个大型怪物（含独立变种，排除训练靶）在 `monster/<完整ID小写>.py` 有独立入口。SDK 与 `src` 之间只通过 JSON 文件交接，双方禁止导入或调用对方的代码。网页构建器位于 `src/processed_data/enemy_battle_logic`，只读取已解析的图 JSON，不能读取游戏资源、IL2CPP 或 EXE。

## 维护边界

- 不运行游戏、EXE、注入或 Hook。Ghidra 只将 EXE 当作数据读取。
- 调试代码、反编译结果、Ghidra 项目、截图及测试输出统一放在项目根目录 `.agents`。默认工作目录是 `.agents/enemy-logic-exporter`。
- 不复制 EXE 或完整 IL2CPP dump 到 Git；不提交 `.agents` 中的证据缓存。
- EM166 的历史图与原始分析只能作为对照，不能作为其他怪物图的节点、连接或判断依据。
- 原生地址、参数索引、字段偏移、静态权重地址、方法名后缀均与游戏版本相关。更新后不能仅替换版本号或 SHA-256 以绕过检查。
- 保留用户已有暂存改动；本目录的迁移或维护不自动授权提交、推送或发布。

## 文件与职责

`shared/native` 负责只读 PE、元数据及原生证据；`shared/resources` 负责资源发现、参数和动作身份；`shared/logic` 负责已核实的条件、命令与机器追踪；`shared/models` 负责图构建、JSON 读写和覆盖校验；`shared/workflow` 负责 CLI 与离线批次调度。各组只保留具体实现，不提供旧路径兼容包装。`shared/config.py` 集中定义项目根目录、数据路径和来源 profile，资源定位不依赖当前工作目录。

`data/evidence` 保存配方的 JSON 证据，`data/rules.v1.json` 保存已核实规则，`data/models` 保存待解析语义输入。`shared` 和 `monster` 只保存 Python 代码，研究运行生成的缓存继续放在项目根目录 `.agents`。

| 文件 | 职责 |
|---|---|
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
| `shared/logic/machine.py`、`shared/logic/common_conditions.py` | 按当前版本的真实指令追踪判断、动作让出、子表调用及准确恢复位置；公共条件只接受已核实的分类，缺少运行时输入保持未知 |
| `shared/logic/command_catalog.py`、`shared/logic/commands.py` | 保留全部命令实现，集中恢复窄范围字段比较、单项写入及参数注释；局部写入不能代表命令全部副作用 |
| `shared/logic/static_pools.py` | 从原始初始化指令提取常量；静态 key 与权重不能直接转换成出招概率 |
| `shared/logic/weights.py` | 校验整数权重、独立候选槽和调用目标，按已核实的取模与累积权重规则检查给定抽样值；不假设随机数生成器 |
| `shared/logic/expressions.py`、`shared/logic/values.py` | 集中构造、校验和求值条件表达式，读取标量及枚举；缺少运行时输入保持未知 |
| `shared/resources/action_names.py` | 绑定并校验准确的资源、动作 GUID、参数变体与说明名，保留 Shell 原名及来源 |
| `shared/models/catalog.py`、`shared/models/io.py`、`shared/models/validation.py` | 维护独立怪物范围、模型入口、大小限制与图结构校验 |
| `shared/logic/rules.py` | 固化通用条件及少数已核实的特殊条件 |
| `monster/em0001_00_0.py` | 雌火龙独立入口，保留局部与上游配方，模型输入位于 `data/models` |
| `monster/em0002_00_0.py` | 火龙独立原生配方，核对 Combat/CommonAttack 的方法、选择器及动作请求覆盖；整场入口和部分条件仍在核查 |
| `monster/em0166_00_0.py` | 独立入口与已核对的阶段应用分析；不能把其历史图用于其他怪物 |
| `__main__.py`、`shared/workflow/cli.py` | 离线 CLI 入口；`shared/config.py` 保存配方已核实的来源标识 |

`manifest`、`decompile`、`verify` 可用于新版本研究。原生配方当前支持经过来源核对的 **1.42.0.2**。34 个独立模块均可通过 `build_model` 提取自身实际 BTableList、导入闭包和原生方法，公共机器追踪器不提供预先编造的怪物行为。当前 34 份已解析图合计覆盖 7,763 个原生方法上下文、8,171 个子表、119,561 个节点和 4,554 个权重选择点；复用资源按其所在模型分别计数。仍保留 5,355 个未知流程节点、2,726 个含未知表达式的条件和 839 个选择器边界，无法确认等价的缓存上下文不继续展开。原先 46 表、408 节点的雌火龙图保留为固定回归样本。动作说明名绑定到资源、请求 GUID 与参数变体；实例 GUID 和基础 GUID 分别保留。Shell 原名及注释按资源与 UID 保存，未核实触发关系时不绑定到具体动作。全局 Combat 事件保持 partial，不能把导出成功描述为完整战斗 AI 已恢复。

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

现有研究缓存可通过 `--work-dir .agents/enemy-action-tree` 复用。确认生成结果、版本身份和差异后，将已解析的图 JSON 更新到 `src/processed_data/enemy_battle_logic/models`。该目录不保存待绑定模板或判断规则文件。预览结果位于 `$work/preview/enemy_battle_logic`。不要将伪 C、EXE 或 Ghidra 缓存作为正式构建依赖。

正式流水线只交付 `enemy_battle_logic/index.html` 和各怪物的 `<enemyId>.html`，语义模型与图数据内嵌在离线页面中。Pages 和压缩包均使用这同一份输出，不另外发布研究索引、伪 C 或重复 JSON。同一怪物只能有一个正式模型；重复版本、来源冲突、断开的连接或图数据不一致会阻止发布。CI 只读取已解析的图 JSON，不读取资源、IL2CPP、EXE，也不运行或安装 SDK。网页显示离线提取时记录的来源核对状态；CI 的 JSON 校验不能证明之后的游戏原生代码没有变化。

正式范围是 EnemyData 中基础编号小于 1000 的完整 ID，排除训练靶 `EM0165_00_0`，当前为 34 个。全部怪物统一使用语义行动图；不得用资源清单、原生方法索引或整张未知表替代。默认构建必须同时具备 34 个模型、经过核实的 Combat 入口，以及 SDK 方法/动作请求位置与模型的覆盖核查。发现记录与摘要、版本必须一致；未进入模型的方法及未找到引用的资源要逐项说明证据和原因。这些静态验收只验证审核材料的一致性，不代替人工语义审核或游戏内验证。

当前网页模型目录已有 34 份实际提取的图 JSON，但全部仍是研究图；默认正式构建因战斗总入口和语义审核未完成而拒绝发布。用显式 `--template` 或 `--preview-all` 可在 `.agents` 生成研究预览，预览不能通过正式发布检查。`freeze --all（从工作目录 reviewed 读取）` 只接收完整、经审核的语义输入，不会自动将方法清单转换成完整战斗逻辑。图保留 Combat 进入、更新、BTable 切换、中断和恢复的实际已核实部分，异步请求只连接到等待调度的目标，不当作同步调用。未知命令的真实 void 调用方连续流可保留，但其副作用仍标未知；未恢复的 Boolean 不能伪造为 0 或整个命令的 opaque 运行时布尔输入。

方法覆盖、原生字节位置覆盖和资源/类型/方法/命令/参数上下文覆盖分别记录。同址方法别名不能只靠地址 set 视为恢复完成；相同子表 GUID 出现在不同资源时保留独立图身份和 nativeTableGuid。非 Combat 的空声明资源不编造入口。当前元数据确认返回 Void、当前原生入口第一条指令为 ret 的空调度函数存入 resourceNonDispatchEntries，不为它补造子表入口；其他未恢复入口继续保留边界。逐候选跳过列表按各自参数槽绑定；新候选的 id 为实际池槽 slot:<nativeCandidateIndex>，nodeId 指向已核实的调用节点。多个槽可以汇入相同上下文的调用节点，各自保留 key、权重和筛选参数，不编造 PC 或合并权重。相同原生调用地址若参数、调用目标或实际保存位置不同，须保留独立语义节点，nativeSite 仍指向原指令；不能以同址为由覆盖恢复 PC 或复用其他路径的条件。旧 JSON 没有 nodeId 时，其 id 仍表示调用节点。真实动作 ID 与参数类名不同不代表绑定无效：核对唯一 GUID、所属参数槽及当前原生选择代码，保留两种类型及应用边界。缺少 ActionInfo 的已确认请求保留请求位置、原始身份和保存的恢复位置，不借用近似 GUID。

本版以既有 EM0166 研究页的详细程度为目标，不继续扩展 Life 历史缓存、HIGH 物理命中或通用栈存储模拟。尚未核实的辅助方法、恢复位置和运行时条件保持未知；深入探索代码只留存在 .agents，不作为网页构建或正式 SDK 的依赖。

原生研究索引只允许保存到 `.agents`。Git 中的正式模型只保留语义、资源绑定及最小原生证据，可以用 `evidenceCatalog` 复用共同证据，并通过带摘要的 `fragments` 拆分语义表。单个模型文件超过 10 MiB 提示审核，超过 25 MiB 拒绝读入；必须去重或分片，不能为缩小文件删除逻辑。旧的 34 个大型原生索引保存在 `.agents/enemy-logic-exporter/legacy-native-models`，不参与正式构建。

## 游戏更新后的维护顺序

1. 取得同版本的 EXE、IL2CPP dump 和资源导出，保存新 profile 与新证据，不覆盖旧证据。
2. 用通用 `manifest` 重新定位方法；核对大 JSON 格式是否仍符合索引器的假设。索引失败应修正索引器，不能读旧地址兜底。
3. 对通用条件、getter、随机算子、计时器更新及具体怪物子表分别比较。只迁移被当前字节、字段布局与资源绑定支持的结论。
4. 更新经过核实的配方和对应 profile；新怪物编写独立配方。部位、目标、阶段、中断和动作内部条件没有证据时仍输出未知，不补造完整树。
5. 运行下面的回归检查与正式 JSON 构建。检查边界值、缺失状态、资源结构变化、版本拒绝、跨表调用和返回位置。重建 HTML 后用真实浏览器检查全图、缩放、定位、离线使用及 SVG 导出。

```powershell
python -B -m tests
python -m src.processed_data.enemy_battle_logic
```

当前计时器：ACTIVATE 重置并启用，DEACTIVATE 保留值并停用，REACTIVATE 保留值并启用；更新到零后停用。时间增量单位未核实。角度特殊 Option、全局调度、实际动作中断仍有边界；不要将静态检查通过写成游戏内验证通过。

## 全图绘制约定

一个怪物的全部已恢复子表出现在同一张图中，以子表分组，共享子表只画一次。用固定版本的 elkjs 分层布局，先排列每个子表，再排列子表之间的调用关系；库与许可证嵌入单文件 HTML，不调用 CDN。跨表调用线从分组边框引出，标明实际调用节点和目标入口；精确节点 ID 仍保留在图数据中。普通实线为条件、调用与后续逻辑；虚线表示调用/动作保存的恢复位置。它是继续执行位置的说明，不是绕过被调用逻辑的执行边。不能将共享子表的所有结束节点连接到所有调用方，这会制造不存在的路径；实际返回由调用栈决定。
