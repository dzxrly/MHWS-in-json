# 怪物行动逻辑提取与维护

本目录是离线研究 SDK，代码统一使用 Python。它读取游戏 EXE 和匹配的 IL2CPP JSON，提取原生方法证据，再用人工核实过的配方固化语义与控制流。正式构建器位于 `src/processed_data/enemy_battle_logic`，只读取规则及资源 JSON，不能导入本 SDK，也不能要求玩家提供 EXE。

## 维护边界

- 不运行游戏、EXE、注入或 Hook。Ghidra 只将 EXE 当作数据读取。
- 调试代码、反编译结果、Ghidra 项目、截图及测试输出统一放在项目根目录 `.agents`。默认工作目录是 `.agents/enemy-logic-exporter`。
- 不复制 EXE 或完整 IL2CPP dump 到 Git；不提交 `.agents` 中的证据缓存。
- EM166 的历史图与原始分析只能作为对照，不能作为其他怪物图的节点、连接或判断依据。
- 原生地址、参数索引、字段偏移、静态权重地址、方法名后缀均与游戏版本相关。更新后不能仅替换版本号或 SHA-256 以绕过检查。
- 保留用户已有暂存改动；本目录的迁移或维护不自动授权提交、推送或发布。

## 文件与职责

| 文件 | 职责 |
|---|---|
| `metadata.py` | 用 mmap 索引大体积 REFramework JSON，按需读取类型、继承字段和枚举 |
| `native.py` | 只读 PE64，依据异常目录及方法地址确定函数边界，保留同地址的方法别名并校验原生字节 |
| `manifest.py` | 按怪物与方法类别从当前元数据重新生成提取清单 |
| `evidence.py` | 去重原生字节身份、地址别名和类型字段，保留每个类型的方法及参数上下文 |
| `batch.py` | 将 34 个怪物及共同调度器的方法定位保存为 `.agents` 研究索引 |
| `decompile.py`、`control_flow.py` | 通过官方 PyGhidra 接口提取伪 C、基本块、P-code、调用点和失败状态 |
| `freeze.py` | 全量核对经审核语义模型、方法与动作请求覆盖；全部通过后才更新固化输入 |
| `weights.py` | 解析已核实版本的静态初始化代码；97 个数组、320 对值只是常量覆盖，不代表 97 个选招点已恢复 |
| `recipes/rules.py` | 固化通用条件及少数已核实的特殊条件 |
| `recipes/em0001_local.py` | 在内存中构建雌火龙基础 4 子表，供上游配方合并，不输出正式基线文件 |
| `recipes/em0001_upstream.py` | 固化一个 Combat 选招点及其局部调用链，并补充状态和计时器语义 |
| `__main__.py` | CLI 及版本校验入口；`SUPPORTED_PROFILE` 是配方已核实的来源标识 |

`manifest`、`decompile`、`verify` 可用于新版本研究。`freeze` 当前仅支持已核实的 **1.42.0.2** 配方；不是全怪物自动反编译器。当前模型有 11 个子表、79 个节点、3 个权重选择点；8 个局部流程已恢复，另有 4 个未知节点。全局战斗入口、若干候选和部位判断仍未恢复，不能把页面命名或描述为完整战斗 AI。

## 环境与输入

在项目根目录运行模块。Python 3、Ghidra 12.0.4、Ghidra 支持的 JDK 和 PyGhidra 3.0.2 已用于当前版本验证。JVM 是 Ghidra 自身的运行依赖，本项目不编写 Java 提取脚本。普通 JSON 构建无需安装这些研究依赖。

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

3. **人工核实条件与状态机。** 阅读方法分支、状态编号和调用点，必要时对照反汇编。追踪 `_CommandArgArray` 字段偏移到资源参数索引、命令工厂类型、子表 GUID、动作 ID、参数变体、变量与计时器 GUID。参数数组顺序不能当作执行顺序。`table_<GUID>` 的编译状态与保存位置决定分支和继续执行的位置；动作请求与子表调用必须保存恢复位置。

4. **核实随机与运行时限制。** 静态数组中的 key 含义若未知就保留未知。核实候选排除、空集合回退、整数权重、随机整数取模及候选目标的连接。当前疲劳判断先于怒判断；普通分支权重 25 的路径先调用吐息子表，返回后再检查远距条件，不能直接说成 25% 概率后空翻。非空跳过列表缺少运行时信息时必须返回未知。

5. **生成待审核的固化结果。** `freeze` 先校验已核实版本的 EXE/元数据摘要及两组证据，再固化规则、在内存中构建局部表并合并为上游模型。默认只将 `rules.v1.json` 和 `em0001.upstream.v1.json` 输出到工作目录 `frozen`，不会覆盖正式模板。配方是人工核实结论的编码，不能自动适配更新。

```powershell
python -m sdk.enemy_logic_exporter --work-dir $work freeze --exe $exe
python -m src.processed_data.enemy_battle_logic --template "$work/frozen/em0001.upstream.v1.json" --rules "$work/frozen/rules.v1.json" --output "$work/preview"
```

现有研究缓存可通过 `--work-dir .agents/enemy-action-tree` 复用。确认生成结果、版本身份和差异后，才将两个固化 JSON 更新到 `src/processed_data/enemy_battle_logic/models`。预览结果位于 `$work/preview/enemy_battle_logic`。不要将伪 C、EXE 或 Ghidra 缓存作为正式构建依赖。

正式流水线只交付 `enemy_battle_logic/index.html` 和各怪物的 `<enemyId>.html`，语义模型与图数据内嵌在离线页面中。Pages 和压缩包均使用这同一份输出，不另外发布研究索引、伪 C 或重复 JSON。同一怪物只能有一个正式模型；重复版本、来源冲突、断开的连接或图数据不一致会阻止发布。CI 无需 EXE 或 Ghidra；未提供 IL2CPP 时标明 `not_supplied`，资源结构检查不能证明原生代码没有变化。

正式范围是 EnemyData 中基础编号小于 1000 的完整 ID，排除训练靶 `EM0165_00_0`，当前为 34 个。全部怪物统一使用语义行动图；不得用资源清单、原生方法索引或整张未知表替代。默认构建必须同时具备 34 个模型、经过核实的 Combat 入口，以及 SDK 方法/动作请求位置与模型的覆盖核查。发现记录与摘要、版本必须一致；未进入模型的方法及未找到引用的资源要逐项说明证据和原因。这些静态验收只验证审核材料的一致性，不代替人工语义审核或游戏内验证。

当前只有雌火龙局部模型，默认正式构建会明确拒绝缺少的 33 个模型。用显式 `--template` 可在 `.agents` 生成研究预览，预览不能通过正式发布检查。`freeze --all（从工作目录 reviewed 读取）` 只接收完整、经审核的语义输入，不会自动将方法清单转换成完整战斗逻辑。实际行动图从 Combat 进入、更新、BTable 切换、中断和恢复等事件入口开始；同一张图应保留条件、循环、调用、恢复位置及未知边界。

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
