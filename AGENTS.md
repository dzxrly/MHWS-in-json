# MHWS 数据维护约定

> MHWS 指《怪物猎人 荒野》。本仓库的 SDK 是 `sdk/` 下独立运行的离线提取工具。它读取游戏内存导出的可执行文件（EXE）以及同一构建的 `il2cpp_dump.json`。后者记录类型、字段布局、方法签名及地址。GUID 是游戏资源用来引用具体记录的全局唯一标识符。下文路径均相对于仓库根目录。

## 三个目录如何交接

- `sdk/` 从游戏文件还原资源表中缺少的关系，输出静态 JSON。武器动作提取器写入 `MHWS-in-json/ActionMap.json`，技能效果和怪物行动提取器分别发布各自的静态数据。更改具体提取器时，先阅读该提取器目录内的 `AGENTS.md`。[SDK 操作说明](sdk/docs/README.zh-Hans.md)
- `src/` 读取 `MHWS-in-json/natives/` 中的原始资源表、`MHWS-in-json/Enums_Internal.json` 和已发布的静态数据。`src/database/` 生成分语言数据库工作簿，`src/processed_data/` 生成加工后的数据，`src/site_data/` 生成网站所需的简体中文 JSON。多个 `src` 导出器需要同一关系时，复用已有的资源读取或数据库逻辑。
- `web/` 是独立的 Vue 和 TypeScript 应用。前端从 `/data/` 读取 JSON。Vite 开发时提供 `src/site_data/data/` 文件，构建时将数据复制到站点输出。预览其他静态数据目录可设置 `MHWS_SITE_DATA`。[Vite 配置](web/vite.config.ts)
- `sdk/`、`src/` 和 `web/` 之间只通过静态数据文件交互。各自的入口独立运行，不跨目录导入模块、执行另一目录的命令或在构建时隐式重新提取数据。变更交接格式时，同步更新负责写出与读取这些字段的实现和校验。

## 文件放在哪里

先确定文件由谁维护、谁读取，再选择目录。同一功能的提取规则、已审核的静态数据、工作簿和网页可以分属不同目录。

| 需要增加或修改的内容 | 位置和组织方式 |
| --- | --- |
| 游戏资源和枚举 | 转换好的游戏资源放在 `MHWS-in-json/natives/`，保留游戏路径、文件名大小写和资源后缀，例如 `STM/GameDesign/Common/Item/itemData.user.3.json`。枚举表放在 `MHWS-in-json/Enums_Internal.json`。整个 `MHWS-in-json/` 会随源数据压缩包发布。 |
| 武器动作与命中判定的关系 | 在 `sdk/action_map_exporter/` 修改提取逻辑。映射的格式和原生规则在该目录的 `data/`，正式产物是 `MHWS-in-json/ActionMap.json`。源数据读取、精确匹配和消费端校验在 `src/shared/action_values/`。[武器映射维护说明](sdk/action_map_exporter/AGENTS.md) |
| 怪物行动逻辑 | `sdk/enemy_logic_exporter/monster/` 按完整怪物 ID 存放专用规则，`shared/` 存放提取器内共用的资源解析、原生分析和模型构建逻辑，`data/` 存放规则与证据 JSON。正式模型按怪物交付给 `src/processed_data/enemy_battle_logic/models/`。[怪物提取器维护说明](sdk/enemy_logic_exporter/AGENTS.md) |
| 技能效果及来源 | `sdk/skill_effect_exporter/skills/hunterskill_<编号>.py` 保存单个技能经核实的含义、条件与说明，`shared/` 存放提取器内共用的原生分析、求值和命令流程。提取结果按类别写入 `src/processed_data/skill_details/data/skill_links/`，随目录内的 `index.json` 一起交付。[技能提取器维护说明](sdk/skill_effect_exporter/AGENTS.md) |
| 分语言数据库工作簿 | `src/database/` 按物品、装备、技能、任务、动作值等主题分包。普通表在所属主题的 `specs.py` 声明工作表与源文件，`build.py` 准备行数据。有专用版式的工作簿在该主题的 `excel.py` 处理样式。新增工作簿时在 `src/database/exporter.py` 接入导出并更新 `WORKBOOK_NAMES`。[数据库入口](src/database/exporter.py) |
| 加工后的工作簿或 JSON | `src/processed_data/` 按用途分包，例如护石池在 `amulet_pools/`，弩枪在 `bowguns/`，技能效果在 `skill_details/`。新的发布文件从所属模块的导出函数接入 `src/processed_data/exporter.py`，并加入 `OUTPUT_NAMES`。[加工数据入口](src/processed_data/exporter.py) |
| 多个 Python 导出器用到的逻辑 | `src/shared/source/` 读取并规范化游戏表，`src/shared/text/` 解析文本引用并按语言取值，`src/shared/excel/` 放通用单元格和工作簿写出。只服务任务的难度表关联留在 `src/database/missions/difficulty.py`，同属 `src/` 的网页数据导出器可以复用。 |
| 导出顺序、校验、打包和落盘 | `src/pipeline/exporter.py` 编排数据库、加工数据和压缩包生成，`validation.py` 校验产物集合并写出清单，`package.py` 管理归档，`publish.py` 在校验通过后替换本地 `output/`。根 `main.py` 是这条流程的命令入口。[导出流程](src/pipeline/exporter.py) |
| 网页专用数据和入口 | `src/site_data/` 下的 Python 模块生成前端实际读取的 JSON，正式输出放在 `src/site_data/data/<模块>/` 并随代码提交。新模块需在 `src/site_data/__init__.py` 接入导出调用和文件清单。任务与武器分别读取 `missions/quests.json` 与 `weapon_actions/actions.json`。[网站数据清单](src/site_data/__init__.py) |
| 页面、样式和视觉资源 | 单个栏目放在 `web/src/sites/<模块>/`，包含 `.vue` 页面、该栏目的 TypeScript 数据类型、交互和样式。在模块 `index.ts` 定义标题和路由，在 `web/src/sites.ts` 注册。首页卡片和路由表都读取这份注册表。全站页面放 `pages/`，共用组件放 `components/`，主题与布局放 `styles/`，共用数据加载和交互逻辑放 `composables/`（均在 `web/src/`）。随模块导入的字体等资源放 `web/src/assets/`，按固定 URL 提供的图标和雪碧图放 `web/public/`。[栏目注册表](web/src/sites.ts) |
| 测试、用户文档和自动发布 | 测试按职责放在 `tests/database/`、`tests/processed_data/`、`tests/site_data/`、`tests/sdk/`、`tests/shared/`、`tests/pipeline/` 或 `tests/release/`。多个测试使用的小型输入放 `tests/fixtures/`。用户用法放根 `README.md` 和 `docs/` 下的简繁中文说明，SDK 的命令用法放 `sdk/README.md` 和 `sdk/docs/`。发布工作流在 `.github/workflows/`，发布说明脚本在 `.github/scripts/`。 |

正式输出和开发过程文件各有位置。`output/<语言代码>/` 包含该语言的工作簿，`output/processed_data/` 包含加工后的文件，压缩包和 `manifest.json` 位于 `output/` 顶层。前端构建结果在 `web/dist/`。需要修正生成结果时，修改生成端并重新生成。一般临时调查和截图用 `.agents/`。已有导出事务、SDK 缓存及各工具约定的试运行目录继续使用 `.tmp/`。本机 EXE、完整 IL2CPP 转储、依赖安装目录、临时诊断文件与本地构建目录不属于提交内容。

## 配置的作用与优先级

根 [config.py](config.py) 供数据库、加工数据与网站数据的 Python 导出器读取。按设置影响的范围选择修改位置。

| 设置 | 用途 |
| --- | --- |
| `BASE_DIR`、`JSON_ROOT`、`NATIVES_DIR`、`ENUMS_PATH`、`OUTPUT_DIR` | 从仓库实际位置派生资源根目录、枚举路径和本地发布输出目录。仅需试读另一份解包数据时，网站数据命令可用 `--natives` 指定资源根目录。 |
| `ACTION_MAP_PATH`、`MHWS_ACTION_MAP_PATH` | 默认读取 `MHWS-in-json/ActionMap.json`。可在启动 Python 进程前设置环境变量 `MHWS_ACTION_MAP_PATH`，使工作簿和网站武器表读取指定映射，用于核对新生成的数据。 |
| `LANGUAGES`、`LANGUAGE_IDS`、`ZH_HANS_LANGUAGE_ID`、`JAPANESE_LANGUAGE_ID` | `LANGUAGES` 对应游戏数字语言 ID、语言代码与名称。`LANGUAGE_IDS` 默认按资源实际提供的语言导出数据库，设置非空列表可缩小范围。简体中文 ID 用于网站等简中产物，日语 ID 用于动作值工作簿的日文名称参考列。 |
| `VERSION`、`RELEASE_VERSION`、各压缩包名前缀 | 根导出入口先取 `VERSION`，再取环境变量 `RELEASE_VERSION`。二者均为空时，用 UTC 日期时间加提交号前缀或 `local` 构造发布包版本。它决定文件名与清单中的版本。游戏二进制的构建号需从本次游戏文件核实。 |
| `SUPPORT_FILES`、`WEAPON_TYPES`、`WEAPON_FILE_STEMS`、工作簿名和列宽 | 分别描述常用资源的相对路径、武器集合及源文件大小写，以及导出文件名与展示宽度。某张工作表的字段、翻译规则和计算留在所属业务模块。 |
| `MISSION_HEALTH_KING_WHEN_NONE_IDS`、`MISSION_HEALTH_NO_AUTO_HARD_IDS` | 记录由游戏原生分支确认、任务资源表本身缺少的形态和难度例外。更新这些常量时同时核对对应分支、枚举身份以及使用它们的任务输出。 |

- **SDK 配置**跟随提取器维护。怪物共用的原生布局和符号定位声明在 `sdk/enemy_logic_exporter/shared/config.py`。技能的类型、字段与已复核游戏版本在 `sdk/skill_effect_exporter/config.py`。武器映射的原生规则和输出格式在 `sdk/action_map_exporter/data/`。根 `requirements.txt` 是导出依赖，`sdk/requirements.txt` 和 `sdk/setup_env.ps1` 用于 SDK 工具环境。[SDK 安装与参数](sdk/docs/README.zh-Hans.md)
- **前端配置**由 `web/` 自己管理。`package.json` 定义依赖和开发、类型检查、构建、预览命令，`package-lock.json` 锁定解析结果，`tsconfig.json` 定义 TypeScript 检查范围。`vite.config.ts` 服务或复制网站 JSON，并注入页脚使用的构建日期与提交号。`MHWS_SITE_DATA` 可指定另一个含 `site.json` 的数据目录。使用绝对路径即可与启动命令的工作目录无关。

## 玩家页面的约定

- 网站沿用主站的 Material 3 Expressive 配色、动效和交互。新页面优先复用 `web/src/components/` 的页头、页脚、卡片和选择器，以及 `web/src/styles/` 的主题变量。页面脚本和数据类型使用 TypeScript。检查深浅主题和窄屏下有变化的交互。
- 任务以游戏内分类为入口，“全部任务”按星级排序。任务卡片保留名称、星级、目标图标和历战形态边色，详情有独立 URL，目标数据、报酬与任务说明在同页阅读。多目标任务按各自的布局取值。血量与报酬档位只展示数值和概率，省去进度条。倍率明细应与当前人数、怪物状态、攻击档位、招式和阶段一致。
- 全站小数在最终展示时四舍五入保留三位，例如 `1.38996` 显示为 `1.390`。整数照常显示。计算、筛选、档位合并和范围比较使用原始精度。
- 武器动作值沿用工作簿的武器分组、动作顺序和判定行。一个动作可对应多个命中判定，同一判定也可被多个动作引用。保留这些关系，用中文说明适用条件，数值和长文本分列展示。玩家页面与技术原始数据面向不同读者。

## 游戏更新后的核对方法

1. 确认资源表、枚举、内存导出的 EXE 和 IL2CPP 数据属于同一游戏构建。`config.py` 指定资源位置和发布包版本。发布标签本身无法确定外部 EXE 与资源是否配套。只涉及单个模块时，优先核对它消费的资源与原生代码。
2. 从当前导出表的类型、主键和外键重新跟随引用。GUID 的取值、资源路径、数组内容及其顺序都可能变化。按字段实际含义区分 GUID、固定 ID 和数组下标。保留已有的空引用语义，出现必需引用缺失或匹配多个目标时指出源表、字段和键值。显示名称、翻译和相似文件名不能单独证明关联。
3. 例如，任务数据库在存在 `MsData` 时，先由 `_QuestUseIndex` 选取怪物布局组，按目标匹配布局，再用 `_DifficultyRankId` 找到难度记录，沿 `_MultiTableId` 找到人数倍率表。同一星级、同一怪物可使用不同配置，多怪任务还需分别匹配每个目标。沿用读取器对独立任务布局的处理。[任务难度读取器](src/database/missions/difficulty.py)
4. 原生函数的地址、字段偏移、方法名及其数字后缀都可能随构建改变。先用新版 IL2CPP 的声明类型、方法签名与字段布局定位候选，再用同版 EXE 复核调用者、被调函数、分支条件、取表方式及最终使用位置。仅有同名函数或相同地址时不能沿用旧结论。新增依赖原生行为的公式或特例时，在对应提取规则或代码旁记录核对所用游戏版本和可重新定位的方法、字段及条件。
5. 血量、速度、伤害等总值按游戏实际取值与运算顺序处理。核对任务难度与目标形态选用哪张表、人数与怪物状态何时生效、招式有无覆盖值，以及随机抽取、取整或限幅发生的位置。已经由上游选表体现的星级或历战形态不能再乘一次。特定动作、弹体或部位才触发的修正应保留其适用条件。
6. 使用实机录像交叉核对速度时，匹配版本、任务、形态、状态和招式。全身招式基准、动画片段的局部变速和整段动作的实测时长是不同的量。记录可重看的时间点以及画面显示的精度。

## 生成与验证

以下命令在仓库根目录运行，按本次修改影响的产物选择。

1. 游戏更新涉及原生关系时，先用对应 SDK 模块重新提取并检查差异。`python -m sdk` 可查看入口，武器动作映射的直接命令为 `python -m sdk.action_map_exporter extract`。其他提取器的检查、提取和发布命令见其目录约定。
2. 上游数据就绪后，数据库工作簿和发布包使用 `python main.py` 生成。网站数据使用独立入口 `python -m src.site_data` 生成到 `src/site_data/data/`。这两个入口按各自产物运行。网站 JSON 的变更应同步生成，修正在生成端完成。
3. 复核本次变更涉及的数值与对应源记录。任务数据可选取上下位、高星、历战王或连续狩猎中受影响的实例，并对照同一目标在不同人数、状态下的结果。`python -B -m unittest tests.site_data.test_committed_data` 比较已提交网站 JSON 与重新生成的内容，目录边界改动使用 `python -B -m unittest tests.sdk.test_package_boundary` 检查。
4. 网站改动使用 `npm --prefix web run build` 执行 TypeScript 检查和 Vite 构建。首次准备依赖使用 `npm --prefix web ci`。要核对玩家实际看到的效果，运行 `npm --prefix web run dev` 并打开受影响的页面或任务详情直链。

例如，增加“任务部位耐久”的展示时，从任务布局跟到难度表，先检查 `src/database/missions/` 已经提供了哪些字段，再在 `src/site_data/mission_rates.py` 组装当前目标的倍率并生成 `missions/quests.json`。页面的数据类型、倍率明细和渲染都在 `web/src/sites/missions/`。如果只调整概率卡片的样式或小数显示，改前端并预览即可。如果改了倍率公式，同时用已知任务核对原始乘数、未舍入总值和最终显示。
