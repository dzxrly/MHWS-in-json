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

OUTPUT_NAME = "SkillDetails.xlsx"
LINKS_DIR = Path(__file__).resolve().parent / "data" / "skill_links"
SKILL_DATA = "STM/GameDesign/Common/Equip/SkillData.user.3.json"
SCHEMA_VERSION = 1
STATUS_TEXT = {
    "too_many_paths": "分支过多，未完整求值",
    "too_long": "指令过多，未完整求值",
    "unsupported": "未支持的指令或数据",
    "null": "经过空引用的路径",
    "throws": "异常路径",
    "writes_state": "会写入运行时状态，不是取值函数",
    "truncated": "路径过多，只列出条件最少的部分",
}
KIND_TEXT = {
    "value": "读取数值槽",
    "level": "读取等级",
    "active": "检查是否发动",
    "other": "其他",
}
ACCESSOR_KIND = (
    "accessor"  # the function calls a skill accessor, not a skill-argument method
)


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


def short_function(function: dict) -> str:
    if not function.get("type"):
        return f"未命名函数 {function['address']}"
    method = re.sub(r"\d+$", "", function["method"])
    return f"{function['type'].rsplit('.', 1)[-1]}.{method}"


def format_value(path: dict) -> str:
    if path["status"] != "ok":
        text = STATUS_TEXT.get(path["status"], path["status"])
        return f"{text}：{path['detail']}" if path.get("detail") else text
    if "value" in path:
        value = path["value"]
        if isinstance(value, bool):
            return "是" if value else "否"
        return f"{value:g}" if isinstance(value, float) else str(value)
    if "expression" in path:
        return f"表达式：{path['expression']}"
    return "无返回值"


def format_write(write: dict) -> str:
    value = write["value"]
    if isinstance(value, bool):
        value = "true" if value else "false"
    elif isinstance(value, float):
        value = f"{value:g}"
    sources = write.get("sources") or [
        f"EXE 常量 {c['address']}" for c in write.get("constants", [])
    ]
    return f"{write['target']} = {value}" + (
        f"（{'、'.join(sources)}）" if sources else ""
    )


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


def usage_text(use: dict) -> str:
    if use["kind"] == ACCESSOR_KIND:
        return f"调用技能取值函数 {use['helper'].rsplit('.', 1)[-1]}"
    return KIND_TEXT[use["kind"]]


def format_cases(cases: list[dict], domains: dict) -> list[tuple[str, str]]:
    """(levels, arguments) texts of a result group, one per Cartesian block."""
    keys = list(dict.fromkeys(key for case in cases for key in case["args"]))
    points = list(
        dict.fromkeys(
            (*(case["args"].get(key) for key in keys), case["level"]) for case in cases
        )
    )
    rows = []
    for *arg_sets, levels in cartesian_blocks(points):
        parts = []
        for key, labels in zip(keys, arg_sets):
            domain = domains.get(key, [])
            labels = sorted(
                labels - {None},
                key=lambda v: domain.index(v) if v in domain else len(domain),
            )
            if len(labels) == len(domain) and len(labels) > 1:
                parts.append(f"{key}=任意")
            elif len(labels) == 1:
                parts.append(f"{key}={labels[0]}")
            elif labels:
                parts.append(f"{key}∈{{{','.join(labels)}}}")
        rows.append((",".join(map(str, sorted(levels))), "；".join(parts)))
    return sorted(rows, key=lambda row: (int(row[0].split(",")[0]), row[1]))


def build_sheets(
    repository: SourceRepository, text_source: TextSource, links: dict
) -> dict[str, list[dict]]:
    zh = text_source.build(ZH_HANS_LANGUAGE_ID)
    ja = text_source.build(JAPANESE_LANGUAGE_ID)
    skills = links["skills"]
    names = {}
    common_rows = [
        row
        for row in repository.table(SUPPORT_FILES["skill_common"])
        if row["skillId"] != "NONE"
    ]
    for row in common_rows:
        names[row["skillId"]] = (
            ja.get(row["skillName"]) or "",
            zh.get(row["skillName"]) or "",
            zh.get(row["skillExplain"]) or "",
        )
    levels = {}
    for row in repository.table(SKILL_DATA):
        if row["skillId"] != "NONE":
            levels.setdefault(row["skillId"], []).append(row)

    def label(skill_id):
        name = names.get(skill_id, ("", "", ""))[1]
        return f"{skill_id}（{name}）" if name else skill_id

    functions = links["functions"]
    by_skill: dict[str, list[dict]] = {}
    for link in links["links"]:
        by_skill.setdefault(link["skill"], []).append(link)
    notes = links["notes"]["skills"]

    overview = []
    for row in common_rows:
        skill_id = row["skillId"]
        ja_name, zh_name, explain = names[skill_id]
        info = skills.get(skill_id, {})
        own = by_skill.get(skill_id, [])
        evaluated = sum(1 for link in own if link.get("results"))
        rows = sorted(levels.get(skill_id, []), key=lambda r: r["SkillLv"]) or [None]
        for data in rows:
            values = data["value"] if data else []
            overview.append(
                {
                    "技能ID": skill_id,
                    "类别": row["skillCategory"],
                    "日文名称": ja_name,
                    "简体中文名称": zh_name,
                    "技能说明": explain,
                    "等级": data["SkillLv"] if data else None,
                    "等级名称": (zh.get(data["skillName"]) or "") if data else "",
                    "等级说明": (zh.get(data["skillExplain"]) or "") if data else "",
                    **{
                        f"数值槽{i}": values[i] if i < len(values) else None
                        for i in range(4)
                    },
                    "打开技能": "、".join(label(s) for s in info.get("openSkills", [])),
                    "代码中的组合技能": (
                        label(info["groupSkill"]) if info.get("groupSkill") else ""
                    ),
                    "关联函数数": len(own),
                    "已求值函数数": evaluated,
                    "说明": "\n".join(notes.get(skill_id, [])),
                }
            )

    effects, pending = [], []
    order = [row["skillId"] for row in common_rows]
    # Skills the code references that SkillCommonData does not list (hidden or unused IDs).
    order += sorted(set(by_skill) - set(order))
    for skill_id in order:
        ja_name, zh_name, _ = names.get(skill_id, ("", "", ""))
        for link in sorted(
            by_skill.get(skill_id, []),
            key=lambda l: short_function(functions[l["function"]]),
        ):
            function = functions[link["function"]]
            base = {
                "技能ID": skill_id,
                "简体中文名称": zh_name,
                "日文名称": ja_name,
                "代码引用的技能": label(link["via"]) if link["via"] != skill_id else "",
                "函数": short_function(function),
                "函数地址": function["address"],
                "返回类型": function["returns"].rsplit(".", 1)[-1],
                "用法": "、".join(sorted({usage_text(use) for use in link["uses"]})),
            }
            results = link.get("results")
            if not results:
                reason = (
                    "无返回值（发动、更新等状态处理）"
                    if function["returns"] == "System.Void"
                    else (
                        "显示或同步用途，未求值"
                        if function["returns"] != "?"
                        else "无方法记录"
                    )
                )
                if not skills.get(skill_id, {}).get("levels"):
                    reason = "技能没有等级数据"
                pending.append({**base, "原因": reason})
                continue
            for group in results["groups"]:
                blocks = format_cases(group["cases"], results["argDomains"])
                for (level_text, args_text), path in (
                    (block, path) for block in blocks for path in group["paths"]
                ):
                    effects.append(
                        {
                            **base,
                            "等级": level_text,
                            "参数": args_text,
                            "运行时条件": "；".join(path.get("conditions", [])),
                            "结果": format_value(path),
                            "数据来源": "\n".join(path.get("sources", [])),
                            "EXE 常量": "、".join(
                                f"{c['address']}={c.get('float', c['hex'])}"
                                for c in path.get("constants", [])
                            ),
                            "写入的运行时状态": "\n".join(
                                format_write(w) for w in path.get("writes", [])
                            ),
                            "未模拟的调用": "\n".join(path.get("opaque", [])),
                            "求值范围": (
                                "仅经过技能读取点的路径" if path.get("focused") else ""
                            ),
                        }
                    )

    remarks = [{"项目": "前提", "内容": text} for text in links["assumptions"]]
    remarks += [
        {"项目": "通用说明", "内容": text} for text in links["notes"]["general"]
    ]
    for diff in links["remapDifferences"]:
        if diff["kind"] == "code_only":
            content = (
                f"代码把 {label(diff['skill'])} 映射到 {label(diff['group'])}，"
                f"SkillData 中该技能打开的是 {'、'.join(label(s) for s in diff['dataOpens']) or '无'}"
            )
        else:
            content = f"SkillData 中 {label(diff['group'])} 打开 {label(diff['skill'])}，代码没有对应映射"
        remarks.append({"项目": "数据与代码不一致", "内容": content})
    remarks.append({"项目": "提取时的游戏版本", "内容": links["gameVersion"]})
    return {
        "技能": overview,
        "技能效果": effects,
        "未求值链路": pending,
        "说明": remarks,
    }


def export_skill_details(
    output_dir: Path, repository: SourceRepository, text_source: TextSource
) -> Path:
    links = load_links()
    sheets = build_sheets(repository, text_source, links)
    return write_workbook(Path(output_dir) / OUTPUT_NAME, sheets, MAX_COLUMN_WIDTH)
