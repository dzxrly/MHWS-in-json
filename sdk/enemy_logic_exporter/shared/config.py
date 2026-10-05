"""Bundled paths, reviewed source identity and version-specific native constants.

Every address, structure offset and IL2CPP type/method/field name below belongs
to the reviewed game version in SUPPORTED_PROFILE. After a game update, review
this file against the new EXE and metadata; replacing the profile digests alone
never proves that an address, offset or method suffix is still valid.
"""

from pathlib import Path

# --------------------------------------------------------------------- paths

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EVIDENCE_DIR = DATA_DIR / "evidence"
MODEL_DIR = DATA_DIR / "models"
RULES_PATH = DATA_DIR / "rules.v1.json"


# ------------------------------------------------------------ source profile

SUPPORTED_PROFILE = {
    "gameVersion": "1.42.0.2",
    "exeSha256": "aa38eb46ae1f3c6c94fb2dd94af59b4665bd4c8ccee56bc36b88cf82397a5b4a",
    "metadataSha256": "01ab8f96c9786f3707fc0fc0376eb2e34124eea2d61b749354cac6e124b323d1",
}


# --------------------------------------------------- native functions (VA)

# Stack-cookie check emitted in every frame; it has no BTable semantics.
FN_STACK_COOKIE_CHECK = 0x14B1295F0
# ace.btable.cOperatorWork.setCurrentPosition233780
FN_SET_CURRENT_POSITION = 0x147739590
# System.Collections.Generic.Stack`1<ace.btable.BTableDef.POSITION>.Push233552
FN_POSITION_STACK_PUSH = 0x1450DC570
# System.Collections.Generic.Stack`1<ace.btable.BTableDef.POSITION>.TryPop233551
FN_POSITION_STACK_TRY_POP = 0x1450DC510
# POSITION[] growth helper reached from inlined Stack.Push.
FN_POSITION_ARRAY_RESIZE = 0x146F5F380

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
GLOBAL_TABLE_ENTRY_ZERO = 0x1547370B0
# Runtime-initialized data starts here; the PE image holds no value for it.
RUNTIME_DATA_START = 0x154000000

# Static weighted-pool initializers in <Export>..cctor.
FN_POOL_PAIR_CONSTRUCT = 0x143928820
FN_POOL_ARRAY_COPY = 0x143801F50
# The allocator receives the array length in r8 and the dimension count in r9.
FN_ARRAY_ALLOCATE = 0x14B030670
FN_STATIC_REF_ACQUIRE = 0x14B007BD0
FN_STATIC_REF_RELEASE = 0x14B0099E0
# Type slot of System.ValueTuple<UInt32, Int32>[] pool arrays.
POOL_ARRAY_TYPE_SLOT = 0x1547535A0
POOL_PAIR_CONSTRUCT_LABELS = (
    "FUN_143928820",
    "func_0x000143928820",
    "mhws_c49d22bf7e7e9cbe",
)
POOL_ARRAY_COPY_LABEL = "FUN_143801f50"


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
EM0166_BATTLE_PHASE_COMMAND = "app.btable.Em0166_00BTableCommand.cCheckBattlePhase"
POOL_ELEMENT_TYPE = "System.ValueTuple<System.UInt32,System.Int32>"
VOID_TYPE = "System.Void"


def extend_types(owner):
    """Self-Extend class names for "Em0021_00", then its species "Em0021"."""
    return [f"app.c{owner}Extend", f"app.c{owner.split('_')[0]}Extend"]


NO_ARGUMENT_TYPES = ("", "ace.btable.cCommandArgumentNone")

# Native evidence of the random-type command read by the machine.
RANDOM_TYPE_COMMAND_EVIDENCE = dict(
    type=RANDOM_TYPE_COMMAND,
    method="onExecute1028270",
    address="0x1445a25f0",
    end="0x1445a2600",
    nativeSha256="8ba94aab93435a2d65e9266143de140bcb34b90369a6894a304afc0d3952c2ee",
)

# The native selector passes a uniquely owned default or branched _ActionClass
# to the requested action's applyActionParam virtual method.
PARAMETER_SELECTION_EVIDENCE = (
    {
        "type": "ace.user_data.ActionParam",
        "method": "toBranchedParamIndex245936",
        "address": "0x1451e3e30",
        "end": "0x1451e3fd3",
        "nativeSha256": "f139b134a58c5dcfd6ec44d02f039e3bacd537906957523cbe24f51cef2c41c5",
    },
    {
        "type": "ace.user_data.ActionParam",
        "method": "applyParamCore245935",
        "address": "0x1451e3c90",
        "end": "0x1451e3e2a",
        "nativeSha256": "241d619ff2645fc76c1c7605b1d97678d7fb8575e7b0c48b805c035d06676977",
    },
)


# -------------------------------------------- shared Combat callback recipe

COMBAT_METHODS = dict(
    request_change="requestChangeBTable578130",
    request_verify="requestChangeBTableVerify592391",
    change_state="changeState577113",
    on_enter="onEnter577109",
    on_return_interrupt="onReturnInterrupt577105",
    on_restart="onRestart577106",
    on_table_end="onBTableEnd577108",
    on_table_change="onBTableChange577107",
    update_btable="updateBTable578143",
    update="update578140",
    wait_until_action_end="isWaitUntilActionEndBTable592376",
    manager_valid="get_Valid330442",
    table_root="get_IsTableRoot578098",
    update_table="updateTable330454",
    resume_jump="resumeJumpBTable578134",
    check_update="checkUpdateExecute578139",
    higher_interrupt="isHigherInterruptAcceptChangeState578225",
)

COMBAT_NATIVE_TARGETS = dict(
    # ace.btable.cManager.setupTable330447
    clear_jump="0x1454bcc60",
    # app.cEmModuleArea.setTargetAreaChidl_CurrentAreaChild276490
    area_target="0x143acf150",
    # mcEnemyAreaMoveCoordinator checkDetachedScheduleCategory/recalcScheule/
    # changeScheduleCategory, an unnamed helper and EnemyUtil.Net.sendPacket.
    area_schedule=(
        "0x1467148a0",
        "0x1467140e0",
        "0x146713810",
        "0x146368d60",
        "0x14635f4e0",
    ),
    # cEmModuleCombat.fetchHighestHateTarget_Random,
    # cEnemyNoticeCombatDetectorAttribute..ctor, cEmModuleDetector.register.
    detector_event=("0x147bf9d90", "0x1493dda70", "0x148d0cae0"),
    # app.cEmModuleCombat.refreshEveryTargetStateInSmoke544906
    smoke="0x147bf8ad0",
    # cEmAIUpdateBTable.resumeJumpBTable, cManager.clear,
    # cEmModuleTarget.setTargetResume and an unnamed restore helper.
    restore=("0x1490c5770", "0x1454bd490", "0x1469cbe60", "0x1454bd9c0"),
)

COMBAT_HELPER_METHODS = dict(
    area_target="app.cEmModuleArea.setTargetAreaChidl_CurrentAreaChild276490",
    smoke="app.cEmModuleCombat.refreshEveryTargetStateInSmoke544906",
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
    nav_query="getDataInfoForNav（0x14563bf40）查询自身位置成功",
    target_module="holder.Em.Target（0x40→0x100）非空；覆盖位置存在时仍检查",
    override_position="命令复制的 Nullable<vec3>._HasValue；0x1547cabf0，不假定其运行时值",
    target_position="Target.getTargetPosition(0, false)（0x1469cc720）的 Nullable 有值",
    wall_query="getWallInfoNearVector（0x145507880）查询目标位移方向成功",
    terrain_fallback="HIGH 物理回退要求本次 TERRAIN_CHARACTER 射线至少命中一个有效对象且包含全局0x1547277c8指定的有效组件；组件类型与查询构造仍未完整核实",
    unique_index_mask="所选 TARGET_ACCESS_KEY.UniqueIndex 的最高位为0；命令掩码0x80000000ffffffff",
    hunter_lookup="findHunterContext 返回非空对象（0x1484a3c10）",
    hunter_character="返回对象0x18的HunterCharacter存在，且角色0x10对象非空",
    occlusion_length="getRayTargetBasePos(_This)/Nullable覆盖位置与getRayTargetBasePos(目标键)之差的 x²+y²+z²；常量0x14dc43cd0=2500",
    special_gimmick_missing="缺少全局0x15480a9b0的特殊GIMMICK索引",
    request_mask="Accessor._Context._Em.BTable._IsBTableRequestActionMask；0x28→0x68→0x40→0x120→0x13",
    actor_net_info="请求 actor 的 Context._Em.NetInfo(0xf0) != null",
    actor_host_index="请求 actor 的 NetInfo._HostMemberIndex(+0x24)",
    actor_self_index="请求 actor 的 NetInfo._SelfMemberIndex(+0x20)",
)

RANDOM_DRAW_SOURCE = "cCommandWork.Random（匹配元数据偏移0x10）在该原生调用位置返回的整数余数"

OCCLUSION_QUERY = dict(
    queryType="app.RAY_CAST_TYPE.TERRAIN_EM_SIGHT",
    specialGimmickIndexGlobal="0x15480a9b0",
    throughIdField="app.cEmModuleTarget._OccludedCheckThroughGmIDs (0x70)",
    hitKeySource="app.TargetAccessKeyUtil.makeTargetAccessKey (0x14841eb30)",
)

REQUEST_EFFECTS = (
    ("cEnemyContext._FlagArray[WAITING_REQUEST_ACTION_RANDOM_OPERATOR=14]", "0x308→0x2e"),
    ("cEnemyContext._FlagArray[NO_REQUEST_ACTION=50]", "0x308→0x52"),
)


# ------------------------------------------------------ rule curation specs

# (command, kind, scope, summary, argument offsets, context type, offset)
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
        "app.btable.Em0021_00BTableCommand.cCheckMushroomType",
        "mushroom",
        "专用",
        "蘑菇类型相等，或当前类型为 5 且要求类型不为 0",
        {"value": 0x10},
        "app.cEm0021_00Extend",
        0x98,
    ),
    (
        "app.btable.Em0021_00BTableCommand.cCheckCatchMushroom",
        "catch_mushroom",
        "专用",
        "拿取物品内部值属于 0、1、2、3、4、5、7",
        {},
        "app.cEm0021_00Extend",
        0xA0,
    ),
    (
        "app.btable.Em0022_00BTableCommand.cCheckBreakFangCount",
        "fang_count",
        "专用",
        "断牙数量：比较类型 0 为 ≥，1 为 ≤，2 为 =",
        {"compare": 0x10, "value": 0x18},
        "app.cEm0022_00Extend",
        0x70,
    ),
    (
        "app.btable.Em0046_00BTableCommand.cCheckElectricLevel",
        "electric",
        "专用",
        "要求电力等级 2 时接受内部值 2 或 3；其余等级使用相等比较",
        {"value": 0x10},
        "app.cEm0046_00Extend",
        0x108,
    ),
    (
        "app.btable.Em0071_00BTableCommand.cCheckStateType",
        "unique_state",
        "专用",
        "专用内部状态相等；不将其解释为全局战斗阶段",
        {"value": 0x10},
        "app.cEm0071_00Extend",
        0xEC,
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
    0x1490C5680: ("app.cEmAIUpdateBTable", "requestChangeBTable578130", "change"),
    0x1490C56F0: ("app.cEmAIUpdateBTable", "requestJumpBTable578131", "jump"),
    0x1499F1110: (
        "app.cMasterEnemyControllerEntity",
        "requestChangeBTableVerify592391",
        "change_verify",
    ),
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
UNIQUE_SLOT_REQUESTER = ("app.cEmAIInterruptUnique", "requestUniqueBTable577693")
UNIQUE_SLOT_TABLE = dict(
    owner="app.EnemyDef",
    method=".cctor758120",
    site=0x14A2B56B2,
    bytes=(
        "41b8030000004889f141b901000000c5f877e8a7afd7004889c7"
        "48b8ffffffff2200000048894720c747282300000048393dd88a5d0a"
    ),
    global_address="0x15488e1c0",
    values=(-1, 0x22, 0x23),
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
RESEARCH_ONLY_MODEL_FIELDS = ("selectionRecovery",)
RESEARCH_ONLY_NODE_FIELDS = (
    "nativeNodeIdentity",
    "nativeSite",
    "nativeContinuation",
    "nativeContinuationRecovery",
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
