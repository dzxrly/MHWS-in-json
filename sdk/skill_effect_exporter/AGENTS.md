# 技能效果链路提取与维护

本目录是离线研究 SDK，代码统一使用 Python。它读取从内存 dump 出的游戏 EXE（如 `MonsterHunterWilds_dump.exe`，不使用原版 EXE）、REFramework 的 `il2cpp_dump.json` 和 `MHWS-in-json/natives` 中的解包 JSON，找出原生代码中使用每个技能的函数，并按技能等级把这些函数实际执行一遍，得到“技能 → 函数 → 数值与来源”的链路。结果写入 `src/processed_data/skill_details/data/skill_links/`（`index.json` 加按技能类别拆分的分片），由 `src/processed_data/skill_details` 在构建 PROCESSED_DATA 时生成 `SkillDetails.xlsx`（每个技能等级的每个效果一行，适用范围写作“【武器】弹种”，只列游戏参数中的数值；函数、条件与来源只保留在链路 JSON 中）。表格的取舍规则与效果名称翻译在 `src/processed_data/skill_details/exporter.py`（`effect_links`、`own_values`、`written_links`）和 `labels.py`；取值函数之外的调用方和写入运行时字段的数值，只有当其数据项没有被技能自身取值函数读到、且只被这一个技能的链路用到时才单独列出（写入的值只来自技能等级时，如发动标志，不列出；同一字段由不同数据写入时按数据分行）；新增取值函数后检查它的效果名称是否通顺，不通顺就在 `labels.py` 的 `EFFECT_NAMES` 中补写。

SDK 与 `src` 之间只通过这份 JSON 交接：`src` 不导入本目录的代码，也不读取 EXE 或 il2cpp；本目录不导入 `src`。EXE 和 il2cpp 由使用者提供，仓库不保存副本。

## 维护边界

- 不运行游戏、EXE，不注入或 Hook；Capstone 只把 EXE 当作字节数据读取。
- 调试脚本、试运行输出放在项目根目录 `.tmp`（默认 `.tmp/skill-effects`）。按技能筛选（`-s`）的结果不能写入正式位置，CLI 会拒绝。
- 原生布局常量（对象头、数组与 `List`1` 偏移、调用约定、栈对齐、扫描用的字节模式）只放在 `config.py` 的“native layout constants”一节；类型名、方法名和字段名也集中在 `config.py`。其他模块不写字面偏移。
- 函数地址、全局变量地址、字段偏移都不写进代码：每次运行按类型名、去后缀方法名和字段名从当前 il2cpp dump 重新定位（`scan.py`、`heap.Layouts`）。
- 需要人工说明的技能写在 `notes.py`（简体中文），每条注明核对的游戏版本；没有证据的内容不写。
- 同步更新用户文档：命令或参数变化时，同一次改动中更新 `sdk/README.md`、`sdk/docs/README.zh-Hans.md`、`sdk/docs/README.zh-Hant.md`（三份内容一致），必要时更新三份 README 的“项目工具”简介，并更新本文件。

## 构建思路（先读这一节）

### 1. 问题：技能和数值之间的连接只存在于代码里

`SkillCommonData` 给出技能身份与名称，`SkillData` 给出每级四个没有名字的整数槽位 `_value[0..3]`。`PlayerSkillParam` 等参数文件里的字段名带有技能含义，但字段里没有技能 ID。原生代码把三者连接起来：

- 技能身份以运行时枚举 `app.HunterDef.Skill` 的立即数传给带 `Skill` 参数的方法（`cHunterSkill.getSkillValue*(skill=r8d, slot=r9d)`、`getSkillLevelCore(skill=r9d)`、`getSkillLevel` / `checkSkillActive(skill=r8d)` 等）。
- 许多调用先装入默认 ID，再用 `HunterSkillDef.SkillToGroupSkill[ID]` 经 `cmov` 替换：打开技能换回它所属的组合/系列技能。这张表由 `HunterSkillDef.createSkillToGroupSkill` 用成对立即数写入，**不是**从 SkillData 读出的；两者不一致时以代码为准并列入 `remapDifferences`（1.42.0.2：代码把 HunterSkill_220 映射到 HunterSkill_219，SkillData 中 219 打开的是 HunterSkill_093）。
- 参数文件经内联的单例链 `[rip+G] → +a → +b` 得到 `PlayerGlobalParam`（`cHunterSkill.get__SkillParam` 是它的非内联形式），再按字段偏移读到 `_SkillParam`、`_MealSkillParam`、`_MusicSkillParam` 等；字段偏移只能从 il2cpp 字段记录对应到名字。

所以链路分两步取得：先静态扫描“谁用了哪个技能”，再动态执行“用这个技能得到什么数值”。

### 2. 静态扫描（`native/scan.py`）

- 从 il2cpp dump 找出全部参数类型为 `app.HunterDef.Skill` / `Skill_Fixed` 的方法（技能参数方法）。函数体被超过 `MAX_HELPER_ALIASES` 个方法共用的地址是通用空函数，不算技能参数方法，否则会产生上千个假调用点。
- 在 EXE 可执行节中查找对这些方法的直接 `call` / `jmp`，按异常目录得到调用方函数。
- 对调用方做线性立即数跟踪：寄存器、栈参数（`[rsp+0x20+]`）、`cmov` 前的默认 ID 都记录下来，得到“函数 → 技能 → 用法（读数值槽/读等级/检查发动）→ 整数参数（如槽位）”。
- 同时定位三个共享结构：`SkillToGroupSkill` 的静态槽与栈保护检查函数（来自 `getSkillValue` 的固定开头和结尾）、`PlayerGlobalParam` 单例链（来自 `get__SkillParam`）、技能到组合技能的成对表（来自 `createSkillToGroupSkill`）。任一模式变化都会直接报错，不会沿用旧值。

### 3. 动态求值（`runtime/scenario.py`、`runtime/evaluate.py`、`native/emulator.py`、`runtime/heap.py`）

- **情境**：一次只装备一个技能、取它的一个等级（组合/系列技能的等级是装备件数）。`Scenario` 按游戏的存储方式拼出 `cHunterSkill`：`_EquipDataHolderRef._EquipSkillDataArray` 为每个技能放一个 `EquipSkillData`（SkillCommonData 行、按等级排序的 SkillData 行列表、类别、最大等级），`_CurrentSkillInfoDic[技能]` 放一个 `EquipSkillInfo`（等级按 `via.rds.Mandrake` 的 `v / m` 存放）。因此 `getSkillValue`、`getSkillLevelCore` 等辅助函数按真实指令执行，不另写模型。
- **对象模型**：解包 JSON 中的类实例按 il2cpp 字段偏移读取（`JsonObj`、`ValueView`、`ArrayObj`、`ListObj`）；`user` 文件之间的引用按 `path` 打开对应 JSON；单字段类（如 `cSkillBasicData`）在 JSON 中直接是标量。`<x>k__BackingField` 运行时枚举按名字从 `_x` 的序列化值换算。导出没有描述的运行时对象是 `UnkObj`：读它的字段得到以字段路径命名的未知值。任何声明为 `app.cHunterSkill` 的未知引用都解析为情境中的同一个技能对象（只有一个猎人）。
- **执行**：`Emulator` 从函数入口按 Windows x64 调用约定装入参数（`rcx` 线程上下文、`this`、`rdx/r8/r9` 或 `xmm1-3`、栈），逐条执行。布尔参数和取值不超过 `MAX_ENUM_VALUES` 的枚举参数逐一枚举（组合数上限 `MAX_ARGUMENT_COMBINATIONS`），其余参数保持未知。条件分支依赖未知值时分叉，并把条件以字段路径写进结果；直接调用按真实代码内联（深度上限 `MAX_CALL_DEPTH`），内联失败时按“未模拟的调用”处理：易失寄存器变为以函数名命名的未知值，并记录原因。`switch` 跳转表（`lea` 取得的映像地址加只读表项）按真实目标跳转。写入运行时对象不会结束路径：写入保存在本路径的覆盖层中（之后读同一位置得到写入值），并作为结果的“写入的运行时状态”输出，例如发动处理把持续时间写进技能状态对象；`ByRef` 参数（il2cpp 参数记录的 `modifier: ByRef`）传入指向临时槽的指针。
- **来源**：每个值都带来源集合（SkillData 槽位、参数文件字段的叶子路径、EXE 只读常量），结果据此列出数据来源；指针本身不带来源。
- **前提**（写入 JSON 的 `assumptions`）：一次只装备一个技能；运行时对象引用视为存在，不展开空引用分支；未导出的运行时状态保持未知。

### 3a. 情境维度、取值函数调用方与聚焦求值

- **情境维度**（`config.DIMENSIONS`）：装备武器类型（`HunterCharacter._HunterComp.Prepare.<WeaponBuilder>k__BackingField._EquippedWeaponType`）、弩弹种类（`app.WeaponGunDef.SHELL_TYPE`）、弹药参数类型（`app.WeaponGunDef.SHELL_PARAM_TYPE`）。函数读到维度字段（按字段名，或按字段/返回值/`out` 参数的枚举类型）时，`heap.inputs_read` 记下它，`extract.evaluate_link` 再按该枚举的每个取值（除 `DIMENSION_EXCLUDED`）分别求值；多个维度依次展开（先武器、在需要时再按弹种）。取值作为参数写进结果。`_ReserveWeaponType` 与装备武器同类型但不是维度，保持运行时状态。超限沿用（`LIMIT_STATUSES`）只在等级、参数之间生效，不跨维度取值。
- **取值函数调用方**：不带技能参数、返回非 void 的 `cHunterSkill` 方法（如 `getSkillDodgeNoHitLv`、`getSkillGunnerAmmo_*`）只给出等级或倍率。它们若只读不超过 `MAX_ACCESSOR_SKILLS` 个技能，`NativeIndex.calls_to` 找出的直接调用方也在同一情境中求值（链路 `uses.kind = "accessor"`）。被内联到调用方的取值函数没有调用点，这时结果来自调用方作为第一层链路的求值。
- **聚焦求值**：完整求值超限且链路有调用点时（`cHunterSkill` 上引用超过 `MAX_ACCESSOR_SKILLS` 个技能、有返回值的汇总方法除外，它们保持超限状态；`update` 这类无返回值的方法照常聚焦），`Evaluator.run(..., sites)` 重新求值：未到达调用点前只保留静态控制流图上仍能到达调用点的分支（`NativeIndex.reaching`），走不到的路径丢弃；除调用点本身、技能参数方法和传入技能参数的调用（参数中有技能参数文件里的对象，或来源是这些文件的值，见 `Emulator.passes_parameters`）外，深度 0 的调用按不透明调用处理。同一函数此后的情形直接聚焦求值。结果标 `focused`；聚焦后仍超限的详情为“只追踪可能经过技能读取点的路径仍超限”。
- **窄聚焦**：聚焦求值仍超限时（`extract.focused_run`），`Evaluator.run(..., narrow=True)` 再求值一次：两个分支都能到达读取点时只走静态距离（`NativeIndex.reaching` 给出到最近读取点的指令数）更近的一个，条件照常记录，到达读取点前后都如此；到达读取点之后，其他分支每条路径最多再分叉 `MAX_NARROW_FORKS` 次（任意调用深度），之后走仍能到达读取点的一侧，否则走离所在函数返回（`NativeIndex.exits`）更近的一侧。这样只追踪先前运行时条件的一种组合，结果不完整但每条路径在其条件下成立。`cHunterSkill.update` 这类由许多互相独立的技能块串成的逐帧函数靠它求值。路径标 `narrow`；仍超限的详情为“只沿最近分支追踪到技能读取点仍超限”。同一函数此后的情形直接窄聚焦。用途追踪超限时同样改为窄聚焦。
- **用途追踪**（链路的 `usage`）：除 `cHunterSkill` 的 `getSkill*`/`isSkill*` 取值函数本身外，每条链路在最高等级再求值一次：本函数里的技能读取调用（`getSkillValue`、`getSkillLevelCore`、`checkSkillActive` 或被调用的取值函数）不执行，返回值换成按 `extract.usage_label` 命名的未知量（如 `技能等级〈HunterSkill_019〉()`、`取值〈getSkillBallisticBeginWideRate_Gun〉()`），并只追踪经过这些调用点的路径（`Emulator.usage`）。这样条件、返回表达式和写入里能看到技能数值与哪些字段比较、相乘、写到哪里。情境维度保持未知，作为条件出现；不提到任何名称的 `ok` 路径不保留。每种情形最多 `MAX_USAGE_PATHS` 条路径、最多 `MAX_USAGE_COMBINATIONS` 种参数组合。
- **参数字段读取点**（链路 `uses.kind = "param"`）：`NativeIndex.param_reads` 静态扫描经 `PlayerGlobalParam` 单例链（或 `get__SkillParam()`）读取参数文件字段的指令，得到“字段 → 函数 → 读取地址”；带变址的读取（`[base+idx*4+off]`）把名称只差数字的相邻字段一并算作读取。首轮链路求值后，仍没有任何 `ok` 路径从中取值的字段，在读取它的、本身使用技能的函数里以读取地址为聚焦点再求值一次（`evaluate_link(..., focus_first=True)`），例如弹道强化 Lv3 在会心距离命中时的攻击力加算就在弩炮的 `getOnHitAttackPowerAdd` 中读取。读取字段的函数本身不使用已知技能时（`extract.parameter_readers`：如 `cHunterSkillParamInfo.beginKnight`、`cHunterSkill.beginRyunyu`，显示、网络类除外），改为在 `MAX_READER_DEPTH` 层以内调用它的、使用技能的函数里，以这些调用点为聚焦点求值；调用点本身按真实代码执行，读到的数值归到调用方在该情境中检查的技能。
- **条件比较的数据**（路径的 `compared`）：分叉条件比较的值带来源时（如心眼的肉质阈值 `_Shingan_MeatThreshold`），来源写进 `compared`；合并路径时随条件一起合并。
- **覆盖统计**（`index.json` 的 `coverage`）：`params` 按技能参数文件（`PlayerGlobalParam` 中类型名以 `SKILL_PARAM_SUFFIX` 结尾的字段，如 `PlayerSkillParam`、`PlayerMealSkillParam`）列出每个字段的静态读取函数，以及按用法（`value` 返回值、`write` 写入运行时状态、`compare` 条件比较）列出用到它的技能；`skillData` 按技能列出非零的 SkillData 槽位和按用法用到的槽位。三种用法都没有的字段/槽位就是表格可能漏掉的效果。参数字段聚焦求值只针对这些技能参数文件。
- **接口调用与不透明调用的返回值**：`mov rax,[obj]; mov rax,[rax+INTERFACE_TABLE_OFFSET]; call [rax+8k]` 在 `obj` 的声明类型是接口时，按该接口第 k 个方法（按 il2cpp 方法 id 排序）处理；接口方法与其他不透明调用声明返回引用类型时，返回该类型的未知对象，之后的字段读取有名字，声明为 `app.cHunterSkill` 的仍解析为情境中的技能对象（例如 `HunterCharacter._ContextHolder.get_Hunter().HunterStatus._Skill`）。
- **同一条件不重复分叉**：路径已经走过的条件或其否定再次出现时直接取已知方向；条件文本含不透明调用结果（`f()`，每次调用可能不同）或被截短时不这样处理。
- **始终不透明的调用**：`config.OPAQUE_CALL_PREFIXES` 中的线程、引擎内部以及只写聊天记录、播放特效的调用（`app.ChatManager`、`app.cHunterEffect` 等）不内联，它们的分支不会把数值带回技能。
- **类型检查与异常**：可写全局量中保存的类型描述地址按 il2cpp dump 的类型记录命名为 `类型 X`（类型记录的 `address` 键可能排在 `RSZ` 之后，`scan.type_addresses` 按类型标题与其后第一个 8 空格缩进的 `address` 配对）。读到异常类型（名称以 `Exception` 结尾）的路径即将构造并抛出异常，直接以 `throws` 结束，不再展开异常对象构造中的分支。
- **其他保证**：同一路径在同一分支地址因未知量分叉超过 `MAX_LOOP_FORKS` 次视为次数未知的循环（`UnknownLoop`），所在内联调用整体回放为不透明调用；`switch` 跳转表的索引未知时，按前面 `cmp idx, N; ja` 的上界逐个情形分叉；不透明调用的 `ByRef` 参数写入以“函数() 的输出 参数名”命名的未知值；结果相同、条件只差一对互为否定条件的路径合并（`extract.merge_paths`）。`inc`/`dec` 的结果和保留的 CF 都未知时，只在后续条件读取 CF 时报告不支持。合并后每个情形最多记录 `MAX_RECORDED_PATHS` 条路径（条件少的优先），其余以 `truncated` 记录计数，控制分片体积。

### 4. 结果的含义

- `status=ok` 且有 `value`：在列出的运行时条件下函数返回这个数。
- `status=ok` 且有 `expression`：返回值依赖未知输入，表达式写出它们的组合（如 `参数1:Single * 0.5`）。
- `usage` 中的路径不是数值结果，而是用途证据：数值本身由 `results` 给出，`usage` 说明它在什么条件下、和什么相乘或比较、写到哪个字段。
- `too_many_paths`、`too_long`：分支（`MAX_PATHS`，含尚未完成的分叉）、单条路径指令（`MAX_STEPS`）或一次求值的全部指令（`MAX_TOTAL_STEPS`）超过上限，没有完整求值。同一函数的一个等级/参数情形超限后，其余情形直接沿用该状态（`LIMIT_STATUSES`），详情注明“其他情形未再单独求值”，以免全量运行被少数大函数拖慢。这多见于把许多技能加在一起的汇总函数（如 `calcAttackRate`、各武器的 `getOnHitAttackPowerAdd`），它们依赖其他技能的计时器等状态；同一技能的精确数值通常由 `getSkill*` 读取函数给出。
- `unsupported`：缺少某条指令语义或某种数据形式，详情给出指令或字段；按“扩展规则”补充后重跑。
- 无返回值的函数（发动、更新、结束处理）也会求值，结果看“写入的运行时状态”。显示、网络同步类调用方只记录链路，不求值（`config.EVALUATE_SKIP_PREFIXES`）。

### 必须坚持的原则

1. **不编造**：没有证据的数值、条件、对应关系保持未知或写明状态；部分求值就写部分。
2. **数据驱动**：地址和偏移每次从当前 dump 重新得到；模式不符时报错，不使用旧地址兜底。
3. **按真实代码执行**：不为辅助函数写简化模型；需要补的是指令语义或对象模型。
4. **常量集中**：版本相关的布局常量只在 `config.py`；人工说明只在 `notes.py`。

## 文件与职责

| 文件 | 职责 |
|---|---|
| `config.py` | 路径、类型/方法/字段名、限制参数、原生布局常量、不求值的调用方前缀 |
| `native/values.py` | 值与来源（`V`、`Ptr`、`Unk`、`unk`）、单精度换算 |
| `native/scan.py` | 技能参数方法、调用点与立即数技能参数、`SkillToGroupSkill` 成对表、栈保护检查函数、单例链、参数字段的静态读取点 |
| `native/emulator.py` | x64 解释执行、分叉与条件文本、调用内联与失败回退、运行时写入覆盖层、浮点与向量指令 |
| `runtime/heap.py` | il2cpp 字段布局（`Layouts`）、解包 JSON 对象模型、未知运行时对象 |
| `runtime/scenario.py` | 情境：技能目录、`EquipSkillData`/`EquipSkillInfo` 拼装、组合技能表、单例链 |
| `runtime/evaluate.py` | 参数取值范围、按调用约定装入参数并执行一次求值（含聚焦求值）、被调方法签名 |
| `workflow/extract.py` | 汇总全部链路与求值结果、用途追踪、参数字段聚焦求值、覆盖统计、整理来源；不记录游戏版本或文件摘要 |
| `workflow/shards.py` | 写出 `index.json` 与按技能类别的分片；分片内的条件、来源、调用文本与常量各自去重成表 |
| `workflow/cli.py`、`__main__.py` | 命令行入口；菜单界面在 `sdk/tui.py`（`python -m sdk`），只调用命令行 |
| `notes.py` | 需要显式说明的技能与通用说明（简体中文） |

## 命令

在项目根目录运行（解释器为 `.tmp/sdk-venv/Scripts/python.exe`，依赖见 `sdk/requirements.txt`，用到其中的 Capstone）：

```powershell
python -B -m sdk.skill_effect_exporter extract                       # EXE 与 il2cpp 取默认位置，写入 src/processed_data/skill_details/data
python -B -m sdk.skill_effect_exporter extract -e <EXE> -i <il2cpp_dump.json> -n MHWS-in-json/natives -o <输出>
python -B -m sdk.skill_effect_exporter extract -s HunterSkill_019 -o .tmp/skill-effects/try.json   # 调试单个技能
```

- `-e/--exe`：dump 出的游戏 EXE；未设环境变量 `MHWS_EXE` 时必须指定。
- `-i/--il2cpp`：`il2cpp_dump.json`；未设环境变量 `MHWS_IL2CPP` 时必须指定。SDK 不猜测这两个路径。
- 全量运行约 30 分钟（多数时间花在按武器、弹药展开、聚焦求值与用途追踪上）；之后运行 `python -m src.processed_data.skill_details` 或完整流水线检查表格。

## 游戏更新后的检查

1. 从更新后的游戏 dump 出新的 EXE，并用 REFramework 生成新的 il2cpp dump；重新解包 `MHWS-in-json`。
2. 运行 `extract`。以下任一项报错都说明代码模式变化，先核对原生指令再修改 `native/scan.py` 或 `config.py`：
   - `getSkillValue` 开头读取 `SkillToGroupSkill`（`mov rax,[rip+X]; movsxd rdx,r8d; mov eax,[rax+rdx*4+ARRAY_DATA_OFFSET]`）与结尾 `xor rcx,rsp; call 栈保护检查`；
   - `get__SkillParam` 仍是三次读取后 `ret` 的单例链；
   - `createSkillToGroupSkill` 仍以 `r8d/r9d` 成对立即数调用同一个写入函数（少于 10 对视为模式变化）。
3. 核对 `config.py` 的布局常量：用一个已知函数（如 `getSkillBallisticBeginWideRate_Gun`）确认数组长度在 `ARRAY_LENGTH_OFFSET`、元素从 `ARRAY_DATA_OFFSET` 开始；`List`1` 的 `_items/_size/_version` 偏移与 il2cpp 字段记录一致；`via.rds.Mandrake` 的 `v/m` 字段与 `EquipSkillInfo._SkillLv` 仍按 `v / m` 解码（见 `getSkillLevelCore`）。
4. 与上一版输出比较 `stats`（各状态的路径数）和关键技能的数值（攻击 `getSkillAttackRate/Add`、弹道强化 `getSkillBallistic*`、恨击 `getSkillViolentAddDamage`）。新出现的 `unsupported` 先看详情：缺指令就在 `native/emulator.py` 补完整语义，缺数据形式就在 `runtime/heap.py` 补对象模型。
5. 复核 `notes.py` 中每条说明对应的代码是否仍成立，更新其中的版本号；`remapDifferences` 有变化时同步更新说明。
6. 构建 `SkillDetails.xlsx` 检查表格；核对数值时直接查看链路 JSON 中的条件与来源。`src` 只核对索引与分片的格式是否一致，不保存游戏版本或解包文件摘要；游戏或 `MHWS-in-json` 更新后必须重新运行 `extract`。

## 扩展规则

- 新指令要写出完整语义：读取哪些操作数、写入哪几位（32 位写入清零高位，8/16 位写入保留其余位）、标志位怎样设置；拿不准就抛出 `Unsupported`，让该路径保持未求值。
- 新的数据形式（值类型、特殊容器）放进 `runtime/heap.py`，按 il2cpp 字段记录确定偏移，不按名字猜。
- 不能为了减少未知而把运行时状态写成固定值；需要固定的前提必须写进 `assumptions`，并在表格“说明”页显示。
- 调整 `EVALUATE_SKIP_PREFIXES`、限制参数或情境构造后，全量重跑并对比 `stats` 与关键技能数值。
