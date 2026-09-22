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
  processed_data/  # Bowguns, enemy actions, graphics, and amulet JSON pools
  shared/          # Source cache, text references, equipment rules, and Excel utilities
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
graphic_preset.xlsx
skill_pool.json
```

`MHWS-in-json_<version>.zip` contains the shared source JSON. It is packaged once, separately from the language archives.

## Workbook notes

`MissionData.xlsx` uses `app.user_data.QuestData`. Each clear condition has its own row, with the other quest fields merged vertically. Quest type retains its source value. Localized text falls back to English when missing; a monster with no name in any language retains its `EM` ID. StreamQuest text comes from its companion data. Numbered `MsData` missions without `QuestData` appear at the end with any available text.

`WeaponActionValues.xlsx` requires `MHWS-in-json/ActionMap.json` in `mhws_static_action_request_set_map_v2` format. To rebuild it, run `motlist-to-json action-map` with inputs from the same game version. Set `MHWS_ACTION_MAP_PATH` to use another map. Each action or resource relation gets a separate row; unmapped requestSets remain in the workbook with a blank `MappingName`. `MappingConfidence` is an evidence category, not a probability.
