# SDK guide

English | [简体中文](sdk.zh-Hans.md) | [繁體中文](sdk.zh-Hant.md)

The `sdk/` directory holds two command-line tools. Run both from the repository root with `python -m`:

| Tool | Purpose | External files |
|---|---|---|
| `sdk.il2cpp` | Uploads or downloads the IL2CPP metadata (`il2cpp_dump.json`) between a GitHub Release and your machine | A logged-in GitHub CLI (`gh`) |
| `sdk.enemy_logic_exporter` | Extracts monster battle logic from the game EXE, IL2CPP metadata, and resource exports, and writes the graph JSON used by the web pages | Game EXE, IL2CPP metadata, `MHWS-in-json` resources; some commands also need Ghidra |

Neither tool is needed to rebuild the web pages without changing the battle logic: the page builder only reads the published models in the repository (see [Build the pages only](#build-the-pages-only)).

## IL2CPP data tool (`sdk.il2cpp`)

The IL2CPP metadata is about 1.6 GB. It is kept out of Git and stored, compressed, in the repository's `build-data` Release. Automated builds and local battle-logic extraction both fetch it from there.

### Download

```powershell
gh auth login                      # first time only
python -m sdk.il2cpp download
```

- Saves to `src/data/il2cpp_dump.json` by default; use `--output <path>` for another location.
- Downloads `il2cpp_dump.json.gz` and its `.sha256` file, verifies the checksum, and only then replaces the target file. The existing file is kept if any step fails.
- Temporary files go to `.agents/il2cpp` (change with `--work-dir`).

### Upload (maintainers)

After a game update, replace the Release data with a dump from the new version (REFramework):

```powershell
python -m sdk.il2cpp upload --dump "D:/path/il2cpp_dump.json" --dry-run   # compress and checksum only
python -m sdk.il2cpp upload --dump "D:/path/il2cpp_dump.json"
```

- Existing assets with the same name are replaced; `build-data` is never marked as the latest Release.
- `--compresslevel 1-9` sets the gzip level (default 9). `--release-title` and `--release-notes` change the Release title and notes.

### Common options

| Option | Meaning |
|---|---|
| `--repo owner/name` | Target repository; defaults to `GITHUB_REPOSITORY`, then the `origin` remote, then `gh repo view` |
| `--tag` | Release tag, default `build-data` |
| `--asset` | Compressed asset name, default `<dump file name>.gz` |

## Monster battle logic SDK (`sdk.enemy_logic_exporter`)

The SDK only reads game files; it never runs or injects into the game. It rebuilds the control flow of each behavior table from the EXE's x64 instructions, combines it with resource arguments and IL2CPP metadata, and writes conditions, actions, and continuation points as JSON. Full research models stay in `.agents/enemy-logic-exporter`; `publish` slims them into `src/processed_data/enemy_battle_logic/models`, from which the pages are built.

The current models match game version **1.42.0.2** (`sdk/enemy_logic_exporter/data/profiles/`). Extraction refuses to run when the EXE or metadata belong to another version.

### Set up (Windows)

1. Install Python 3.13 (with the `py` launcher) and Git, and clone the repository.
2. From the repository root, run the setup script. It creates a virtual environment in `.agents/sdk-venv`, installs the pinned dependencies (Capstone, PyGhidra), and runs the environment check:

   ```powershell
   powershell -ExecutionPolicy Bypass -File sdk/enemy_logic_exporter/setup_env.ps1
   ```

3. Fix whatever the check reports as missing, then check again:

   ```powershell
   .agents/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env
   .agents/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env --verify   # also hashes the EXE and dump (slower)
   ```

| Item | How to provide it |
|---|---|
| Game EXE | Found in any Steam library by default; elsewhere, set `MHWS_EXE` or pass `--exe` |
| IL2CPP dump | `python -m sdk.il2cpp download`, or pass `--metadata` |
| Resource exports | `MHWS-in-json/natives` from the repository, or pass `--natives` |
| Resource line endings | Resource files must keep their exported LF bytes. If the check fails, delete the `MHWS-in-json` folder and run `git checkout -- MHWS-in-json` |
| Research caches `--index`, `--helpers`, `--inventory`, `--requests` | Copy the whole `.agents/enemy-logic-exporter` from an existing machine, or regenerate them as in [After a game update](#after-a-game-update) (needs Ghidra) |
| Work directory | `.agents/enemy-logic-exporter` by default; change it with `--work-dir` or `MHWS_SDK_WORK_DIR`, but it must stay inside the project's `.agents`. To keep caches on another disk, make `.agents` a directory junction |
| `GHIDRA_INSTALL_DIR`, `JAVA_HOME` | Only for `decompile` and `analyze`: install Ghidra 12.0.4 and a JDK it supports, then set both variables |

In the examples below, `python` is the interpreter of that virtual environment, and every command runs from the repository root. For all options of a command, run `python -m sdk.enemy_logic_exporter <command> --help`.

### Build the pages only

No SDK dependencies or game files are needed:

```powershell
python -m src.processed_data.enemy_battle_logic                     # release build into output/processed_data
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
python -m src.processed_data.enemy_battle_logic --template <model.json> --output .agents/one
```

Open `enemy_battle_logic/index.html` in the output folder. The pages work offline.

### Re-extract after a code change

`--exe` and the research cache options use their default locations when omitted. A full extraction takes about 15 minutes.

```powershell
$w = '.agents/enemy-logic-exporter/fix'
python -B -m sdk.enemy_logic_exporter extract --enemy EM0002_00_0 --output "$w/one"   # try one monster
python -B -m sdk.enemy_logic_exporter extract-all --output "$w/s1"                     # all 34
python -B -m sdk.enemy_logic_exporter player-view --models "$w/s1" --output "$w/s1p"  # player view
python -B -m sdk.enemy_logic_exporter census --models "$w/s1p"                         # conditions with unknown parts, by command and reason
python -B -m sdk.enemy_logic_exporter uncertainty --models "$w/s1p"                    # player-tree conditions still undecided with all inputs known
python -B -m sdk.enemy_logic_exporter publish --models "$w/s1p"                        # write the web models
python -B -m src.processed_data.enemy_battle_logic --output "$w/site"
python -B -m unittest discover -s tests/sdk -t .
```

Compare `unknownConditions` from `census` and `total.uncertain` from `uncertainty` before and after every change. `player-view` only accepts full models from `.agents`, not published ones.

### After a game update

You need the new EXE, a new IL2CPP dump (after `sdk.il2cpp upload`, other machines can download it), re-exported resources, and Ghidra.

```powershell
python -B -m sdk.enemy_logic_exporter check-env --verify
python -B -m sdk.enemy_logic_exporter resolve-symbols --version <new version>   # writes data/profiles/<new version>.json
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<new version>.json           # report first
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<new version>.json --apply   # move unchanged evidence
python -B -m sdk.enemy_logic_exporter analyze --version <new version> --output .agents/enemy-logic-exporter/full-run/result --cache-dir .agents/enemy-logic-exporter/full-run/native
python -B -m sdk.enemy_logic_exporter requests --index .agents/enemy-logic-exporter/full-run/native/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --output .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter recover --index .agents/enemy-logic-exporter/full-run/native/index.json --helpers .agents/enemy-logic-exporter/per-monster/helpers/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --requests .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter scheduler-slots
python -B -m sdk.enemy_logic_exporter roster --write
python -B -m sdk.enemy_logic_exporter new-monster --enemy <new monster ID>     # for each monster added to the roster
```

Then set `ACTIVE_GAME_VERSION` in `sdk/enemy_logic_exporter/shared/config.py` to the new version and run [Re-extract after a code change](#re-extract-after-a-code-change). Every item listed for review by `migrate-evidence` and every `changed` symbol from `resolve-symbols` must be checked against the native code; replacing a version number or digest proves nothing. The full review order is in the [SDK maintenance notes](../sdk/enemy_logic_exporter/AGENTS.md) (Chinese).

### Commands

| Command | What it does | Needs |
|---|---|---|
| `check-env` | Checks dependencies, game files, research caches, and Ghidra settings | — |
| `extract` / `extract-all` | Extracts the full research model of one or all monsters | EXE, dump, resources, research caches |
| `player-view` | Adds the player view (conditions and inputs used by the pages) | Full models |
| `census` | Counts conditions with unknown parts, by command and reason | Full models |
| `uncertainty` | Counts undecided conditions in the player battle tree | Full models with player view |
| `publish` | Drops research fields, shares repeated values, writes `src/processed_data/enemy_battle_logic/models` | Full models with player view |
| `resolve-symbols` | Writes the symbol address profile for a new version | EXE, dump |
| `migrate-evidence` | Moves evidence rows whose bytes did not change; lists the rest for review | EXE, dump, new profile |
| `scheduler-slots` | Recovers the behavior-table slots requested by AI states and interrupts | EXE, dump |
| `roster` / `new-monster` | Updates the large-monster roster; creates an entry module for a new monster | Resources |
| `analyze` | Full resource and native evidence analysis that builds the research caches | EXE, dump, resources, Ghidra |
| `requests` / `recover` | Finds action requests; recovers arguments and command implementations per monster | Research caches, EXE |
| `manifest` / `decompile` / `verify` / `index` | New-version research: locate methods, decompile, verify bytes, build the native index | EXE, dump (`decompile` needs Ghidra) |

### Troubleshooting

- **"资源发现后行为表发生变化" (behavior table changed after resource discovery)**: resource bytes differ from the research caches, usually because Git converted line endings to CRLF. See "Resource line endings" above.
- **"原生配方的 EXE 来源变化" (EXE source changed) or a version mismatch**: the EXE or dump is not the version recorded in the profile. Check where the files came from; if the game was updated, follow [After a game update](#after-a-game-update).
- **"缺少研究缓存" (research caches missing)**: no caches at the standard location in `.agents/enemy-logic-exporter`. Run `check-env` for the paths, then copy or regenerate them.
- **Output must be inside `.agents`**: research output is restricted to the project's `.agents` so that large evidence caches never reach Git.
