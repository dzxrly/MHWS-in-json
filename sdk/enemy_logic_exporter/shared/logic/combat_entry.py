"""Reviewed shared Combat callbacks and asynchronous BTable request boundaries.

The event tables describe the shared native owner. Their dispatch destinations
come only from this monster's inventory and a separately verified dispatcher.
Unreviewed helper bodies remain explicit boundaries, including onEnter's area
schedule work and the scheduler's base/override resource selection.
"""

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from ..config import EVIDENCE_DIR, SUPPORTED_PROFILE
from .expressions import combined, compare, runtime


@lru_cache(maxsize=1)
def receipt():
    return json.loads(
        (EVIDENCE_DIR / "combat_entry_evidence.v1.json").read_text(encoding="utf8")
    )


def verify_sources(profile, metadata, pe):
    """Verify the actual method identities, field layout and read-only PE bytes."""
    if profile != SUPPORTED_PROFILE or profile != receipt()["profile"]:
        raise ValueError("共享 Combat 配方与来源版本不匹配")
    if metadata.sha256 != profile["metadataSha256"]:
        raise ValueError("共享 Combat 配方的元数据来源变化")
    for row in receipt()["methods"].values():
        method = metadata.get(row["type"])["methods"].get(row["method"])
        if not method or int(method["function"], 16) != int(row["address"], 16):
            raise ValueError("共享 Combat 方法身份或地址变化：" + row["method"])
        start, end = int(row["address"], 16), int(row["end"], 16)
        body = pe.read(start, end - start)
        if (
            len(body) != end - start
            or hashlib.sha256(body).hexdigest() != row["nativeSha256"]
        ):
            raise ValueError("共享 Combat 原生字节变化：" + row["method"])
    for owner, expected in receipt()["layouts"].items():
        fields = metadata.fields(owner)
        for name, identity in expected.items():
            field = fields.get(name, {})
            if (
                field.get("type") != identity["type"]
                or field.get("offset_from_base") != identity["offset"]
            ):
                raise ValueError("共享 Combat 字段布局变化：" + owner + "." + name)
    for owner, expected in receipt()["enums"].items():
        fields = metadata.get(owner)["fields"]
        if any(
            fields.get(name, {}).get("default") != value
            for name, value in expected.items()
        ):
            raise ValueError("共享 Combat 枚举变化：" + owner)


def _condition(identity, summary, expression, yes, no, **extra):
    return dict(
        id=identity,
        kind="condition",
        summary=summary,
        expression=expression,
        true=yes,
        false=no,
        **extra
    )


def _effect(identity, summary, following, effect, **extra):
    return dict(
        id=identity,
        kind="mutation",
        effect=effect,
        summary=summary,
        next=following,
        **extra
    )


def _boundary(identity, reason, following, **extra):
    return dict(id=identity, kind="unknown", reason=reason, next=following, **extra)


def _end():
    return dict(
        id="end",
        kind="return",
        value=None,
        returnType="void",
        summary="本次原生回调结束",
    )


def _raw(key, source):
    return runtime("combat:" + key, source)


def _eq(key, value, source):
    return compare("combat:" + key, value, source=source)


def _not(value):
    return dict(kind="not", item=value)


def build_combat_entries(model, monster):
    """Build JSON-only event tables after the caller verified source identities.

    This pure construction entry point supports bounded regression fixtures.
    Production extraction must use attach_combat_entries, which verifies sources.
    No event receives a blanket verified or complete Combat status.
    """
    if (
        model["profile"] != receipt()["profile"]
        or monster["enemyId"] != model["enemyId"]
    ):
        raise ValueError("共享 Combat 入口的怪物或来源版本不匹配")
    tables = {table["tableGuid"]: table for table in model["tables"]}
    bindings = {}
    for slot, source in monster["slots"].items():
        root = model.get("resourceEntries", {}).get(source)
        if root is not None:
            if (
                root.get("status") != "native_dispatch_table_zero_verified"
                or root.get("tableGuid") not in tables
            ):
                raise ValueError("共享 Combat 请求目标未经本资源原生调度器核实")
        bindings[slot] = dict(
            resource=source,
            **(
                {
                    "dispatchTarget": root["tableGuid"],
                    "dispatcherEvidence": root["evidence"],
                }
                if root
                else {}
            )
        )
    if "COMBAT" not in bindings:
        raise ValueError("本怪物的实际 BTableList 缺少 Combat 槽")

    def queue(identity, slot, following, *, verified=False):
        return _effect(
            identity,
            "排队请求 " + slot + " 行为表",
            following,
            "request_btable",
            requestedSlot=slot,
            requestedSlotId=receipt()["enums"]["app.EnemyDef.BTABLE_ID"][slot],
            changeRequestMode="verify_current_slot" if verified else "direct",
            waitUntilActionEnd={
                "status": "partial",
                "reason": "由 isWaitUntilActionEndBTable 的实际策略计算；不能固定为立即切换",
            },
            **bindings.get(slot, {})
        )

    def request(identity, slot, following, *, verified=False):
        return dict(
            id=identity,
            kind="call",
            targetTable="combat-request-" + slot.lower() + "-direct",
            resume=following,
            summary="按实际恢复请求状态排队请求 " + slot,
            verifiedCurrentSlot=verified,
        )

    manager = _raw(
        "controller_exists", "cEmAIState._EntityHolders(0x28)._Master(0x20) != null"
    )
    done_combat = _raw(
        "done_combat_begin",
        "cEnemyContext._FlagArray[DONE_COMBAT_BEGIN_ACTION=0]，0x308→数组0x20",
    )
    done_combat_em = _raw(
        "done_combat_em_begin",
        "cEnemyContext._FlagArray[DONE_COMBAT_EM_BEGIN_ACTION=1]，0x308→数组0x21",
    )
    sign_exists = _raw(
        "state_sign_exists",
        "cEnemyContext.BTable._ExistBTableArray[STATE_SIGN=25]，0x120→0x18→0x39",
    )
    begin_required = combined(
        "all", _not(done_combat), _not(done_combat_em), sign_exists
    )
    initial_phase_guard = combined(
        "any",
        _eq("previous_ai_state", 5, "AIStateManager._PrevAIStateID(0xe8)：PREDATOR=5"),
        combined(
            "all",
            _eq(
                "previous_ai_state",
                -1,
                "AIStateManager._PrevAIStateID(0xe8)：INVALID=-1",
            ),
            _not(_raw("any_interrupt", "AIStateManager._AnyInterruptResult(0x103)")),
        ),
        _raw(
            "lead_interrupt_exists",
            "AIStateManager._ExistInterruptResult[LEAD=5]，0xd0→数组0x25",
        ),
    )
    evidence = receipt()["methods"]
    results = []

    def table(identity, name, method, nodes, *, entry=None, extra_evidence=()):
        result = dict(
            tableGuid=identity,
            tableIndex=-1,
            name=name,
            evidence=deepcopy(evidence[method]),
            nativeEvidence=[deepcopy(evidence[key]) for key in extra_evidence],
            flowStatus="partial",
            entry=entry or nodes[0]["id"],
            nodes=nodes,
            sharedCombatEvent=True,
        )
        results.append(result)
        return result

    for slot in ("COMBAT", "STATE_SIGN"):
        table(
            "combat-request-" + slot.lower() + "-direct",
            "排队切换 " + slot + "：先处理恢复请求与跳表",
            "requestChangeBTable578130",
            [
                _boundary(
                    "wait_policy",
                    "调用方先计算 isWaitUntilActionEndBTable；该方法检查重启、反应事件、故事表和位集等上下文，也可能清除 ReactionGm+0x13 标志。完整等待策略尚未固化，不能将未知结果设成固定立即切换",
                    "resume_pending",
                    nativeEvidence=deepcopy(
                        evidence["isWaitUntilActionEndBTable592376"]
                    ),
                    callerScope=True,
                ),
                _condition(
                    "resume_pending",
                    "存在跳表恢复请求？",
                    _raw(
                        "jump_resume_requested",
                        "cEmAIUpdateBTable._IsRequestJumpBTableResume(0x68)",
                    ),
                    "same_main",
                    "queue",
                ),
                _condition(
                    "same_main",
                    "待恢复主表的当前槽已经是请求槽？",
                    _eq(
                        "scheduler_current_main_slot",
                        receipt()["enums"]["app.EnemyDef.BTABLE_ID"][slot],
                        "cEmAIUpdateBTable._CurrentMainBTable.ID(0x50)",
                    ),
                    "end",
                    "clear_resume",
                ),
                _effect(
                    "clear_resume",
                    "取消本次跳表恢复请求",
                    "queue",
                    "set_runtime_field",
                    field="cEmAIUpdateBTable._IsRequestJumpBTableResume(0x68)",
                    value=False,
                ),
                queue("queue", slot, "jump_valid"),
                _condition(
                    "jump_valid",
                    "当前跳表管理器有效？",
                    _raw(
                        "jump_manager_valid",
                        "cManager.get_Valid(JumpBTableManager=0x40)",
                    ),
                    "clear_jump",
                    "end",
                ),
                _effect(
                    "clear_jump",
                    "清除当前跳表槽并重置跳表管理器",
                    "end",
                    "clear_jump_manager",
                    fields={"_CurrentJumpBTable.ID": -1},
                    nativeTarget="0x1454bcc60",
                    reason="setupTable(null,false,true,false)；此操作不把主表恢复到根",
                ),
                _end(),
            ],
            extra_evidence=("isWaitUntilActionEndBTable592376", "get_Valid330442"),
        )

    table(
        "combat-request-verify",
        "核对当前槽后请求 Combat",
        "requestChangeBTableVerify592391",
        [
            _condition(
                "same_slot",
                "当前实际槽已经是 COMBAT？",
                _eq(
                    "current_btable_slot",
                    1,
                    "cEnemyContext.BTable._CurrentBTableID(0x14)；COMBAT=1",
                ),
                "clear_pending",
                "queue",
            ),
            _effect(
                "clear_pending",
                "取消已有主表待处理请求（存在时）",
                "end",
                "clear_pending_main_request",
                guard="_RequestMainBTable.ID != NONE=-1",
                fields={
                    "_RequestMainBTable.ID": -1,
                    "_RequestMainBTable.IsWaitUntilActionEnd": False,
                    "_RequestMainBTable.IsOverride": False,
                },
                reason="同一当前槽不会重新排队请求，也不会自动把当前位置改回根",
            ),
            request("queue", "COMBAT", "end", verified=True),
            _end(),
        ],
        extra_evidence=(
            "isWaitUntilActionEndBTable592376",
            "requestChangeBTable578130",
        ),
    )
    table(
        "combat-change-begin",
        "选择战斗开始提示或持续战斗",
        "changeState577113",
        [
            _condition(
                "begin",
                "尚未完成开战动作且存在 STATE_SIGN 表？",
                begin_required,
                "queue_sign",
                "combat",
            ),
            request("queue_sign", "STATE_SIGN", "sign_type"),
            _effect(
                "sign_type",
                "状态提示类型设为 COMBAT_BEGIN",
                "phase_begin",
                "set_runtime_field",
                field="cEnemyContext.StateSignActionType(0x358)",
                value=5,
            ),
            _effect(
                "phase_begin",
                "Combat 阶段设为 BEGIN",
                "end",
                "set_runtime_field",
                field="cEmAIStateCombat._State(0x3c)",
                value=0,
            ),
            dict(
                id="combat",
                kind="call",
                targetTable="combat-request-verify",
                resume="phase_update",
                summary="changeState(BEGIN,false) 转入 UPDATE 时核对当前 Combat 槽",
            ),
            _effect(
                "phase_update",
                "Combat 阶段设为 UPDATE",
                "end",
                "set_runtime_field",
                field="cEmAIStateCombat._State(0x3c)",
                value=1,
            ),
            _end(),
        ],
        extra_evidence=(
            "requestChangeBTable578130",
            "isWaitUntilActionEndBTable592376",
        ),
    )
    activation = {
        "MiniCompUpdator_BeforeBTableOnce(0x70)": [0, 1],
        "MiniCompUpdator_CtrlUpdate(0x68)": [12, 14, 63, 9],
        "MiniCompUpdator_AfterBTableOnce(0x78)": [8],
    }
    table(
        "combat-enter",
        "进入战斗：初始化、阶段选择及探测器",
        "onEnter577109",
        [
            _effect(
                "activate",
                "启用本次战斗所需的 MiniComponent",
                "component_setup",
                "activate_minicomponents",
                componentIds=activation,
                reason="onEnter 中的 activateComponentBase 调用；组件内部的执行语义另行核查",
            ),
            _boundary(
                "component_setup",
                "AfterBTableOnce 中索引8对应组件存在且类型匹配时调用 activateSetup；组件内部更新逻辑尚未全部恢复",
                "area_target",
            ),
            _effect(
                "area_target",
                "将目标子区域设为当前子区域",
                "manager",
                "native_helper_call",
                nativeTarget="0x143acf150",
                method="app.cEmModuleArea.setTargetAreaChidl_CurrentAreaChild276490",
            ),
            _condition("manager", "主控制器存在？", manager, "reset_flags", "end"),
            _effect(
                "reset_flags",
                "清除隐藏技能丢失和保留目标重置标志",
                "schedule",
                "set_runtime_fields",
                fields={
                    "Combat.IsHidingSkillLost(0xfa)": False,
                    "Combat.IsReservedResetDest(0x11)": False,
                },
            ),
            _boundary(
                "schedule",
                "按区域迁移类别、下一个中断及当前调度重新计算区域迁移，并可能变更调度类别和发送同步包；这些 helper 的完整副作用尚未逐项恢复",
                "initial_phase",
                nativeTargets=[
                    "0x1467148a0",
                    "0x1467140e0",
                    "0x146713810",
                    "0x146368d60",
                    "0x14635f4e0",
                ],
            ),
            _condition(
                "initial_phase",
                "前一状态为捕食、无前一状态且无中断，或存在引导中断？",
                initial_phase_guard,
                "change_begin",
                "send_detector",
            ),
            dict(
                id="change_begin",
                kind="call",
                targetTable="combat-change-begin",
                resume="send_detector",
            ),
            _condition(
                "send_detector",
                "请求发送探测器且未禁止发送？",
                combined(
                    "all",
                    combined(
                        "any",
                        _raw("send_detector", "Combat._IsSendDetector(0xf9)"),
                        _raw("auto_send_detector", "Combat._IsAutoSendDetector(0xfb)"),
                    ),
                    _not(
                        _raw(
                            "disable_send_detector",
                            "Combat._IsDisableSendDetector(0xfc)",
                        )
                    ),
                ),
                "detector_event",
                "clear_detector",
            ),
            _boundary(
                "detector_event",
                "构造并提交 Combat 探测器事件；事件对象与接收方完整行为尚未恢复",
                "clear_detector",
                nativeTargets=["0x147bf9d90", "0x1493dda70", "0x148d0cae0"],
            ),
            _effect(
                "clear_detector",
                "清除一次发送请求和禁止发送标志",
                "end",
                "set_runtime_fields",
                fields={
                    "Combat._IsSendDetector(0xf9)": False,
                    "Combat._IsDisableSendDetector(0xfc)": False,
                },
            ),
            _end(),
        ],
        extra_evidence=("changeState577113",),
    )
    table(
        "combat-return-interrupt",
        "从中断返回：重新选择战斗阶段",
        "onReturnInterrupt577105",
        [
            _condition("manager", "主控制器存在？", manager, "choose", "end"),
            dict(
                id="choose",
                kind="call",
                targetTable="combat-change-begin",
                resume="end",
                summary="原生尾跳 changeState(BEGIN,false)；由完成标志和 STATE_SIGN 存在性决定阶段",
            ),
            _end(),
        ],
        extra_evidence=("changeState577113",),
    )
    table(
        "combat-restart",
        "重启 Combat 回调",
        "onRestart577106",
        [
            _effect(
                "activate",
                "重新启用战斗 MiniComponent",
                "request_guard",
                "activate_minicomponents",
                componentIds=activation,
            ),
            _condition(
                "request_guard",
                "主控制器存在且第一个重启参数为真？",
                combined(
                    "all",
                    manager,
                    _raw(
                        "restart_request",
                        "onRestart 的第一个 Boolean 参数（r8b）；第二个参数不参与当前原生分支",
                    ),
                ),
                "queue",
                "end",
            ),
            request("queue", "COMBAT", "phase"),
            _effect(
                "phase",
                "Combat 阶段设为 UPDATE",
                "end",
                "set_runtime_field",
                field="cEmAIStateCombat._State(0x3c)",
                value=1,
            ),
            _end(),
        ],
        extra_evidence=(
            "requestChangeBTable578130",
            "isWaitUntilActionEndBTable592376",
        ),
    )
    table(
        "combat-table-end",
        "行为表结束：检查中断权限后继续 Combat",
        "onBTableEnd577108",
        [
            _condition(
                "interrupt",
                "有较高优先级中断允许强制切换？",
                dict(
                    kind="unknown",
                    reason="isHigherInterruptAcceptChangeState(ACCEPT_FORCE_ONLY=1,true) 检查待处理及按层缓存的中断权限；完整 helper 尚未恢复，不能固定为否",
                ),
                "end",
                "manager",
            ),
            _condition("manager", "主控制器存在？", manager, "smoke", "end"),
            _effect(
                "smoke",
                "刷新每个目标的烟雾状态",
                "phase",
                "native_helper_call",
                nativeTarget="0x147bf8ad0",
                method="app.cEmModuleCombat.refreshEveryTargetStateInSmoke544906",
            ),
            _condition(
                "phase",
                "阶段为 UPDATE，或 BEGIN 阶段结束的是 STATE_SIGN？",
                combined(
                    "any",
                    _eq("phase", 1, "Combat._State(0x3c)，UPDATE=1"),
                    combined(
                        "all",
                        _eq("phase", 0, "Combat._State(0x3c)，BEGIN=0"),
                        _eq(
                            "ended_btable_slot",
                            25,
                            "onBTableEnd 的实际槽参数，STATE_SIGN=25",
                        ),
                    ),
                ),
                "queue",
                "end",
            ),
            dict(
                id="queue",
                kind="call",
                targetTable="combat-request-verify",
                resume="set_update",
            ),
            _effect(
                "set_update",
                "Combat 阶段设为 UPDATE",
                "end",
                "set_runtime_field",
                field="cEmAIStateCombat._State(0x3c)",
                value=1,
            ),
            _end(),
        ],
        extra_evidence=("isHigherInterruptAcceptChangeState578225",),
    )
    table(
        "combat-table-change",
        "STATE_SIGN 开始执行时记录开战完成标志",
        "onBTableChange577107",
        [
            _condition(
                "slot",
                "变化后的实际槽为 STATE_SIGN？",
                _eq(
                    "changed_btable_slot",
                    25,
                    "onBTableChange 的实际参数；STATE_SIGN=25",
                ),
                "done",
                "end",
            ),
            _effect(
                "done",
                "记录 DONE_COMBAT_BEGIN_ACTION=true",
                "activate",
                "set_runtime_field",
                field="cEnemyContext._FlagArray[DONE_COMBAT_BEGIN_ACTION=0]",
                value=True,
                reason="标志在 STATE_SIGN 表切换回调时写入，不能改成该表所有动作结束后才写入",
            ),
            _effect(
                "activate",
                "启用 CtrlUpdate 组件72",
                "end",
                "activate_minicomponents",
                componentIds={"MiniCompUpdator_CtrlUpdate(0x68)": [72]},
                reason="原生内联检查组件存在后，按组件当前激活状态写入0x27与0x26；组件内部功能尚未恢复",
            ),
            _end(),
        ],
    )

    def scheduler_channel(channel):
        prefix = "scheduler:" + channel + ":"

        def raw(key, source):
            return runtime(prefix + key, source)

        def relation(key, value, operator="eq", source=""):
            return compare(prefix + key, value, operator, source=source)

        current = "_Current" + channel.title() + "BTable"
        pending = "_Request" + channel.title() + "BTable"
        needs_update = _raw(
            "btable_request_update", "cEnemyContext.BTable._IsReuqestUpdateBTable(0x11)"
        )
        pending_exists = relation("pending_slot", -1, "ne", pending + ".ID；NONE=-1")
        resource_refresh = combined(
            "all",
            relation("current_slot", -1, "ne", current + ".ID"),
            relation(
                "current_slot",
                40,
                "lt",
                "当前槽必须小于 BTABLE_ID.MAX=40；STORY=41 不参加自动覆盖表刷新",
            ),
        )
        waits = combined(
            "all",
            _not(needs_update),
            raw(
                "pending_wait",
                pending
                + ".IsWaitUntilActionEnd（结构偏移+4；检查的是待请求，不是当前表）",
            ),
            combined(
                "any",
                relation("pending_slot", 41, source=pending + ".ID；STORY=41"),
                relation("current_slot", 41, "ne", current + ".ID；STORY=41"),
            ),
        )
        manager_export = raw("manager_export", "cManager._IsExportTable(0x49)")
        operator_exists = raw("operator_exists", "cManager._OperatorWork(0x10) != null")
        manager_valid = combined(
            "any",
            manager_export,
            combined(
                "all",
                operator_exists,
                relation(
                    "operator_table_count",
                    0,
                    "ne",
                    "OperatorWork+0x48 所指表的0x18计数；get_Valid 的真实分支",
                ),
            ),
        )
        root_index = dict(
            kind="compare",
            operator="eq",
            left=runtime(
                prefix + "saved_table", "OperatorWork 当前保存位置 Table，0xa0"
            ),
            right=runtime(
                prefix + "export_root_index",
                "get_IsTableRoot 原生比较 ExportRuntimeBTable+0x30 的实际整数；未把字段名称推定为根表编号",
            ),
        )
        at_root = combined(
            "all",
            operator_exists,
            combined(
                "any",
                combined(
                    "all",
                    manager_export,
                    combined(
                        "any",
                        relation(
                            "saved_table",
                            0,
                            source="OperatorWork 当前保存位置 Table，0xa0",
                        ),
                        root_index,
                    ),
                ),
                combined(
                    "all",
                    _not(manager_export),
                    relation("saved_table", 0, "le", "普通表当前保存位置 Table，0xa0"),
                ),
            ),
            relation("saved_pc", 0, "le", "OperatorWork 当前保存位置 PC，0xa4"),
            relation("saved_command", 0, "le", "OperatorWork 当前保存位置命令，0xa8"),
        )
        nodes = [
            _effect(
                "eligibility",
                "本次更新许可取 BTable 的实际请求更新标志",
                "pending",
                "copy_runtime_field",
                sourceKey="combat:btable_request_update",
                targetKey=prefix + "update_eligible",
                reason="updateBTable 局部 bVar13 初值来自 _IsReuqestUpdateBTable；成功换表后会设为true",
            ),
            _condition(
                "pending", "已有待切换行为表？", pending_exists, "wait", "refresh_guard"
            ),
            _condition(
                "refresh_guard",
                "当前槽为有效的普通槽（非 STORY）？",
                resource_refresh,
                "refresh",
                "blocked",
            ),
            _boundary(
                "refresh",
                "没有显式待请求时，检查当前槽的基础/覆盖资源、资源启用状态及资源 GUID 差异；符合条件时将当前槽复制到待请求并更新覆盖标志。资源过滤和自动覆盖刷新仍有未核实 helper",
                "pending_after_refresh",
                channel=channel,
                currentFields=current,
                pendingFields=pending,
            ),
            _condition(
                "pending_after_refresh",
                "自动刷新后存在待切换请求？",
                pending_exists,
                "wait",
                "blocked",
            ),
            _condition(
                "wait", "待请求要求等待且本帧未获更新许可？", waits, "end", "resource"
            ),
            _condition(
                "resource",
                "请求的行为资源可用且通过基础/覆盖资源筛选？",
                dict(
                    kind="unknown",
                    reason="STORY 使用 _OverrideBTableFromStory(0x30)；其他槽按 IsEnableOverrideNew 位集及实际资源启用状态选择基础/覆盖表。资源 GUID 比较和启用 helper 尚未完全固化",
                ),
                "install",
                "blocked",
            ),
            _effect(
                "install",
                "切换管理器资源并清除待请求槽",
                "change_callback",
                "install_requested_btable",
                channel=channel,
                currentFields=current,
                pendingFields=pending,
                writes={prefix + "update_eligible": True},
                reason="复制待请求到当前数据，setupTable(selectedResource,true,true)，仅将待请求ID写为NONE=-1；IsOverride由实际选择的资源确定",
            ),
            _effect(
                "change_callback",
                "通知实际槽变化 OnBTableChange",
                "blocked",
                "emit_btable_callback",
                channel=channel,
                callback="OnBTableChange",
                slotKey=prefix + "current_slot",
            ),
            _condition(
                "blocked",
                "持续或永久标志禁止 BTable 更新？",
                combined(
                    "any",
                    _raw(
                        "permanent_disable_btable",
                        "cEnemyContext._PermanentFlag(0x2e8) bit0",
                    ),
                    _raw(
                        "continue_disable_btable",
                        "cEnemyContext._ContinueFlag(0x2d8).check(DISABLE_BTABLE_UPDATE=0)",
                    ),
                ),
                "end",
                "execute_guard",
            ),
            _condition(
                "execute_guard",
                "本次获得更新许可且管理器有效？",
                combined(
                    "all",
                    raw(
                        "update_eligible",
                        "本次调用局部 bVar13：请求更新标志或成功安装待请求",
                    ),
                    manager_valid,
                ),
                "root",
                "end",
            ),
            _condition(
                "root",
                "当前保存位置是行为表根位置？",
                at_root,
                "begin_callback",
                "execute",
            ),
            _effect(
                "begin_callback",
                "通知表从根位置开始 OnBTableBegin",
                "execute",
                "emit_btable_callback",
                channel=channel,
                callback="OnBTableBegin",
                slotKey=prefix + "current_slot",
                reason="真实 getter 同时核对Table、PC与命令保存位置，不把每帧更新都当作重新进入根",
            ),
            _effect(
                "execute",
                "执行该管理器保存位置上的行为逻辑",
                "ended",
                "update_btable_manager",
                channel=channel,
                nativeEvidence=deepcopy(evidence["updateTable330454"]),
                reason="Export 模式经虚表 updateTableInpl 执行；结束标志由导出方法状态和 OperatorWork+0xc6决定。普通模式使用单独的命令循环",
            ),
            _condition(
                "ended",
                "该管理器的真实 IsTableEnd 标志为真？",
                raw(
                    "manager_table_end",
                    "cManager.<IsTableEnd>k__BackingField(0x4a)，在 updateTable 执行之后读取",
                ),
                "end_callback",
                "end",
            ),
            _effect(
                "end_callback",
                "发送实际槽的 OnBTableEnd 回调",
                "end",
                "emit_btable_callback",
                channel=channel,
                callback="OnBTableEnd",
                slotKey=prefix + "current_slot",
                reason="回调由 AIStateManager 按活跃中断或当前 AI 状态路由；不能无条件返回 Combat 根",
            ),
            _end(),
        ]
        table(
            "combat-scheduler-" + channel,
            ("跳表" if channel == "jump" else "主表") + "请求、等待与执行",
            "updateBTable578143",
            nodes,
            extra_evidence=(
                "get_Valid330442",
                "get_IsTableRoot578098",
                "updateTable330454",
            ),
        )

    scheduler_channel("jump")
    scheduler_channel("main")
    table(
        "combat-scheduler-update",
        "逐帧调度：跳表优先及保存位置恢复",
        "update578140",
        [
            _condition(
                "enabled",
                "本帧允许 BTable 更新？",
                _raw(
                    "need_btable_update",
                    "cEmAIUpdateBTable._IsNeedUpdate(0x69)；活跃中断可由 checkUpdateExecute 将其清零",
                ),
                "resume_requested",
                "end",
            ),
            _condition(
                "resume_requested",
                "已请求从跳表恢复？",
                _raw(
                    "jump_resume_requested",
                    "cEmAIUpdateBTable._IsRequestJumpBTableResume(0x68)",
                ),
                "restore",
                "jump_update",
            ),
            _boundary(
                "restore",
                "先通知主表槽变化，清除跳表及其目标备份，再恢复主表保存的 table/PC/命令位置；原生 export 与普通表恢复路径不同，尚未全部接到已恢复节点",
                "end",
                nativeTargets=[
                    "0x1490c5770",
                    "0x1454bd490",
                    "0x1469cbe60",
                    "0x1454bd9c0",
                ],
                resumeScope="saved_main_table_position",
                freshRoot=False,
            ),
            dict(
                id="jump_update",
                kind="call",
                targetTable="combat-scheduler-jump",
                resume="jump_active",
                summary="先处理跳表的待请求、等待与保存位置执行",
            ),
            _condition(
                "jump_active",
                "跳表管理器仍有效？",
                _raw(
                    "jump_manager_valid",
                    "cManager.get_Valid(JumpBTableManager=0x40)；true 时本帧不更新主表",
                ),
                "end",
                "main_update",
            ),
            dict(
                id="main_update",
                kind="call",
                targetTable="combat-scheduler-main",
                resume="end",
                summary="跳表无效时处理主表；当前槽和保存位置独立",
            ),
            _end(),
        ],
        extra_evidence=(
            "updateBTable578143",
            "resumeJumpBTable578134",
            "updateTable330454",
            "checkUpdateExecute578139",
        ),
    )
    entries = [
        dict(
            kind=kind,
            status="partial",
            label=name,
            table=identity,
            node=next(t["entry"] for t in results if t["tableGuid"] == identity),
            evidence=deepcopy(evidence[method]),
        )
        for kind, name, identity, method in [
            ("combat_enter", "进入 Combat", "combat-enter", "onEnter577109"),
            (
                "resume",
                "从中断返回 Combat",
                "combat-return-interrupt",
                "onReturnInterrupt577105",
            ),
            ("resume", "重启 Combat", "combat-restart", "onRestart577106"),
            (
                "combat_update",
                "逐帧更新主表/跳表",
                "combat-scheduler-update",
                "update578140",
            ),
            (
                "combat_update",
                "Combat 收到行为表结束回调",
                "combat-table-end",
                "onBTableEnd577108",
            ),
            (
                "combat_update",
                "Combat 收到槽变化回调",
                "combat-table-change",
                "onBTableChange577107",
            ),
        ]
    ]
    scheduler = dict(
        status="partial",
        sourceProfile=deepcopy(model["profile"]),
        slotBindings=bindings,
        requestSemantics="request_btable 排队写入待切换字段；dispatchTarget 是调度器之后可能选择的资源入口，不是同步子表调用",
        updateSemantics="跳表优先；跳表管理器有效时该帧不更新主表；恢复请求使用主表保存位置",
        limits=deepcopy(receipt()["limits"]),
        semanticReviewComplete=False,
    )
    return dict(tables=results, entryPoints=entries, combatScheduler=scheduler)


def attach_combat_entries(model, monster, metadata, pe):
    """Attach verified-source partial shared events to this monster's native graph."""
    verify_sources(model["profile"], metadata, pe)
    additions = build_combat_entries(model, monster)
    identities = {t["tableGuid"] for t in model["tables"]}
    if identities & {t["tableGuid"] for t in additions["tables"]}:
        raise ValueError("模型已含共享 Combat 事件，不能重复附加")
    model["localBattleEntry"] = model["entry"]
    model["entry"] = "combat-enter"
    model["tables"].extend(additions["tables"])
    model.setdefault("entryPoints", []).extend(additions["entryPoints"])
    model["combatScheduler"] = additions["combatScheduler"]
    model["semanticReviewComplete"] = False
    return model
