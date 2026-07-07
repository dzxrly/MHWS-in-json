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

This project also exports Monster Hunter Wilds JSON database dumps into Excel workbooks and release-ready zip packages.

## Outputs

Running `python main.py` writes everything to `output/`.

- `output/<language>/*.xlsx`: localized database workbooks.
- `output/DATABASE_<language>_<version>.zip`: one package per language. Each zip contains that language's xlsx files and the `MHWS-in-json/` source directory.
- `output/processed_data/`: language-independent processed files from the extra converter flow.
- `output/PROCESSED_DATA_<version>.zip`: contains `skill_pool.json`, `amulet_pool.json`, and `graphic_preset.xlsx`.

Zip files are written with the maximum deflate compression level.
Languages whose text index is `-1` in any message file are skipped.

## Usage

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

No command-line arguments are used. Edit [config.py](config.py) to change paths, selected languages, output names, and version settings.

## GitHub Release

[.github/workflows/release.yml](.github/workflows/release.yml) runs on every push and can also be started manually. The release version is `yyyyMMdd-HHmmss-<short_hash>` in UTC, and all generated zip files under `output/` are uploaded as release assets.

Large Stage VoxelData and Enemy Constraint JSON files are ignored by [.gitignore](.gitignore). If those files were already committed before the ignore rules were added, remove them from Git history before pushing to GitHub.

See [Git Large File Cleanup](docs/GIT_LARGE_FILE_CLEANUP.md) for the required cleanup boundary.
