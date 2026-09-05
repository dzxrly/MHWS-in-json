<div align="center">

# MHWS-in-json

English | [简体中文](docs/README.zh-Hans.md) | [繁體中文](docs/README.zh-Hant.md)

</div>

Exports MHWS game data to JSON and Excel. The output layout follows [eigeen/mhws-data-dump-scripts](https://github.com/eigeen/mhws-data-dump-scripts) and [dtlnor/MHWs-in-json](https://github.com/dtlnor/MHWs-in-json).

<div align="center">

<a href="https://github.com/dzxrly/PyREUser3">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-dark.svg">
    <img alt="Powered by PyREUser3" src="https://raw.githubusercontent.com/dzxrly/PyREUser3/branding/powered-by-pyreuser3-light.svg">
  </picture>
</a>

</div>

## Outputs

Running `python main.py` writes the following files to `output/`:

- `output/<language>/*.xlsx`: localized database workbooks.
- `output/<language>/FullText.xlsx`: message GUIDs and localized text grouped as available, rejected, then empty. Source order is retained within each group. Rejected text starts with `[#Rejected#]`; unmarked empty text stays blank.
- `output/<language>/AmuletCollection.xlsx`: normalized amulet, skill, and slot pools. Names are localized, rarity uses `Rare.X`, and weapon and armor slots are separate. Slot levels use `Lv.X`. `SkillPool` stores each skill-point pool in its own column as `Skill Name Lv.X`.
- `output/<language>/WeaponActionValues.xlsx`: one sheet per weapon plus `Ammo`. Action and resource mappings are identified separately; requestSets with neither mapping stay at the bottom with a blank `MappingName` cell and orange fill.
- `output/DATABASE_<language>_<version>.zip`: one release asset per language. Each zip contains only that language's xlsx files and does not include `MHWS-in-json/`.
- `output/processed_data/`: language-independent processed files from the extra converter flow.
- `output/PROCESSED_DATA_<version>.zip`: one language-independent release asset containing `skill_pool.json`, `amulet_pool.json`, `graphic_preset.xlsx`, `Bowgun_Custom.xlsx`, `HeavyBowgun.xlsx`, and `LightBowgun.xlsx`.
- `output/MHWS-in-json_<version>.zip`: one shared source JSON release asset containing the `MHWS-in-json/` directory.

Archives use the maximum deflate compression level. The source JSON is packaged once rather than copied into every language archive.
Bowgun workbooks in `PROCESSED_DATA` are exported in Simplified Chinese only.
Languages whose text index is `-1` in any message file are skipped.
Progress and packaging details are printed to the terminal.

### Action-value mapping

`WeaponActionValues.xlsx` reads mappings only from `MHWS-in-json/ActionMap.json` (`_format = mhws_static_action_request_set_map_v2`). Generate this file locally with `motlist-to-json action-map` using inputs from the same game version: the executable dump, `il2cpp_dump.json`, motbank/motlist resources, PAK file list, and MHWS JSON. Version 1 is not accepted. Set `MHWS_ACTION_MAP_PATH` to test a file elsewhere. CI reads the committed package and does not need the generator inputs.

The package includes `MHWS-in-json/schema/action-map-v2.schema.json` and `MHWS-in-json/schema/motlist-action-tracks-v1.schema.json` for validating ActionMap v2 and motlist action-track JSON respectively.

Only player attack-value requestSets are exported. Nested values are flattened to leaf columns, and an RS is repeated for every action or resource mapping edge. `MappingKind`, stable identity, internal-name, name-source, resource-role, confidence, condition, and provenance columns make the two relation types explicit.

`MappingNameSource` records where the base `MappingName` came from. It describes name provenance, not the strength of the mapping. The generator can emit the following values; `+request_set_resource_marker` is appended to a base source when a requestSet resource marker distinguishes an inferred variant.

| `MappingNameSource` value | Meaning |
| --- | --- |
| `action_guide_message` | Localized text addressed by the ActionGuide message GUID. |
| `action_internal_fallback` | The action has no usable ActionGuide message GUID; its fallback or internal name is used. |
| `weapon_gun_static_item_table` | Ammo name and message GUID from the WeaponGun static item table. |
| `shell_fixed_enum` | Fixed enum name from the ShellList entry. |
| `main_param_stem` | Filename stem of the shell's main-parameter resource. |
| `prefab_stem` | Filename stem of the shell PFB. |
| `generated_shell_identity` | Generated `<scope>_SHELL_<fixed_id>` name when the shell has no better name source. |
| `rcol_filename` | RCOL filename stem used by an RCOL structural fallback. |
| `<base>+request_set_resource_marker` | The base source plus a requestSet resource marker; the marker is also appended to `MappingName` in brackets. |

`MappingConfidence` is a categorical evidence grade for the relation, not a probability.

| `MappingConfidence` value | Meaning |
| --- | --- |
| `proven` | Exact static evidence directly connects the action or resource to the requestSet, such as action/motion evidence or a ShellList → PFB → RCOL chain. |
| `derived` | The relation is inferred from established static structure, such as a shell relation without an exact action-name hash or a repeated requestSet offset paired with a resource marker. |
| `structural` | PFB/RCOL structure establishes that the requestSet belongs to the referenced RCOL, but does not safely identify a more specific shell; the row is an explicit RCOL fallback. |

Both columns are blank for an unmapped requestSet.

`MappingCondition` preserves supplied conditions, including collider roles, ammo levels and unverified activation. Nonempty conditions wrap and increase the row height within Excel's limit. A derived family name does not confirm collider activation.

`actionRelations` and `resourceRelations` are separate arrays. Every edge targets the exact identity `(scope, rcol, requestSetID, keyHash, sourceRequestSetOrdinal)`; export stops on a stale target or conflicting edge. Missing localization GUIDs use generated internal/resource names instead of requiring a manual mapping. Many-to-many identities remain separate even when their localized display text is the same. Resource relations include exact ShellList/PFB/RCOL evidence, automatically inferred variants, and an explicit RCOL structural fallback.

Row 1 of each sheet lists the RCOL source paths, and row 2 contains the headers. Data rows omit the repeated `rcol` path.

The first five columns are `MappingName`, `MappingInternalName`, `MappingConfidence`, `_Attack`, and `_FixAttack`, in that order, and remain frozen when scrolling. The remaining original data columns keep their source order, followed by the remaining mapping columns.

## Usage

```powershell
conda activate torch
python -m pip install -r requirements.txt
python main.py
```

No command-line arguments are used. Edit [config.py](config.py) to change paths, selected languages, output names, and version settings.
