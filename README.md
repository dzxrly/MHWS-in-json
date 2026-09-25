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
  database/  processed_data/  shared/  pipeline/  release/
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
```

`damage_calculator.zh-Hans.json` retains monster part and scar GUIDs, normal and alternate meat tables, source vitality values, and player RCOL hit profiles with their exact request-set identities. The four hit rates are `_PartsBreakRate` and the tear/raw/old scar rates. The seven sharpness levels export separate physical and elemental rates from the enemy common table; hit profiles also retain the source sharpness and critical flags. Missing alternate meat references stay explicit as `null`. Items remain in this file; damage skill effects are exported only in `skill_effects.zh-Hans.json`. The full release validates both JSON files before publication. For standalone snapshots, run `python -m src.processed_data.damage_calculator.exporter --output .agents/damage_calculator.zh-Hans.json` and `python -m src.processed_data.skill_effects.exporter --output .agents/skill_effects.zh-Hans.json` from the project root.

The skill catalog retains every source skill identity, localized descriptions, level values, evidence status, and source hashes. Verified damage effects have explicit calculation stages, weapon and element scopes, and optional active states. Its consumer treats selected skills as active and lets the user choose whether the current hit is critical; trigger rules, durations, affinity chance bonuses, meal skills, and status buildup are outside this catalog. Weapon-specific Coalescence effects, Black Eclipse after overcoming Frenzy, and verified Challenger Attribute effects retain their separate calculation stages. Skills without a verified numeric effect remain visible in the data but must not be applied as zero-valued bonuses.

Damage schema version 10 retains PlayerStatus attack limits, exports shared Normal Lv1-3 ammunition levels, and includes distinct audited physical curves for elemental and pierce ammunition. Other curves retain their source reference without inferred points. Skill schema version 4 adds First Shot attack additions and its separate on-hit elemental multiplier, scoped to light/heavy bowgun projectiles with an explicit active condition. The multiplier applies before elemental flat additions and the unchanged cap; the condition belongs to the projectile, not its penetration index.

`MHWS-in-json_<version>.zip` contains the shared source JSON. It is packaged once, separately from the language archives.

## Workbook notes

`MissionData.xlsx` uses `app.user_data.QuestData`. Each clear condition has its own row, with the other quest fields merged vertically. Quest type retains its source value. Localized text falls back to English when missing; a monster with no name in any language retains its `EM` ID. StreamQuest text comes from its companion data. Numbered `MsData` missions without `QuestData` appear at the end with any available text.

For resolved monster targets, `SoloHealth` immediately precedes the quest `_Health` rate. It contains initial solo maximum HP calculated from the enemy's `_BaseHealth`, the selected quest difficulty, the possible random health grades, and the Legendary rate; multiple values appear in ascending order separated by `、`. Rows without a resolved monster target leave it blank. Numeric cells are centered; text cells, including lists of possible HP values, are left aligned. The compiled enemy ID exceptions in `config.py` were checked against a local game executable and should be rechecked after game updates.

`WeaponActionValues.xlsx` requires `MHWS-in-json/ActionMap.json` in `mhws_static_action_request_set_map_v2` format. To rebuild it, run `motlist-to-json action-map` with inputs from the same game version. Set `MHWS_ACTION_MAP_PATH` to use another map. Each action or resource relation gets a separate row; unmapped requestSets remain in the workbook with a blank `MappingName`. `MappingConfidence` is an evidence category, not a probability.
