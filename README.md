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

## Website

[mhws-info.eggtargaryen.com](https://mhws-info.eggtargaryen.com/) (Simplified Chinese only):

- Monster battle logic: each monster's attack decision tree, filterable by distance, angle and state. Covers 34 monsters, with a page for each variant.
- Skill effect values: the effect values and activation conditions of every skill at each level.

## Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Set paths, languages, and version in [config.py](config.py). The script takes no command-line arguments and writes to `output/`. A failed export keeps the previous output. Run tests with `python -B -m tests`.

## Code layout

```text
main.py, config.py           # Entry point and settings
MHWS-in-json/                # Source JSON
src/
  database/                  # Database workbooks
  processed_data/            # Processed workbooks and JSON; monster battle models
  shared/                    # Source data, text, RCOL, Excel, and logging utilities
  pipeline/                  # Export, validation, packaging, and publication
  site_data/                 # Website data; the generated data/ is committed
sdk/                         # Offline SDK that reads the game files
  enemy_logic_exporter/      # Monster battle logic
    shared/  data/  monster/ #   shared code, rules and evidence, one module per monster
  skill_effect_exporter/     # Skill effect values
  action_map_exporter/       # ActionMap v2
    shared/  skills/         #   native emulation and workflow, one module per skill
web/                         # Website (Vite + Vue); src/sites/ holds one folder per site
tests/
```

After the monster models or skill effects change, regenerate the website data with `python -m src.site_data` and commit it; the tests fail while it is out of date. Building the website needs only Node.js 22 or later: `npm --prefix web ci`, then `npm --prefix web run build`.

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
enemy_battle_logic.json
graphic_preset.xlsx
skill_details.json
skill_pool.json
```

`enemy_battle_logic.json` and `skill_details.json` hold the full data behind the [website](#website).

`MHWS-in-json_<version>.zip` contains the source JSON, packaged separately from the workbooks.

## Project tools

The `sdk/` directory is an offline SDK that reads the game files; `python -m sdk` opens its menu. Its features:

- Monster battle logic (`sdk.enemy_logic_exporter`) extracts monster battle logic into the graph JSON behind the battle pages. The 34 models in `src/processed_data/enemy_battle_logic/models` keep unresolved branches marked.
- Skill effects (`sdk.skill_effect_exporter`) finds the native functions that use each skill, evaluates them per level, and writes the skill effect link JSON behind `SkillDetails.xlsx`.
- Weapon action mapping (`sdk.action_map_exporter`) builds `MHWS-in-json/ActionMap.json` from matching dumps and converted JSON, for the action names in `WeaponActionValues.xlsx`.

The SDK needs the game EXE dumped from memory (e.g. `MonsterHunterWilds_dump.exe`) and the REFramework `il2cpp_dump.json`, which you provide; it records no game version. Setup (`sdk/setup_env.ps1`) and usage: [SDK guide](sdk/README.md). Rebuilding the website or the workbooks does not need the SDK.

## Data notes

- `SkillDetails.xlsx`: each row is one effect of a skill at one level, with its value, what it applies to, how it is calculated, when it applies, and its unit. Values assume only that skill is equipped; a value that depends on the situation gets one row per situation.
- `MissionData.xlsx`: one row per quest clear condition. `SoloHealth` lists the possible initial solo maximum HP values, counting quest difficulty, random health grades, and Legendary modifiers.
- `WeaponActionValues.xlsx` needs `MHWS-in-json/ActionMap.json`; rebuild it with `python -m sdk.action_map_exporter extract` from the same game version, or point `MHWS_ACTION_MAP_PATH` at another file. Actions without a match keep a blank `MappingName`.
