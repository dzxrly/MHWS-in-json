"""Skill effect values for the website, from the same links as SkillDetails.xlsx.

Values, applicability and situations come from the workbook exporter's
functions, so the page and the workbook follow one set of rules.
"""

from __future__ import annotations

import json
from pathlib import Path

from config import SUPPORT_FILES, ZH_HANS_LANGUAGE_ID
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource

from src.processed_data.skill_details.exporter import (
    MEANING_COLUMNS,
    SKILL_DATA,
    applies_texts,
    bare_method,
    build_sheets,
    cartesian_blocks,
    cell_value,
    effect_links,
    effect_points,
    load_links,
)

OUTPUT_NAME = "skill_details/skills.json"
CATEGORY_NAMES = {
    "WEAPON": "武器技能",
    "EQUIP": "防具技能",
    "SERIES": "系列技能",
    "GROUP": "组合技能",
}
UNLISTED = "未列出"
READING_NOTES = [
    "每个效果一张小表：列是技能等级，行是适用的武器、弹种、动作或情形；与上一等级相比变化的数值加粗显示",
    "“倍率”是乘算系数（1.05 即提高 5%），“加算”是直接加上的数值，“概率”是百分比；时间、距离等数值保留游戏内部单位，未换算",
    "“适用”为“全部”表示对所有武器、弹种和动作都相同；同一等级在不同情形下（如连续命中次数）取不同数值时分行列出",
    "只在其他效果（饭技、狩猎笛旋律、武器自身状态）生效时才出现的数值不列出；随机判定的效果写作发动概率（如 80%）",
    "仍写作“a / b”的数值，是代码中找不到区分条件的几种取值",
    "“作用于”“计算”“条件”“单位”是对照代码中数值的用途整理的；标注“游戏说明”的内容取自技能说明，标注“推测”“未核实”的内容尚无代码证据",
    "效果名称以“写入”开头的，是技能发动等处理写入运行时字段的数值（如持续时间），名称保留代码中的字段名",
    "按“只装备该技能”的情境求值；本页没有效果数值时标为“未提取到数值”，发动条件请查看技能说明与已核实备注",
]


def effect_tables(links: dict) -> dict[str, list[dict]]:
    """Per skill, its shown effects with one value table each.

    A table row is one applicability text and situation; it maps each level to
    the cell text of the workbook. Values and situations are those of the
    workbook's 技能效果 rows (build_sheets); only the grouping of weapons, ammo
    kinds and actions into rows is done across levels instead of per level."""
    meanings = links["meanings"]
    functions = links["functions"]
    out: dict[str, list[dict]] = {}
    for skill_id, entries in effect_links(links).items():
        effects = []
        for link, effect, key in entries:
            meaning = meanings.get(skill_id, {}).get(key, {})
            dims, domains, points = effect_points(link, meaning.get("情形"))
            # Points with the same values at every level share one row, so a
            # row reads across levels (the workbook groups each level alone).
            by_series: dict[tuple, list[tuple]] = {}
            for (point, situation), levels in points.items():
                series = tuple(
                    sorted(
                        (level, frozenset(values)) for level, values in levels.items()
                    )
                )
                by_series.setdefault((situation or "", series), []).append(point)
            rows: dict[tuple, dict] = {}
            for (situation, series), members in by_series.items():
                for block in cartesian_blocks(members):
                    for applies in applies_texts(dims, domains, block):
                        if (applies, situation) in rows:
                            raise ValueError(
                                f"{skill_id} {key} 的“{applies}”“{situation}”有多组数值"
                            )
                        rows[applies, situation] = {
                            "applies": applies,
                            "situation": situation,
                            "values": {
                                level: {
                                    "text": display(cell_value(set(values))),
                                    "unsure": len(values) > 1,
                                }
                                for level, values in series
                            },
                        }
            effects.append(
                {
                    "name": meaning.get("效果") or effect,
                    "key": key,
                    "code": bare_method(functions[link["function"]]),
                    "written": "written" in link,
                    "meaning": {
                        field: meaning.get(field, "")
                        for field in (*MEANING_COLUMNS, "依据")
                    },
                    "rows": sorted(
                        rows.values(),
                        key=lambda r: (r["applies"], r["situation"]),
                    ),
                }
            )
        out[skill_id] = effects
    return out


def display(value) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def build_site_data(
    repository: SourceRepository, text_source: TextSource, links: dict
) -> dict:
    """Skills in SkillCommonData order with names, level texts and effects."""
    overview = build_sheets(repository, text_source, links)["技能"]
    tables = effect_tables(links)
    skills: dict[str, dict] = {}
    for row in overview:
        skill = skills.setdefault(
            row["技能ID"],
            {
                "id": row["技能ID"],
                "category": CATEGORY_NAMES.get(row["类别"], row["类别"]),
                "name": row["简体中文名称"] or row["技能ID"],
                "ja": row["日文名称"],
                "explain": row["技能说明"],
                "openSkills": row["打开技能"],
                "notes": [n for n in row["说明"].split("\n") if n],
                "levels": [],
            },
        )
        if row["技能等级"]:
            skill["levels"].append(
                {
                    "level": int(row["技能等级"].removeprefix("Lv.")),
                    "explain": row["等级说明"],
                }
            )
    for skill_id in sorted(set(tables) - set(skills)):
        info = links["skills"].get(skill_id, {})
        skills[skill_id] = {
            "id": skill_id,
            "category": CATEGORY_NAMES.get(info.get("category"), UNLISTED),
            "name": skill_id,
            "ja": "",
            "explain": "",
            "openSkills": "",
            "notes": links["notes"]["skills"].get(skill_id, []),
            "levels": [{"level": lv, "explain": ""} for lv in info.get("levels", [])],
        }
    for skill_id, skill in skills.items():
        skill["effects"] = tables.get(skill_id, [])
        levels = {lv["level"] for lv in skill["levels"]}
        levels |= {
            level
            for effect in skill["effects"]
            for row in effect["rows"]
            for level in row["values"]
        }
        skill["levelColumns"] = sorted(levels)
    # Rejected message placeholders are not names or explanations. Keep the
    # game numbering for empty records, without changing named internal skills.
    common_rows = repository.table(SUPPORT_FILES["skill_common"])
    for row in common_rows:
        if row["skillId"] in skills and not text_source.text(
            row["skillExplain"], ZH_HANS_LANGUAGE_ID
        ):
            skills[row["skillId"]]["explain"] = ""
    empty_records = {
        row["skillId"]
        for row in common_rows
        if not text_source.text(row["skillName"], None)
        and not text_source.text(row["skillExplain"], None)
    }
    empty_records = {
        skill_id
        for skill_id in empty_records
        if skill_id in skills
        and not skills[skill_id]["levels"]
        and not skills[skill_id]["effects"]
    }
    remap = {row["skill"]: row["group"] for row in links["remap"]}
    for skill_id in empty_records:
        skill = skills[skill_id]
        skill.update(name=skill_id, ja="", explain="")
        target = remap.get(skill_id)
        if target in skills:
            skill["mappedSkill"] = {"id": target, "name": skills[target]["name"]}
    for skill_id, skill in skills.items():
        skill["openSkills"] = "、".join(
            skills.get(target, {}).get("name") or target
            for target in links["skills"].get(skill_id, {}).get("openSkills", [])
        )
    # An openSkill entry is a resource relation, not proof of code equivalence.
    # Preserve disagreements (currently including 093) without inventing remaps.
    for row in repository.table(SKILL_DATA):
        for target in row["openSkill"]:
            if target in empty_records and target not in remap:
                owner = skills[row["skillId"]]
                reference = {
                    "id": owner["id"],
                    "name": owner["name"],
                    "level": row["SkillLv"],
                }
                references = skills[target].setdefault("resourceOpenSkills", [])
                if reference not in references:
                    references.append(reference)
    categories = list(dict.fromkeys(s["category"] for s in skills.values()))
    return {
        "categories": categories,
        "skills": list(skills.values()),
        "notes": READING_NOTES,
        "generalNotes": links["notes"]["general"],
    }


def export_skill_data(
    output_dir: Path,
    repository: SourceRepository,
    text_source: TextSource,
    name: str = OUTPUT_NAME,
) -> Path:
    """The page data; the release ships the same content as one file."""
    data = build_site_data(repository, text_source, load_links())
    path = Path(output_dir) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return path
