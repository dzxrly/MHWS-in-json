# SDK 使用说明

[English](README.md) | 简体中文 | [繁體中文](README.zh-Hant.md)

仓库的 `sdk/` 目录中有两个离线命令行工具，都在项目根目录用 `python -m` 运行：

| 工具 | 用途 | 需要的外部文件 |
|---|---|---|
| `sdk.enemy_logic_exporter` | 从游戏 EXE、IL2CPP 元数据和资源导出中提取怪物行动逻辑，生成网页使用的行动图 JSON | 游戏 EXE、IL2CPP 元数据、`MHWS-in-json` 资源；部分命令还需要 Ghidra |
| `sdk.skill_effect_exporter` | 找出原生代码中使用每个技能的函数，按技能等级求值，生成技能效果链路 JSON（`SkillDetails.xlsx` 的数据来源） | 游戏 EXE、IL2CPP 元数据、`MHWS-in-json` 资源 |

IL2CPP 元数据是 REFramework 导出的 `il2cpp_dump.json`，必须与 EXE 同一游戏版本。它和 EXE 一样由使用者提供，仓库和 Release 都不保存副本。两个工具查找它的顺序相同：`-i/--il2cpp` 参数、环境变量 `MHWS_IL2CPP`、EXE 同目录的 `il2cpp_dump.json`。EXE 与 dump 的 SHA-256 只登记在 `sdk/game_versions.json`；提交的数据与模型只记录游戏版本号。

只想重新生成网页或表格、不改动提取结果时，两个工具都不需要：构建器只读取仓库中已提交的 JSON（见“[只构建网页](#只构建网页)”）。

## 通用参数

| 参数 | 说明 |
|---|---|
| `-e`, `--exe` | 游戏 EXE；默认取环境变量 `MHWS_EXE`，其次在所有 Steam 库中查找 |
| `-i`, `--il2cpp` | 与 EXE 同版本的 `il2cpp_dump.json`；默认取环境变量 `MHWS_IL2CPP`，其次取 EXE 同目录的文件 |
| `-n`, `--natives` | 解包 JSON 的 `natives` 目录，默认 `MHWS-in-json/natives` |
| `-o`, `--output` | 输出位置 |
| `-m`, `--models` | 研究模型目录（`sdk.enemy_logic_exporter`） |
| `-w`, `--work-dir` | 研究缓存目录，写在子命令前（`sdk.enemy_logic_exporter`） |

## 搭建环境（Windows）

1. 安装 Python 3.13（勾选 `py` 启动器）与 Git，克隆仓库。
2. 在项目根目录运行安装脚本。它在 `.agents/sdk-venv` 建虚拟环境，安装固定版本的依赖（Capstone、PyGhidra、questionary），最后运行环境检查：

   ```powershell
   powershell -ExecutionPolicy Bypass -File sdk/enemy_logic_exporter/setup_env.ps1
   ```

3. 按检查结果补齐缺失项，然后再检查一次：

   ```powershell
   .agents/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env
   .agents/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env --verify   # 同时核对 EXE 与 dump 的版本摘要（较慢）
   ```

| 检查项 | 怎样补齐 |
|---|---|
| 游戏 EXE | 默认在所有 Steam 库中查找；装在别处时设环境变量 `MHWS_EXE`，或给命令加 `-e` |
| IL2CPP dump | 用 REFramework 导出与 EXE 同版本的 `il2cpp_dump.json`，放在 EXE 同目录；放在别处时设环境变量 `MHWS_IL2CPP` 或用 `-i` 指定 |
| 资源导出 | 随仓库检出的 `MHWS-in-json/natives`，或用 `-n` 指定 |
| 资源换行 | 资源文件必须保持导出时的 LF 字节。报错时删除 `MHWS-in-json` 目录，再执行 `git checkout -- MHWS-in-json` |
| 研究缓存 `--index`、`--helpers`、`--inventory`、`--requests` | 从已有机器复制整个 `.agents/enemy-logic-exporter`，或按“[游戏更新后](#游戏更新后)”重新生成（需要 Ghidra） |
| 工作目录 | 默认 `.agents/enemy-logic-exporter`；可用 `-w` 或环境变量 `MHWS_SDK_WORK_DIR` 修改，但必须位于项目 `.agents` 内。缓存放在其他磁盘时，用目录联接把 `.agents` 指过去 |
| `GHIDRA_INSTALL_DIR`、`JAVA_HOME` | 只有 `decompile`、`analyze` 需要：安装 Ghidra 12.0.4 及其支持的 JDK 后设置这两个环境变量 |

以下示例中的 `python` 指上面虚拟环境中的解释器；所有命令都在项目根目录运行。查看任一命令的完整参数：`python -m sdk.<工具> <命令> --help`。

## 菜单界面（TUI）

`python -m sdk` 打开常用任务的菜单：环境检查、技能效果提取（全部或指定技能）、重建 `SkillDetails.xlsx`、怪物提取与玩家视图、未知条件统计、发布与构建行动逻辑网页，以及 SDK 测试。用方向键和回车选择。每个操作先打印要执行的完整命令行再执行，同样的步骤可以直接写进脚本。EXE 与 IL2CPP dump 的查找方式和命令行相同，“设置 EXE 与 il2cpp 路径”可在本次会话中修改。发布前会先确认，避免误覆盖已提交的模型。

```powershell
.agents/sdk-venv/Scripts/python.exe -m sdk
```

## 怪物行动逻辑 SDK（`sdk.enemy_logic_exporter`）

SDK 只读取游戏文件，不运行游戏、不注入。它从 EXE 的 x64 指令中还原每张行为表的控制流，再结合资源参数和 IL2CPP 元数据，把判断条件、动作和继续位置写成 JSON。完整研究模型保存在 `.agents/enemy-logic-exporter`，用 `publish` 精简后写入 `src/processed_data/enemy_battle_logic/models`，网页由这些模型生成。

当前模型对应游戏版本 **1.42.0.2**（`sdk/enemy_logic_exporter/data/profiles/`）。EXE 与 IL2CPP dump 必须与 `sdk/game_versions.json` 中该版本登记的摘要一致，否则提取命令会拒绝运行。

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

需要新版本的 EXE、与之同版本的 IL2CPP dump、重新导出的资源，以及 Ghidra。

```powershell
python -B -m sdk.enemy_logic_exporter check-env --verify
python -B -m sdk.enemy_logic_exporter resolve-symbols --version <新版本>       # 生成 data/profiles/<新版本>.json
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<新版本>.json           # 先看报告
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<新版本>.json --apply   # 迁移字节未变的证据
python -B -m sdk.enemy_logic_exporter analyze --version <新版本> -o .agents/enemy-logic-exporter/full-run/result --cache-dir .agents/enemy-logic-exporter/full-run/native
python -B -m sdk.enemy_logic_exporter requests --index .agents/enemy-logic-exporter/full-run/native/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json -o .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter recover --index .agents/enemy-logic-exporter/full-run/native/index.json --helpers .agents/enemy-logic-exporter/per-monster/helpers/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --requests .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter scheduler-slots
python -B -m sdk.enemy_logic_exporter roster --write
python -B -m sdk.enemy_logic_exporter new-monster --enemy <新怪物ID>          # 名单新增的每只怪物
```

之后把 `sdk/enemy_logic_exporter/shared/config.py` 中的 `ACTIVE_GAME_VERSION` 改为新版本，再按“修改代码后重新提取”跑一遍。`migrate-evidence` 列出的待复核项和 `resolve-symbols` 报告的 `changed` 项必须逐条核对原生代码，不能只替换版本号或摘要。游戏版本不变、只换用另一份 IL2CPP dump 时的步骤，以及详细的核对顺序，见 [SDK 维护说明](enemy_logic_exporter/AGENTS.md)。

### 命令一览

| 命令 | 作用 | 需要 |
|---|---|---|
| `check-env` | 检查依赖、游戏文件、研究缓存和 Ghidra 设置 | — |
| `extract` / `extract-all` | 提取一只或全部怪物的完整研究模型 | EXE、dump、资源、研究缓存 |
| `player-view` | 为完整模型生成玩家视图（网页使用的条件与输入） | 完整模型 |
| `census` | 统计含未知部分的条件，按命令和原因分组 | 完整模型 |
| `uncertainty` | 统计玩家战斗树中无法判定的条件 | 带玩家视图的完整模型 |
| `publish` | 删除研究字段、共享重复值，写入 `src/processed_data/enemy_battle_logic/models` | 带玩家视图的完整模型 |
| `resolve-symbols` | 为新版本生成符号地址 profile | EXE、dump |
| `migrate-evidence` | 迁移字节未变的证据行，其余列入人工复核 | EXE、dump、新 profile |
| `scheduler-slots` | 恢复 AI 状态与中断请求的行为表槽 | EXE、dump |
| `roster` / `new-monster` | 更新大型怪物名单；为新怪物生成入口模块 | 资源 |
| `analyze` | 全量资源与原生证据分析，生成研究缓存 | EXE、dump、资源、Ghidra |
| `requests` / `recover` | 发现动作请求；逐怪物恢复参数与命令实现 | 研究缓存、EXE |
| `manifest` / `decompile` / `verify` / `index` | 新版本研究：定位方法、反编译、核对字节、建立原生索引 | EXE、dump（`decompile` 需要 Ghidra） |

### 常见问题

- **“资源发现后行为表发生变化”**：资源文件的字节与研究缓存不一致，通常是换行被 Git 改成了 CRLF。按上表“资源换行”一项处理。
- **“原生配方的 EXE 来源变化”或版本不符**：EXE 或 dump 不是 profile 记录的版本。确认文件来源；游戏已更新时按“游戏更新后”处理。
- **“缺少 il2cpp dump”**：没有找到 `il2cpp_dump.json`。放到 EXE 同目录，或用 `-i`、`MHWS_IL2CPP` 指定。
- **“缺少研究缓存”**：`.agents/enemy-logic-exporter` 中没有标准位置的缓存。运行 `check-env` 查看路径，复制或重新生成。
- **只能输出到 `.agents`**：研究输出必须位于项目 `.agents` 内，这是为了不把大型证据缓存提交到 Git。

## 技能效果 SDK（`sdk.skill_effect_exporter`）

游戏没有“技能 → 效果数值”的数据表：SkillData 的四个数值槽没有名称，`PlayerSkillParam` 等参数文件里的字段也不带技能 ID，二者只在原生代码中连接。这个工具先扫描 EXE，找出以技能 ID 调用技能读取方法的全部函数；再在“只装备该技能、取某一等级”的情境下，按真实指令执行这些函数（布尔与枚举参数逐一枚举），记录返回值、运行时条件以及数值来自哪个 SkillData 槽位、参数文件字段或 EXE 常量。结果写入 `src/processed_data/skill_details/data/skill_links/`（`index.json` 加按技能类别拆分的分片），构建 PROCESSED_DATA 时与 SkillCommonData、SkillData 合并成 `SkillDetails.xlsx`。

```powershell
python -B -m sdk.skill_effect_exporter extract                                     # 全部技能，约 20 分钟，写入正式位置
python -B -m sdk.skill_effect_exporter extract -e <EXE> -i <il2cpp_dump.json>      # 指定输入
python -B -m sdk.skill_effect_exporter extract -s HunterSkill_019 -o .agents/skill-effects/try.json   # 调试单个技能
python -m src.processed_data.skill_details                                         # 只重建 SkillDetails.xlsx
```

- 依赖与上面的虚拟环境相同（Capstone）。
- 读取猎人装备武器类型（`HunterCharacter._HunterComp.Prepare.<WeaponBuilder>k__BackingField._EquippedWeaponType`）或弩弹种类（`app.WeaponGunDef.SHELL_TYPE`、`SHELL_PARAM_TYPE`，包括由调用返回或写入 `out` 参数的情况）的函数，按每种取值分别求值，表格把取值列为参数“武器”“弹种”“弹药参数类型”。清单是 `sdk/skill_effect_exporter/config.py` 中的 `DIMENSIONS`。
- 有些 `cHunterSkill` 取值函数只返回等级或倍率，实际效果由调用它的函数决定，例如 `getSkillDodgeNoHitLv` 的调用方 `getDodgeNoHitTime` 给出各回避动作的无敌时间。读取的技能不超过 `MAX_ACCESSOR_SKILLS` 个的取值函数，其调用方也会求值，“用法”列写作“调用技能取值函数 …”。
- 超过路径或指令上限的函数，会只保留仍能走到技能读取点的路径重新求值，其他调用按不透明调用处理；这些行在“求值范围”列中标出。“只追踪可能经过技能读取点的路径仍超限”表示技能可能在此处（该武器或弹种下）起作用，但数值仍不完整。
- 结果相同、条件只差一个条件及其否定的路径会合并，不影响结果的条件不再列出。每个情形最多保留 `MAX_RECORDED_PATHS` 条路径，条件少的优先，最后一行注明未列出的条数。
- 输出只记录游戏版本，不保存解包文件摘要；更新 `MHWS-in-json` 后要重新运行 `extract`。
- 汇总多个技能的函数（如攻击力合计）依赖其他技能的计时器等运行时状态，表格中可能显示“分支过多，未完整求值”；同一技能的精确数值通常由 `getSkill*` 读取函数给出。
- 需要人工说明的技能写在 `sdk/skill_effect_exporter/notes.py`；版本相关的布局常量集中在 `sdk/skill_effect_exporter/config.py`。游戏更新后的检查步骤见 [技能效果 SDK 维护说明](skill_effect_exporter/AGENTS.md)。
