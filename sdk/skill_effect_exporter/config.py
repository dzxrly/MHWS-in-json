"""Paths, IL2CPP identities and limits of the skill effect extractor.

Everything native is located by type and method name in the supplied il2cpp
dump; nothing here is a build-specific address.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Layout version of the link directory (index.json + shards).
SCHEMA_VERSION = 1
DEFAULT_NATIVES = ROOT / "MHWS-in-json/natives"
DEFAULT_OUTPUT = ROOT / "src/processed_data/skill_details/data/skill_links"
TMP_DIR = ROOT / ".tmp"

SKILL_COMMON = "STM/GameDesign/Common/Equip/SkillCommonData.user.3.json"
SKILL_DATA = "STM/GameDesign/Common/Equip/SkillData.user.3.json"
PLAYER_GLOBAL_PARAM = (
    "STM/GameDesign/Player/ActionData/Common/GlobalParam/PlayerGlobalParam.user.3.json"
)

SKILL_ENUM = "app.HunterDef.Skill"
SKILL_FIXED_ENUM = "app.HunterDef.Skill_Fixed"
CATEGORY_ENUM = "app.HunterDef.SkillCategory"
HUNTER_SKILL = "app.cHunterSkill"
SKILL_DEF = "app.HunterSkillDef"
EQUIP_SKILL_INFO = "app.EquipDef.EquipSkillInfo"
EQUIP_SKILL_DATA = "app.EquipDef.EquipSkillData"
EQUIP_DATA_HOLDER = "app.EquipDataHolder"
SKILL_COMMON_ROW = "app.user_data.SkillCommonData.cData"
SKILL_DATA_ROW = "app.user_data.SkillData.cData"
PLAYER_GLOBAL_TYPE = "app.user_data.PlayerGlobalParam"

# cHunterSkill methods whose bodies identify shared runtime structures.
VALUE_HELPER = "getSkillValue"  # loads HunterSkillDef.SkillToGroupSkill first
PARAM_GETTER = "get__SkillParam"  # [rip+G] -> +a -> +b -> PlayerSkillParam
REMAP_BUILDER = "createSkillToGroupSkill"  # (skill, group) pairs as immediates

# Methods taking a skill identity; their call sites name the skills a caller uses.
SKILL_PARAM_TYPES = (SKILL_ENUM, SKILL_FIXED_ENUM)
# One native body shared by more methods than this is a generic stub, not a skill helper.
MAX_HELPER_ALIASES = 4

# ------------------------------------------------ native layout constants
# Managed object layouts of the RE Engine IL2CPP runtime. They are verified
# against the current build (see AGENTS.md "游戏更新后的检查"): array length
# and data offsets from getSkillBallistic*/getSkillValue, List`1 offsets from
# the BCL field records, the value-type box header from any struct's fields.
ARRAY_LENGTH_OFFSET = 0x1C  # Int32 element count
ARRAY_DATA_OFFSET = 0x20  # first element
LIST_ITEMS_OFFSET = 0x10  # List`1._items
LIST_SIZE_OFFSET = 0x18  # List`1._size
LIST_VERSION_OFFSET = 0x1C  # List`1._version
OBJECT_HEADER_WORD = 0x8  # checked for its sign by getSkillLevelCore (tagged reference)
BOX_HEADER = 0x10  # value-type field offsets in the dump include this header
REFERENCE_TAG_BIT = 63  # tagged references; btr 63 / and 0x7fff... clear it
# A float-vector native type and its exported float count.
FLOAT_VECTORS = {
    "via.vec2": 2,
    "via.vec3": 4,
    "via.vec4": 4,
    "via.Quaternion": 4,
    "via.Float2": 2,
    "via.Float3": 3,
    "via.Float4": 4,
}
VEC3_SIZE = 16  # via.vec3 is padded to 16 bytes inline

# Windows x64 calls of IL2CPP methods: rcx carries the thread context; then
# this (instance methods) and the parameters in rdx/r8/r9 or xmm1-3, then the stack.
ARGUMENT_REGISTERS = ("rdx", "r8", "r9")
CALLER_STACK_ARGUMENT = 0x20  # [rsp + 0x20] at the call site
FIRST_STACK_ARGUMENT = 0x28  # [rsp + 0x28] at entry: 0x20 shadow space + return address
ENTRY_STACK_PHASE = 8  # rsp is 8 mod 16 at function entry
OUT_PARAMETER_AREA = -0x400  # scratch below the frame for ByRef parameters
OUT_PARAMETER_STRIDE = 0x10

# Byte scan for direct calls and jumps; executable section flag of PE headers.
CALL_OPCODES = rb"[\xe8\xe9]"
EXECUTABLE_SECTION = 0x20000000
# REFramework dumps indent method records by 12 spaces.
METHOD_RECORD = rb'^ {12}"([^"\r\n]+)": \{'

# Callers that only display or replicate skill state: kept as links, not evaluated.
EVALUATE_SKIP_PREFIXES = (
    "app.GUI",
    "app.cGUI",
    "app.Net",
    "app.cMasterHunterNetwork",
    "app.cReplicaHunterNetwork",
    "app.cHunterNetworkBase",
    "app.MessageUtil",
    "app.IconUtil",
    "app.SoundPlayerInfoHolder",
    "System.",
    "app.user_data.SkillData",
    "app.EquipDef",
    "app.HunterDef",
)

# Emulation limits per evaluated function.
MAX_STEPS = 20000
MAX_TOTAL_STEPS = 60000  # all paths of one evaluation together
# Once one level/argument case of a function exceeds a limit, the rest reuse that status.
LIMIT_STATUSES = ("too_many_paths", "too_long")
MAX_PATHS = 256  # pending forks included; forks inside a replayed callee collapse
MAX_CALL_DEPTH = 4
# A path forking more often than this at one branch is in a loop whose trip
# count is unknown (see emulator.UnknownLoop).
MAX_LOOP_FORKS = 4
MAX_ARGUMENT_COMBINATIONS = 64
MAX_ENUM_VALUES = 40
# Callers of a cHunterSkill accessor are evaluated for the skills it reads,
# unless it reads more than this many (sums over many skills, like calcAttackRate).
MAX_ACCESSOR_SKILLS = 2
# Paths kept per case after merging; the ones with fewest conditions first.
MAX_RECORDED_PATHS = 32

# Scenario dimensions: runtime values that choose between per-weapon or
# per-ammo parameters. A function that reads one is evaluated once per enum
# value (except DIMENSION_EXCLUDED), and the value is listed as an argument
# named by the dimension. "field" names the exact runtime field, given as
# (declaring type, field name); without it any runtime field of the enum type
# counts, and so does the result of an opaque call declared to return it.
# The weapon is HunterCharacter._HunterComp.Prepare
# .<WeaponBuilder>k__BackingField._EquippedWeaponType; _ReserveWeaponType, of
# the same enum, stays runtime state.
# "only" limits a dimension to cases where another dimension, when known, has
# one of the listed values: the ammo enums belong to WeaponGunDef (bowguns).
BOWGUNS = {"武器": ("HEAVY_BOWGUN", "LIGHT_BOWGUN")}
DIMENSIONS = (
    dict(
        name="武器",
        enum="app.WeaponDef.TYPE",
        field=("app.mcHunterWeaponBuilder", "_EquippedWeaponType"),
    ),
    dict(name="弹种", enum="app.WeaponGunDef.SHELL_TYPE", field=None, only=BOWGUNS),
    dict(
        name="弹药参数类型",
        enum="app.WeaponGunDef.SHELL_PARAM_TYPE",
        field=None,
        only=BOWGUNS,
    ),
)
DIMENSION_EXCLUDED = ("INVALID", "MAX")
