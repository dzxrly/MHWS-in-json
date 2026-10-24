"""SkillDetails.xlsx: SkillCommonData and SkillData joined, with native effect links.

The links come from ``data/skill_links/`` (``index.json`` plus one shard per
skill category), written offline by ``python -m sdk.skill_effect_exporter
extract``. This builder never reads the EXE or il2cpp dump. The links name the
game version they were extracted from; rerun the extractor after updating
MHWS-in-json to a new game version.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from config import (
    JAPANESE_LANGUAGE_ID,
    MAX_COLUMN_WIDTH,
    SUPPORT_FILES,
    ZH_HANS_LANGUAGE_ID,
)
from src.shared.excel.writer import write_workbook
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource

from .labels import DIMENSION_NAMES, ENUMS, WEAPON_CODES, effect_name, enum_label

OUTPUT_NAME = "SkillDetails.xlsx"
LINKS_DIR = Path(__file__).resolve().parent / "data" / "skill_links"
SKILL_DATA = "STM/GameDesign/Common/Equip/SkillData.user.3.json"
SCHEMA_VERSION = 1
DIMENSION_EXCLUDED = {"INVALID", "MAX"}
OWN_SOURCES = {"PlayerSkillParam", "SkillData"}
OTHER_SOURCES = {"PlayerMealSkillParam"}
# A condition that a meal effect is running, e.g. "_MealEffect._IsEffectActive != 0"
# or "_MealEffect._SkillParamInfo._Collab03BreakKingTimer > 0.0".
OTHER_ACTIVE = re.compile(r"_MealEffect\..*(!= 0|> 0)|^0 < .*_MealEffect\.")
READING_NOTES = [
    "技能效果表每行是一个效果在某个技能等级的数值；“倍率”是乘算系数（1.05 即提高 5%），“加算”是直接加上的数值，“概率”是百分比",
    "“适用”为空表示对所有武器、弹种和动作都相同；列出时只对这些武器、弹种或动作生效",
    "数值为“a / b”时，表示同一等级在不同战斗状态下（如连击段数、是否满足发动条件）取不同数值",
    "时间、距离等数值保留游戏内部单位，未换算",
    "没有把握翻译的动作、射击类型保留游戏内部名称（如 QUICK_SHOT、EX_FIELD），效果名称中的英文同理",
    "只列出从游戏参数读取到的数值；只有发动条件、没有数值的技能在“技能”表中标为“未提取到”",
    "“代码名称”是游戏中读取该数值的函数名，便于核对",
]


def load_links(directory: Path = LINKS_DIR) -> dict:
    """Reassemble the link document from index.json and its category shards."""
    directory = Path(directory)
    document = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    if document.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"技能链路索引版本不是 {SCHEMA_VERSION}：{directory}")
    listed = {entry["file"] for entry in document.pop("shards")}
    present = {path.name for path in directory.glob("*.json")} - {"index.json"}
    if listed != present:
        raise ValueError(
            f"技能链路分片与索引不一致：缺少 {sorted(listed - present)}，多出 {sorted(present - listed)}"
        )
    links = []
    for name in sorted(listed):
        shard = json.loads((directory / name).read_text(encoding="utf-8"))
        if (
            shard.get("schemaVersion") != SCHEMA_VERSION
            or shard.get("gameVersion") != document["gameVersion"]
        ):
            raise ValueError(f"技能链路分片的格式或游戏版本与索引不一致：{name}")
        links.extend(
            unpack_link(link, shard["strings"], shard["constants"])
            for link in shard["links"]
        )
    document["links"] = links
    return document


def unpack_link(link: dict, strings: list, constants: list) -> dict:
    """Replace string and constant table positions by their values."""
    if "results" not in link:
        return link

    def path(item):
        item = dict(item)
        for field in ("conditions", "sources", "opaque"):
            if field in item:
                item[field] = [strings[i] for i in item[field]]
        for field in ("expression", "detail"):
            if field in item:
                item[field] = strings[item[field]]
        if "constants" in item:
            item["constants"] = [constants[i] for i in item["constants"]]
        if "writes" in item:
            item["writes"] = [
                dict(
                    w,
                    target=strings[w["target"]],
                    **(
                        {"sources": [strings[i] for i in w["sources"]]}
                        if "sources" in w
                        else {}
                    ),
                    **(
                        {"constants": [constants[i] for i in w["constants"]]}
                        if "constants" in w
                        else {}
                    ),
                )
                for w in item["writes"]
            ]
        return item

    results = link["results"]
    groups = [
        dict(group, paths=[path(p) for p in group["paths"]])
        for group in results["groups"]
    ]
    return dict(link, results=dict(results, groups=groups))


def cartesian_blocks(points: list[tuple]) -> list[list[set]]:
    """Split distinct points into blocks whose per-dimension value sets multiply out
    to exactly the block's points, so a row never implies combinations it lacks."""
    if len(points[0]) == 1:
        return [[{p[0] for p in points}]]
    lasts: dict[tuple, set] = {}
    for p in points:
        lasts.setdefault(p[:-1], set()).add(p[-1])
    by_last: dict[frozenset, list[tuple]] = {}
    for prefix, values in lasts.items():
        by_last.setdefault(frozenset(values), []).append(prefix)
    return [
        block + [set(values)]
        for values, prefixes in by_last.items()
        for block in cartesian_blocks(prefixes)
    ]


def sourced(path: dict) -> bool:
    """A finished path whose value was read from game data, not a code fallback."""
    return path["status"] == "ok" and "value" in path and bool(path.get("sources"))


def own_values(paths: list[dict]) -> list[dict]:
    """The data-sourced paths that show the skill's own effect.

    A path reading only PlayerGlobalParam is the value without the skill; one
    that reads PlayerMealSkillParam, or runs with a meal effect active (the meal
    raises the skill level), stacks a meal effect on top. Both are dropped when
    a path reads the skill's own parameters alone."""
    paths = [p for p in paths if sourced(p)]
    own = []
    for path in paths:
        roots = {re.split(r"[.\[]", source, 1)[0] for source in path["sources"]}
        if (
            roots & OWN_SOURCES
            and not roots & OTHER_SOURCES
            and not any(OTHER_ACTIVE.search(c) for c in path.get("conditions", []))
        ):
            own.append(path)
    return own or paths


def bare_method(function: dict) -> str:
    return re.sub(r"\d+$", "", function.get("method") or "")


def effect_links(links: dict) -> dict[str, list[dict]]:
    """Per skill, the links shown in the simplified sheet.

    Only links with data-sourced values count. Level getters are dropped when the
    skill has anything else, and the skill's own getters (getSkill*/isSkill*)
    win over callers that combine them with other state."""
    functions = links["functions"]
    chosen: dict[str, list[dict]] = {}
    for link in links["links"]:
        results = link.get("results")
        if results and any(
            sourced(p) for group in results["groups"] for p in group["paths"]
        ):
            chosen.setdefault(link["skill"], []).append(link)
    for skill, own in chosen.items():
        method = {id(l): bare_method(functions[l["function"]]) for l in own}
        effects = [
            l for l in own if not re.search(r"(Lv|Level)$", method[id(l)])
        ] or own
        direct = [
            l
            for l in effects
            if method[id(l)].lower().startswith(("getskill", "isskill"))
        ]
        chosen[skill] = direct or effects
    return chosen


def effect_points(link: dict) -> tuple[list[str], dict, dict]:
    """(dimensions, domains, {point: {level: values}}) of one link.

    A point holds one label per dimension (None when it does not apply). Boolean
    arguments are dropped because the dump does not name them; the weapon a data
    path belongs to (``_Wp11Data`` and so on) stands in for them when the
    function has no weapon dimension of its own."""
    results = link["results"]
    keys, domains = {}, {}
    for key, labels in results["argDomains"].items():
        raw = key.split(":", 1)[-1]
        if raw == "Boolean":
            continue
        name = DIMENSION_NAMES.get(raw, raw)
        keys[key] = name
        domains.setdefault(name, set()).update(set(labels) - DIMENSION_EXCLUDED)
    dims = list(dict.fromkeys(keys.values()))
    inferred = "武器" not in dims
    if inferred:
        dims.append("武器")
    points: dict[tuple, dict[int, set]] = {}
    for group in results["groups"]:
        paths = own_values(group["paths"])
        if not paths:
            continue
        values = {p["value"] for p in paths}
        weapons = {
            WEAPON_CODES[code]
            for p in paths
            for source in p["sources"]
            for code in re.findall(r"Wp\d\d", source)
            if code in WEAPON_CODES
        }
        for case in group["cases"]:
            labels = dict.fromkeys(dims)
            for key, name in keys.items():
                labels[name] = labels[name] or case["args"].get(key)
            if inferred and len(weapons) == 1:
                labels["武器"] = next(iter(weapons))
            levels = points.setdefault(tuple(labels.values()), {})
            levels.setdefault(case["level"], set()).update(values)
    return dims, domains, points


def applies_texts(dims: list[str], domains: dict, block: list[set]) -> list[str]:
    """Texts such as "【重弩、轻弩】散弹": weapons in brackets, then ammo kinds or
    actions. Actions named after one weapon (``WP03_MIKIRI``) go under that
    weapon; a block mixing them with general actions becomes one text per
    weapon so that every text has at most one bracket."""
    weapons, parts, by_weapon = "", [], {}
    for name, labels in zip(dims, block):
        labels = labels - {None} - DIMENSION_EXCLUDED
        domain = domains.get(name, set())
        if not labels or (len(domain) > 1 and labels >= domain):
            continue
        order = list(ENUMS.get(name, {}))
        labels = sorted(
            labels, key=lambda v: (order.index(v) if v in order else len(order), v)
        )
        if name == "武器":
            weapons = "、".join(enum_label(name, label) for label in labels)
            continue
        plain = []
        for label in labels:
            prefix = re.match(r"WP(\d\d)_(.+)", label)
            weapon = prefix and WEAPON_CODES.get(f"Wp{prefix.group(1)}")
            if weapon:
                text = ENUMS.get(name, {}).get(label, prefix.group(2))
                by_weapon.setdefault(weapon, []).append(text)
            else:
                plain.append(enum_label(name, label))
        if plain:
            parts.append("、".join(plain))
    texts = []
    if parts or not by_weapon:
        texts.append((f"【{weapons}】" if weapons else "") + "；".join(parts))
    texts += [
        f"【{enum_label('武器', weapon)}】" + "、".join(actions)
        for weapon, actions in by_weapon.items()
    ]
    return texts


def level_text(level: int) -> str:
    return f"Lv.{level}"


def cell_value(values: set):
    # Single-precision values: 6 significant digits drop the float32 tail.
    values = {float(f"{v:.6g}") if isinstance(v, float) else v for v in values}
    if len(values) == 1:
        (value,) = values
        return ("是" if value else "否") if isinstance(value, bool) else value
    return " / ".join(
        ("是" if v else "否") if isinstance(v, bool) else f"{v:g}"
        for v in sorted(values)
    )


def build_sheets(
    repository: SourceRepository, text_source: TextSource, links: dict
) -> dict[str, list[dict]]:
    """技能效果: one row per skill level and effect; 技能: SkillCommonData x SkillData."""
    zh = text_source.build(ZH_HANS_LANGUAGE_ID)
    ja = text_source.build(JAPANESE_LANGUAGE_ID)
    common_rows = [
        row
        for row in repository.table(SUPPORT_FILES["skill_common"])
        if row["skillId"] != "NONE"
    ]
    names = {
        row["skillId"]: (
            ja.get(row["skillName"]) or "",
            zh.get(row["skillName"]) or "",
            zh.get(row["skillExplain"]) or "",
        )
        for row in common_rows
    }
    levels_of = {}
    for row in repository.table(SKILL_DATA):
        if row["skillId"] != "NONE":
            levels_of.setdefault(row["skillId"], []).append(row)
    level_explain = {
        (skill_id, row["SkillLv"]): zh.get(row["skillExplain"]) or ""
        for skill_id, rows in levels_of.items()
        for row in rows
    }
    skills = links["skills"]
    functions = links["functions"]
    chosen = effect_links(links)
    effects = []
    order = [row["skillId"] for row in common_rows]
    order += sorted(set(chosen) - set(order))
    for skill_id in order:
        ja_name, zh_name, explain = names.get(skill_id, ("", "", ""))
        rows = []
        for link in chosen.get(skill_id, []):
            function = functions[link["function"]]
            dims, domains, points = effect_points(link)
            # Per level, points with the same values share one row.
            by_level: dict[tuple, list[tuple]] = {}
            for point, levels in points.items():
                for level, values in levels.items():
                    by_level.setdefault((level, frozenset(values)), []).append(point)
            for (level, values), members in by_level.items():
                for block in cartesian_blocks(members):
                    for applies in applies_texts(dims, domains, block):
                        rows.append(
                            {
                                "技能ID": skill_id,
                                "日文名称": ja_name,
                                "简体中文名称": zh_name,
                                "技能说明": explain,
                                "技能等级": level,
                                "数值": cell_value(set(values)),
                                "适用": applies,
                                "等级说明": level_explain.get((skill_id, level), ""),
                                "效果": effect_name(function["method"]),
                                "备注": (
                                    "数值随战斗状态不同" if len(values) > 1 else ""
                                ),
                                "代码名称": bare_method(function),
                            }
                        )
        rows.sort(key=lambda r: (r["技能等级"], r["效果"], r["适用"]))
        for row in rows:
            row["技能等级"] = level_text(row["技能等级"])
        effects += rows

    counted = {row["技能ID"] for row in effects}
    notes = links["notes"]["skills"]
    overview = []
    for row in common_rows:
        skill_id = row["skillId"]
        ja_name, zh_name, explain = names[skill_id]
        info = skills.get(skill_id, {})
        for data in sorted(levels_of.get(skill_id, []), key=lambda r: r["SkillLv"]) or [
            None
        ]:
            overview.append(
                {
                    "技能ID": skill_id,
                    "类别": row["skillCategory"],
                    "日文名称": ja_name,
                    "简体中文名称": zh_name,
                    "技能说明": explain,
                    "技能等级": level_text(data["SkillLv"]) if data else "",
                    "等级说明": (zh.get(data["skillExplain"]) or "") if data else "",
                    "打开技能": "、".join(
                        names.get(s, ("", s, ""))[1] or s
                        for s in info.get("openSkills", [])
                    ),
                    "效果数值": "见技能效果表" if skill_id in counted else "未提取到",
                    "说明": "\n".join(notes.get(skill_id, [])),
                }
            )

    remarks = [{"项目": "读法", "内容": text} for text in READING_NOTES]
    remarks += [
        {"项目": "通用说明", "内容": text} for text in links["notes"]["general"]
    ]
    remarks.append({"项目": "提取时的游戏版本", "内容": links["gameVersion"]})
    return {"技能效果": effects, "技能": overview, "说明": remarks}


def export_skill_details(
    output_dir: Path, repository: SourceRepository, text_source: TextSource
) -> Path:
    links = load_links()
    sheets = build_sheets(repository, text_source, links)
    return write_workbook(Path(output_dir) / OUTPUT_NAME, sheets, MAX_COLUMN_WIDTH)
