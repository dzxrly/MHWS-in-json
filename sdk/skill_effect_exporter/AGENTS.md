# 技能效果链路提取与维护

本目录是离线研究 SDK，代码统一使用 Python。它读取从内存 dump 出的游戏 EXE（如 `MonsterHunterWilds_dump.exe`，不使用原版 EXE）、REFramework 的 `il2cpp_dump.json` 和 `MHWS-in-json/natives` 中的解包 JSON，找出原生代码中使用每个技能的函数，并按技能等级把这些函数实际执行一遍，得到“技能 → 函数 → 数值与来源”的链路。结果写入 `src/processed_data/skill_details/data/skill_links/`（`index.json` 加按技能类别拆分的分片），由 `src/processed_data/skill_details` 在构建 PROCESSED_DATA 时生成 `SkillDetails.xlsx`（每个技能等级的每个效果一行，适用范围写作“【武器】弹种”，只列游戏参数中的数值；函数、条件与来源只保留在链路 JSON 中）。表格的取舍规则与效果名称翻译在 `src/processed_data/skill_details/exporter.py`（`effect_links`、`own_values`、`written_links`）和 `labels.py`；取值函数之外的调用方和写入运行时字段的数值，只有当其数据项没有被技能自身取值函数读到、且只被这一个技能的链路用到时才单独列出（写入的值只来自技能等级时，如发动标志，不列出；同一字段由不同数据写入时按数据分行）；`labels.effect_name` 按方法名逐词翻译得到的名称只是还没有含义时的占位，效果名称写在技能模块 `MEANINGS` 的 `效果` 中，`labels.py` 不再按方法名单独补写。每个技能在 `skills/hunterskill_<编号>.py` 有独立模块（与敌人逻辑的 `monster/<ID>.py` 相同的组织方式；`skills/__init__.py` 按编号加载并核对 `SKILL_ID` 与字段名），`MEANINGS` 按 `effect_links` 给出的效果键写明每个显示效果的效果名称、作用于、计算、条件、单位和依据，`NOTES` 写只属于这个技能的已核实说明；`extract` 把它们写进 `index.json` 的 `meanings` 和 `notes.skills`，只改模块时运行 `annotate` 更新，不必重新求值（`tests/sdk/test_skill_modules.py` 检查二者一致）。技能表新增技能时 `extract` 会列出缺少模块的技能，用 `new-skill -s <ID>` 生成空模块；同一等级取多个数值时，`exporter.value_situations` 按布尔参数、各值独有的数据字段或条件分行，`情形` 字段把这些代码文本对应成可读的情形名（对应为空串的条件不列出）。`own_values` 只保留技能自身的数值：饭技、狩猎笛旋律、武器状态标志位生效（`OTHER_ACTIVE`）或读取其他技能 SkillData 的路径不算，随机判定（`RANDOM_CHECK`）写作概率。只写用途追踪或游戏说明能支持的内容；`python -m src.processed_data.skill_details --meanings-report <文件.md>` 列出每个效果的含义、数值与用途证据，以及已不再显示的条目，重跑提取后用它核对。

SDK 与 `src` 之间只通过这份 JSON 交接：`src` 不导入本目录的代码，也不读取 EXE 或 il2cpp；本目录不导入 `src`。EXE 和 il2cpp 由使用者提供，仓库不保存副本。

## 维护边界

- 不运行游戏、EXE，不注入或 Hook；Capstone 只把 EXE 当作字节数据读取。
- 调试脚本、试运行输出放在项目根目录 `.tmp`（默认 `.tmp/skill-effects`）。按技能筛选（`-s`）的结果不能写入正式位置，CLI 会拒绝。
- 原生布局常量（对象头、数组与 `List`1` 偏移、调用约定、栈对齐、扫描用的字节模式）只放在 `config.py` 的“native layout constants”一节；类型名、方法名和字段名也集中在 `config.py`。其他模块不写字面偏移。
- 函数地址、全局变量地址、字段偏移都不写进代码：每次运行按类型名、去后缀方法名和字段名从当前 il2cpp dump 重新定位（`scan.py`、`heap.Layouts`）。
- 共通代码只放在 `shared/`，不写任何技能编号或只属于一个技能的常量；只属于一个技能的提取处理、常量、人工说明和数值含义写在它的 `skills/hunterskill_<编号>.py`，对所有技能都成立的说明写在 `notes.py`（简体中文），每条说明注明核对的游戏版本：版本号统一取自 `config.GAME_VERSION`（字符串中用 f-string 引用，注释中写 `config.GAME_VERSION`），代码与说明中不写字面版本号；没有证据的内容不写或标明未核实。
- 同步更新用户文档：命令或参数变化时，同一次改动中更新 `sdk/README.md`、`sdk/docs/README.zh-Hans.md`、`sdk/docs/README.zh-Hant.md`（三份内容一致），必要时更新三份 README 的“项目工具”简介，并更新本文件。

## 构建思路（先读这一节）

### 1. 问题：技能和数值之间的连接只存在于代码里

`SkillCommonData` 给出技能身份与名称，`SkillData` 给出每级四个没有名字的整数槽位 `_value[0..3]`。`PlayerSkillParam` 等参数文件里的字段名带有技能含义，但字段里没有技能 ID。原生代码把三者连接起来：

- 技能身份以运行时枚举 `app.HunterDef.Skill` 的立即数传给带 `Skill` 参数的方法（`cHunterSkill.getSkillValue*(skill=r8d, slot=r9d)`、`getSkillLevelCore(skill=r9d)`、`getSkillLevel` / `checkSkillActive(skill=r8d)` 等）。
- 许多调用先装入默认 ID，再用 `HunterSkillDef.SkillToGroupSkill[ID]` 经 `cmov` 替换：打开技能换回它所属的组合/系列技能。这张表由 `HunterSkillDef.createSkillToGroupSkill` 用成对立即数写入，**不是**从 SkillData 读出的；两者不一致时以代码为准并列入 `remapDifferences`（`config.GAME_VERSION` 中：代码把 HunterSkill_220 映射到 HunterSkill_219，SkillData 中 219 打开的是 HunterSkill_093）。
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
- **聚焦求值**：完整求值超限且链路有调用点时（`cHunterSkill` 上引用超过 `MAX_ACCESSOR_SKILLS` 个技能、有返回值的汇总方法除外，它们保持超限状态；`update` 这类无返回值的方法照常聚焦；技能自身的 `cHunterSkill` 方法在聚焦求值中，路径读到技能参数文件里的对象后（`Emulator.param_focus`、`State.param_read`），走不到读取点的分支不再丢弃，这样跳过等级读取的分支，如连击连续命中不足 5 次时的数值，也会保留），`Evaluator.run(..., sites)` 重新求值：未到达调用点前只保留静态控制流图上仍能到达调用点的分支（`NativeIndex.reaching`），走不到的路径丢弃；除调用点本身、技能参数方法和传入技能参数的调用（参数中有技能参数文件里的对象，或来源是这些文件的值，见 `Emulator.passes_parameters`）外，深度 0 的调用按不透明调用处理。同一函数此后的情形直接聚焦求值。结果标 `focused`；聚焦后仍超限的详情为“只追踪可能经过技能读取点的路径仍超限”。
- **窄聚焦**：聚焦求值仍超限时（`extract.focused_run`），`Evaluator.run(..., narrow=True)` 再求值一次：两个分支都能到达读取点时只走静态距离（`NativeIndex.reaching` 给出到最近读取点的指令数）更近的一个，条件照常记录，到达读取点前后都如此；到达读取点之后，其他分支每条路径最多再分叉 `MAX_NARROW_FORKS` 次（任意调用深度），之后走仍能到达读取点的一侧，否则走离所在函数返回（`NativeIndex.exits`）更近的一侧。这样只追踪先前运行时条件的一种组合，结果不完整但每条路径在其条件下成立。`cHunterSkill.update` 这类由许多互相独立的技能块串成的逐帧函数靠它求值。路径标 `narrow`；仍超限的详情为“只沿最近分支追踪到技能读取点仍超限”。同一函数此后的情形直接窄聚焦。用途追踪超限时同样改为窄聚焦。
- **用途追踪**（链路的 `usage`）：除 `cHunterSkill` 的 `getSkill*`/`isSkill*` 取值函数本身外，每条链路在最高等级再求值一次：本函数里的技能读取调用（`getSkillValue`、`getSkillLevelCore`、`checkSkillActive` 或被调用的取值函数）不执行，返回值换成按 `extract.usage_label` 命名的未知量（如 `技能等级〈HunterSkill_019〉()`、`取值〈getSkillBallisticBeginWideRate_Gun〉()`），并只追踪经过这些调用点的路径（`Emulator.usage`）。这样条件、返回表达式和写入里能看到技能数值与哪些字段比较、相乘、写到哪里。情境维度保持未知，作为条件出现；不提到任何名称的 `ok` 路径不保留。每种情形最多 `MAX_USAGE_PATHS` 条路径、最多 `MAX_USAGE_COMBINATIONS` 种参数组合。
- **参数字段读取点**（链路 `uses.kind = "param"`）：`NativeIndex.param_reads` 静态扫描经 `PlayerGlobalParam` 单例链（或 `get__SkillParam()`）读取参数文件字段的指令，得到“字段 → 函数 → 读取地址”；带变址的读取（`[base+idx*4+off]`）把名称只差数字的相邻字段一并算作读取。首轮链路求值后，仍没有任何 `ok` 路径从中取值的字段，在读取它的、本身使用技能的函数里以读取地址为聚焦点再求值一次（`evaluate_link(..., focus_first=True)`），例如弹道强化 Lv3 在会心距离命中时的攻击力加算就在弩炮的 `getOnHitAttackPowerAdd` 中读取。读取字段的函数本身不使用已知技能时（`extract.parameter_readers`：如 `cHunterSkillParamInfo.beginKnight`、`cHunterSkill.beginRyunyu`，显示、网络类除外），改为在 `MAX_READER_DEPTH` 层以内调用它的、使用技能的函数里，以这些调用点为聚焦点求值；调用点本身按真实代码执行，读到的数值归到调用方在该情境中检查的技能。
- **条件比较的数据**（路径的 `compared`）：分叉条件比较的值带来源时（如心眼的肉质阈值 `_Shingan_MeatThreshold`），来源写进 `compared`；合并路径时随条件一起合并。
- **覆盖统计**（`index.json` 的 `coverage`）：`params` 按技能参数文件（`PlayerGlobalParam` 中类型名以 `SKILL_PARAM_SUFFIX` 结尾的字段，如 `PlayerSkillParam`、`PlayerMealSkillParam`）列出每个字段的静态读取函数，以及按用法（`value` 返回值、`write` 写入运行时状态、`compare` 条件比较）列出用到它的技能；`skillData` 按技能列出非零的 SkillData 槽位和按用法用到的槽位。三种用法都没有的字段/槽位就是表格可能漏掉的效果。参数字段聚焦求值只针对这些技能参数文件。
- **接口调用与不透明调用的返回值**：`mov rax,[obj]; mov rax,[rax+INTERFACE_TABLE_OFFSET]; call [rax+8k]` 在 `obj` 的声明类型是接口时，按该接口第 k 个方法（按 il2cpp 方法 id 排序）处理；接口方法与其他不透明调用声明返回引用类型时，返回该类型的未知对象，之后的字段读取有名字，声明为 `app.cHunterSkill` 的仍解析为情境中的技能对象（例如 `HunterCharacter._ContextHolder.get_Hunter().HunterStatus._Skill`）。
- **技能状态对象与虚函数调用**：`config.SKILL_STATE_OWNER`（`cHunterSkillParamInfo`）的构造函数为许多技能各分配一个状态对象（`cInfo` 或其子类），把技能的运行时枚举立即数写进对象的 `_Skill`，再存入 `_DisasterInfo` 这类字段；之后的代码把 `_Skill` 交给技能辅助函数，扫描因此看不到立即数技能参数。`NativeIndex.state_objects` 从构造函数读出“字段 → 实际分配的类型与立即数写入”（`mov rdx,[rip+类型描述]`、分配调用、对新对象的立即数写入、`mov [this+F], 对象`，写屏障等其他调用只清除易失寄存器），`SkillWorld` 只保留类型为技能枚举的字段，其余初值（如 `InitType`）是运行时状态，保持未知。读这些字段得到 `StateObj`：类型字（`[obj]`）是 `ClassDescriptor`，从它的 `VTABLE_OFFSET + 8k` 读出的调用目标按实际类型的 il2cpp `vtable_index == k`（先找派生类）解析，间接 `call`/`jmp` 据此按真实代码内联（如 `beginDisaster` 经 `cInfo.beginSkill` 写入持续时间）；其他未知对象的虚函数调用仍按不透明调用处理。
- **技能模块声明的函数**（链路 `uses.kind = "module"`）：扫描无法把某个函数对应到技能时（调用处的技能判断经状态对象或其他技能，或没有直接调用），技能模块在 `DECLARED_METHODS` 中写明（类型、方法、核对过的依据），`extract` 调用 `SkillContext.extract_method`，在该技能的情境中求值，读取参数文件字段的静态地址作为聚焦点；依据写入链路的 `uses`。表格把这类链路用到的数据项算作声明它的技能所有，即使扫描还把同一函数归到其他技能（如 `beginTechnicalAttack` 也读取 HunterSkill_215 的等级）。调用处求值分支过多时，也可以直接声明内部真正写入数值的函数（如能量石声明 `beginSkillIamCoalMiner`，不经过先查物品表的 `ItemUtil.sendSkilllamCoalMiner`）。声明项可以再给出参数字段名（第四项），这时只聚焦这些字段的读取点（含对读取函数的调用处），用于许多技能共用的大函数：浸水刃纹在 `updateAfter` 中只聚焦 `_BubbleToishiMaxContinueTime`，否则共通步骤会同时追踪其他字段，窄聚焦很少到达这次写入。
- **技能模块跳过的函数**（链路的 `skipped`）：全量求值中大量情形都得不到本技能可显示数值的函数（汇总或命中处理函数，只有等级判断或其他技能的数据），技能模块在 `SKIPPED_FUNCTIONS` 中写明（类型、方法、依据：哪个版本、多少情形、路径状态），`extract_skill`/`extract_parameters` 仍记录链路和用法，但不求值，链路带 `skipped` 说明。现有跳过项按两次全量结果（加入状态对象与虚函数调用之前和之后）选出每条至少 50 种情形、两次都没有本技能数值的链路，排除技能含义的依据中提到的函数和表格中还没有任何行的技能。`extract --all-links` 忽略跳过，照常求值；匹配不到链路的跳过项在提取日志中列出。
- **同一条件不重复分叉**：路径已经走过的条件或其否定再次出现时直接取已知方向；条件文本含不透明调用结果（`f()`，每次调用可能不同）或被截短时不这样处理。
- **始终不透明的调用**：`config.OPAQUE_CALL_PREFIXES` 中的线程、引擎内部以及只写聊天记录、播放特效的调用（`app.ChatManager`、`app.cHunterEffect`、取特效颜色的 `HunterSkillDef.getSkillCommonEffectColor` 等）不内联，它们的分支不会把数值带回技能。只供特效使用的参数字段（`config.DISPLAY_PARAM_FIELDS`，如 `_CommonEffectSetting`）不作为参数字段读取点的聚焦目标。
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
4. **常量集中**：版本相关的布局常量只在 `config.py`；人工说明与数值含义只在 `skills/<ID>.py` 和 `notes.py`。

## 文件与职责

与敌人逻辑 SDK 相同，共通代码在 `shared/`，每个技能一个模块在 `skills/`；配置 `config.py` 与通用说明 `notes.py` 在本目录根部。本文其他位置提到的 `native/`、`runtime/`、`workflow/` 都在 `shared/` 下。

| 文件 | 职责 |
|---|---|
| `config.py` | 路径、类型/方法/字段名、限制参数、原生布局常量、不求值的调用方前缀、数值含义的字段名 |
| `shared/native/values.py` | 值与来源（`V`、`Ptr`、`Unk`、`unk`）、单精度换算 |
| `shared/native/scan.py` | 技能参数方法、调用点与立即数技能参数、`SkillToGroupSkill` 成对表、栈保护检查函数、单例链、参数字段的静态读取点、构造函数分配的技能状态对象 |
| `shared/native/emulator.py` | x64 解释执行、分叉与条件文本、调用内联与失败回退（含实际类型已知对象的虚函数调用）、运行时写入覆盖层、浮点与向量指令 |
| `shared/runtime/heap.py` | il2cpp 字段布局（`Layouts`，含虚函数表槽位解析）、解包 JSON 对象模型、未知运行时对象、技能状态对象（`StateObj`）与其类型字 |
| `shared/runtime/scenario.py` | 情境：技能目录、`EquipSkillData`/`EquipSkillInfo` 拼装、组合技能表、单例链 |
| `shared/runtime/evaluate.py` | 参数取值范围、按调用约定装入参数并执行一次求值（含聚焦求值）、被调方法签名 |
| `shared/workflow/context.py` | `SkillContext`：一次提取共用的扫描、求值器与链路；按技能预先规划工作，提供技能模块调用的 `extract_skill`（使用技能的函数、取值函数的调用方）、`extract_parameters`（未求得数值的参数字段读取点）与 `extract_method`（模块声明的函数），汇总文档 |
| `shared/workflow/extract.py` | 提取入口：依次运行每个技能模块的 `extract`，再运行每个技能模块的 `extract_parameters`；单条链路求值、用途追踪、覆盖统计、整理来源；不记录游戏版本或文件摘要 |
| `shared/workflow/shards.py` | 写出 `index.json` 与按技能类别的分片；分片内的条件、来源、调用文本与常量各自去重成表 |
| `shared/workflow/annotate.py` | 把技能模块的含义与说明写进链路文档或已写出的 `index.json`（`annotate` 命令） |
| `shared/workflow/cli.py`、`__main__.py` | 命令行入口；菜单界面在 `sdk/tui.py`（`python -m sdk`），只调用命令行 |
| `notes.py` | 对所有技能成立的通用说明（简体中文） |
| `skills/__init__.py` | 按编号加载技能模块并核对 `SKILL_ID` 与含义字段；没有模块的技能用 `DefaultSkill`（共通步骤）并列为缺少；`new-skill` 生成新模块 |
| `skills/hunterskill_<编号>.py` | 每个技能一个模块（含 SkillCommonData 之外、代码中出现的技能）：`extract(context)` 与 `extract_parameters(context)` 两个提取步骤（多数只是调用 `SkillContext` 共通步骤的薄入口，这是正常的；只属于这个技能的特殊处理和常量写在这里，如扫描找不到的函数 `DECLARED_METHODS`、只记录不求值的函数 `SKIPPED_FUNCTIONS`），`MEANINGS`（显示效果的数值含义）与 `NOTES` |

## 命令

在项目根目录运行（解释器为 `.tmp/sdk-venv/Scripts/python.exe`，依赖见 `sdk/requirements.txt`，用到其中的 Capstone）：

```powershell
python -B -m sdk.skill_effect_exporter extract                       # EXE 与 il2cpp 取默认位置，写入 src/processed_data/skill_details/data
python -B -m sdk.skill_effect_exporter extract -e <EXE> -i <il2cpp_dump.json> -n MHWS-in-json/natives -o <输出>
python -B -m sdk.skill_effect_exporter extract -s HunterSkill_019 -o .tmp/skill-effects/try.json   # 调试单个技能
python -B -m sdk.skill_effect_exporter extract --all-links -o .tmp/skill-effects/all   # 也求值技能模块跳过的函数
python -B -m sdk.skill_effect_exporter annotate                      # 修改技能模块后，只更新 index.json 的含义与说明
python -B -m sdk.skill_effect_exporter new-skill -s HunterSkill_250  # 为新增技能生成空模块
```

- `-e/--exe`：dump 出的游戏 EXE；未设环境变量 `MHWS_EXE` 时必须指定。
- `-i/--il2cpp`：`il2cpp_dump.json`；未设环境变量 `MHWS_IL2CPP` 时必须指定。SDK 不猜测这两个路径。
- `--all-links`：同时求值各技能模块 `SKIPPED_FUNCTIONS` 中的函数，用于游戏更新后核对跳过是否仍成立。
- 全量运行约 30 分钟（多数时间花在按武器、弹药展开、聚焦求值与用途追踪上）；之后运行 `python -m src.processed_data.skill_details` 或完整流水线检查表格。

## 游戏更新后的检查

1. 从更新后的游戏 dump 出新的 EXE，并用 REFramework 生成新的 il2cpp dump；重新解包 `MHWS-in-json`。
2. 运行 `extract`。以下任一项报错都说明代码模式变化，先核对原生指令再修改 `native/scan.py` 或 `config.py`：
   - `getSkillValue` 开头读取 `SkillToGroupSkill`（`mov rax,[rip+X]; movsxd rdx,r8d; mov eax,[rax+rdx*4+ARRAY_DATA_OFFSET]`）与结尾 `xor rcx,rsp; call 栈保护检查`；
   - `get__SkillParam` 仍是三次读取后 `ret` 的单例链；
   - `createSkillToGroupSkill` 仍以 `r8d/r9d` 成对立即数调用同一个写入函数（少于 10 对视为模式变化）。
3. 核对 `config.py` 的布局常量：用一个已知函数（如 `getSkillBallisticBeginWideRate_Gun`）确认数组长度在 `ARRAY_LENGTH_OFFSET`、元素从 `ARRAY_DATA_OFFSET` 开始；``List`1`` 的 `_items/_size/_version` 偏移与 il2cpp 字段记录一致；`via.rds.Mandrake` 的 `v/m` 字段与 `EquipSkillInfo._SkillLv` 仍按 `v / m` 解码（见 `getSkillLevelCore`）。
4. 与上一版输出比较 `stats`（各状态的路径数）和关键技能的数值（攻击 `getSkillAttackRate/Add`、弹道强化 `getSkillBallistic*`、恨击 `getSkillViolentAddDamage`）。新出现的 `unsupported` 先看详情：缺指令就在 `native/emulator.py` 补完整语义，缺数据形式就在 `runtime/heap.py` 补对象模型。
5. 用 `extract --all-links -o .tmp/...` 再运行一次，核对技能模块 `SKIPPED_FUNCTIONS` 中的函数仍然没有本技能可显示的数值（与正常运行的表格行一致），否则删去对应跳过项。复核 `DECLARED_METHODS` 的依据（状态对象的 `_Skill`、调用关系）是否仍成立。
6. 复核 `notes.py` 与各技能模块 `NOTES` 中每条说明对应的代码是否仍成立，全部复核后再把 `config.GAME_VERSION` 改为新版本（说明、声明与跳过依据中的版本号都引用它）；`remapDifferences` 有变化时同步更新说明。用 `python -m src.processed_data.skill_details --meanings-report <文件.md>` 核对各技能模块的 `MEANINGS`：新出现的效果补写含义，“已不再显示的条目”从模块中删除，然后运行 `annotate`。
7. 构建 `SkillDetails.xlsx` 检查表格；核对数值时直接查看链路 JSON 中的条件与来源。`src` 只核对索引与分片的格式是否一致，不保存游戏版本或解包文件摘要；游戏或 `MHWS-in-json` 更新后必须重新运行 `extract`。

## 扩展规则

- 新指令要写出完整语义：读取哪些操作数、写入哪几位（32 位写入清零高位，8/16 位写入保留其余位）、标志位怎样设置；拿不准就抛出 `Unsupported`，让该路径保持未求值。
- 新的数据形式（值类型、特殊容器）放进 `runtime/heap.py`，按 il2cpp 字段记录确定偏移，不按名字猜。
- 不能为了减少未知而把运行时状态写成固定值；需要固定的前提必须写进 `assumptions`，并在表格“说明”页显示。
- 调整 `EVALUATE_SKIP_PREFIXES`、限制参数或情境构造后，全量重跑并对比 `stats` 与关键技能数值。
