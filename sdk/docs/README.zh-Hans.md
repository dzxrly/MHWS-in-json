# SDK 使用说明

[English](../README.md) | 简体中文 | [繁體中文](README.zh-Hant.md)

仓库的 `sdk/` 目录是读取游戏文件的离线 SDK。`python -m sdk` 打开它的[菜单界面](#菜单界面tui)；各项功能也可以在项目根目录用 `python -m` 单独运行。安装脚本 `sdk/setup_env.ps1` 和依赖清单 `sdk/requirements.txt` 由所有功能共用：

| 功能 | 用途 | 需要的外部文件 |
|---|---|---|
| `sdk.enemy_logic_exporter` | 从 dump 出的游戏 EXE、IL2CPP 元数据和资源导出中提取怪物行动逻辑，生成网页使用的行动图 JSON | dump 出的 EXE、IL2CPP 元数据、`MHWS-in-json` 资源；部分命令还需要 Ghidra |
| `sdk.skill_effect_exporter` | 找出原生代码中使用每个技能的函数，按技能等级求值，生成技能效果链路 JSON（`SkillDetails.xlsx` 的数据来源） | dump 出的 EXE、IL2CPP 元数据、`MHWS-in-json` 资源 |

两项功能读取的都是从内存 dump 出的游戏 EXE（例如 `MonsterHunterWilds_dump.exe`），生成 REFramework 的 `il2cpp_dump.json` 之前本来就会得到它；不使用原版 `MonsterHunterWilds.exe`。这两个文件都由使用者提供，仓库和 Release 都不保存副本，SDK 也不猜测路径：用 `-e/--exe`、`-i/--il2cpp` 指定，或设环境变量 `MHWS_EXE`、`MHWS_IL2CPP`。SDK 不记录游戏版本或文件摘要；游戏更新后，代码或数据对不上的地方会直接报错（符号无法定位、原生字节不一致等），按“[游戏更新后](#游戏更新后)”处理。

只想重新生成网页或表格、不改动提取结果时，不需要 SDK：构建器只读取仓库中已提交的 JSON（见“[只构建网页](#只构建网页)”）。

## 通用参数

| 参数 | 说明 |
|---|---|
| `-e`, `--exe` | dump 出的游戏 EXE；未设环境变量 `MHWS_EXE` 时必须指定 |
| `-i`, `--il2cpp` | REFramework 导出的 `il2cpp_dump.json`；未设环境变量 `MHWS_IL2CPP` 时必须指定 |
| `-n`, `--natives` | 解包 JSON 的 `natives` 目录，默认 `MHWS-in-json/natives` |
| `-o`, `--output` | 输出位置 |
| `-m`, `--models` | 研究模型目录（`sdk.enemy_logic_exporter`） |
| `-w`, `--work-dir` | 研究缓存目录，写在子命令前（`sdk.enemy_logic_exporter`） |

## 搭建环境（Windows）

1. 安装 Python 3.13（勾选 `py` 启动器）与 Git，克隆仓库。
2. 在项目根目录运行安装脚本。它在 `.agents/sdk-venv` 建虚拟环境，安装固定版本的依赖（Capstone、PyGhidra、questionary、rich），最后运行环境检查：

   ```powershell
   powershell -ExecutionPolicy Bypass -File sdk/setup_env.ps1 -Exe <dump 出的 EXE> -Il2cpp <il2cpp_dump.json>
   ```

3. 按检查结果补齐缺失项，然后再检查一次：

   ```powershell
   .agents/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env -e <dump 出的 EXE> -i <il2cpp_dump.json>
   ```

| 检查项 | 怎样补齐 |
|---|---|
| dump 出的 EXE | 从运行中的游戏 dump 出的 EXE（如 `MonsterHunterWilds_dump.exe`）；用 `-e` 指定或设环境变量 `MHWS_EXE` |
| IL2CPP dump | REFramework 对同一游戏导出的 `il2cpp_dump.json`；用 `-i` 指定或设环境变量 `MHWS_IL2CPP` |
| 资源导出 | 随仓库检出的 `MHWS-in-json/natives`，或用 `-n` 指定 |
| 资源换行 | 资源文件必须保持导出时的 LF 字节。报错时删除 `MHWS-in-json` 目录，再执行 `git checkout -- MHWS-in-json` |
| 研究缓存 `--index`、`--helpers`、`--inventory`、`--requests` | 从已有机器复制整个 `.agents/enemy-logic-exporter`，或按“[游戏更新后](#游戏更新后)”重新生成（需要 Ghidra） |
| 工作目录 | 默认 `.agents/enemy-logic-exporter`；可用 `-w` 或环境变量 `MHWS_SDK_WORK_DIR` 修改，但必须位于项目 `.agents` 内。缓存放在其他磁盘时，用目录联接把 `.agents` 指过去 |
| `GHIDRA_INSTALL_DIR`、`JAVA_HOME` | 只有 `decompile`、`analyze` 需要：安装 Ghidra 12.0.4 及其支持的 JDK 后设置这两个环境变量 |

以下示例中的 `python` 指上面虚拟环境中的解释器；所有命令都在项目根目录运行，并已设置 `MHWS_EXE`、`MHWS_IL2CPP`（否则加上 `-e`、`-i`）。查看任一命令的完整参数：`python -m sdk.<工具> <命令> --help`。

## 菜单界面（TUI）

`python -m sdk` 打开常用任务的菜单：环境检查、技能效果提取（全部或指定技能）、重建 `SkillDetails.xlsx`、怪物提取与玩家视图、未知条件统计、发布与构建行动逻辑网页，以及 SDK 测试。用方向键和回车选择。每个操作先打印要执行的完整命令行再执行，同样的步骤可以直接写进脚本。菜单启动时读取 `MHWS_EXE`、`MHWS_IL2CPP`；未设置时先询问 dump 出的 EXE 与 IL2CPP dump 的路径，“设置 EXE 与 il2cpp 路径”可在本次会话中修改。发布前会先确认，避免误覆盖已提交的模型。耗时的步骤（技能提取、`extract-all`、`player-view`、`publish`）会显示进度条，给出已完成数量、用时与预计剩余时间，菜单和命令行中都会显示（`sdk/progress.py`）。安装脚本会把项目根目录登记到虚拟环境中（`mhws_sdk.pth`），因此菜单可以在任意目录启动；此前建好的环境需要重新运行一次安装脚本。

```powershell
.agents/sdk-venv/Scripts/python.exe -m sdk
```

## 怪物行动逻辑 SDK（`sdk.enemy_logic_exporter`）

SDK 只读取游戏文件，不运行游戏、不注入。它从 EXE 的 x64 指令中还原每张行为表的控制流，再结合资源参数和 IL2CPP 元数据，把判断条件、动作和继续位置写成 JSON。完整研究模型保存在 `.agents/enemy-logic-exporter`，用 `publish` 精简后写入 `src/processed_data/enemy_battle_logic/models`，网页由这些模型生成。

函数地址取自 `sdk/enemy_logic_exporter/data/profile.json`，由 `resolve-symbols` 按当前 dump 出的 EXE 与 IL2CPP dump 重新生成。

### 只构建网页

不需要 SDK 依赖和游戏文件：

```powershell
python -m src.processed_data.enemy_battle_logic                     # 正式构建，输出到 output/processed_data
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
python -m src.processed_data.enemy_battle_logic --template <模型.json> --output .agents/one
```

打开输出目录下的 `enemy_battle_logic/index.html` 浏览。页面可离线使用。

### 修改代码后重新提取

`-e`、`-i` 和研究缓存参数省略时使用默认位置。全量提取约 15 分钟。

```powershell
$w = '.agents/enemy-logic-exporter/fix'
python -B -m sdk.enemy_logic_exporter extract --enemy EM0002_00_0 -o "$w/one"   # 试跑一只怪物
python -B -m sdk.enemy_logic_exporter extract-all -o "$w/s1"                     # 全部 34 只
python -B -m sdk.enemy_logic_exporter player-view -m "$w/s1" -o "$w/s1p"         # 生成玩家视图
python -B -m sdk.enemy_logic_exporter census -m "$w/s1p"                         # 含未知部分的条件，按命令与原因分组
python -B -m sdk.enemy_logic_exporter uncertainty -m "$w/s1p"                    # 玩家战斗树中输入都已知后仍无法判定的条件
python -B -m sdk.enemy_logic_exporter publish -m "$w/s1p"                        # 写入网页模型目录
python -B -m src.processed_data.enemy_battle_logic --output "$w/site"
python -B -m unittest discover -s tests/sdk -t .
```

每次改动前后都比较 `census` 的 `unknownConditions` 和 `uncertainty` 的 `total.uncertain`。`player-view` 只接受 `.agents` 中的完整模型，不接受已发布的精简模型。

### 游戏更新后

需要新的 dump 出的 EXE、对应的 IL2CPP dump、重新导出的资源，以及 Ghidra。

```powershell
python -B -m sdk.enemy_logic_exporter check-env
python -B -m sdk.enemy_logic_exporter resolve-symbols -o .agents/enemy-logic-exporter/new-profile.json   # 报告移动、变化的符号
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile .agents/enemy-logic-exporter/new-profile.json           # 先看报告
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile .agents/enemy-logic-exporter/new-profile.json --apply   # 迁移代码未变的证据
Copy-Item .agents/enemy-logic-exporter/new-profile.json sdk/enemy_logic_exporter/data/profile.json
python -B -m sdk.enemy_logic_exporter analyze -o .agents/enemy-logic-exporter/full-run/result --cache-dir .agents/enemy-logic-exporter/full-run/native
python -B -m sdk.enemy_logic_exporter requests --index .agents/enemy-logic-exporter/full-run/native/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json -o .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter recover --index .agents/enemy-logic-exporter/full-run/native/index.json --helpers .agents/enemy-logic-exporter/per-monster/helpers/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --requests .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter scheduler-slots
python -B -m sdk.enemy_logic_exporter roster --write
python -B -m sdk.enemy_logic_exporter new-monster --enemy <新怪物ID>          # 名单新增的每只怪物
```

之后按“修改代码后重新提取”跑一遍。`migrate-evidence` 列出的待复核项和 `resolve-symbols` 报告的 `changed` 项必须逐条核对原生代码。详细的核对顺序见 [SDK 维护说明](../enemy_logic_exporter/AGENTS.md)。

### 命令一览

| 命令 | 作用 | 需要 |
|---|---|---|
| `check-env` | 检查依赖、游戏文件、研究缓存和 Ghidra 设置 | — |
| `extract` / `extract-all` | 提取一只或全部怪物的完整研究模型 | EXE、dump、资源、研究缓存 |
| `player-view` | 为完整模型生成玩家视图（网页使用的条件与输入） | 完整模型 |
| `census` | 统计含未知部分的条件，按命令和原因分组 | 完整模型 |
| `uncertainty` | 统计玩家战斗树中无法判定的条件 | 带玩家视图的完整模型 |
| `publish` | 删除研究字段、共享重复值，写入 `src/processed_data/enemy_battle_logic/models` | 带玩家视图的完整模型 |
| `resolve-symbols` | 按当前 EXE 重新生成符号地址 profile（默认写入 `data/profile.json`） | EXE、dump |
| `migrate-evidence` | 迁移代码未变的证据行，其余列入人工复核 | EXE、dump、新 profile |
| `scheduler-slots` | 恢复 AI 状态与中断请求的行为表槽 | EXE、dump |
| `roster` / `new-monster` | 更新大型怪物名单；为新怪物生成入口模块 | 资源 |
| `analyze` | 全量资源与原生证据分析，生成研究缓存 | EXE、dump、资源、Ghidra |
| `requests` / `recover` | 发现动作请求；逐怪物恢复参数与命令实现 | 研究缓存、EXE |
| `manifest` / `decompile` / `verify` / `index` | 新构建研究：定位方法、反编译、核对字节、建立原生索引 | EXE、dump（`decompile` 需要 Ghidra） |

### 常见问题

- **“资源发现后行为表发生变化”**：资源文件的字节与研究缓存不一致，通常是换行被 Git 改成了 CRLF。按上表“资源换行”一项处理。
- **“原生字节不匹配”/“Native evidence mismatch”或“辅助函数特征不唯一或失效”**：EXE 的代码与 profile、研究缓存所依据的不同——游戏已更新，或传入的是原版 EXE 而不是 dump 出的 EXE。先检查 `-e`；游戏已更新时按“游戏更新后”处理。
- **“the following arguments are required: -e/--exe”或“-i/--il2cpp”**：指定 dump 出的 EXE 和 IL2CPP dump，或设环境变量 `MHWS_EXE`、`MHWS_IL2CPP`。
- **“缺少研究缓存”**：`.agents/enemy-logic-exporter` 中没有标准位置的缓存。运行 `check-env` 查看路径，复制或重新生成。
- **只能输出到 `.agents`**：研究输出必须位于项目 `.agents` 内，这是为了不把大型证据缓存提交到 Git。

## 技能效果 SDK（`sdk.skill_effect_exporter`）

游戏没有“技能 → 效果数值”的数据表：SkillData 的四个数值槽没有名称，`PlayerSkillParam` 等参数文件里的字段也不带技能 ID，二者只在原生代码中连接。这个工具先扫描 EXE，找出以技能 ID 调用技能读取方法的全部函数；再在“只装备该技能、取某一等级”的情境下，按真实指令执行这些函数（布尔与枚举参数逐一枚举），记录返回值、运行时条件以及数值来自哪个 SkillData 槽位、参数文件字段或 EXE 常量。结果写入 `src/processed_data/skill_details/data/skill_links/`（`index.json` 加按技能类别拆分的分片），构建 PROCESSED_DATA 时据此生成 `SkillDetails.xlsx`。

```powershell
python -B -m sdk.skill_effect_exporter extract -e <dump 出的 EXE> -i <il2cpp_dump.json>   # 全部技能，约 20 分钟，写入正式位置
python -B -m sdk.skill_effect_exporter extract -s HunterSkill_019 -o .agents/skill-effects/try.json   # 调试单个技能
python -m src.processed_data.skill_details                                         # 只重建 SkillDetails.xlsx
```

- `SkillDetails.xlsx` 的“技能效果”表每行是一个技能等级（`Lv.X`）的一个效果，列出游戏内的技能说明与等级说明，以及适用的武器、弹种或动作（“【武器】弹种”）。表中只保留从游戏参数读取到的数值，优先采用技能自身的 `getSkill*` 取值函数，不采用组合多个来源的函数；只在未装备技能或叠加餐点效果时出现的数值不列出。效果名称由取值函数名翻译而来（`src/processed_data/skill_details/labels.py`），最后一列保留函数名。数值为“a / b”表示数值随战斗状态变化，例如连击的命中段数。
- 表格不列出的函数地址、参数、运行时条件、数据来源、EXE 常量和未模拟的调用保留在链路 JSON 中。

- 依赖与上面的虚拟环境相同（Capstone）。
- 读取猎人装备武器类型（`HunterCharacter._HunterComp.Prepare.<WeaponBuilder>k__BackingField._EquippedWeaponType`）或弩弹种类（`app.WeaponGunDef.SHELL_TYPE`、`SHELL_PARAM_TYPE`，包括由调用返回或写入 `out` 参数的情况）的函数，按每种取值分别求值，链路 JSON 把取值记为参数“武器”“弹种”“弹药参数类型”。清单是 `sdk/skill_effect_exporter/config.py` 中的 `DIMENSIONS`。
- 有些 `cHunterSkill` 取值函数只返回等级或倍率，实际效果由调用它的函数决定，例如 `getSkillDodgeNoHitLv` 的调用方 `getDodgeNoHitTime` 给出各回避动作的无敌时间。读取的技能不超过 `MAX_ACCESSOR_SKILLS` 个的取值函数，其调用方也会求值，链路中的用法记为 `accessor`。
- 超过路径或指令上限的函数，会只保留仍能走到技能读取点的路径重新求值，其他调用按不透明调用处理；这些路径标记为 `focused`。“只追踪可能经过技能读取点的路径仍超限”表示技能可能在此处（该武器或弹种下）起作用，但数值仍不完整。
- 结果相同、条件只差一个条件及其否定的路径会合并，不影响结果的条件不再列出。每个情形最多保留 `MAX_RECORDED_PATHS` 条路径，条件少的优先，最后一行注明未列出的条数。
- 输出不记录游戏版本或摘要；游戏或 `MHWS-in-json` 更新后要重新运行 `extract`。
- 汇总多个技能的函数（如攻击力合计）依赖其他技能的计时器等运行时状态，链路 JSON 中可能记为 `too_many_paths`；同一技能的精确数值通常由 `getSkill*` 读取函数给出。
- 需要人工说明的技能写在 `sdk/skill_effect_exporter/notes.py`；版本相关的布局常量集中在 `sdk/skill_effect_exporter/config.py`。游戏更新后的检查步骤见 [技能效果 SDK 维护说明](../skill_effect_exporter/AGENTS.md)。
