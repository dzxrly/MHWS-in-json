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
python main.py
```

Set paths, languages, and version in [config.py](config.py). The script takes no command-line arguments and writes to `output/`. A failed export keeps the previous output. Run tests with `python -B -m tests`.

## Code layout

```text
src/
  database/        # Database workbooks
  processed_data/  # Processed workbooks, JSON datasets, and battle graph pages
  shared/          # Source data, text, RCOL, Excel, and logging utilities
  pipeline/        # Export, validation, packaging, and publication
sdk/
  il2cpp/          # IL2CPP upload and download tools
  enemy_logic_exporter/
    shared/        # Python: native, resources, logic, models, workflow
    data/          # JSON: evidence/, models/, rules.v1.json
    monster/       # One entry per monster and variant
tests/
```

Temporary files and research caches stay under `.agents/`.

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

`PROCESSED_DATA_<version>.zip` contains the processed data in Simplified Chinese:

```text
Bowgun_Custom.xlsx
EnemyActionNames.xlsx
HeavyBowgun.xlsx
LightBowgun.xlsx
SkillDetails.xlsx
amulet_pool.json
graphic_preset.xlsx
skill_pool.json
enemy_battle_logic/index.html
enemy_battle_logic/EM0001_00_0.html
...
```

The battle graph bundle consists of an index and 34 monster pages. Variants have separate pages; the training target is excluded. Online battle graphs: [mhws-monsters-ai.eggtargaryen.com](https://mhws-monsters-ai.eggtargaryen.com/).

`MHWS-in-json_<version>.zip` contains the source JSON, packaged separately from the workbooks.

## Project tools

- `sdk.enemy_logic_exporter` extracts monster battle logic from the game files into the graph JSON behind the battle pages. The 34 models in `src/processed_data/enemy_battle_logic/models` cover game version **1.42.0.2**; unresolved branches stay marked.
- `sdk.skill_effect_exporter` finds the native functions that use each skill, evaluates them per level, and writes the skill effect link JSON behind `SkillDetails.xlsx`.

Both tools need the game EXE and a REFramework `il2cpp_dump.json` of the same version, which you provide. Setup and usage: [SDK guide](docs/sdk.md). Rebuilding the pages or workbooks needs neither tool:

```powershell
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
```

Then open `.agents/battle-preview/enemy_battle_logic/index.html`; the pages work offline.

## Data notes

- `SkillDetails.xlsx` joins SkillCommonData with SkillData and lists, for each skill, the native functions that use it and their results per level. Names are given in Japanese and Simplified Chinese, descriptions in Simplified Chinese only. Each row of the 技能效果 (effects) sheet is one function's result for a set of levels and arguments: the value, the runtime conditions it still depends on, and whether it comes from a SkillData slot, a parameter file field, or an EXE constant. Results assume only that skill is equipped; functions that add up many skills may be marked as not fully evaluated. The 说明 (notes) sheet lists the assumptions, where the group-skill mapping in the data differs from the code, and the digests of the source EXE and il2cpp dump.
- `MissionData.xlsx` gives each quest clear condition its own row and merges the remaining quest fields. Missing localized text falls back to English; monsters without a name retain their `EM` ID. `SoloHealth` lists the possible initial solo maximum HP values, including quest difficulty, random health grades, and Legendary modifiers. It stays blank when the target cannot be resolved.
- `WeaponActionValues.xlsx` requires `MHWS-in-json/ActionMap.json` in `mhws_static_action_request_set_map_v2` format. Rebuild it with `motlist-to-json action-map` using inputs from the same game version, or set `MHWS_ACTION_MAP_PATH` to use another file. Each relation has its own row; unmatched requestSets retain a blank `MappingName`. `MappingConfidence` describes the evidence category. Workbooks for languages other than Japanese add a `MappingNameJa` column with the Japanese name before `MappingName`.
