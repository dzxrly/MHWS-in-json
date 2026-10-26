# SDK guide

English | [简体中文](docs/README.zh-Hans.md) | [繁體中文](docs/README.zh-Hant.md)

The `sdk/` directory is an offline SDK that reads the game files. `python -m sdk` opens its [menu](#menu-tui); each feature is also a module run from the repository root with `python -m`. One setup script and one requirements file (`sdk/setup_env.ps1`, `sdk/requirements.txt`) cover all of them:

| Feature | Purpose | External files |
|---|---|---|
| `sdk.enemy_logic_exporter` | Extracts monster battle logic from the dumped game EXE, IL2CPP metadata, and resource exports, and writes the graph JSON used by the web pages | Dumped EXE, IL2CPP metadata, `MHWS-in-json` resources; some commands also need Ghidra |
| `sdk.skill_effect_exporter` | Finds the native functions that use each skill, evaluates them per skill level, and writes the skill effect link JSON behind `SkillDetails.xlsx` | Dumped EXE, IL2CPP metadata, `MHWS-in-json` resources |

Both features read the game EXE dumped from memory (for example `MonsterHunterWilds_dump.exe`), which you get anyway before REFramework writes `il2cpp_dump.json`; the shipped `MonsterHunterWilds.exe` is not used. You provide both files yourself; neither the repository nor a Release keeps a copy, and no path is guessed: pass `-e/--exe` and `-i/--il2cpp`, or set `MHWS_EXE` and `MHWS_IL2CPP`. The SDK records no game version or file hash. After a game update the commands simply fail where the code or data no longer match (a symbol cannot be located, native bytes differ), and the steps in [After a game update](#after-a-game-update) apply.

The SDK is not needed to rebuild the pages or workbooks without changing the extracted results: the builders only read the JSON committed to the repository (see [Build the pages only](#build-the-pages-only)).

## Common options

| Option | Meaning |
|---|---|
| `-e`, `--exe` | Dumped game EXE; required unless `MHWS_EXE` is set |
| `-i`, `--il2cpp` | REFramework `il2cpp_dump.json`; required unless `MHWS_IL2CPP` is set |
| `-n`, `--natives` | The `natives` folder of the resource exports, default `MHWS-in-json/natives` |
| `-o`, `--output` | Output location |
| `-m`, `--models` | Research model folder (`sdk.enemy_logic_exporter`) |
| `-w`, `--work-dir` | Research cache folder, given before the command (`sdk.enemy_logic_exporter`) |

## Set up (Windows)

1. Install Python 3.13 (with the `py` launcher) and Git, and clone the repository.
2. From the repository root, run the setup script. It creates a virtual environment in `.tmp/sdk-venv`, installs the pinned dependencies (Capstone, PyGhidra, questionary, rich), and runs the environment check:

   ```powershell
   powershell -ExecutionPolicy Bypass -File sdk/setup_env.ps1 -Exe <dumped EXE> -Il2cpp <il2cpp_dump.json>
   ```

3. Fix whatever the check reports as missing, then check again:

   ```powershell
   .tmp/sdk-venv/Scripts/python.exe -B -m sdk.enemy_logic_exporter check-env -e <dumped EXE> -i <il2cpp_dump.json>
   ```

| Item | How to provide it |
|---|---|
| Dumped EXE | The EXE dumped from the running game (e.g. `MonsterHunterWilds_dump.exe`); pass `-e` or set `MHWS_EXE` |
| IL2CPP dump | `il2cpp_dump.json` written by REFramework from the same game; pass `-i` or set `MHWS_IL2CPP` |
| Resource exports | `MHWS-in-json/natives` from the repository, or pass `-n` |
| Resource line endings | Resource files must keep their exported LF bytes. If the check fails, delete the `MHWS-in-json` folder and run `git checkout -- MHWS-in-json` |
| Research caches `--index`, `--helpers`, `--inventory`, `--requests` | Copy the whole `.tmp/enemy-logic-exporter` from an existing machine, or regenerate them as in [After a game update](#after-a-game-update) (needs Ghidra) |
| Work directory | `.tmp/enemy-logic-exporter` by default; change it with `-w` or `MHWS_SDK_WORK_DIR`, but it must stay inside the project's `.tmp`. To keep caches on another disk, make `.tmp` a directory junction |
| `GHIDRA_INSTALL_DIR`, `JAVA_HOME` | Only for `decompile` and `analyze`: install Ghidra 12.0.4 and a JDK it supports, then set both variables |

In the examples below, `python` is the interpreter of that virtual environment, every command runs from the repository root, and `MHWS_EXE` / `MHWS_IL2CPP` are set (otherwise add `-e` and `-i`). For all options of a command, run `python -m sdk.<tool> <command> --help`.

## Menu (TUI)

`python -m sdk` opens a menu for the common tasks: the environment check, skill effect extraction (all skills or chosen ones), rebuilding `SkillDetails.xlsx`, monster extraction with the player view, the census, publishing and building the battle logic pages, and the SDK tests. Choose with the arrow keys and Enter (the menu text is in Chinese). Each action first prints the exact command line and then runs it, so the same step can go into a script. The menu starts from `MHWS_EXE` / `MHWS_IL2CPP`; when they are not set it first asks for the dumped EXE and the IL2CPP dump, and "设置 EXE 与 il2cpp 路径" changes them for the session. Publishing asks before it overwrites the committed models. Long steps (skill extraction, `extract-all`, `player-view`, `publish`) show a progress bar with the count done, elapsed and remaining time, in the menu and on the command line (`sdk/progress.py`). The setup script registers the repository root in the virtual environment (`mhws_sdk.pth`), so the menu can be started from any directory; on an environment created before this change, run the setup script again.

```powershell
.tmp/sdk-venv/Scripts/python.exe -m sdk
```

## Monster battle logic SDK (`sdk.enemy_logic_exporter`)

The SDK only reads game files; it never runs or injects into the game. It rebuilds the control flow of each behavior table from the EXE's x64 instructions, combines it with resource arguments and IL2CPP metadata, and writes conditions, actions, and continuation points as JSON. Full research models stay in `.tmp/enemy-logic-exporter`; `publish` slims them into `src/processed_data/enemy_battle_logic/models`, from which the pages are built.

Function addresses come from `sdk/enemy_logic_exporter/data/profile.json`, which `resolve-symbols` regenerates from the current dumped EXE and IL2CPP dump.

### Build the pages only

No SDK dependencies or game files are needed. The pages are part of the [website](../README.md#website):

```powershell
python -m src.site_data                                         # release data, all 34 monsters
python -m src.site_data --enemy-models <folder> --preview --output .tmp/site-preview   # some monsters, e.g. freshly extracted
python -m src.site_data --enemy-template <model.json> --output .tmp/site-preview       # one monster
$env:MHWS_SITE_DATA = (Resolve-Path .tmp/site-preview)        # show the preview instead of the committed data
npm --prefix web run dev                                       # browse at http://localhost:5173
```

Without `--output` it rewrites the committed `src/site_data/data/`; commit it after `publish`. Previews must go elsewhere. See the [website](../README.md#website) for the web commands.

### Re-extract after a code change

`-e`, `-i`, and the research cache options use their default locations when omitted. A full extraction takes about 15 minutes.

```powershell
$w = '.tmp/enemy-logic-exporter/fix'
python -B -m sdk.enemy_logic_exporter extract --enemy EM0002_00_0 -o "$w/one"   # try one monster
python -B -m sdk.enemy_logic_exporter extract-all -o "$w/s1"                     # all 34
python -B -m sdk.enemy_logic_exporter player-view -m "$w/s1" -o "$w/s1p"         # player view
python -B -m sdk.enemy_logic_exporter census -m "$w/s1p"                         # conditions with unknown parts, by command and reason
python -B -m sdk.enemy_logic_exporter uncertainty -m "$w/s1p"                    # player-tree conditions still undecided with all inputs known
python -B -m sdk.enemy_logic_exporter publish -m "$w/s1p"                        # write the web models
python -B -m src.site_data                                                       # website JSON; commit src/site_data/data
python -B -m unittest discover -s tests/sdk -t .
```

Compare `unknownConditions` from `census` and `total.uncertain` from `uncertainty` before and after every change. `player-view` only accepts full models from `.tmp`, not published ones.

Compound conditions short-circuit in native order. The player view applies reviewed variable updates and resource limits before evaluating later conditions that read them. Ordinary state inputs still need confirmation after an action or an effect whose implementation is only partly recovered.

> Previous random interval: the last selection range saved in a behaviour table's private parameters, used to redirect the next random value.

Recovered intervals update along the selected path and survive an action. Only histories supported by evidence are expanded; other histories remain unknown. A constructor default is not the value on every table entry, and these selections must not be treated as independent draws.

Large full research models use compact JSON to retain all logic. If the compact file still exceeds 25 MiB, extraction fails and requires deduplication or sharding.

### After a game update

You need the new dumped EXE, its IL2CPP dump, re-exported resources, and Ghidra.

```powershell
python -B -m sdk.enemy_logic_exporter check-env
python -B -m sdk.enemy_logic_exporter resolve-symbols -o .tmp/enemy-logic-exporter/new-profile.json   # report moved/changed symbols
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile .tmp/enemy-logic-exporter/new-profile.json           # report first
python -B -m sdk.enemy_logic_exporter migrate-evidence --profile .tmp/enemy-logic-exporter/new-profile.json --apply   # move unchanged evidence
Copy-Item .tmp/enemy-logic-exporter/new-profile.json sdk/enemy_logic_exporter/data/profile.json
python -B -m sdk.enemy_logic_exporter analyze -o .tmp/enemy-logic-exporter/full-run/result --cache-dir .tmp/enemy-logic-exporter/full-run/native
python -B -m sdk.enemy_logic_exporter requests --index .tmp/enemy-logic-exporter/full-run/native/index.json --inventory .tmp/enemy-logic-exporter/full-run/result/inventory.json -o .tmp/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter recover --index .tmp/enemy-logic-exporter/full-run/native/index.json --helpers .tmp/enemy-logic-exporter/per-monster/helpers/index.json --inventory .tmp/enemy-logic-exporter/full-run/result/inventory.json --requests .tmp/enemy-logic-exporter/full-run/result/action-requests.json
python -B -m sdk.enemy_logic_exporter scheduler-slots
python -B -m sdk.enemy_logic_exporter roster --write
python -B -m sdk.enemy_logic_exporter new-monster --enemy <new monster ID>     # for each monster added to the roster
```

Then run [Re-extract after a code change](#re-extract-after-a-code-change). Every item listed for review by `migrate-evidence` and every `changed` symbol from `resolve-symbols` must be checked against the native code. The full review order is described in the [SDK maintenance notes](enemy_logic_exporter/AGENTS.md) (Chinese).

### Commands

| Command | What it does | Needs |
|---|---|---|
| `check-env` | Checks dependencies, game files, research caches, and Ghidra settings | — |
| `extract` / `extract-all` | Extracts the full research model of one or all monsters | EXE, dump, resources, research caches |
| `player-view` | Adds the player view (conditions and inputs used by the pages) | Full models |
| `census` | Counts conditions with unknown parts, by command and reason | Full models |
| `uncertainty` | Counts undecided conditions in the player battle tree | Full models with player view |
| `publish` | Drops research fields, shares repeated values, writes `src/processed_data/enemy_battle_logic/models` | Full models with player view |
| `resolve-symbols` | Regenerates the symbol address profile for the current EXE (`data/profile.json` by default) | EXE, dump |
| `migrate-evidence` | Moves evidence rows whose code did not change; lists the rest for review | EXE, dump, new profile |
| `scheduler-slots` | Recovers the behavior-table slots requested by AI states and interrupts | EXE, dump |
| `roster` / `new-monster` | Updates the large-monster roster; creates an entry module for a new monster | Resources |
| `analyze` | Full resource and native evidence analysis that builds the research caches | EXE, dump, resources, Ghidra |
| `requests` / `recover` | Finds action requests; recovers arguments and command implementations per monster | Research caches, EXE |
| `manifest` / `decompile` / `verify` / `index` | New-build research: locate methods, decompile, verify bytes, build the native index | EXE, dump (`decompile` needs Ghidra) |

### Troubleshooting

- **"资源发现后行为表发生变化" (behavior table changed after resource discovery)**: resource bytes differ from the research caches, usually because Git converted line endings to CRLF. See "Resource line endings" above.
- **"原生字节不匹配" / "Native evidence mismatch" (native bytes changed) or "辅助函数特征不唯一或失效" (helper pattern not unique)**: the EXE's code differs from what the profile and research caches were built on — the game was updated, or the shipped EXE was passed instead of the dumped one. Check `-e`; after a game update follow [After a game update](#after-a-game-update).
- **"the following arguments are required: -e/--exe" or "-i/--il2cpp"**: pass the dumped EXE and the IL2CPP dump, or set `MHWS_EXE` / `MHWS_IL2CPP`.
- **"缺少研究缓存" (research caches missing)**: no caches at the standard location in `.tmp/enemy-logic-exporter`. Run `check-env` for the paths, then copy or regenerate them.
- **Output must be inside `.tmp`**: research output is restricted to the project's `.tmp` so that large evidence caches never reach Git.

## Skill effect SDK (`sdk.skill_effect_exporter`)

The game has no table mapping skills to effect values: the four SkillData value slots are unnamed, and fields in parameter files such as `PlayerSkillParam` carry no skill ID; the two are only connected in native code. This tool scans the EXE for every function that calls a skill accessor with a skill ID. It then executes those functions instruction by instruction in a scenario where only that skill is equipped at one level, enumerating Boolean and enum arguments. For each result it records the return value, the runtime conditions, and whether the number came from a SkillData slot, a parameter file field, or an EXE constant. The result goes to `src/processed_data/skill_details/data/skill_links/` (`index.json` plus one shard per skill category); the PROCESSED_DATA build turns it into `SkillDetails.xlsx`.

```powershell
python -B -m sdk.skill_effect_exporter extract -e <dumped EXE> -i <il2cpp_dump.json>   # all skills, about 30 minutes, writes the committed location
python -B -m sdk.skill_effect_exporter extract -s HunterSkill_019 -o .tmp/skill-effects/try.json   # debug one skill
python -B -m sdk.skill_effect_exporter extract --all-links -o .tmp/skill-effects/all   # also evaluate the functions skill modules skip (after a game update)
python -B -m sdk.skill_effect_exporter annotate                                    # copy the skill modules' meanings and notes into index.json, no evaluation
python -B -m sdk.skill_effect_exporter new-skill -s HunterSkill_250                # empty module for a skill new to the skill table
python -m src.processed_data.skill_details                                         # rebuild SkillDetails.xlsx only
```

- The 技能效果 (effects) sheet of `SkillDetails.xlsx` has one row per skill level (`Lv.X`) and effect, with the in-game skill and level descriptions and the weapons, ammo kinds or actions it applies to ("【weapon】ammo"). It keeps only numbers read from game parameters, prefers the skill's own `getSkill*` accessors over functions that combine several sources, and leaves out values that only appear without the skill or with a meal effect on top. Each skill has a module `sdk/skill_effect_exporter/skills/hunterskill_<n>.py` holding the reviewed meaning of each of its shown effects (`MEANINGS`: name, what it applies to, how, when, unit, the code it was read from, and names for the situations a value depends on) and verified notes (`NOTES`); `extract` copies them into `index.json`, and `annotate` does only that after editing a module. Effects without a meaning are named from the accessor name (`src/processed_data/skill_details/labels.py`); the accessor name itself is in the last column. A value that depends on the situation, such as the hit count for 连击 (Burst), gets one row per situation; "a / b" remains only where nothing in the code tells the values apart.
- The link JSON keeps what the workbook leaves out: function addresses, arguments, runtime conditions, data sources, EXE constants and functions not emulated.
- It uses the same virtual environment (Capstone).
- A function that reads the hunter's equipped weapon type (`HunterCharacter._HunterComp.Prepare.<WeaponBuilder>k__BackingField._EquippedWeaponType`) or a bowgun ammo kind (`app.WeaponGunDef.SHELL_TYPE` or `SHELL_PARAM_TYPE`, also when a call returns it or writes it to an `out` argument) is evaluated once per value. The link JSON records the value as the argument "武器", "弹种" or "弹药参数类型". The list is `DIMENSIONS` in `sdk/skill_effect_exporter/config.py`.
- Some `cHunterSkill` accessors return a level or a rate whose effect is decided by their callers, for example `getSkillDodgeNoHitLv`, whose caller `getDodgeNoHitTime` gives the invulnerable time per dodge action. Callers of accessors that read at most `MAX_ACCESSOR_SKILLS` skills are evaluated as well; their links record the use as `accessor`.
- A function that exceeds the path or instruction limits is evaluated again keeping only the paths that can still reach the skill's call site, with other calls left opaque; those paths are marked `focused`. "只追踪可能经过技能读取点的路径仍超限" means the skill may be used there (for that weapon or ammo kind) but its number is still incomplete. Calls given skill parameters (a parameter block or a value read from one) still run inline. When the focused run exceeds a limit too, it is narrowed: before the call site, of two branches that both lead there only the nearer one is taken, so one combination of the earlier runtime conditions is followed (paths marked `narrow`, details "只沿最近分支追踪到技能读取点仍超限" when even that is too large). Large per-frame functions such as `cHunterSkill.update` are evaluated this way.
- Paths with the same result whose conditions differ only in one condition and its negation are merged, so conditions that do not change the result are left out. At most `MAX_RECORDED_PATHS` paths are kept per case, those with the fewest conditions first; a final row says how many were left out.
- Usage tracing: each link except the `getSkill*`/`isSkill*` accessors themselves is evaluated once more at the highest level with the skill reads (`getSkillValue`, `getSkillLevelCore`, `checkSkillActive`, or a called accessor) replaced by named unknowns such as `技能等级〈HunterSkill_019〉()`. Its `usage` field shows what the skill's values are compared with, multiplied by and written to, under which conditions; the numbers themselves stay in `results`.
- Parameter fields that no evaluated path read a value from (found by a static scan of reads through the `PlayerGlobalParam` singleton) are evaluated again in the functions that read them and use a skill, focused on the read instruction; these links record the use as `param`. For example the +5 attack of Ballistics (弹道强化) level 3 at critical distance is read inside the bowgun and bow hit handlers. The effects sheet also shows such a caller when it reads data the skill's accessors do not, named after that data. A field read only by a function that uses no skill itself (`cHunterSkillParamInfo.beginKnight`, `cHunterSkill.beginRyunyu`) is evaluated through the skill-using functions that call it within two calls, focused on those calls, so the value is attributed to the skill those callers check.
- When a branch compares a value from the game data (such as the hitzone threshold of Mind's Eye, `_Shingan_MeatThreshold`), the path lists it under `compared`.
- `index.json` has a `coverage` section: for each skill parameter file (`PlayerSkillParam`, `PlayerMealSkillParam` and the other `PlayerGlobalParam` fields whose type ends in `SkillParam`), every field with the functions that read it and the skills whose paths returned it (`value`), wrote it to runtime state (`write`) or compared it (`compare`); for each skill, the non-zero SkillData slots and the slots used in the same three ways. Items with none of these are effects the workbook may still miss.
- The effects sheet also lists numbers a handler writes into runtime state (a duration stored when the skill activates; effect names starting with "写入" keep the field name), and values only read outside the skill's accessors. Either shows only when the data item is not already shown and no other skill's links use it, which keeps functions that sum many skills from adding other skills' data.
- The output records no game version or digests; run `extract` again after updating the game or `MHWS-in-json`.
- Functions that add up many skills (such as total attack) depend on other skills' timers and other runtime state, so the link JSON may record them as `too_many_paths`; the exact numbers of a skill usually come from its `getSkill*` accessors.
- Like the enemy logic SDK, shared code is in `sdk/skill_effect_exporter/shared/` and each skill has its own module in `skills/`: its extraction steps (`extract`, then `extract_parameters` once every skill's links exist; mostly thin calls of the shared steps, with any handling that belongs to that skill alone, such as functions the scan cannot tie to the skill, listed in `DECLARED_METHODS` with the reviewed evidence, and functions that give the skill no shown value, listed in `SKIPPED_FUNCTIONS` and kept as links without being evaluated), the meanings of its shown effects and its notes. Notes that hold for every skill are in `notes.py` and version-dependent layout constants in `config.py`, both at the top of `sdk/skill_effect_exporter/`. What to check after a game update is in the [skill effect SDK maintenance notes](skill_effect_exporter/AGENTS.md) (Chinese).
