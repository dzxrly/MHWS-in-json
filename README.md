<div align="center">

# MHWS-in-json

English | [简体中文](docs/README.zh-Hans.md) | [繁體中文](docs/README.zh-Hant.md)

</div>

Converts the bundled MHWS JSON data into Excel workbooks and release archives. The JSON layout follows [eigeen/mhws-data-dump-scripts](https://github.com/eigeen/mhws-data-dump-scripts) and [dtlnor/MHWs-in-json](https://github.com/dtlnor/MHWs-in-json).

<div align="center">

<a href="https://github.com/dzxrly/PyREUser3">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-dark.svg">
    <img alt="Powered by PyREUser3" src="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-light.svg">
  </picture>
</a>

</div>

## Run

```powershell
python -m pip install -r requirements.txt
python -B -m tests
python main.py
```

The script takes no command-line arguments. Set paths, languages, and version in [config.py](config.py). Files are written to `output/`. The output path must remain inside the project. Exports are built under `.agents/export-runs/`, checked for complete workbooks and archive contents, then published together. A failed generation leaves the previous output in place. `output/manifest.json` records file hashes, language IDs, input table paths, and stage timings.

## Code layout

```text
src/
  database/        # DATABASE workbooks, with one subdirectory per feature
  processed_data/  # Bowguns, enemy actions, calculator JSON, graphics, and amulet JSON pools
  shared/          # Source cache, text references, RCOL parsing, and Excel utilities
  pipeline/        # Export coordination, packaging, validation, and publication
tests/
  database/  processed_data/  shared/  pipeline/  release/  sdk/
```

Common source tables are read and normalized once per export. Database preparation keeps explicit message GUID references, including compound skill and material descriptions; localization fills those references for each language. Structural GUIDs remain identifiers. Text policies preserve the separate database and quest fallback rules. Action-value and mission workbooks reuse registered cell styles; the flat full-text workbook is streamed to Excel.

Run the regression suite with `python -B -m tests`. CI runs it before exporting. Temporary test files stay under `.agents/`. The release-notes script in `.github/scripts/` remains standalone.

## Release archives

`DATABASE_<language>_<version>.zip` contains the database workbooks for one language:

```text
AmuletCollection.xlsx
EquipCollection.xlsx
EquipRecipeCollection.xlsx
FullText.xlsx
ItemDataCollection.xlsx
MissionData.xlsx
SkillCollection.xlsx
WeaponActionValues.xlsx
```

`PROCESSED_DATA_<version>.zip` contains post-processed data outside the database. It is published as a Simplified Chinese edition only; no other language editions are provided:

```text
Bowgun_Custom.xlsx
EnemyActionNames.xlsx
HeavyBowgun.xlsx
LightBowgun.xlsx
amulet_pool.json
damage_calculator.zh-Hans.json
graphic_preset.xlsx
skill_effects.zh-Hans.json
skill_pool.json
enemy_battle_logic/index.html
enemy_battle_logic/EM0001_00_0.html
```

`enemy_battle_logic` 的正式交付范围是 34 个大型怪物的 HTML 和一个索引页。变种保留独立身份，训练靶不进入该范围。每个页面内嵌已解析的图 JSON、布局库和来源证据；条件、动作请求、子表调用及恢复位置来自经过核对的原生控制流，资源参数数组顺序不能作为执行顺序。仍有未知分支或未完成审核的研究图只能显式预览，不能通过正式发布检查。

默认分支工作流将相同的已验收页面发布到 GitHub Pages。`.github/scripts/build_pages.py` 只复制正式构建结果，不重新提取逻辑。Pages 使用 GitHub Actions 作为发布来源；分支构建保留发布压缩包，但不部署公开站点。

`damage_calculator.zh-Hans.json` retains monster part and scar GUIDs, normal and alternate meat tables, source vitality values, and player RCOL hit profiles with their exact request-set identities. The four hit rates are `_PartsBreakRate` and the tear/raw/old scar rates. The seven sharpness levels export separate physical and elemental rates from the enemy common table; hit profiles also retain the source sharpness and critical flags. Missing alternate meat references stay explicit as `null`. Items remain in this file; damage skill effects are exported only in `skill_effects.zh-Hans.json`. The full release validates both JSON files before publication. For standalone snapshots, run `python -m src.processed_data.damage_calculator.exporter --output .agents/damage_calculator.zh-Hans.json` and `python -m src.processed_data.skill_effects.exporter --output .agents/skill_effects.zh-Hans.json` from the project root.

The skill catalog retains every source skill identity, localized descriptions, level values, evidence status, and source hashes. Verified damage effects have explicit calculation stages, weapon and element scopes, and optional active states. Its consumer treats selected skills as active and lets the user choose whether the current hit is critical; trigger rules, durations, affinity chance bonuses, meal skills, and status buildup are outside this catalog. Weapon-specific Coalescence effects, Black Eclipse after overcoming Frenzy, and verified Challenger Attribute effects retain their separate calculation stages. Skills without a verified numeric effect remain visible in the data but must not be applied as zero-valued bonuses.

Damage schema version 10 retains PlayerStatus attack limits, exports shared Normal Lv1-3 ammunition levels, and includes distinct audited physical curves for elemental and pierce ammunition. Other curves retain their source reference without inferred points. Skill schema version 4 adds First Shot attack additions and its separate on-hit elemental multiplier, scoped to light/heavy bowgun projectiles with an explicit active condition. The multiplier applies before elemental flat additions and the unchanged cap; the condition belongs to the projectile, not its penetration index.

`MHWS-in-json_<version>.zip` contains the shared source JSON. It is packaged once, separately from the language archives.

## Project tools

Project maintenance tools live under `sdk/`. Run `python -m sdk.il2cpp upload --dry-run` or `python -m sdk.il2cpp download` to prepare or retrieve the IL2CPP build data. GitHub operations use the existing `gh` authentication; temporary files stay under `.agents/il2cpp`.

怪物行动逻辑的离线提取入口是 `python -m sdk.enemy_logic_exporter --help`。公共分析代码位于 `sdk/enemy_logic_exporter/shared`，34 个大型怪物（变种分开，排除训练靶）分别位于 `monster/<完整ID小写>.py`。规则和待解析的语义输入保存在 `monster/models`，已解析的图 JSON 交给 `src/processed_data/enemy_battle_logic/models`。SDK 与 `src` 之间只通过 JSON 文件交接，双方不导入或调用对方代码。维护细节见 [SDK 说明](sdk/enemy_logic_exporter/AGENTS.md)。

`src/processed_data/enemy_battle_logic/models` 现有 34 个已解析的离线图，全部来自游戏 1.42.0.2 的匹配 EXE、IL2CPP 和实际 BTableList/导入闭包。各图合计包含 7,763 个原生方法上下文、8,171 个子表（含 Combat 事件表）、103,964 个节点和 4,539 个加权选择点。原先 46 表、408 节点的雌火龙局部图保存在回归样本中。当前仍有 3,132 个未知流程节点、2,726 个未完整恢复条件和 854 个选择器边界；整场战斗入口与语义审核尚未完成，默认 `python main.py` 和正式发布验收继续拒绝这些研究图。原生缓存只保存在 `.agents`，不进入 Git 或发布包。

网页构建只读取 SDK 离线生成的图 JSON，不读取解包资源、IL2CPP、EXE 或 Ghidra，也不导入 SDK。`python -m src.processed_data.enemy_battle_logic --template <已提取图.json> --output <预览目录>` 可生成单怪物预览；正式构建仍要求全部 34 只怪物通过战斗入口和语义覆盖检查。游戏更新后，必须通过 SDK 重新核对源文件和逻辑，再更新图 JSON。

全怪物研究预览使用 `python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview`。每个单文件 HTML 内嵌全部已恢复子表和 ELK 布局库，可缩放、定位和导出 SVG。SDK 的 `extract-all` 命令要求同版本 `--index`、`--helpers`、`--inventory` 和 `--requests`；它调用每只怪物的独立入口，并分别统计原生地址与资源/类型/方法/命令/参数上下文。动作请求缺口、异型参数和未知边界会保留，不能把导出成功当作完整战斗 AI 已恢复。

## Workbook notes

`MissionData.xlsx` uses `app.user_data.QuestData`. Each clear condition has its own row, with the other quest fields merged vertically. Quest type retains its source value. Localized text falls back to English when missing; a monster with no name in any language retains its `EM` ID. StreamQuest text comes from its companion data. Numbered `MsData` missions without `QuestData` appear at the end with any available text.

For resolved monster targets, `SoloHealth` immediately precedes the quest `_Health` rate. It contains initial solo maximum HP calculated from the enemy's `_BaseHealth`, the selected quest difficulty, the possible random health grades, and the Legendary rate; multiple values appear in ascending order separated by `、`. Rows without a resolved monster target leave it blank. Numeric cells are centered; text cells, including lists of possible HP values, are left aligned. The compiled enemy ID exceptions in `config.py` were checked against a local game executable and should be rechecked after game updates.

`WeaponActionValues.xlsx` requires `MHWS-in-json/ActionMap.json` in `mhws_static_action_request_set_map_v2` format. To rebuild it, run `motlist-to-json action-map` with inputs from the same game version. Set `MHWS_ACTION_MAP_PATH` to use another map. Each action or resource relation gets a separate row; unmapped requestSets remain in the workbook with a blank `MappingName`. `MappingConfidence` is an evidence category, not a probability.

SDK 的 `analyze` 命令执行全量资源发现、可续跑的原生证据提取、动作请求绑定和独立怪物模块分析，只输出离线 JSON 与回执。研究缓存、未核实结果和 ZIP 保存在 `.agents`。建立 34 个模块或完成原生证据提取不等于完成 34 只怪物的玩家战斗行为树；真实条件、分支、调用、续招、等待和中断恢复仍须逐只核实。
