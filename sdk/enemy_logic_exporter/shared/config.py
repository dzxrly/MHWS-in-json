"""Bundled paths, reviewed source identity and version-specific native constants.

Native functions are declared as version-independent symbols (SYMBOL_SPECS)
and resolved per build into data/profiles/<gameVersion>.json by the
``resolve-symbols`` command; constants below read their addresses from the
active profile. Structure offsets and IL2CPP names below still belong to the
reviewed version: after a game update, re-resolve the profile, migrate the
evidence and review what changed. Replacing digests alone proves nothing.
"""

import json
from pathlib import Path

from .native.symbols import Helper, Method, Reviewed

# --------------------------------------------------------------------- paths

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EVIDENCE_DIR = DATA_DIR / "evidence"
MODEL_DIR = DATA_DIR / "models"
RULES_PATH = DATA_DIR / "rules.v1.json"
ROSTER_PATH = DATA_DIR / "roster.v1.json"
MONSTER_MODULE_DIR = Path(__file__).resolve().parents[1] / "monster"

# Publication scope: EnemyData IDs below this base number, minus exclusions.
LARGE_ENEMY_MAX_BASE = 1000
TRAINING_ENEMY_ID = "EM0165_00_0"
EXCLUDED_ENEMY_IDS = (TRAINING_ENEMY_ID,)


# ---------------------------------------------- active build profile

# Switching game versions means resolving a new profile and changing this.
ACTIVE_GAME_VERSION = "1.42.0.2"
PROFILE_DIR = DATA_DIR / "profiles"
ACTIVE_PROFILE_PATH = PROFILE_DIR / f"{ACTIVE_GAME_VERSION}.json"
ACTIVE_PROFILE = json.loads(ACTIVE_PROFILE_PATH.read_text(encoding="utf-8"))
SUPPORTED_PROFILE = dict(ACTIVE_PROFILE["profile"])
SYMBOLS = ACTIVE_PROFILE["symbols"]


def symbol(name):
    """Resolved virtual address of a function symbol in the active build."""
    return int(SYMBOLS[name]["address"], 16)


def symbol_value(name):
    """Reviewed constant carried by the active profile."""
    return SYMBOLS[name]["value"]


def symbol_evidence(name):
    record = SYMBOLS[name]
    return {k: record[k] for k in ("type", "method", "address", "end", "nativeSha256")}


def symbol_name(name):
    record = SYMBOLS[name]
    return record["type"] + "." + record["method"]


# --------------------------------------------------- native functions (VA)

# Stack-cookie check emitted in every frame; it has no BTable semantics.
FN_STACK_COOKIE_CHECK = symbol("stack_cookie_check")
FN_SET_CURRENT_POSITION = symbol("set_current_position")
FN_POSITION_STACK_PUSH = symbol("position_stack_push")
FN_POSITION_STACK_TRY_POP = symbol("position_stack_try_pop")
# POSITION[] growth helper reached from inlined Stack.Push.
FN_POSITION_ARRAY_RESIZE = symbol("position_array_resize")

# Calls that only save positions or check the stack cookie inside table code.
MACHINE_TRANSPARENT_CALLS = frozenset(
    {
        FN_SET_CURRENT_POSITION,
        FN_POSITION_STACK_PUSH,
        FN_POSITION_STACK_TRY_POP,
        FN_STACK_COOKIE_CHECK,
    }
)
# Calls accepted while tracing an inlined Stack<POSITION>.Push.
INLINE_PUSH_CALLS = frozenset(
    {FN_SET_CURRENT_POSITION, FN_POSITION_ARRAY_RESIZE, FN_STACK_COOKIE_CHECK}
)

# Static field read on table entry; the reviewed table path treats it as 0.
GLOBAL_TABLE_ENTRY_ZERO = int(symbol_value("global_table_entry_zero"), 16)
# Runtime-initialized data starts here; the PE image holds no value for it.
RUNTIME_DATA_START = int(symbol_value("runtime_data_start"), 16)

# Static weighted-pool initializers in <Export>..cctor.
FN_POOL_PAIR_CONSTRUCT = symbol("pool_pair_construct")
FN_POOL_ARRAY_COPY = symbol("pool_array_copy")
# The allocator receives the array length in r8 and the dimension count in r9.
FN_ARRAY_ALLOCATE = symbol("array_allocate")
FN_STATIC_REF_ACQUIRE = symbol("static_ref_acquire")
FN_STATIC_REF_RELEASE = symbol("static_ref_release")
# Type slot of System.ValueTuple<UInt32, Int32>[] pool arrays.
POOL_ARRAY_TYPE_SLOT = int(symbol_value("pool_array_type_slot"), 16)
# Ghidra spellings of the two pool helpers in cached pseudo-C; the mhws_ label
# was assigned by the earlier research project.
POOL_PAIR_CONSTRUCT_LABELS = (
    f"FUN_{FN_POOL_PAIR_CONSTRUCT:x}",
    f"func_0x{FN_POOL_PAIR_CONSTRUCT:012x}",
    "mhws_c49d22bf7e7e9cbe",
)
POOL_ARRAY_COPY_LABEL = f"FUN_{FN_POOL_ARRAY_COPY:x}"

# Runtime "object class derives from class" test used before Extend casts.
FN_CLASS_HIERARCHY_CHECK = symbol("class_hierarchy_check")
CLASS_HIERARCHY_CHECK_LABELS = (
    f"FUN_{FN_CLASS_HIERARCHY_CHECK:x}",
    f"func_0x{FN_CLASS_HIERARCHY_CHECK:012x}",
)
# cEmModuleUniqueLeveledValue.getLevel(category) -> Nullable<UInt32>.
FN_UNIQUE_LEVEL = symbol("unique_leveled_value_get_level")
UNIQUE_LEVEL_LABELS = (f"FUN_{FN_UNIQUE_LEVEL:x}", f"func_0x{FN_UNIQUE_LEVEL:012x}")


# ------------------------------------------------------- structure layouts

# Managed object/array headers.
ARRAY_LENGTH = 0x1C
ARRAY_ELEMENTS = 0x20
REFERENCE_ARRAY_STRIDE = 8

# ValueTuple<UInt32, Int32> pool element: key then weight.
POOL_KEY = ARRAY_ELEMENTS
POOL_WEIGHT = ARRAY_ELEMENTS + 4

# ace.btable.cOperatorWork (and the app.cEnemyBTableOperatorWork subclass).
OPERATOR_CLASS = 0x0
OPERATOR_POSITION_CALLBACK = 0x40  # OnChangedCurrnetPosition
OPERATOR_POSITION_STACK = 0x80  # _PositionStack
OPERATOR_POSITION = 0xA0  # _CurrentPosition.RuntimeBTableIndex
OPERATOR_POSITION_TABLE = 0xA4  # _CurrentPosition.TableIndex
OPERATOR_POSITION_ROW = 0xA8  # _CurrentPosition.RowIndex (compiled table state)
OPERATOR_PREV_COMMAND_POSITION = 0xAC  # PrevCommandPosition
OPERATOR_REQUEST_COMMAND = 0xB0  # PrevCommandPosition.CommandNum
OPERATOR_EXPORT_JUMP = 0xC5  # <IsExportTableJump>k__BackingField
OPERATOR_EXPORT_END = 0xC6  # <IsExportTableEnd>k__BackingField
OPERATOR_RANDOM_STATE = 0xD8
OPERATOR_RANDOM_SELECTED = 0xDC

# ace.btable.BTableDef.POSITION as an unboxed 12-byte element.
POSITION_SIZE = 12
POSITION_TABLE = 4
POSITION_ROW = 8

# System.Collections.Generic.Stack`1<POSITION>.
STACK_REFERENCE_TAG = 0x8
STACK_ARRAY = 0x10
STACK_SIZE = 0x18
STACK_VERSION = 0x1C
# Action`2 position callback: invocation count and the single target pair.
CALLBACK_COUNT = 0x10
CALLBACK_TARGET = 0x18
CALLBACK_METHOD = 0x20

# Export table and command work.
EXPORT_RUNTIME_ROOT = 0x30
EXPORT_COMMANDS = 0x10
EXPORT_ARGUMENTS = 0x18
COMMAND_WORK_RANDOM = 0x10
OBJECT_VTABLE_FROM_INTERFACE = -0x18
EDIT_FIELD_VALUE = 0x10
# Command work -> accessor (param_3[5]) -> self Extend holder -> value.
COMMAND_WORK_ACCESSOR = 0x28
EXTEND_HOLDER = 0x78
# Accessor -> target context (0x68) -> cEnemyContext (0x40).
ACCESSOR_TARGET_CONTEXT = 0x68
TARGET_CONTEXT_ENEMY = 0x40
# Extend base fields read by unique-state commands and getters.
EXTEND_BASE_TYPE = "app.cEnemyExtendBase"
EXTEND_ACCESSOR_FIELD = "_Accessor"
EXTEND_UNIQUE_STATE_FIELD = "_UniqueStateFixedID"
UNIQUE_LEVELED_MODULE_FIELD = "UniqueLeveledValue"
# Stand-state layers read by CheckStatus.execute_StandState.
STAND_STATE_ENUM = "app.CharacterDef.STAND_STATE"
EXTRA_STATE_ENUM = "app.EnemyDef.EXTRA_STATE"


# -------------------------------------------------------- IL2CPP identities

COMMON_COMMAND_PREFIX = "app.btable.EmCommonCommand."
ENEMY_CONTEXT_TYPE = "app.cEnemyContext"
OPERATOR_WORK_TYPE = "ace.btable.cOperatorWork"
EXPORT_COMMAND_POSITION_TYPE = "ace.btable.BTableDef.EXPORT_COMMAND_POSITION"
BTABLE_RESOURCE_TYPE = "ace.btable.user_data.BTable"
SELECT_ACTION_ARGUMENT = "app.btable.EmCommonCommand.cSelectActionArg"
REQUEST_ACTION_COMMANDS = (
    "app.btable.EmCommonCommand.cRequestAction",
    "app.btable.EmCommonCommand.cRequestActionSync",
)
SKIP_ACTION_TABLE_ARGUMENT = "app.btable.EmCommonCommand.cSetSkipActionTblArg"
RANDOM_TYPE_COMMAND = "ace.btable.cCommandRandamRandomType"
UNFAIR_ROUTINE_COMMAND = "app.btable.EmCommonCommand.cCheckUnfairRoutineActive"
UNFAIR_ACTIVE_FIELD = "app.cEmModuleUnfair.<IsActiveUnfairRoutine>k__BackingField"
UNFAIR_ACTIVE_OFFSET = "0x44"
POOL_ELEMENT_TYPE = "System.ValueTuple<System.UInt32,System.Int32>"
VOID_TYPE = "System.Void"
BOOLEAN_TYPE = "System.Boolean"


def extend_types(owner):
    """Self-Extend class names for "Em0021_00", then its species "Em0021"."""
    return [f"app.c{owner}Extend", f"app.c{owner.split('_')[0]}Extend"]


NO_ARGUMENT_TYPES = ("", "ace.btable.cCommandArgumentNone")

# Native evidence of the random-type command read by the machine.
RANDOM_TYPE_COMMAND_EVIDENCE = symbol_evidence("random_type_execute")

# The native selector passes a uniquely owned default or branched _ActionClass
# to the requested action's applyActionParam virtual method.
PARAMETER_SELECTION_EVIDENCE = (
    symbol_evidence("action_param_branch"),
    symbol_evidence("action_param_apply"),
)


# -------------------------------------------- shared Combat callback recipe

# (type, method name without the version-specific numeric suffix); the
# suffixed keys come from data/evidence/combat_entry_evidence.v1.json.
COMBAT_METHODS = dict(
    request_change=("app.cEmAIUpdateBTable", "requestChangeBTable"),
    request_verify=("app.cMasterEnemyControllerEntity", "requestChangeBTableVerify"),
    change_state=("app.cEmAIStateCombat", "changeState"),
    on_enter=("app.cEmAIStateCombat", "onEnter"),
    on_return_interrupt=("app.cEmAIStateCombat", "onReturnInterrupt"),
    on_restart=("app.cEmAIStateCombat", "onRestart"),
    on_table_end=("app.cEmAIStateCombat", "onBTableEnd"),
    on_table_change=("app.cEmAIStateCombat", "onBTableChange"),
    update_btable=("app.cEmAIUpdateBTable", "updateBTable"),
    update=("app.cEmAIUpdateBTable", "update"),
    wait_until_action_end=("app.cMasterEnemyControllerEntity", "isWaitUntilActionEndBTable"),
    manager_valid=("ace.btable.cManager", "get_Valid"),
    table_root=("app.cEnemyBTableManager", "get_IsTableRoot"),
    update_table=("ace.btable.cManager", "updateTable"),
    resume_jump=("app.cEmAIUpdateBTable", "resumeJumpBTable"),
    check_update=("app.cEmAIUpdateBTable", "checkUpdateExecute"),
    higher_interrupt=("app.cEmAIStateManager", "isHigherInterruptAcceptChangeState"),
)

COMBAT_NATIVE_TARGETS = dict(
    clear_jump=hex(symbol("manager_setup_table")),
    area_target=hex(symbol("area_target_child")),
    area_schedule=tuple(
        hex(symbol(name))
        for name in (
            "area_check_detached",
            "area_recalc_schedule",
            "area_change_category",
            "area_schedule_helper",
            "net_send_packet",
        )
    ),
    detector_event=tuple(
        hex(symbol(name))
        for name in ("fetch_hate_target", "detector_attribute_ctor", "detector_register")
    ),
    smoke=hex(symbol("refresh_smoke")),
    restore=tuple(
        hex(symbol(name))
        for name in ("resume_jump_btable", "manager_clear", "target_resume", "restore_helper")
    ),
)

COMBAT_HELPER_METHODS = dict(
    area_target=symbol_name("area_target_child"),
    smoke=symbol_name("refresh_smoke"),
)

# Native field labels shown with each runtime key; they include the offsets
# read by the reviewed method bodies.
COMBAT_FIELDS = dict(
    controller_exists="cEmAIState._EntityHolders(0x28)._Master(0x20) != null",
    done_combat_begin="cEnemyContext._FlagArray[DONE_COMBAT_BEGIN_ACTION=0]，0x308→数组0x20",
    done_combat_em_begin="cEnemyContext._FlagArray[DONE_COMBAT_EM_BEGIN_ACTION=1]，0x308→数组0x21",
    state_sign_exists="cEnemyContext.BTable._ExistBTableArray[STATE_SIGN=25]，0x120→0x18→0x39",
    previous_ai_predator="AIStateManager._PrevAIStateID(0xe8)：PREDATOR=5",
    previous_ai_invalid="AIStateManager._PrevAIStateID(0xe8)：INVALID=-1",
    any_interrupt="AIStateManager._AnyInterruptResult(0x103)",
    lead_interrupt_exists="AIStateManager._ExistInterruptResult[LEAD=5]，0xd0→数组0x25",
    jump_resume_requested="cEmAIUpdateBTable._IsRequestJumpBTableResume(0x68)",
    current_main_slot="cEmAIUpdateBTable._CurrentMainBTable.ID(0x50)",
    jump_manager_valid="cManager.get_Valid(JumpBTableManager=0x40)",
    jump_manager_active="cManager.get_Valid(JumpBTableManager=0x40)；true 时本帧不更新主表",
    current_btable_slot="cEnemyContext.BTable._CurrentBTableID(0x14)；COMBAT=1",
    state_sign_type="cEnemyContext.StateSignActionType(0x358)",
    combat_state="cEmAIStateCombat._State(0x3c)",
    combat_state_update="Combat._State(0x3c)，UPDATE=1",
    combat_state_begin="Combat._State(0x3c)，BEGIN=0",
    hiding_skill_lost="Combat.IsHidingSkillLost(0xfa)",
    reserved_reset_dest="Combat.IsReservedResetDest(0x11)",
    send_detector="Combat._IsSendDetector(0xf9)",
    auto_send_detector="Combat._IsAutoSendDetector(0xfb)",
    disable_send_detector="Combat._IsDisableSendDetector(0xfc)",
    btable_request_update="cEnemyContext.BTable._IsReuqestUpdateBTable(0x11)",
    manager_export="cManager._IsExportTable(0x49)",
    operator_exists="cManager._OperatorWork(0x10) != null",
    operator_table_count="OperatorWork+0x48 所指表的0x18计数；get_Valid 的真实分支",
    saved_table="OperatorWork 当前保存位置 Table，0xa0",
    saved_table_plain="普通表当前保存位置 Table，0xa0",
    saved_pc="OperatorWork 当前保存位置 PC，0xa4",
    saved_command="OperatorWork 当前保存位置命令，0xa8",
    export_root_index="get_IsTableRoot 原生比较 ExportRuntimeBTable+0x30 的实际整数；未把字段名称推定为根表编号",
    override_story="STORY 使用 _OverrideBTableFromStory(0x30)；其他槽按 IsEnableOverrideNew 位集及实际资源启用状态选择基础/覆盖表。资源 GUID 比较和启用 helper 尚未完全固化",
    permanent_disable_btable="cEnemyContext._PermanentFlag(0x2e8) bit0",
    continue_disable_btable="cEnemyContext._ContinueFlag(0x2d8).check(DISABLE_BTABLE_UPDATE=0)",
    manager_table_end="cManager.<IsTableEnd>k__BackingField(0x4a)，在 updateTable 执行之后读取",
    need_btable_update="cEmAIUpdateBTable._IsNeedUpdate(0x69)；活跃中断可由 checkUpdateExecute 将其清零",
    execute_reason="Export 模式经虚表 updateTableInpl 执行；结束标志由导出方法状态和 OperatorWork+0xc6决定。普通模式使用单独的命令循环",
    wait_policy_flag="ReactionGm+0x13",
)

COMBAT_MINICOMPONENTS = {
    "MiniCompUpdator_BeforeBTableOnce(0x70)": [0, 1],
    "MiniCompUpdator_CtrlUpdate(0x68)": [12, 14, 63, 9],
    "MiniCompUpdator_AfterBTableOnce(0x78)": [8],
}
COMBAT_STATE_SIGN_COMPONENTS = {"MiniCompUpdator_CtrlUpdate(0x68)": [72]}
COMBAT_STATE_SIGN_COMPONENT_WRITES = "0x27与0x26"


# ------------------------------------------- reviewed condition field sources

CONDITION_FIELDS = dict(
    command_work_valid="cEnemyBTableCommandWork 存在且通过此命令的原生类型检查",
    command_work_valid_short="命令工作存在且原生类型身份匹配 cEnemyBTableCommandWork",
    command_work_valid_request="命令工作存在且原生类型检查为 cEnemyBTableCommandWork",
    target_context="Accessor.TargetContext（命令工作偏移0x28，经0x68）存在",
    target_context_nav="Accessor.TargetContext 存在（命令工作0x28→0x68）",
    target_context_unfair="Accessor.TargetContext 存在（0x28→0x68）",
    selected_target="cEmModuleTarget.getTarget(requireValid=True, slot=0)：状态不为1时返回无效键",
    legendary_id="cEnemyContext.Basic.LegendaryID（0x108→0x50）",
    enemy_id="cEnemyContext.Basic.EmID（0x108→0x48）",
    role_id="cEnemyContext.Basic.RoleID（0x108→0x4c）",
    category="cEnemyContext.Basic.Category（0x108→0x54）；0 BOSS、1 ZAKO、2 ANIMAL",
    hunter_stun="cHunterBadConditions._Stun（0x40）._IsActive（0x2f） != 0",
    enemy_enabled="选中怪物 Context 存在且其启用标志（0x308→0x27）为真",
    enemy_condition_15="cEmModuleConditions._Conditions[15]._State（0xb0→数组项→0x58）",
    parts_break_count="cEnemyContext.Parts 的破坏索引数量（0x128→0x8c）",
    parts_record_break_count="匹配破坏记录的 _BreakCount（0x18）",
    state_sign="cEnemyContext.StateSignActionType（0x40→0x358）；-1 表示无",
    area_no="cEnemyContext.Area._CurrentAreaNo（0x1d8→0xe0）；不是AI状态",
    stage_no="cEnemyContext.Area._CurrentStageNo（0x1d8→0x14）",
    stage_no_short="Area._CurrentStageNo（0x14）",
    stage_no_unfair="Area._CurrentStageNo（0x14）；原生命令最后参数=true",
    area_no_short="Area._CurrentAreaNo（0xe0）",
    nav_query=f"getDataInfoForNav（{symbol('nav_data_info'):#x}）查询自身位置成功",
    target_module="holder.Em.Target（0x40→0x100）非空；覆盖位置存在时仍检查",
    override_position=f"命令复制的 Nullable<vec3>._HasValue；{symbol_value('destination_override_global')}，不假定其运行时值",
    target_position=f"Target.getTargetPosition(0, false)（{symbol('target_position'):#x}）的 Nullable 有值",
    wall_query=f"getWallInfoNearVector（{symbol('wall_info_near'):#x}）查询目标位移方向成功",
    terrain_fallback=f"HIGH 物理回退要求本次 TERRAIN_CHARACTER 射线至少命中一个有效对象且包含全局{symbol_value('terrain_component_global')}指定的有效组件；组件类型与查询构造仍未完整核实",
    unique_index_mask="所选 TARGET_ACCESS_KEY.UniqueIndex 的最高位为0；命令掩码0x80000000ffffffff",
    hunter_lookup=f"findHunterContext 返回非空对象（{symbol('player_manage_info'):#x}）",
    hunter_character="返回对象0x18的HunterCharacter存在，且角色0x10对象非空",
    occlusion_length=f"getRayTargetBasePos(_This)/Nullable覆盖位置与getRayTargetBasePos(目标键)之差的 x²+y²+z²；常量{symbol_value('occlusion_length_constant')}=2500",
    special_gimmick_missing=f"缺少全局{symbol_value('special_gimmick_global')}的特殊GIMMICK索引",
    request_mask="Accessor._Context._Em.BTable._IsBTableRequestActionMask；0x28→0x68→0x40→0x120→0x13",
    actor_net_info="请求 actor 的 Context._Em.NetInfo(0xf0) != null",
    actor_host_index="请求 actor 的 NetInfo._HostMemberIndex(+0x24)",
    actor_self_index="请求 actor 的 NetInfo._SelfMemberIndex(+0x20)",
)

RANDOM_DRAW_SOURCE = "cCommandWork.Random（匹配元数据偏移0x10）在该原生调用位置返回的整数余数"

OCCLUSION_QUERY = dict(
    queryType="app.RAY_CAST_TYPE.TERRAIN_EM_SIGHT",
    specialGimmickIndexGlobal=symbol_value("special_gimmick_global"),
    throughIdField="app.cEmModuleTarget._OccludedCheckThroughGmIDs (0x70)",
    hitKeySource=f"app.TargetAccessKeyUtil.makeTargetAccessKey ({symbol('make_target_key'):#x})",
)

REQUEST_EFFECTS = (
    ("cEnemyContext._FlagArray[WAITING_REQUEST_ACTION_RANDOM_OPERATOR=14]", "0x308→0x2e"),
    ("cEnemyContext._FlagArray[NO_REQUEST_ACTION=50]", "0x308→0x52"),
)


# ------------------------------------------------------ rule curation specs

# (command, kind, scope, summary, argument offsets, context type, offset)
# Common commands only; monster commands declare RULE_SPECS in monster/<id>.py.
RULE_SPECS = (
    (
        "app.btable.EmCommonCommand.cCheckDistance",
        "distance",
        "通用",
        "命令距离：XZ/XYZ 使用严格近远比较；Y 轴使用高度比较",
        {"threshold": 0x10, "compare": 0x18, "height": 0x20, "axis": 0x28, "base": 0x30},
        None,
        None,
    ),
    (
        "app.btable.EmCommonCommand.cCheckAngle",
        "angle",
        "通用",
        "相对指定方向的夹角 ≤ 角度宽度 / 2；包含边界",
        {"base": 0x10, "width": 0x18, "option": 0x20, "option2": 0x28},
        None,
        None,
    ),
    (
        "ace.btable.cCheckTimerValue",
        "timer",
        "通用",
        "指定计时器的剩余值 ≤ 0",
        {"variable": 0x18},
        None,
        None,
    ),
    (
        "ace.btable.cCompareBoolValue",
        "variable_bool",
        "通用",
        "变量布尔值与指定值相等",
        {"variable": 0x18, "value": 0x20},
        None,
        None,
    ),
    (
        "app.btable.EmCommonCommand.cCheckSelfStatus",
        "self_status",
        "通用",
        "自身状态分类检查；已核实站立状态、生命比例和部分 AI 状态",
        {"category": 0x18, "stand": 0x20, "health": 0x38, "ai": 0x40},
        None,
        None,
    ),
)
CHECK_STATUS_TYPE = "app.btable.EmCommonCommand.CheckStatus"
CHECK_STATUS_METHOD_PREFIXES = (
    "execute123",
    "execute_StandState",
    "execute_Health",
    "execute_AIState",
)
DISTANCE_MODIFIER_FIELDS = (
    ("app.cEmAIStateManager", "_CurrentAIStateID", 0xFC),
    ("app.cEmAIStateManager", "_NextAIStateID", 0xEC),
    ("app.cEmModuleCombatEm", "<CombatRangeScale>k__BackingField", 0x14),
    ("app.cEmModuleCombatEm", "<CombatRangeOffset>k__BackingField", 0xB8),
)
AI_STATE_ENUM = "app.EnemyDef.AI_STATE_ID"
COMMAND_RESULT_TYPE = "ace.btable.COMMAND_RESULT"
COMMAND_RESULT_ENUM = "ace.btable.BTableDef.COMMAND_RESULT_TYPE"
BOOLEAN_COMMAND_FUNC = (
    "ace.btable.cCommandFunc`2<app.btable.EmCommonCommand.cCheckDistanceArg,System.Boolean>"
)
RANDOM_OPERATOR_TYPE = "ace.btable.cOperatorRandom"
SET_TIMER_TYPE = "ace.btable.cSetTimerValue"


# --------------------------------------------------- manifest type selection

MANIFEST_SCHEDULER_TYPES = (
    "app.cEmAIState",
    "app.cEmAIStateCombat",
    "app.cEmAIStateCaution",
    "app.cEmAIStateAreaMove",
    "app.cEmAIStateDie",
    "app.cEmAIInterruptDamage",
    "app.cEmAIUpdateBTable",
    "app.cMasterEnemyControllerEntity",
    "app.cEnemyBTableManager",
    "app.cEnemyControllerEntityBase",
    "app.cEmAIStateManager",
)
MANIFEST_STATE_PREFIXES = ("app.cEmAIState", "app.cEmAIInterrupt")
VARIABLE_STORAGE_TYPE = "ace.btable.cVariableStorage"
MANIFEST_RUNTIME_TYPES = (
    "ace.btable.cVariableStorage",
    "ace.btable.cVariableStorage.cRuntimeTimer",
    "ace.btable.user_data.BTableVariable.TimerValueInfo",
    "app.cEnemyBTableCommandWork",
    "app.cEnemyBTableOperatorWork",
    "app.btable.EmCommonCommand.cCheckStatusStatusArg.CONDITION_TYPE",
)


# ------------------------------------------------ AI state -> BTable slot

# Methods that queue a BTable slot. The slot (app.EnemyDef.BTABLE_ID) is the
# third native argument (r8d) of each of them.
SLOT_REQUEST_METHODS = {
    symbol(name): (SYMBOLS[name]["type"], SYMBOLS[name]["method"], mode)
    for name, mode in (
        ("request_change_btable", "change"),
        ("request_jump_btable", "jump"),
        ("request_change_btable_verify", "change_verify"),
    )
}
SLOT_REQUEST_ARGUMENT = "r8"
BTABLE_SLOT_ENUM = "app.EnemyDef.BTABLE_ID"
# Owners of slot requests; every direct caller found in a full EXE scan of the
# reviewed version belongs to one of these type families.
SLOT_REQUEST_OWNER_PREFIXES = (
    "app.cEmAIState",
    "app.cEmAIInterrupt",
    "app.cMasterEnemyControllerEntity",
)
# Wrappers that forward their own slot parameter; their callers are scanned.
SLOT_REQUEST_FORWARDERS = ("app.cMasterEnemyControllerEntity",)

# cEmAIInterruptUnique.requestUniqueBTable reads cEnemyContext+0x35c and maps it
# through app.EnemyDef's static int[3]. Its .cctor writes [-1, 0x22, 0x23].
UNIQUE_SLOT_REQUESTER = (
    SYMBOLS["request_unique_btable"]["type"],
    SYMBOLS["request_unique_btable"]["method"],
)
_UNIQUE_TABLE = symbol_value("unique_slot_table")
UNIQUE_SLOT_TABLE = dict(
    owner=SYMBOLS["enemy_def_cctor"]["type"],
    method=SYMBOLS["enemy_def_cctor"]["method"],
    site=int(_UNIQUE_TABLE["site"], 16),
    bytes=_UNIQUE_TABLE["bytes"],
    global_address=_UNIQUE_TABLE["globalAddress"],
    values=tuple(_UNIQUE_TABLE["values"]),
    contextField="cEnemyContext+0x35c",
)

# Player-facing slot names and grouping of the scheduler layer.
SLOT_LABELS = dict(
    COMBAT="普通战斗选招",
    STATE_SIGN="状态提示动作（开战、发怒、怒结束等）",
    DAMAGE="受击、倒地与硬直反应",
    ATTACK_HIT="攻击命中后的派生",
    FLASH="闪光弹致盲",
    RIDE="被玩家骑乘",
    RIDE_OTHER="骑乘其他怪物",
    OBSTACLE="越过障碍",
    DETOUR="绕行",
    REACTION_GM="环境与机关反应",
    UNIQUE_00="专用中断 1",
    UNIQUE_01="专用中断 2",
    LOOP_INSURANCE="防死循环兜底",
    DEPLETION_RETRY_CHARGE="力竭后重新蓄力",
    LEAD_CHASE="引导追击",
    GRAPPLE="角力",
    PETIT_CAUTION="短暂警戒",
    COMBAT_EM="怪物间战斗",
    ATTACK_STAY="怪物间战斗待机",
    POP_INTERACT="与环境物互动",
    CAUTION="警戒",
    FIND="发现目标",
    AREA_MOVE="区域移动",
    RETURN_AREA_CENTER="返回区域中心",
    ENTRY_EXIT="登场与退场",
    ESCAPE="逃跑",
    ESCAPE_SAFETY="逃往安全处",
    ESCAPE_PANIC="慌乱逃跑",
    PREDATOR="捕食",
    HUNT="狩猎",
    TAKE_OUT_APPROACH="接近猎物",
    TAKE_OUT_READY="准备捕获猎物",
    PREY_READY="被捕食准备",
    TRAIL="追踪",
    LIFE="生态行动",
    EVENT="事件演出",
    NPC_JACK="NPC 牵引",
    ANIMAL_PREVIEW="生态预览",
    REPEL="击退",
    GATHER_LEADER="群体集合",
    STORY="剧情",
)
SLOT_GROUPS = (
    (
        "与玩家战斗",
        (
            "COMBAT",
            "STATE_SIGN",
            "DAMAGE",
            "ATTACK_HIT",
            "FLASH",
            "RIDE",
            "OBSTACLE",
            "DETOUR",
            "REACTION_GM",
            "UNIQUE_00",
            "UNIQUE_01",
            "DEPLETION_RETRY_CHARGE",
            "LEAD_CHASE",
            "GRAPPLE",
            "PETIT_CAUTION",
            "LOOP_INSURANCE",
        ),
    ),
    ("与其他怪物", ("COMBAT_EM", "ATTACK_STAY", "RIDE_OTHER")),
)


# ------------------------------------------- target status and state signs

# CheckStatus.execute_BadCondition, player branch: resource CONDITION_TYPE ->
# cHunterBadConditions.get_Item index, whose _IsActive (0x2f) is read.
HUNTER_BAD_CONDITION_INDEX = dict(
    POISON=0,
    PARALYSE=3,
    SLEEP=2,
    BLAST=10,
    STUN=1,
    FIRE=4,
    ELEC=5,
    WATER=6,
    ICE=7,
    DRAGON=8,
    FROZEN=0xE,
    SPIDER_WEB=0xD,
    BUBBLE=0x10,
)
BAD_CONDITION_LABELS = dict(
    POISON="中毒",
    PARALYSE="麻痹",
    SLEEP="睡眠",
    BLAST="爆破异常",
    STUN="眩晕",
    FIRE="火焰异常",
    ELEC="雷异常",
    WATER="水异常",
    ICE="冰异常",
    DRAGON="龙异常",
    FROZEN="冻结",
    SPIDER_WEB="蛛网束缚",
    BUBBLE="泡沫异常",
)
# CheckStatus.execute_Status, player branch: HunterCharacter status-flag bits;
# either listed bit satisfies the status.
HUNTER_STATUS_BITS = dict(DOWN_PL=(9, 8), SMASH=(10, 11))
HUNTER_STATUS_LABELS = dict(DOWN_PL="玩家倒地", SMASH="玩家被击飞")
HUNTER_BAD_CONDITION_SOURCE = (
    "getPlayerManageInfo 的 HunterCharacter 状态模块；cHunterBadConditions.get_Item({index})._IsActive（0x2f） != 0"
)
HUNTER_STATUS_SOURCE = (
    "getPlayerManageInfo 的 HunterCharacter（0x18→0xe0→0x20）状态位 {bits} 任一为真"
)
STATE_SIGN_SOURCE = (
    "cEnemyContext.StateSignActionType（0x40→0x358）不为 -1，且等于 getSTATE_SIGN_ACTION_TYPEFromFixed(资源值)"
)
STATE_SIGN_LABELS = dict(
    COMBAT_BEGIN="刚进入战斗",
    ANGRY_BEGIN="刚进入愤怒",
    ANGRY_END="愤怒刚结束",
    TIRED_BEGIN="刚进入疲劳",
    TIRED_RECOVER="疲劳刚恢复",
    LEAD_BEGIN="开始引导",
    FLASH_END="闪光效果刚结束",
    COMBAT_EM_END="怪物间战斗刚结束",
    COMBAT_EM_REACTION_INTIMIDATE="对其他怪物的威吓反应",
    REACTION_GIMMICK_BEGIN="环境机关反应开始",
    REACTION_GIMMICK_END="环境机关反应结束",
    DEPLETION_BEGIN="开始力竭",
    CAUTION_BEGIN="开始警戒",
    CAUTION_END="警戒结束",
    AREA_MOVE_BEGIN="开始区域移动",
    RETURN_CENTER_BEGIN="开始返回区域中心",
    HUNT_BEGIN="开始狩猎",
    ENTRY_END="登场结束",
    EXIT_BEGIN="开始退场",
)


# ------------------------------------------------------ published web models

# Published models keep what the web builder renders and validates. Research
# provenance stays in the full models under .agents.
PUBLISHED_STORAGE_FORMAT = "shared-values-v1"
RESEARCH_ONLY_MODEL_FIELDS = ("selectionRecovery", "standStates")
RESEARCH_ONLY_NODE_FIELDS = (
    "nativeNodeIdentity",
    "nativeSite",
    "nativeContinuation",
    "nativeContinuationRecovery",
    "nativePositionCallbackRecovery",
    "nativeRequestPosition",
    "nativeResumeRecovery",
    "nativeBinding",
    "requestSite",
    "callSite",
    "execution",
    "sourceBodyPointer",
    "expectedCommandType",
    "expectedArgumentType",
    "commandIndex",
    "selectionEffects",
    "initializerEvidence",
    "staticArray",
)
# Predicate fields that repeat the node's own binding.
PREDICATE_DUPLICATE_FIELDS = ("argument", "commandType", "argumentType")
# Repeated JSON values at least this long are stored once and referenced.
SHARED_VALUE_MIN_BYTES = 48


# ------------------------------------------------- version-independent symbols


POSITION_TYPE = "ace.btable.BTableDef.POSITION"
POSITION_STACK = "System.Collections.Generic.Stack`1<ace.btable.BTableDef.POSITION>"
# Every native identity the SDK relies on. ``resolve-symbols`` turns these into
# data/profiles/<gameVersion>.json for each build; code reads addresses from the
# active profile, never from literals.
SYMBOL_SPECS = {
    "set_current_position": Method(
        "ace.btable.cOperatorWork", "setCurrentPosition", (POSITION_TYPE,)
    ),
    "position_stack_push": Method(POSITION_STACK, "Push"),
    "position_stack_try_pop": Method(POSITION_STACK, "TryPop"),
    "request_change_btable": Method("app.cEmAIUpdateBTable", "requestChangeBTable"),
    "request_jump_btable": Method("app.cEmAIUpdateBTable", "requestJumpBTable"),
    "request_change_btable_verify": Method(
        "app.cMasterEnemyControllerEntity", "requestChangeBTableVerify"
    ),
    "request_unique_btable": Method("app.cEmAIInterruptUnique", "requestUniqueBTable"),
    "enemy_def_cctor": Method("app.EnemyDef", ".cctor"),
    "combat_on_enter": Method("app.cEmAIStateCombat", "onEnter"),
    "random_type_execute": Method("ace.btable.cCommandRandamRandomType", "onExecute"),
    "action_param_branch": Method("ace.user_data.ActionParam", "toBranchedParamIndex"),
    "action_param_apply": Method("ace.user_data.ActionParam", "applyParamCore"),
    "manager_setup_table": Method("ace.btable.cManager", "setupTable"),
    "manager_clear": Method("ace.btable.cManager", "clear"),
    "resume_jump_btable": Method("app.cEmAIUpdateBTable", "resumeJumpBTable"),
    "area_target_child": Method(
        "app.cEmModuleArea", "setTargetAreaChidl_CurrentAreaChild"
    ),
    "area_check_detached": Method(
        "app.mcEnemyAreaMoveCoordinator", "checkDetachedScheduleCategory"
    ),
    "area_recalc_schedule": Method("app.mcEnemyAreaMoveCoordinator", "recalcScheule"),
    "area_change_category": Method(
        "app.mcEnemyAreaMoveCoordinator", "changeScheduleCategory"
    ),
    "net_send_packet": Method("app.EnemyUtil.Net", "sendPacket"),
    "fetch_hate_target": Method("app.cEmModuleCombat", "fetchHighestHateTarget_Random"),
    "detector_attribute_ctor": Method(
        "app.cEnemyNoticeCombatDetectorAttribute",
        ".ctor",
        ("app.cEnemyContextHolder", "app.TARGET_ACCESS_KEY"),
    ),
    "detector_register": Method("app.cEmModuleDetector", "register"),
    "refresh_smoke": Method("app.cEmModuleCombat", "refreshEveryTargetStateInSmoke"),
    "target_resume": Method("app.cEmModuleTarget", "setTargetResume"),
    "target_position": Method("app.cEmModuleTarget", "getTargetPosition"),
    "nav_data_info": Method("app.VoxelDataManager", "getDataInfoForNav"),
    "wall_info_near": Method("app.VoxelDataManager", "getWallInfoNearVector"),
    "player_manage_info": Method("app.TargetAccessKeyUtil", "getPlayerManageInfo"),
    "make_target_key": Method(
        "app.TargetAccessKeyUtil", "makeTargetAccessKey", ("via.GameObject",)
    ),
    "unique_leveled_value_get_level": Method(
        "app.cEmModuleUniqueLeveledValue", "getLevel", ("System.Int32",)
    ),
    "check_angle_execute": Method(
        "app.btable.EmCommonCommand.cCheckAngle", "onExecute"
    ),
    "stack_cookie_check": Helper(),
    "position_array_resize": Helper(
        anchors=("position_stack_push",), exclude=("stack_cookie_check",)
    ),
    "pool_pair_construct": Helper(),
    "pool_array_copy": Helper(),
    "array_allocate": Helper(),
    "static_ref_acquire": Helper(),
    "static_ref_release": Helper(),
    "area_schedule_helper": Helper(anchors=("combat_on_enter",)),
    "class_hierarchy_check": Helper(anchors=("check_angle_execute",)),
    "restore_helper": Helper(),
    "global_table_entry_zero": Reviewed("表入口读取的静态字段；已核实路径中视为 0"),
    "runtime_data_start": Reviewed("运行时初始化数据起点；PE 映像中没有其值"),
    "pool_array_type_slot": Reviewed("ValueTuple<UInt32, Int32>[] 静态池数组的类型槽"),
    "unique_slot_table": Reviewed("EnemyDef..cctor 写入专用中断槽映射的指令位置与字节"),
    "destination_override_global": Reviewed("命令复制的 Nullable<vec3> 覆盖位置全局"),
    "terrain_component_global": Reviewed("HIGH 物理回退要求的有效组件全局"),
    "occlusion_length_constant": Reviewed("遮挡射线长度平方阈值常量"),
    "special_gimmick_global": Reviewed("遮挡检查的特殊 GIMMICK 索引全局"),
}
