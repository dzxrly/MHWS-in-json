# MHWS 数据维护约定

> MHWS 指《怪物猎人 荒野》。SDK 指本仓库离线运行的游戏数据提取工具。dump EXE 是从游戏进程内存导出的可执行文件，IL2CPP 元数据指同一构建的 `il2cpp_dump.json`，记录类型、字段布局、方法签名和地址。GUID 是资源间引用记录的全局唯一标识符，EM 编号标识怪物及其变种。下文仓库路径均相对于根目录。

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
| 怪物行动逻辑 | 每只大型怪物及每个独立变种各用一个 `sdk/enemy_logic_exporter/monster/<完整EM编号小写>.py`，训练靶排除。该怪物的阶段、条件、字段和例外写在本模块。共用原生布局归 `shared/config.py`，共用解析和模型构建归 `shared/`，规则与证据 JSON 归 `data/`。正式模型按怪物交付给 `src/processed_data/enemy_battle_logic/models/`。[怪物提取器维护说明](sdk/enemy_logic_exporter/AGENTS.md) |
| 技能效果及来源 | 每个技能一个 `sdk/skill_effect_exporter/skills/hunterskill_<编号>.py`，包含该技能专用的调用链追踪、难以自动定位的字段、常量、条件和效果说明。共用求值、追踪和命令流程在 `shared/`，所有技能通用的说明在 `notes.py`。结果按类别写入 `src/processed_data/skill_details/data/skill_links/`，与 `index.json` 一起交付。[技能提取器维护说明](sdk/skill_effect_exporter/AGENTS.md) |
| 分语言数据库工作簿 | `src/database/` 按物品、装备、技能、任务、动作值等主题分包。普通表在所属主题的 `specs.py` 声明工作表与源文件，`build.py` 准备行数据。有专用版式的工作簿在该主题的 `excel.py` 处理样式。新增工作簿时在 `src/database/exporter.py` 接入导出并更新 `WORKBOOK_NAMES`。[数据库入口](src/database/exporter.py) |
| 加工后的工作簿或 JSON | `src/processed_data/` 按用途分包，例如护石池在 `amulet_pools/`，弩枪在 `bowguns/`，技能效果在 `skill_details/`。新的发布文件从所属模块的导出函数接入 `src/processed_data/exporter.py`，并加入 `OUTPUT_NAMES`。[加工数据入口](src/processed_data/exporter.py) |
| 多个 Python 导出器用到的逻辑 | `src/shared/source/` 读取并规范化游戏表，`src/shared/text/` 解析文本引用并按语言取值，`src/shared/excel/` 放通用单元格和工作簿写出。只服务任务的难度表关联留在 `src/database/missions/difficulty.py`，同属 `src/` 的网页数据导出器可以复用。 |
| 导出顺序、校验、打包和落盘 | `src/pipeline/exporter.py` 编排数据库、加工数据和压缩包生成，`validation.py` 校验产物集合并写出清单，`package.py` 管理归档，`publish.py` 在校验通过后替换本地 `output/`。根 `main.py` 是这条流程的命令入口。[导出流程](src/pipeline/exporter.py) |
| 网页专用数据和入口 | `src/site_data/` 下的 Python 模块生成前端实际读取的 JSON，正式输出放在 `src/site_data/data/<模块>/` 并随代码提交。新模块需在 `src/site_data/__init__.py` 接入导出调用和文件清单。任务读取 `missions/index.json` 与 `missions/quests/<questId>.json`，武器读取 `weapon_actions/actions.json`。[网站数据清单](src/site_data/__init__.py) |
| 页面、样式和视觉资源 | 单个栏目放在 `web/src/sites/<模块>/`，包含 `.vue` 页面、该栏目的 TypeScript 数据类型、交互和样式。在模块 `index.ts` 定义标题和路由，在 `web/src/sites.ts` 注册。首页卡片、路由表和静态页面构建都读取这份注册表。需要逐条生成详情页时，由该命名路由的 `staticParams` 从静态 JSON 提取参数，页面根据实际数据给出元数据，站点地图读取静态渲染的结果。全站页面放 `pages/`，共用组件放 `components/`，主题与布局放 `styles/`，共用数据加载和交互逻辑放 `composables/`（均在 `web/src/`）。随模块导入的字体等资源放 `web/src/assets/`，按固定 URL 提供的图标和雪碧图放 `web/public/`。[栏目注册表](web/src/sites.ts) |
| 测试、用户文档和发布 | 测试按职责放在 `tests/database/`、`tests/processed_data/`、`tests/site_data/`、`tests/sdk/`、`tests/shared/`、`tests/pipeline/` 或 `tests/release/`。多个测试使用的小型输入放 `tests/fixtures/`。用户用法放根 `README.md` 和 `docs/` 下的简繁中文说明，SDK 的命令用法放 `sdk/README.md` 和 `sdk/docs/`。发布工作流在 `.github/workflows/`，发布说明脚本在 `.github/scripts/`。 |

正式输出写入 `output/<语言代码>/` 和 `output/processed_data/`，压缩包和 `manifest.json` 位于 `output/` 顶层，前端构建结果在 `web/dist/`。修正产物时修改生成端，再重新生成。

本项目的临时文件统一放在根 `.tmp/`。一次性调查脚本、截图、试导出、测试输出、导出暂存、SDK 环境和分析缓存，以及 GitHub Actions 在仓库内产生的临时文件都按此约定放置。SDK 各工具沿用自己的工作子目录。临时文件、本机 EXE、完整 IL2CPP 转储、依赖安装目录和本地构建结果均不提交。

游戏资源遇到 Git 单文件大小限制时，先确认具体文件的实际大小，再在 `.gitignore` 写入该文件相对仓库根目录的精确路径。避免用整个目录、后缀或资源类型代替文件名。可以用 `git check-ignore -v -- <路径>` 对照超限文件与同目录可正常提交的文件。更新后按实际文件重新核对。此规则针对源资源，开发缓存仍可按目录忽略。

## Python 导出逻辑与多语言数据

> `DATABASE` 是按游戏语言导出的数据库工作簿，`PROCESSED_DATA` 是把原始记录关联、计算后单独交付的加工数据。

- 按产物分配职责。`src/pipeline/` 编排生成、校验和打包，调用业务入口。`src/database/` 和 `src/processed_data/` 各按功能建子目录，彼此不导入，也不反向调用流水线。两者都可以使用 `src/shared/`，公共层不能反向依赖业务包或流水线。网站数据在 `src/site_data/` 组装，可以复用 `src` 内已经解析好的业务关系。
- 单个功能的模型、源表关系、计算和专属版式留在该功能目录。职责较多时可在目录内拆成读取、构建和写出等小文件。多个功能确实需要同一含义的逻辑时再抽到公共层。例如动作与命中判定的关联归 `src/shared/action_values/`，工作表的列顺序和合并方式归 `src/database/action_values/`。新增产物在对应的 `exporter.py` 显式登记入口和文件名。
- 同一次全量导出先准备语言无关的数据。用 `SourceRepository` 读取并规范化源表，建立 GUID、主外键、目标、判定和行布局的关系。需要翻译的单元格保留 `TextRef`，组合文本用 `TextParts`。进入各语言的写出步骤后，用该语言的文本视图解析并填值。共享模板和缓存中保留引用，禁止把某种语言的译文写回模板，也不要为每种语言重新扫描相同源表。
- 文本索引可以共享，显示策略归对应产物。任务文本保留换行，处理拒用标记和英语回退。全文本工作簿保留拒用记录及其标识。加工数据使用各自约定的名称语言。改变语言输出顺序不应改变同一语言的内容。
- 资源升级以当前上游格式为准。遇到 PyREUser3 的 ID、字段或资源路径变化时，修改本项目的读取与关联，核对主外键、枚举和路径大小写。旧格式不再兼容，不添加旧字段别名、猜测性回退或专门的兼容分支。当前格式定义的缺省字段、空引用及文本回退仍按其业务含义处理。

## 配置的作用与优先级

根入口固定为无参命令 `python main.py`。使用者在根 `config.py` 调整输入、输出、语言和版本。终端应显示当前处理阶段、进度和耗时。SDK 及网站数据工具各自保留命令行参数。[根配置](config.py)

| 设置 | 用途 |
| --- | --- |
| `BASE_DIR`、`JSON_ROOT`、`NATIVES_DIR`、`ENUMS_PATH`、`OUTPUT_DIR` | 从仓库实际位置派生资源根目录、枚举路径和本地发布输出目录。仅需试读另一份解包数据时，网站数据命令可用 `--natives` 指定资源根目录。 |
| `ACTION_MAP_PATH`、`MHWS_ACTION_MAP_PATH` | 默认读取 `MHWS-in-json/ActionMap.json`。可在启动 Python 进程前设置环境变量 `MHWS_ACTION_MAP_PATH`，使工作簿和网站武器表读取指定映射，用于核对新生成的数据。 |
| `LANGUAGES`、`LANGUAGE_IDS`、`ZH_HANS_LANGUAGE_ID`、`JAPANESE_LANGUAGE_ID` | `LANGUAGES` 对应游戏数字语言 ID、语言代码与名称。`LANGUAGE_IDS` 默认按资源实际提供的语言导出数据库，设置非空列表可缩小范围。简体中文 ID 用于网站等简中产物，日语 ID 用于动作值工作簿的日文名称参考列。 |
| `GAME_VERSION` | 当前核对的游戏构建。唯一配置在根 `config.py`。代码和动态生成的说明从这里取值，禁止在提取器、业务模块、前端或说明模板中另写当前版本字面量。更新前按同版输入复核受影响的规则和随版本显示的说明。历史证据标注的是当时核对的构建，保留原记录。 |
| `VERSION`、`RELEASE_VERSION`、各压缩包名前缀 | 根导出入口先取 `VERSION`，再取环境变量 `RELEASE_VERSION`。二者均为空时，用 UTC 日期时间加提交号前缀或 `local` 构造发布包版本。它决定文件名与清单中的版本。游戏二进制的构建号需从本次游戏文件核实。 |
| `SUPPORT_FILES`、`WEAPON_TYPES`、`WEAPON_FILE_STEMS`、工作簿名和列宽 | 分别描述常用资源的相对路径、武器集合及源文件大小写，以及导出文件名与展示宽度。某张工作表的字段、翻译规则和计算留在所属业务模块。 |
| `MISSION_HEALTH_KING_WHEN_NONE_IDS`、`MISSION_HEALTH_NO_AUTO_HARD_IDS` | 记录由游戏原生分支确认、任务资源表本身缺少的形态和难度例外。更新这些常量时同时核对对应分支、枚举身份以及使用它们的任务输出。 |

- **SDK 配置**跟随提取器维护。怪物共用的原生布局和符号定位声明在 `sdk/enemy_logic_exporter/shared/config.py`。技能的类型、字段和布局在 `sdk/skill_effect_exporter/config.py`，其中的 `GAME_VERSION` 引用根配置。武器映射的原生规则和输出格式在 `sdk/action_map_exporter/data/`。根 `requirements.txt` 是导出依赖，`sdk/requirements.txt` 和 `sdk/setup_env.ps1` 用于 SDK 工具环境。[SDK 安装与参数](sdk/docs/README.zh-Hans.md)
- **前端配置**由 `web/` 自己管理。`package.json` 定义依赖和开发、类型检查、构建、预览命令，`package-lock.json` 锁定解析结果，`tsconfig.json` 定义 TypeScript 检查范围。`vite.config.ts` 服务或复制网站 JSON，并注入页脚使用的构建日期与提交号，以及规范链接和分享元数据共用的网站地址。构建前可设置 `SITE_ORIGIN` 指定网站的源地址。`MHWS_SITE_DATA` 可指定另一个含 `site.json` 的数据目录，使用绝对路径即可与启动命令的工作目录无关。研究预览数据及设置了 `MHWS_SITE_PREVIEW=1` 的构建会生成预览抓取规则。

## SDK 的输入与使用入口

> TUI 指在终端里用方向键和回车操作的交互菜单。Hook 指工具或模组对游戏原生函数入口或指令的拦截、替换。

- 原生提取只读取使用者提供的**一份纯净的内存 dump EXE**、同一游戏构建的 IL2CPP 元数据，以及该构建的解包资源和枚举。导出前停用会安装 Hook 的脚本或插件并重启游戏。入口已被改写时重新取得纯净 dump。禁止混用安装目录中的原版 EXE、另一份 dump 或不同构建的元数据拼接证据。表格和网站从已交付的静态文件构建，构建阶段无需 EXE 或 IL2CPP，二者也不作为 Release 附件。
- 安装脚本放在 SDK 根目录，Windows 使用 `sdk/setup_env.ps1`。SDK 保留独立命令和 `python -m sdk` 菜单。常用的文件参数同时给出长短形式，EXE 用 `--exe/-e`，IL2CPP 用 `--il2cpp/-i`，也可显式提供 `MHWS_EXE` 和 `MHWS_IL2CPP`。未提供时由菜单询问或由命令提示缺少输入，禁止猜测安装路径。
- 长时间运行的提取、全怪物处理和发布步骤在终端及 TUI 中显示进度，能确定总量时显示完成数、总数、用时及预计剩余时间。可以复用适用的原生分析库及现有进度组件。安装方式、参数、菜单和输入变化时，同步维护 SDK 的英文、简体中文和繁体中文说明。

## 工作簿与加工数据

数据库工作簿普通内容默认垂直居中、水平左对齐。`MissionData.xlsx` 中真正的整数、浮点数单元格水平也居中，带顿号或单位的内容按文本处理。保留单元格原有数值类型和精度。

### 全文本与任务

- **`FullText.xlsx`** 每种语言一份，单个工作表只放 `guid`、`text` 两列。依次列出有效文本、源数据标为拒用（Rejected）的记录、真正的空项，组内保留读取顺序。拒用记录加 `[#Rejected#]` 前缀，未标拒用的空值留空。正文列应足够宽，行高保持紧凑。
- **`MissionData.xlsx` 的记录来源。** 每种语言一份。从资源中的 `app.user_data.QuestData` 枚举任务，再用任务编号清单补全有编号但缺少定义的记录，信息不全的记录排在末尾。`_QuestType` 保留原始枚举标识。任务名、说明等可本地化文本优先用当前语言，缺失时回退英语。活动任务优先读取对应的 `StreamQuestTextData`。怪物名依次查当前语言、英语、其他可用语言，均缺失时保留完整 EM 编号。物品目标的怪物栏留空，副怪名单去重。
- **任务列与完成条件。** 在 `_MissionId` 和 `_TitleMsg` 之间依次放星级 `_QuestLv`、受理条件 `_OrderHR` 和 `_OrderMR`。冻结列直至目标形态 `_LegendaryID`（含该列）。同一任务的完成条件及其目标连续逐行展开，只合并任务共用信息。难度参数紧靠目标列，异常状态按种类分组，多人参数按 `_Count` 人数分组。
- **任务血量。** `SoloHealth` 位于单人血量倍率左侧，列出该目标计入任务难度、形态和随机档位后的实际初始血量。有多个可能值时按数值升序，用顿号放在同一格。工作簿这一列展示单人结果，任务网站另按所选人数展示对应变化。

### 武器动作值、护石和怪物招式

- **`WeaponActionValues.xlsx`** 每种武器一张工作表，弹药单独一张。首行写源碰撞资源路径，表头下每个动作与命中判定的关联占一行。收录具有动作值数据的判定，数值为零的有效记录仍保留。核对弹体、炮击、瓶和追加碰撞等独立来源。同一动作可对应多个判定，同一判定也可在多个动作下出现。
- 同一动作的判定相邻，合并该组的名称单元格，组间清楚分隔。嵌套属性展开到叶字段。未匹配到名称的判定留在各自工作表末尾，`MappingName` 留空，不填固定中文占位词。非日语版在 `MappingName` 前放日语参考名 `MappingNameJa`。来源与置信度分别由 `MappingNameSource`、`MappingConfidence` 表达。
- **护石。** `AmuletCollection.xlsx` 进入每种语言的 DATABASE。武器孔、防具孔分列，有孔时用 `Lv.X`，稀有度用 `Rare.X`。第二张工作表每列对应一个技能池，每行以本语言的“技能名 Lv.X”展示池内条目。`skill_pool.json` 和 `amulet_pool.json` 属于加工数据，紧凑写出。
- **弩枪与图形预设。** `Bowgun_Custom.xlsx`、`LightBowgun.xlsx` 和 `HeavyBowgun.xlsx` 仅进入简中加工包。`graphic_preset.xlsx` 同属加工包，图形设置项给出简体中文名称。
- **`EnemyActionNames.xlsx`** 进入加工包。首页按完整 EM 编号和怪物名建立可点击目录，每只怪物及其独立变种各有一张工作表。`name`、`comment` 分列，两者都为空才跳过，只有两列都相同才去重。

### 技能原表与实际效果

- `SkillCollection.xlsx` 在每种语言的 DATABASE 中保留原始导出格式。`SkillDetails.xlsx` 将 `SkillCommonData`、`SkillData` 与 SDK 核实的效果链路对应，随 Release 放在 `PROCESSED_DATA`。详表使用日文技能名、简中技能名和简中说明，逐级列出实际效果。本项目的技能产物为表格和静态数据，不包含独立伤害计算器。
- 从技能引用和取参继续追到数值的最终用途，写明作用对象、计算方式、单位和触发条件。只计该技能自身的影响，按实际等级、武器、弹种、怪物状态或其他有效条件分行。随机效果列概率。数值槽相同也要核实实际用途，汇总函数中其他技能的效果不能归入本技能。
- 游戏中只作映射的空壳技能保留 `HunterSkill_xxx` 标识并链接到实际技能。玩家看到的名称使用已核实的游戏官方简中，涉及上下位、伤口计数等条件时查证最终判定，未核实的项目单列。工作簿与网站共同使用的数值、名称或条件应从来源修正，再核对两端展示。底层地址和调用证据保留在技术数据中。

## 玩家页面的约定

- 网站沿用主站和博客的 Material 3 Expressive 配色、字体、形状、动效和交互。视觉与行为与主站及博客保持一致，在本站实现共用组件。新页面复用 `web/src/components/` 的页头、页脚、卡片和选择器，以及 `web/src/styles/` 的主题变量。页面脚本与数据类型使用 TypeScript，核对桌面、手机和深浅主题的相关状态。
- 全站路由直接切换页面，不添加进出场动画。页面大标题随滚动衔接到页头。滚动条沿用主站的简洁样式并兼顾浏览器兼容性，404 使用主站的错误页风格。首页导航卡片保留右下角箭头和“完整数据下载”入口，去掉多余徽标。技能表数值使用一致的颜色和字重。删除已明确多余的页面教学文字，保留理解数值和操作需要的信息。
- 怪物行动树用一张交互画布表达一只怪物的整场战斗。阶段在树内分支，沿实际入口展示距离、角度、相对站位、怪物状态、随机选招及后续派生。动作优先用玩家可辨认的招式名，缺名时保留可辨认的动作或专有类名，长节点文字应能读全。入口或分支只恢复一部分时，明确标记未知，允许发布已证实的部分。
- 任务以游戏内分类为入口，“全部任务”和各分类的筛选结果都按星级从高到低排列，同星级保留数据中的先后顺序。任务卡片保留名称、星级、目标图标和历战形态边色，详情有独立 URL，目标数据、报酬与任务说明在同页阅读。多目标任务按各自的布局取值。血量与报酬档位只展示数值和概率，省去进度条。倍率明细应与当前人数、怪物状态、攻击档位、招式和阶段一致。
- 全站小数在最终展示时四舍五入保留三位，例如 `1.38996` 显示为 `1.390`。整数照常显示。计算、筛选、档位合并和范围比较使用原始精度。
- 武器动作值沿用工作簿的武器分组、动作顺序和判定行。一个动作可对应多个命中判定，同一判定也可被多个动作引用。保留这些关系，用中文说明适用条件，数值和长文本分列展示。玩家页面与技术原始数据面向不同读者。
- 全站统一名称为 `怪物猎人：荒野数据站`（取自 `web/src/seo/config.ts` 的 `SITE_TITLE`，不加空格），域名统一通过构建期 `SITE_ORIGIN` 注入，默认分享图 `web/public/og-image.png` 不写死域名。各子站保持独立：内容区不跨模块互相依赖数据或硬链，跨栏导航统一由首页与页脚提供。
- 网站采用构建期预渲染（`web/src/entry-server.ts` + `web/scripts/prerender.ts`），同步产出 `sitemap.xml`、`robots.txt`、`_redirects`、`_headers` 与根目录 `404.html`。新增含详情页的子站时，在各自 `index.ts` 的命名路由 `meta.staticParams` 声明参数枚举，页面通过 `useSeoMeta` 按实际字段输出标题、描述与 `indexable` 标记；组件保持 SSR 安全、不泄漏模块级状态，并使用 `onServerPrefetch` 与轻量数据切片避免把大体积 JSON 内联到 HTML。

## 游戏更新后的核对方法

1. 从实际输入确认资源表、枚举、纯净 dump EXE 和 IL2CPP 数据属于同一游戏构建。根 `config.py` 中的 `GAME_VERSION` 用于引用已核对的游戏版本，发布包命名使用独立的 `VERSION`。两者均不替代对外部文件的核对。只涉及单个模块时，优先核对它消费的资源与原生代码。
2. 从当前导出表的类型、主键和外键重新跟随引用。GUID 的取值、资源路径、数组内容及其顺序都可能变化。按字段实际含义区分 GUID、固定 ID 和数组下标。保留已有的空引用语义，出现必需引用缺失或匹配多个目标时指出源表、字段和键值。显示名称、翻译和相似文件名不能单独证明关联。
3. 例如，任务数据库在存在 `MsData` 时，先由 `_QuestUseIndex` 选取怪物布局组，按目标匹配布局，再用 `_DifficultyRankId` 找到难度记录，沿 `_MultiTableId` 找到人数倍率表。同一星级、同一怪物可使用不同配置，多怪任务还需分别匹配每个目标。沿用读取器对独立任务布局的处理。[任务难度读取器](src/database/missions/difficulty.py)
4. 原生函数的地址、字段偏移、方法名及其数字后缀都可能随构建改变。先用新版 IL2CPP 的声明类型、方法签名与字段布局定位候选，再用同版 EXE 复核调用者、被调函数、分支条件、取表方式及最终使用位置。仅有同名函数或相同地址时不能沿用旧结论。新增依赖原生行为的公式或特例时，记录可重新定位的方法、字段、条件及最终用途。随代码生成的当前版本说明引用根 `GAME_VERSION`。更新此值前复核会随之改变版本标注的说明和规则。
5. 血量、速度、伤害等总值按游戏实际取值与运算顺序处理。核对任务难度与目标形态选用哪张表、人数与怪物状态何时生效、招式有无覆盖值，以及随机抽取、取整或限幅发生的位置。已经由上游选表体现的星级或历战形态不能再乘一次。特定动作、弹体或部位才触发的修正应保留其适用条件。
6. 使用实机录像交叉核对速度时，匹配版本、任务、形态、状态和招式。全身招式基准、动画片段的局部变速和整段动作的实测时长是不同的量。记录可重看的时间点以及画面显示的精度。

## 生成与验证

以下命令在仓库根目录运行，按本次修改影响的产物选择。

1. 游戏更新涉及原生关系时，先用对应 SDK 模块重新提取并检查差异。`python -m sdk` 可查看入口，武器动作映射的直接命令为 `python -m sdk.action_map_exporter extract`。其他提取器的检查、提取和发布命令见其目录约定。
2. 上游数据就绪后，数据库工作簿和发布包使用 `python main.py` 生成。网站数据使用独立入口 `python -m src.site_data` 生成到 `src/site_data/data/`。这两个入口按各自产物运行。网站 JSON 的变更应同步生成，修正在生成端完成。
3. 复核本次变更涉及的数值与对应源记录。任务数据可选取上下位、高星、历战王或连续狩猎中受影响的实例，并对照同一目标在不同人数、状态下的结果。`python -B -m unittest tests.site_data.test_committed_data` 比较已提交网站 JSON 与重新生成的内容，目录边界改动使用 `python -B -m unittest tests.sdk.test_package_boundary` 检查。
4. 网站改动使用 `npm --prefix web run build` 执行 TypeScript 检查和 Vite 构建。首次准备依赖使用 `npm --prefix web ci`。要核对玩家实际看到的效果，运行 `npm --prefix web run dev` 并打开受影响的页面或任务详情直链。

只为具体且重要的回归引入必要的测试。已有测试能覆盖风险时直接复用，可以合并重复场景、简化准备过程或删除已失去用途的断言，同时保留对实际行为的检查。正式回归纳入持续集成（CI），一次性调查使用 `.tmp/`。CI 缺少必要测试依赖时，在工作流中安装兼容版本并实际执行测试。自动审查报告的问题先核对触发条件和影响，再决定是否修改。

例如，增加“任务部位耐久”的展示时，从任务布局跟到难度表，先检查 `src/database/missions/` 已经提供了哪些字段，再在 `src/site_data/mission_rates.py` 组装当前目标的倍率并重新生成 `missions/quests/<questId>.json`。页面的数据类型、倍率明细和渲染都在 `web/src/sites/missions/`。如果只调整概率卡片的样式或小数显示，改前端并预览即可。如果改了倍率公式，同时用已知任务核对原始乘数、未舍入总值和最终显示。

## 用户文档与 Git 协作

- 数据库 Release 和网站共用 `Publish database and website` 工作流。仅在默认分支手动运行 `workflow_dispatch`。同一次运行完成回归测试、数据库导出和前端构建，上传 `web/dist/` 到现有 Cloudflare Pages 项目 `mhws-in-json` 后，再发布同一提交的数据库压缩包。推送、标签和 PR 不触发构建。
- 切换到手动发布时，在仓库 Actions 配置中添加 `CLOUDFLARE_API_TOKEN`（Secret，所属账户的 Cloudflare Pages 编辑权限）和 `CLOUDFLARE_ACCOUNT_ID`（Variable）。同时在 Pages 项目的 **Build → Branch control** 关闭生产分支自动部署，并把预览分支设为 **None**。GitHub 工作流和 Pages 的 Git 集成各自控制触发方式。[Cloudflare 分支控制说明](https://developers.cloudflare.com/pages/configuration/branch-build-controls/)
- 根 `README.md` 默认英文，简体中文、繁体中文译本分别放在 `docs/README.zh-Hans.md` 和 `docs/README.zh-Hant.md`。SDK 对应的三份文档在 `sdk/README.md` 和 `sdk/docs/`。每组三语互链。改动影响用户的功能、配置、命令或产物时，同批更新受影响的三语文档。
- 根 README 面向下载数据或运行导出的用户，目录树与当前代码对应，简洁说明网站、数据用途和运行方式，保留既有 PyREUser3 品牌区块。工作簿文档应解释 `MappingNameSource` 表示名称从哪里获得，`MappingConfidence` 表示映射依据的确定程度。Cloudflare 部署教程不放进根 README。公开文档和 PR 说明避免披露私有上游项目的名称和地址。
- 提交按功能分批，使用符合 gitmoji 规范的 emoji 和详细中文提交说明，写清改了什么、涉及哪个产物及原因。Codex 参与时，在正文后空一行并保留一次 `Co-authored-by: Codex <noreply@openai.com>`。PR 说明使用详细中文，写明动机、主要变化及相关验证，Codex 参与时末尾按全局约定署名。
- 本地提交、推送、创建 PR 和合并分别按当次授权执行。例如用户只要求分批提交并在本地预览时，完成本地提交与预览即止。
