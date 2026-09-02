<div align="center">

# MHWS-in-json

English | [简体中文](docs/README.zh-Hans.md) | [繁體中文](docs/README.zh-Hant.md)

</div>

MHWS game data export libraries similar to [eigeen/mhws-data-dump-scripts](https://github.com/eigeen/mhws-data-dump-scripts) and [dtlnor/MHWs-in-json](https://github.com/dtlnor/MHWs-in-json).

<div align="center">

<a href="https://github.com/dzxrly/PyREUser3">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-dark.svg">
    <img alt="Powered by PyREUser3" src="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-light.svg">
  </picture>
</a>

</div>

## Outputs

Running `python main.py` writes everything to `output/`.

- `output/<language>/*.xlsx`: localized database workbooks. `FullText.xlsx` is a single-sheet table containing every message GUID and its localized text; rows are grouped as available text, rejected text, then empty text while preserving source order within each group. Rejected text is prefixed with `[#Rejected#]`; unmarked empty text remains empty. `AmuletCollection.xlsx` contains normalized amulet, skill, and slot pools with localized names, `Rare.X` rarity display, and separate weapon/armor slot columns using `Lv.X` notation. Its `SkillPool` sheet places each skill-point pool in a separate column and displays entries as `Skill Name Lv.X`. `WeaponActionValues.xlsx` contains one sheet per weapon plus an `Ammo` sheet. It keeps only player attack-value requestSets, recursively flattens their leaf properties, duplicates a requestSet when it maps to multiple displayed action names, and places unresolved requestSets in an orange `[未映射]` block at the end of the applicable sheet.
- `output/DATABASE_<language>_<version>.zip`: one release asset per language. Each zip contains only that language's xlsx files and does not include `MHWS-in-json/`.
- `output/processed_data/`: language-independent processed files from the extra converter flow.
- `output/PROCESSED_DATA_<version>.zip`: one language-independent release asset containing `skill_pool.json`, `amulet_pool.json`, `graphic_preset.xlsx`, `Bowgun_Custom.xlsx`, `HeavyBowgun.xlsx`, and `LightBowgun.xlsx`.
- `output/MHWS-in-json_<version>.zip`: one shared source JSON release asset containing the `MHWS-in-json/` directory.

Zip files are written with the maximum deflate compression level. The source JSON dump has no multilingual semantics, so it is packaged once instead of being repeated in every language package.
Bowgun workbooks in `PROCESSED_DATA` are exported in Simplified Chinese only.
Languages whose text index is `-1` in any message file are skipped.
The script prints detailed loading, conversion, saving, and packaging logs in the terminal.

### Action-value mapping

Weapon/action mappings are consumed exclusively from the portable static package `MHWS-in-json/ActionMap.json` (`_format = mhws_static_action_request_set_map_v1`). Generate this package locally with `motlist-to-json action-map`, using the matching game executable dump, `il2cpp_dump.json`, motbank/motlist resources, PAK file list, and MHWS JSON corpus. GitHub Actions therefore never needs the multi-gigabyte local dependencies. Set `MHWS_ACTION_MAP_PATH` only when testing a package outside `MHWS-in-json/`.

Every relation must resolve the exact five-part identity `(scope, rcol, requestSetID, keyHash, sourceRequestSetOrdinal)` in the current RCOL corpus. Stale or conflicting packages fail the export. Relations without a real message GUID are not treated as named actions and remain in the final orange `[未映射]` block. Genuine many-to-many mappings are retained; identical RS rows are deduplicated within one final displayed action name, and equal localized action names are merged.

Each action-value sheet lists its RCOL source paths in a merged first row, places the field header on the second row, and omits the RCOL path as a repeated data column.

## Usage

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

No command-line arguments are used. Edit [config.py](config.py) to change paths, selected languages, output names, and version settings.
