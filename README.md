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

Full exports currently stop at the monster battle graph review check. Use the preview command below to view the research graphs.

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
amulet_pool.json
damage_calculator.zh-Hans.json
graphic_preset.xlsx
skill_effects.zh-Hans.json
skill_pool.json
enemy_battle_logic/index.html
enemy_battle_logic/EM0001_00_0.html
...
```

The battle graph bundle consists of an index and 34 monster pages. Variants have separate pages; the training target is excluded. Approved pages are also published to GitHub Pages from the default branch.

`MHWS-in-json_<version>.zip` contains the source JSON, packaged separately from the workbooks.

## Project tools

Use `python -m sdk.il2cpp upload --dry-run` to prepare an IL2CPP upload, or `python -m sdk.il2cpp download` to retrieve the build data. Both use the existing `gh` login.

The monster SDK reads game resources, a matching EXE, and IL2CPP metadata to produce graph JSON. The page builder reads only that JSON. See the [SDK guide](sdk/enemy_logic_exporter/AGENTS.md) for extraction and maintenance.

The 34 models in `src/processed_data/enemy_battle_logic/models` currently cover game version **1.42.0.2**. They retain unresolved branches and are pending semantic review, so they are available as research previews only.

```powershell
python -m sdk.enemy_logic_exporter --help
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
```

Open `.agents/battle-preview/enemy_battle_logic/index.html` to browse the graphs. Each page works offline and supports zooming, node lookup, and SVG export. To preview one model, replace `--preview-all` with `--template <graph.json>`.

## Data notes

- `damage_calculator.zh-Hans.json` contains monster hitzones, parts and scars, player hit profiles, sharpness rates, and item modifiers. Missing alternate hitzones remain `null`.
- `skill_effects.zh-Hans.json` contains skill levels and reviewed damage effects, with calculation stages, weapon and element scopes, and active states. Consumers assume selected skills are active and choose whether the hit is critical. Trigger logic, durations, affinity chance bonuses, meal skills, and status buildup are outside this dataset; unverified effects remain unapplied.
- `MissionData.xlsx` gives each quest clear condition its own row and merges the remaining quest fields. Missing localized text falls back to English; monsters without a name retain their `EM` ID. `SoloHealth` lists the possible initial solo maximum HP values, including quest difficulty, random health grades, and Legendary modifiers. It stays blank when the target cannot be resolved.
- `WeaponActionValues.xlsx` requires `MHWS-in-json/ActionMap.json` in `mhws_static_action_request_set_map_v2` format. Rebuild it with `motlist-to-json action-map` using inputs from the same game version, or set `MHWS_ACTION_MAP_PATH` to use another file. Each relation has its own row; unmatched requestSets retain a blank `MappingName`. `MappingConfidence` describes the evidence category.
