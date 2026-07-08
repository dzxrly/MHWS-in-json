# MHWS-in-json

English | [简体中文](docs/README.zh-Hans.md) | [繁體中文](docs/README.zh-Hant.md)

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

- `output/<language>/*.xlsx`: localized database workbooks.
- `output/DATABASE_<language>_<version>.zip`: one release asset per language. Each zip contains only that language's xlsx files and does not include `MHWS-in-json/`.
- `output/processed_data/`: language-independent processed files from the extra converter flow.
- `output/PROCESSED_DATA_<version>.zip`: one language-independent release asset containing `skill_pool.json`, `amulet_pool.json`, `graphic_preset.xlsx`, `弩枪客制零件信息.xlsx`, `HeavyBowgun.xlsx`, and `LightBowgun.xlsx`.
- `output/MHWS-in-json_<version>.zip`: one shared source JSON release asset containing the `MHWS-in-json/` directory.

Zip files are written with the maximum deflate compression level. The source JSON dump has no multilingual semantics, so it is packaged once instead of being repeated in every language package.
Bowgun workbooks in `PROCESSED_DATA` are exported in Simplified Chinese only.
Languages whose text index is `-1` in any message file are skipped.
The script prints detailed loading, conversion, saving, and packaging logs in the terminal.

## Usage

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

No command-line arguments are used. Edit [config.py](config.py) to change paths, selected languages, output names, and version settings.
