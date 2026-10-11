# SDK 使用说明

[English](sdk.md) | 简体中文 | [繁體中文](sdk.zh-Hant.md)

仓库的 `sdk/` 目录中有两个命令行工具，都在项目根目录用 `python -m` 运行：

| 工具 | 用途 | 需要的外部文件 |
|---|---|---|
| `sdk.il2cpp` | 在 GitHub Release 与本地之间上传或下载 IL2CPP 元数据（`il2cpp_dump.json`） | 已登录的 GitHub CLI（`gh`） |
| `sdk.enemy_logic_exporter` | 从游戏 EXE、IL2CPP 元数据和资源导出中提取怪物行动逻辑，生成网页使用的行动图 JSON | 游戏 EXE、IL2CPP 元数据、`MHWS-in-json` 资源；部分命令还需要 Ghidra |

只想重新生成网页、不改动行动逻辑时，两个工具都不需要：网页构建器只读取仓库中已发布的模型（见“[只构建网页](#只构建网页)”）。

## IL2CPP 数据工具（`sdk.il2cpp`）

IL2CPP 元数据约 1.6 GB，不进入 Git，而是以压缩包形式保存在仓库的 `build-data` Release 中。自动构建和本地行动逻辑提取都从这里获取。

### 下载

```powershell
gh auth login                      # 首次使用时登录
python -m sdk.il2cpp download
```

- 默认保存到 `src/data/il2cpp_dump.json`；用 `--output <路径>` 指定其他位置。
- 先下载 `il2cpp_dump.json.gz` 及其 `.sha256` 校验文件，校验通过后再解压替换目标文件。任何一步失败都保留原有文件。
- 临时文件在 `.agents/il2cpp`（可用 `--work-dir` 修改）。

### 上传（维护者）

游戏更新后，用新版本的 REFramework dump 替换 Release 中的数据：

```powershell
python -m sdk.il2cpp upload --dump "D:/path/il2cpp_dump.json" --dry-run   # 只压缩并计算校验值
python -m sdk.il2cpp upload --dump "D:/path/il2cpp_dump.json"
```

- 上传覆盖同名附件；`build-data` 不会被设为最新正式 Release。
- `--compresslevel 1-9` 控制 gzip 压缩级别（默认 9）。`--release-title`、`--release-notes` 修改 Release 的标题和说明。

### 通用参数

| 参数 | 说明 |
|---|---|
| `--repo owner/name` | 目标仓库；默认依次取环境变量 `GITHUB_REPOSITORY`、`origin` 远端和 `gh repo view` |
| `--tag` | Release 标签，默认 `build-data` |
| `--asset` | 压缩包附件名，默认 `<dump 文件名>.gz` |

## 怪物行动逻辑 SDK（`sdk.enemy_logic_exporter`）

SDK 只读取游戏文件，不运行游戏、不注入。它从 EXE 的 x64 指令中还原每张行为表的控制流，再结合资源参数和 IL2CPP 元数据，把判断条件、动作和继续位置写成 JSON。完整研究模型保存在 `.agents/enemy-logic-exporter`，用 `publish` 精简后写入 `src/processed_data/enemy_battle_logic/models`，网页由这些模型生成。

当前模型对应游戏版本 **1.42.0.2**（`sdk/enemy_logic_exporter/data/profiles/`）。EXE 或元数据与该版本不符时，提取命令会拒绝运行。

### 搭建环境（Windows）

1. 安装 Python 3.13（勾选 `py` 启动器）与 Git，克隆仓库。
2. 在项目根目录运行安装脚本。它在 `.agents/sdk-venv` 建虚拟环境，安装固定版本的依赖（Capstone、PyGhidra），最后运行环境检查：

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
| 游戏 EXE | 默认在所有 Steam 库中查找；装在别处时设环境变量 `MHWS_EXE`，或给命令加 `--exe` |
| IL2CPP dump | `python -m sdk.il2cpp download`，或用 `--metadata` 指定 |
| 资源导出 | 随仓库检出的 `MHWS-in-json/natives`，或用 `--natives` 指定 |
| 资源换行 | 资源文件必须保持导出时的 LF 字节。报错时删除 `MHWS-in-json` 目录，再执行 `git checkout -- MHWS-in-json` |
| 研究缓存 `--index`、`--helpers`、`--inventory`、`--requests` | 从已有机器复制整个 `.agents/enemy-logic-exporter`，或按“[游戏更新后](#游戏更新后)”重新生成（需要 Ghidra） |
| 工作目录 | 默认 `.agents/enemy-logic-exporter`；可用 `--work-dir` 或环境变量 `MHWS_SDK_WORK_DIR` 修改，但必须位于项目 `.agents` 内。缓存放在其他磁盘时，用目录联接把 `.agents` 指过去 |
| `GHIDRA_INSTALL_DIR`、`JAVA_HOME` | 只有 `decompile`、`analyze` 需要：安装 Ghidra 12.0.4 及其支持的 JDK 后设置这两个环境变量 |

以下示例中的 `python` 指上面虚拟环境中的解释器；所有命令都在项目根目录运行。查看任一命令的完整参数：`python -m sdk.enemy_logic_exporter <命令> --help`。

### 只构建网页

不需要 SDK 依赖和游戏文件：

```powershell
python -m src.processed_data.enemy_battle_logic                     # 正式构建，输出到 output/processed_data
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
python -m src.processed_data.enemy_battle_logic --template <模型.json> --output .agents/one
```

打开输出目录下的 `enemy_battle_logic/index.html` 浏览。页面可离线使用。

### 修改代码后重新提取

`--exe` 和研究缓存参数省略时使用默认位置。全量提取约 15 分钟。

```powershell
$w = '.agents/enemy-logic-exporter/fix'
python -B -m sdk.enemy_logic_exporter extract --enemy EM0002_00_0 --output "$w/one"   # 试跑一只怪物
python -B -m sdk.enemy_logic_exporter extract-all --output "$w/s1"                     # 全部 34 只
python -B -m sdk.enemy_logic_exporter player-view --models "$w/s1" --output "$w/s1p"  # 生成玩家视图
python -B -m sdk.enemy_logic_exporter census --models "$w/s1p"                         # 含未知部分的条件，按命令与原因分组
python -B -m sdk.enemy_logic_exporter uncertainty --models "$w/s1p"                    # 玩家战斗树中输入都已知后仍无法判定的条件
python -B -m sdk.enemy_logic_exporter publish --models "$w/s1p"                        # 写入网页模型目录
python -B -m src.processed_data.enemy_battle_logic --output "$w/site"
python -B -m unittest discover -s tests/sdk -t .
```

每次改动前后都比较 `census` 的 `unknownConditions` 和 `uncertainty` 的 `total.uncertain`。`player-view` 只接受 `.agents` 中的完整模型，不接受已发布的精简模型。

### 游戏更新后

需要新版本的 EXE、IL2CPP dump（用 `sdk.il2cpp upload` 上传后，其他机器即可下载）和重新导出的资源，以及 Ghidra。

```powershell
python -B -m sdk.enemy_logic_exporter check-env --verify
python -B -m sdk.enemy_logic_exporter resolve-symbols --version <新版本>       # 生成 data/profiles/<新版本>.json
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<新版本>.json           # 先看报告
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<新版本>.json --apply   # 迁移字节未变的证据
python -B -m sdk.enemy_logic_exporter analyze --version <新版本> --output .agents/enemy-logic-exporter/full-run/result --cache-dir .agents/enemy-logic-exporter/full-run/native
python -B -m sdk.enemy_logic_exporter requests --index .agents/enemy-logic-exporter/full-run/native/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --output .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter recover --index .agents/enemy-logic-exporter/full-run/native/index.json --helpers .agents/enemy-logic-exporter/per-monster/helpers/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --requests .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter scheduler-slots
python -B -m sdk.enemy_logic_exporter roster --write
python -B -m sdk.enemy_logic_exporter new-monster --enemy <新怪物ID>          # 名单新增的每只怪物
```

之后把 `sdk/enemy_logic_exporter/shared/config.py` 中的 `ACTIVE_GAME_VERSION` 改为新版本，再按“修改代码后重新提取”跑一遍。`migrate-evidence` 列出的待复核项和 `resolve-symbols` 报告的 `changed` 项必须逐条核对原生代码，不能只替换版本号或摘要。详细的核对顺序见 [SDK 维护说明](../sdk/enemy_logic_exporter/AGENTS.md)。

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
- **“缺少研究缓存”**：`.agents/enemy-logic-exporter` 中没有标准位置的缓存。运行 `check-env` 查看路径，复制或重新生成。
- **只能输出到 `.agents`**：研究输出必须位于项目 `.agents` 内，这是为了不把大型证据缓存提交到 Git。
