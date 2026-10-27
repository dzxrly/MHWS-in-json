"""Offline analysis entry for EM0022_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0022_00_0"
NATIVE_OWNER = "Em0022_00"

# Area checks (game 1.42.0.2) read cEnemyContext.Area _CurrentStageNo (+0x14)
# and _CurrentAreaNo (+0xe0): cCheckNest is area 14 on stage 3; cCheckThrowBall
# is true unless the monster is in area 4 of stage 3.
FIELD_CHECKS = {
    "app.btable.Em0022_00BTableCommand.cCheckNest": dict(
        spec=(
            "all",
            ("key:self_current_area_no", "==", 14),
            ("key:self_current_stage_no", "==", 3),
        ),
        evidence=[
            dict(
                type="app.btable.Em0022_00BTableCommand.cCheckNest",
                method="onExecute1233721",
                address="0x145393190",
                end="0x1453931c0",
            )
        ],
        summary="怪物位于地图 3 的区域 14",
    ),
    "app.btable.Em0022_00BTableCommand.cCheckThrowBall": dict(
        spec=(
            "any",
            ("key:self_current_stage_no", "!=", 3),
            ("key:self_current_area_no", "!=", 4),
        ),
        evidence=[
            dict(
                type="app.btable.Em0022_00BTableCommand.cCheckThrowBall",
                method="onExecute1233725",
                address="0x1459df7b0",
                end="0x1459df7f0",
            )
        ],
        summary="怪物不在地图 3 的区域 4",
    ),
}


FORMULA_HISTORY_TABLES = {
    "app.Em0022_00_BTable_CommonAttack_Export": (
        "table_14307a99_b47d_42ba_80d3_729489e9247a",
    ),
    "app.Em0022_00_BTable_Life_Export": ("table_1ec993b5_de43_4558_ab33_ccb68d9ce785",),
}


def table_history_policy(row):
    method = row["method"]
    policy = {}
    formula = FORMULA_HISTORY_TABLES.get(row["type"], ())
    if any(
        method.startswith(stem) and method[len(stem) :].isdigit() for stem in formula
    ):
        policy["formula"] = True
    return policy or None


def recover_condition(node, enemy_id, resources):
    """Reviewed field-comparison commands of this monster (FIELD_CHECKS)."""
    from ..shared.logic.field_checks import declared_condition

    count = _recover_group_count(node)
    return count if count is not None else declared_condition(FIELD_CHECKS, node)


GROUP_COUNT_COMMANDS = {
    "app.btable.Em0022_00BTableCommand.cCheckEm1023Count": "squad",
    "app.btable.Em0022_00BTableCommand.cCheckServantCount": "servant",
}
COUNT_OPERATORS = {0: "ge", 1: "le", 2: "eq"}


def _recover_group_count(node):
    from ..shared.logic.expressions import combined, compare, runtime
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition
    from ..shared.logic.values import enum_number, scalar

    kind = GROUP_COUNT_COMMANDS.get(node.get("commandType"))
    if kind is None:
        return None
    argument = node["argument"]
    operator = COUNT_OPERATORS.get(enum_number(argument["_EditCheckType"]))
    count = scalar(argument["_EditCheckCount"])
    if operator is None or type(count) is not int:
        return None
    if kind == "squad":
        total = "em0022_squad_member_count"
        leader = "em0022_squad_leader_system_index"
        found = "em0022_squad_extend_valid"
        # Native subtracts one only when the group's Em0022 index is not -1.
        expression = combined(
            "all",
            runtime(found, "findSquad 非空且 ExtendInfo 类型是 cEm0022_00GroupExtend"),
            combined(
                "any",
                combined(
                    "all",
                    compare(leader, -1, source="_Em0022SysIndex"),
                    compare(
                        total, count, operator, source="小队 _MemberList._IdxMgr.Count"
                    ),
                ),
                combined(
                    "all",
                    compare(leader, -1, "ne", source="_Em0022SysIndex"),
                    compare(
                        total,
                        count + 1,
                        operator,
                        source="小队 _MemberList._IdxMgr.Count，扣除雪狮子王",
                    ),
                ),
            ),
        )
        inputs = {
            found: dict(label="自身小队存在且有雪狮子王组扩展", boolean=True),
            total: dict(
                label="自身小队的有效成员总数（含已登记的雪狮子王）",
                number=True,
                min=0,
                max=None,
            ),
            leader: dict(
                label="小队登记的雪狮子王系统索引（-1 表示未登记）",
                number=True,
                min=-1,
                max=None,
            ),
        }
        summary = f"扣除已登记雪狮子王后，小队成员数 { {'ge': '≥', 'le': '≤', 'eq': '='}[operator]} {count}"
        evidence = "snow_squad_count"
    else:
        found = "em0022_corps_found"
        total = "em0022_owned_servant_count"
        expression = combined(
            "all",
            runtime(found, "EnemyManager.findCorps(Context.Group) 非空"),
            compare(
                total,
                count,
                operator,
                source="corps 有效成员中 CreatedOwner 等于自身 Context.Target._This 的数量",
            ),
        )
        inputs = {
            found: dict(label="自身所属群体记录存在", boolean=True),
            total: dict(
                label="该群体中由自身创建的有效成员数", number=True, min=0, max=None
            ),
        }
        summary = f"群体中由自身创建的成员数 { {'ge': '≥', 'le': '≤', 'eq': '='}[operator]} {count}"
        evidence = "snow_servant_count"
    return reviewed_condition(
        expression, condition_evidence(evidence), summary=summary, inputs=inputs
    )


# Verified Extend rule of this monster (game 1.42.0.2); the record lives in
# data/rules.v1.json, the offsets below are checked by the curation command.
EXTEND_TYPE = "app.cEm0022_00Extend"
BREAK_FANG_COMMAND = "app.btable.Em0022_00BTableCommand.cCheckBreakFangCount"
BREAK_FANG_OFFSET = 0x70
# Resource compare type -> operator over the broken fang count.
FANG_COMPARE = {0: "ge", 1: "le", 2: "eq"}

RULE_SPECS = (
    (
        BREAK_FANG_COMMAND,
        "fang_count",
        "专用",
        "断牙数量：比较类型 0 为 ≥，1 为 ≤，2 为 =",
        {"compare": 0x10, "value": 0x18},
        EXTEND_TYPE,
        BREAK_FANG_OFFSET,
    ),
)


def _compile_fang_count(compiler, predicate, values):
    from ..shared.logic.values import enum_number
    from ..shared.models.player_view import comparison, missing_state, unknown

    if not predicate.get("contextBinding"):
        return missing_state()
    key, label = compiler.context_field(predicate["contextBinding"])
    operator = FANG_COMPARE.get(enum_number(values["compare"]))
    if operator is None:
        return unknown("不支持的断牙数量比较")
    compiler.inputs[key] = dict(label=label, number=True, min=0, max=None)
    return comparison(key, operator, values["value"])


def _evaluate_fang_count(rule, bound, context, state):
    from ..shared.logic.predicates import context_value
    from ..shared.logic.values import MissingState, enum_number, number

    actual = context_value(state, bound["contextBinding"])
    expected = number(bound["values"]["value"])
    operator = FANG_COMPARE.get(enum_number(bound["values"]["compare"]))
    if operator is None:
        raise MissingState("不支持的断牙数量比较")
    return {
        "ge": actual >= expected,
        "le": actual <= expected,
        "eq": actual == expected,
    }[operator]


RULE_KINDS = {
    "fang_count": dict(compile=_compile_fang_count, evaluate=_evaluate_fang_count)
}


def extract(context):
    """Select this monster's declared tables, imports and native method contexts."""
    return context.extract_enemy(ENEMY_ID, NATIVE_OWNER)


def build_model(
    exe,
    metadata,
    natives,
    native_index,
    helper_index,
    *,
    requests_path=None,
    inventory_path=None,
    context=None,
):
    """Extract this EM from its real slot/import closure and typed native calls."""
    from ..shared.models.native_recipe import build_monster

    return build_monster(
        ENEMY_ID,
        NATIVE_OWNER,
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        requests_path=requests_path,
        inventory_path=inventory_path,
        context=context,
    )
