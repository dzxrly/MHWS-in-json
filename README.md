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
  processed_data/  # Processed workbooks and JSON datasets; battle graph models
  shared/          # Source data, text, RCOL, Excel, and logging utilities
  pipeline/        # Export, validation, packaging, and publication
  site_data/       # JSON read by the website (the only link to web/)
sdk/
  il2cpp/          # IL2CPP upload and download tools
  enemy_logic_exporter/
    shared/        # Python: native, resources, logic, models, workflow
    data/          # JSON: evidence/, models/, rules.v1.json
    monster/       # One entry per monster and variant
web/               # Vite + Vue website; reads only the committed JSON of src/site_data
tests/
```

## Website

[mhws-info.eggtargaryen.com](https://mhws-info.eggtargaryen.com/) gathers the information sites, in Simplified Chinese only: monster battle logic (34 monsters; variants have their own pages, the training target is excluded) and skill effect values (from the same skill effect link JSON as `SkillDetails.xlsx`).

`sdk/`, `src/` and `web/` do not import each other; they exchange JSON only. The site reads the JSON committed in `src/site_data/data/`, which holds only what the pages show, split so that no file exceeds about 7 MB:

```text
site.json                                    schema version, preview flag
enemy_battle_logic/index.json                monster list
enemy_battle_logic/<enemyId>/tree.json       decision tree and names
enemy_battle_logic/<enemyId>/tables.json     behaviour table nodes (raw data)
enemy_battle_logic/<enemyId>/flow.json       technical flow chart
skill_details/skills.json                    skill effect values and their meanings
```

Regenerate it offline with `python -m src.site_data` after the monster models or the skill links change, and commit it; the tests fail while it is out of date. The release carries the same data as two complete single files instead (see below).

`web/` is a Vite + Vue app with the home page and one route per information site (`/enemy_battle_logic/`, `/skill_details/`). Building it needs only Node.js 22 or later, no Python; the build copies the JSON into the site's `data/`:

```powershell
npm --prefix web ci
npm --prefix web run build           # into web/dist
npm --prefix web run preview         # browse it at http://localhost:4173
```

`npm --prefix web run dev` serves the same JSON while editing. `MHWS_SITE_DATA` points the site at another data folder, such as a preview of models the SDK has not published (`python -m src.site_data --enemy-models <model folder> --preview --output .tmp/site-preview`).

To add an information site, write its JSON from `src/site_data` (a module called from `export_site_data`), then declare its title, home page card and routes in `web/src/sites/<site>/index.js` and list it in `web/src/sites.js`.

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

`enemy_battle_logic.json` holds every monster's full battle graph and `skill_details.json` the skill effect values, each as one file; the [website](#website) reads a trimmed, split copy of the same data, and its pages are not in the release.

`MHWS-in-json_<version>.zip` contains the source JSON, packaged separately from the workbooks.

## Project tools

The `sdk/` directory is an offline SDK that reads the game files; `python -m sdk` opens its menu. Its features:

- Monster battle logic (`sdk.enemy_logic_exporter`) extracts monster battle logic into the graph JSON behind the battle pages. The 34 models in `src/processed_data/enemy_battle_logic/models` keep unresolved branches marked.
- Skill effects (`sdk.skill_effect_exporter`) finds the native functions that use each skill, evaluates them per level, and writes the skill effect link JSON behind `SkillDetails.xlsx`.

The SDK needs the game EXE dumped from memory (e.g. `MonsterHunterWilds_dump.exe`) and the REFramework `il2cpp_dump.json`, which you provide; it records no game version. Setup (`sdk/setup_env.ps1`) and usage: [SDK guide](sdk/README.md). Rebuilding the [website](#website) or the workbooks does not need the SDK.

## Data notes

- `SkillDetails.xlsx` gives the effect values of each skill. Each row of the 技能效果 (effects) sheet is one effect of a skill at one level (`Lv.1`, `Lv.2`, …), with the in-game skill and level descriptions, the effect value, and the weapons, ammo kinds or actions it applies to, written as "【weapon】ammo". Only numbers read from game parameters are listed, assuming only that skill is equipped. When a value depends on the situation (such as the number of consecutive hits), each situation gets its own row with the situation at the start of 条件; values that only appear while another effect runs (a meal skill, a hunting horn melody, the weapon's own state, another skill's data) are left out, and a random check is shown as its chance (such as 80%). "a / b" remains only where nothing in the code tells the values apart. The 作用于, 计算, 条件 and 单位 columns (what the value applies to, how it is applied, when, and its unit) come from the reviewed meanings in the SDK's per-skill modules `sdk/skill_effect_exporter/skills/hunterskill_<n>.py`, copied into the link JSON, written from the code's use of each value; `python -m src.processed_data.skill_details --meanings-report <file.md>` lists every effect with its meaning and the usage evidence behind it. The 技能 (skills) sheet joins SkillCommonData with SkillData. Names are in Japanese and Simplified Chinese, descriptions and effect names in Simplified Chinese only.
- `MissionData.xlsx` gives each quest clear condition its own row and merges the remaining quest fields. Missing localized text falls back to English; monsters without a name retain their `EM` ID. `SoloHealth` lists the possible initial solo maximum HP values, including quest difficulty, random health grades, and Legendary modifiers. It stays blank when the target cannot be resolved.
- `WeaponActionValues.xlsx` requires `MHWS-in-json/ActionMap.json` in `mhws_static_action_request_set_map_v2` format. Rebuild it with `motlist-to-json action-map` using inputs from the same game version, or set `MHWS_ACTION_MAP_PATH` to use another file. Each relation has its own row; unmatched requestSets retain a blank `MappingName`. `MappingConfidence` describes the evidence category. Workbooks for languages other than Japanese add a `MappingNameJa` column with the Japanese name before `MappingName`.
