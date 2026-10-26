"""Copy the skill modules' meanings and notes into a link document or directory."""

import json
from pathlib import Path

from ... import notes
from ...skills import annotations
from .shards import INDEX_NAME


def apply_annotations(document):
    """Set document["meanings"] and document["notes"] from the skill modules;
    returns (catalog skills without a module, modules of skills the document
    does not know)."""
    skills = document["skills"]
    catalog = [s for s, info in skills.items() if info["inSkillCommonData"]]
    meanings, skill_notes, missing, extra = annotations(catalog, skills)
    document["meanings"] = meanings
    document["notes"] = dict(general=notes.GENERAL, skills=skill_notes)
    return missing, extra


def annotate_directory(directory):
    """Refresh index.json of a written link directory without evaluating again."""
    path = Path(directory) / INDEX_NAME
    index = json.loads(path.read_text(encoding="utf-8"))
    missing, extra = apply_annotations(index)
    path.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return index, missing, extra
