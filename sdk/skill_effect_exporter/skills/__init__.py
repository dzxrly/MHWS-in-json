"""One module per skill (``hunterskill_<n>.py``), like monster/<id>.py of the
enemy logic exporter: how its links are extracted (``extract`` and
``extract_parameters``, usually thin calls of the shared steps in
workflow/context.py), the reviewed meanings of its shown effect values
(MEANINGS) and verified notes (NOTES).

The extractor runs every module's ``extract``, then every module's
``extract_parameters``, and copies MEANINGS and NOTES into the link JSON
(``meanings`` and ``notes.skills``); ``annotate`` refreshes only those parts.
Keys of MEANINGS are the effect keys of the shown sheet (src effect_links):
the function, the function with its data items, or the function with the
field it writes. Constants and handling that belong to one skill go in its
module only.
"""

from importlib import import_module
from pathlib import Path

from ..config import MEANING_FIELDS

DIRECTORY = Path(__file__).resolve().parent


def module_name(skill_id):
    return skill_id.lower()


def get_skill(skill_id):
    try:
        module = import_module(f"{__name__}.{module_name(skill_id)}")
    except ModuleNotFoundError as error:
        raise ValueError(
            f"{skill_id} 还没有技能模块，请运行 new-skill --skill {skill_id}"
        ) from error
    if module.SKILL_ID != skill_id:
        raise ValueError(f"技能模块的 SKILL_ID 与文件名不一致：{skill_id}")
    for key, fields in module.MEANINGS.items():
        unknown = set(fields) - set(MEANING_FIELDS)
        if unknown:
            raise ValueError(f"{skill_id} 的含义 {key} 有未知字段 {sorted(unknown)}")
    return module


class DefaultSkill:
    """The shared steps for a skill that has no module yet (reported as missing)."""

    MEANINGS, NOTES = {}, []

    def __init__(self, skill_id):
        self.SKILL_ID = skill_id

    def extract(self, context):
        return context.extract_skill(self.SKILL_ID)

    def extract_parameters(self, context):
        return context.extract_parameters(self.SKILL_ID)


def entry(skill_id):
    """The skill's module, or the shared steps when it has none."""
    if skill_id in skill_ids():
        return get_skill(skill_id)
    return DefaultSkill(skill_id)


def skill_ids():
    """Skill IDs that have a module, in file order."""
    return [
        path.stem.replace("hunterskill", "HunterSkill")
        for path in sorted(DIRECTORY.glob("hunterskill_*.py"))
    ]


def annotations(catalog, known):
    """(meanings, notes, missing, extra): per skill with a module the
    non-empty MEANINGS and NOTES of the skills in known (the link document's
    skill table, which also lists skills used in code but not in
    SkillCommonData), the catalog skills (SkillCommonData) without a module,
    and the modules of skills known does not list (removed by a game update)."""
    meanings, notes = {}, {}
    present = set(skill_ids())
    for skill_id in sorted(present & set(known)):
        module = get_skill(skill_id)
        if module.MEANINGS:
            meanings[skill_id] = module.MEANINGS
        if module.NOTES:
            notes[skill_id] = list(module.NOTES)
    return meanings, notes, sorted(set(catalog) - present), sorted(present - set(known))


def new_skill(skill_id, name=""):
    """Write an empty module for a skill; an existing module is kept."""
    path = DIRECTORY / f"{module_name(skill_id)}.py"
    if path.exists():
        raise ValueError(f"{path.name} 已存在，不覆盖")
    path.write_text(module_text(skill_id, name, {}, []), encoding="utf-8")
    return path


def module_text(skill_id, name, meanings, notes):
    """Source of a skill module: the shared extraction steps, then its data."""
    import pprint

    title = f"{skill_id} {name}".strip()
    return (
        f'"""{title}: extraction steps, meanings of its shown effect values, notes."""\n'
        "\n"
        f'SKILL_ID = "{skill_id}"\n'
        "\n"
        "# Shown effect key (src effect_links) -> meaning; see config.MEANING_FIELDS.\n"
        # One line per value (no split strings); Black wraps the module after.
        f"MEANINGS = {pprint.pformat(meanings, width=10**6, sort_dicts=False)}\n"
        "\n"
        "# Verified statements shown in the 技能 sheet; each names config.GAME_VERSION.\n"
        f"NOTES = {pprint.pformat(notes, width=10**6)}\n"
        "\n"
        "\n"
        "def extract(context):\n"
        '    """Links of the functions using this skill and of its accessors\' callers."""\n'
        "    return context.extract_skill(SKILL_ID)\n"
        "\n"
        "\n"
        "def extract_parameters(context):\n"
        '    """Parameter fields no path valued, focused where they are read."""\n'
        "    return context.extract_parameters(SKILL_ID)\n"
    )
