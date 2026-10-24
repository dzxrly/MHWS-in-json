"""Write the link document as index.json plus one interned shard per skill category."""

import json
from collections import defaultdict
from pathlib import Path

from ..config import SCHEMA_VERSION

# Shard and string-table layout of the committed link directory.
INDEX_NAME = "index.json"
INTERNED = ("conditions", "sources", "opaque")


def shard_name(category):
    return f"{(category or 'UNLISTED').lower()}.json"


def write_shards(document, directory):
    """index.json (skills, functions, notes) plus one shard per skill category.

    Each shard keeps its own string and constant tables: repeated condition,
    source and call texts are stored once and referenced by position.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob("*.json"):
        old.unlink()
    by_category = defaultdict(list)
    for link in document["links"]:
        by_category[document["skills"][link["skill"]]["category"]].append(link)
    shards = []
    for category, links in sorted(by_category.items(), key=lambda item: item[0] or ""):
        strings, string_index, constants, constant_index = [], {}, [], {}

        def text(value):
            if value not in string_index:
                string_index[value] = len(strings)
                strings.append(value)
            return string_index[value]

        def constant(value):
            key = json.dumps(value, sort_keys=True)
            if key not in constant_index:
                constant_index[key] = len(constants)
                constants.append(value)
            return constant_index[key]

        def pack(path):
            packed = dict(path)
            for field in INTERNED:
                if field in packed:
                    packed[field] = [text(item) for item in packed[field]]
            for field in ("expression", "detail"):
                if field in packed:
                    packed[field] = text(packed[field])
            if "constants" in packed:
                packed["constants"] = [constant(c) for c in packed["constants"]]
            if "writes" in packed:
                packed["writes"] = [
                    dict(
                        w,
                        target=text(w["target"]),
                        **(
                            {"sources": [text(x) for x in w["sources"]]}
                            if "sources" in w
                            else {}
                        ),
                        **(
                            {"constants": [constant(c) for c in w["constants"]]}
                            if "constants" in w
                            else {}
                        ),
                    )
                    for w in packed["writes"]
                ]
            return packed

        packed_links = []
        for link in links:
            link = dict(link)
            if "results" in link:
                results = link["results"]
                link["results"] = dict(
                    results,
                    groups=[
                        dict(group, paths=[pack(p) for p in group["paths"]])
                        for group in results["groups"]
                    ],
                )
            packed_links.append(link)
        name = shard_name(category)
        shard = dict(
            schemaVersion=SCHEMA_VERSION,
            category=category,
            strings=strings,
            constants=constants,
            links=packed_links,
        )
        (directory / name).write_text(
            json.dumps(shard, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        shards.append(dict(file=name, category=category, links=len(links)))
    index = {k: v for k, v in document.items() if k != "links"}
    index["shards"] = shards
    (directory / INDEX_NAME).write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return [directory / INDEX_NAME, *(directory / s["file"] for s in shards)]
