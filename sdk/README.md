# SDK guide

English | [简体中文](README.zh-Hans.md) | [繁體中文](README.zh-Hant.md)

The `sdk/` directory holds two offline command-line tools. Run both from the repository root with `python -m`:

| Tool | Purpose | External files |
|---|---|---|
| `sdk.enemy_logic_exporter` | Extracts monster battle logic from the game EXE, IL2CPP metadata, and resource exports, and writes the graph JSON used by the web pages | Game EXE, IL2CPP metadata, `MHWS-in-json` resources; some commands also need Ghidra |
| `sdk.skill_effect_exporter` | Finds the native functions that use each skill, evaluates them per skill level, and writes the skill effect link JSON behind `SkillDetails.xlsx` | Game EXE, IL2CPP metadata, `MHWS-in-json` resources |

The IL2CPP metadata is the `il2cpp_dump.json` written by REFramework, and it must come from the same game version as the EXE. Like the EXE, you provide it yourself; neither the repository nor a Release keeps a copy. Both tools look for it in the same order: the `-i/--il2cpp` option, the `MHWS_IL2CPP` environment variable, then `il2cpp_dump.json` next to the EXE. The SHA-256 of the EXE and dump are registered only in `sdk/game_versions.json`; committed data and models record the game version number.

Neither tool is needed to rebuild the pages or workbooks without changing the extracted results: the builders only read the JSON committed to the repository (see [Build the pages only](#build-the-pages-only)).

## Common options

| Option | Meaning |
|---|---|
| `-e`, `--exe` | Game EXE; defaults to `MHWS_EXE`, then any Steam library |
| `-i`, `--il2cpp` | `il2cpp_dump.json` of the same version as the EXE; defaults to `MHWS_IL2CPP`, then the file next to the EXE |
| `-n`, `--natives` | The `natives` folder of the resource exports, default `MHWS-in-json/natives` |
| `-o`, `--output` | Output location |
| `-m`, `--models` | Research model folder (`sdk.enemy_logic_exporter`) |
| `-w`, `--work-dir` | Research cache folder, given before the command (`sdk.enemy_logic_exporter`) |

## Set up (Windows)

1. Install Python 3.13 (with the `py` launcher) and Git, and clone the repository.
2. From the repository root, run the setup script. It creates a virtual environment in `.agents/sdk-venv`, installs the pinned dependencies (Capstone, PyGhidra, questionary), and runs the environment check:

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
| Game EXE | Found in any Steam library by default; elsewhere, set `MHWS_EXE` or pass `-e` |
| IL2CPP dump | Export `il2cpp_dump.json` for the same version with REFramework and put it next to the EXE; elsewhere, set `MHWS_IL2CPP` or pass `-i` |
| Resource exports | `MHWS-in-json/natives` from the repository, or pass `-n` |
| Resource line endings | Resource files must keep their exported LF bytes. If the check fails, delete the `MHWS-in-json` folder and run `git checkout -- MHWS-in-json` |
| Research caches `--index`, `--helpers`, `--inventory`, `--requests` | Copy the whole `.agents/enemy-logic-exporter` from an existing machine, or regenerate them as in [After a game update](#after-a-game-update) (needs Ghidra) |
| Work directory | `.agents/enemy-logic-exporter` by default; change it with `-w` or `MHWS_SDK_WORK_DIR`, but it must stay inside the project's `.agents`. To keep caches on another disk, make `.agents` a directory junction |
| `GHIDRA_INSTALL_DIR`, `JAVA_HOME` | Only for `decompile` and `analyze`: install Ghidra 12.0.4 and a JDK it supports, then set both variables |

In the examples below, `python` is the interpreter of that virtual environment, and every command runs from the repository root. For all options of a command, run `python -m sdk.<tool> <command> --help`.

## Menu (TUI)

`python -m sdk` opens a menu for the common tasks: the environment check, skill effect extraction (all skills or chosen ones), rebuilding `SkillDetails.xlsx`, monster extraction with the player view, the census, publishing and building the battle logic pages, and the SDK tests. Choose with the arrow keys and Enter (the menu text is in Chinese). Each action first prints the exact command line and then runs it, so the same step can go into a script. The EXE and IL2CPP dump are found as on the command line; "设置 EXE 与 il2cpp 路径" changes them for the session. Publishing asks before it overwrites the committed models.

```powershell
.agents/sdk-venv/Scripts/python.exe -m sdk
```

## Monster battle logic SDK (`sdk.enemy_logic_exporter`)

The SDK only reads game files; it never runs or injects into the game. It rebuilds the control flow of each behavior table from the EXE's x64 instructions, combines it with resource arguments and IL2CPP metadata, and writes conditions, actions, and continuation points as JSON. Full research models stay in `.agents/enemy-logic-exporter`; `publish` slims them into `src/processed_data/enemy_battle_logic/models`, from which the pages are built.

The current models match game version **1.42.0.2** (`sdk/enemy_logic_exporter/data/profiles/`). The EXE and IL2CPP dump must match the digests registered for that version in `sdk/game_versions.json`; extraction refuses to run otherwise.

### Build the pages only

No SDK dependencies or game files are needed:

```powershell
python -m src.processed_data.enemy_battle_logic                     # release build into output/processed_data
python -m src.processed_data.enemy_battle_logic --preview-all --output .agents/battle-preview
python -m src.processed_data.enemy_battle_logic --template <model.json> --output .agents/one
```

Open `enemy_battle_logic/index.html` in the output folder. The pages work offline.

### Re-extract after a code change

`-e`, `-i`, and the research cache options use their default locations when omitted. A full extraction takes about 15 minutes.

```powershell
$w = '.agents/enemy-logic-exporter/fix'
python -B -m sdk.enemy_logic_exporter extract --enemy EM0002_00_0 -o "$w/one"   # try one monster
python -B -m sdk.enemy_logic_exporter extract-all -o "$w/s1"                     # all 34
python -B -m sdk.enemy_logic_exporter player-view -m "$w/s1" -o "$w/s1p"         # player view
python -B -m sdk.enemy_logic_exporter census -m "$w/s1p"                         # conditions with unknown parts, by command and reason
python -B -m sdk.enemy_logic_exporter uncertainty -m "$w/s1p"                    # player-tree conditions still undecided with all inputs known
python -B -m sdk.enemy_logic_exporter publish -m "$w/s1p"                        # write the web models
python -B -m src.processed_data.enemy_battle_logic --output "$w/site"
python -B -m unittest discover -s tests/sdk -t .
```

Compare `unknownConditions` from `census` and `total.uncertain` from `uncertainty` before and after every change. `player-view` only accepts full models from `.agents`, not published ones.

### After a game update

You need the new EXE, an IL2CPP dump of the same version, re-exported resources, and Ghidra.

```powershell
python -B -m sdk.enemy_logic_exporter check-env --verify
python -B -m sdk.enemy_logic_exporter resolve-symbols --version <new version>   # writes data/profiles/<new version>.json
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<new version>.json           # report first
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile sdk/enemy_logic_exporter/data/profiles/<new version>.json --apply   # move unchanged evidence
python -B -m sdk.enemy_logic_exporter analyze --version <new version> -o .agents/enemy-logic-exporter/full-run/result --cache-dir .agents/enemy-logic-exporter/full-run/native
python -B -m sdk.enemy_logic_exporter requests --index .agents/enemy-logic-exporter/full-run/native/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json -o .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter recover --index .agents/enemy-logic-exporter/full-run/native/index.json --helpers .agents/enemy-logic-exporter/per-monster/helpers/index.json --inventory .agents/enemy-logic-exporter/full-run/result/inventory.json --requests .agents/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter scheduler-slots
python -B -m sdk.enemy_logic_exporter roster --write
python -B -m sdk.enemy_logic_exporter new-monster --enemy <new monster ID>     # for each monster added to the roster
```

Then set `ACTIVE_GAME_VERSION` in `sdk/enemy_logic_exporter/shared/config.py` to the new version and run [Re-extract after a code change](#re-extract-after-a-code-change). Every item listed for review by `migrate-evidence` and every `changed` symbol from `resolve-symbols` must be checked against the native code; replacing a version number or digest proves nothing. Switching to another IL2CPP dump of the same game version, and the full review order, are described in the [SDK maintenance notes](enemy_logic_exporter/AGENTS.md) (Chinese).

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
- **"缺少 il2cpp dump" (il2cpp dump missing)**: no `il2cpp_dump.json` was found. Put it next to the EXE, or pass `-i` / set `MHWS_IL2CPP`.
- **"缺少研究缓存" (research caches missing)**: no caches at the standard location in `.agents/enemy-logic-exporter`. Run `check-env` for the paths, then copy or regenerate them.
- **Output must be inside `.agents`**: research output is restricted to the project's `.agents` so that large evidence caches never reach Git.

## Skill effect SDK (`sdk.skill_effect_exporter`)

The game has no table mapping skills to effect values: the four SkillData value slots are unnamed, and fields in parameter files such as `PlayerSkillParam` carry no skill ID; the two are only connected in native code. This tool scans the EXE for every function that calls a skill accessor with a skill ID. It then executes those functions instruction by instruction in a scenario where only that skill is equipped at one level, enumerating Boolean and enum arguments. For each result it records the return value, the runtime conditions, and whether the number came from a SkillData slot, a parameter file field, or an EXE constant. The result goes to `src/processed_data/skill_details/data/skill_links/` (`index.json` plus one shard per skill category); the PROCESSED_DATA build joins it with SkillCommonData and SkillData into `SkillDetails.xlsx`.

```powershell
python -B -m sdk.skill_effect_exporter extract                                     # all skills, about 20 minutes, writes the committed location
python -B -m sdk.skill_effect_exporter extract -e <EXE> -i <il2cpp_dump.json>      # explicit inputs
python -B -m sdk.skill_effect_exporter extract -s HunterSkill_019 -o .agents/skill-effects/try.json   # debug one skill
python -m src.processed_data.skill_details                                         # rebuild SkillDetails.xlsx only
```

- It uses the same virtual environment (Capstone).
- A function that reads the hunter's equipped weapon type (`HunterCharacter._HunterComp.Prepare.<WeaponBuilder>k__BackingField._EquippedWeaponType`) or a bowgun ammo kind (`app.WeaponGunDef.SHELL_TYPE` or `SHELL_PARAM_TYPE`, also when a call returns it or writes it to an `out` argument) is evaluated once per value. The workbook lists the value as the argument "武器", "弹种" or "弹药参数类型". The list is `DIMENSIONS` in `sdk/skill_effect_exporter/config.py`.
- Some `cHunterSkill` accessors return a level or a rate whose effect is decided by their callers, for example `getSkillDodgeNoHitLv`, whose caller `getDodgeNoHitTime` gives the invulnerable time per dodge action. Callers of accessors that read at most `MAX_ACCESSOR_SKILLS` skills are evaluated as well; their usage column reads "调用技能取值函数 …".
- A function that exceeds the path or instruction limits is evaluated again keeping only the paths that can still reach the skill's call site, with other calls left opaque; the rows are marked in the "求值范围" column. "只追踪可能经过技能读取点的路径仍超限" means the skill may be used there (for that weapon or ammo kind) but its number is still incomplete.
- Paths with the same result whose conditions differ only in one condition and its negation are merged, so conditions that do not change the result are left out. At most `MAX_RECORDED_PATHS` paths are kept per case, those with the fewest conditions first; a final row says how many were left out.
- The output records the game version only, not resource digests; run `extract` again after updating `MHWS-in-json`.
- Functions that add up many skills (such as total attack) depend on other skills' timers and other runtime state, so the workbook may show "分支过多，未完整求值" (too many branches, not fully evaluated) for them; the exact numbers of a skill usually come from its `getSkill*` accessors.
- Skills that need a written explanation are listed in `sdk/skill_effect_exporter/notes.py`; version-dependent layout constants live in `sdk/skill_effect_exporter/config.py`. What to check after a game update is in the [skill effect SDK maintenance notes](skill_effect_exporter/AGENTS.md) (Chinese).
