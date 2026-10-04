"""Reviewed request-command guards; actor helpers remain bounded evidence."""

from copy import deepcopy
from functools import lru_cache
import json
from ..config import EVIDENCE_DIR
from .expressions import combined, runtime


@lru_cache(maxsize=1)
def receipt():
    return json.loads(
        (EVIDENCE_DIR / "action_command_evidence.v1.json").read_text(encoding="utf8")
    )


def request_details(command, profile, command_evidence=None, metadata=None):
    if profile != receipt()["profile"]:
        raise ValueError("动作请求配方与来源版本不匹配")
    row = receipt()["commands"].get(command)
    if row is None:
        return None
    if command_evidence is None:
        return None
    if any(
        command_evidence.get(key) != row[key]
        for key in ("type", "method", "address", "end", "nativeSha256")
    ):
        raise ValueError("动作请求实现与已核实的原生命令身份不匹配")
    if metadata is not None:
        for owner, expected in receipt()["layouts"].items():
            fields = metadata.fields(owner)
            if any(
                fields.get(name, {}).get("type") != field["type"]
                or fields.get(name, {}).get("offset_from_base") != field["offset"]
                for name, field in expected.items()
            ):
                raise ValueError("动作请求命令的字段布局变化：" + owner)
    guard = combined(
        "all",
        runtime(
            "enemy_command_work_valid",
            "命令工作存在且原生类型检查为 cEnemyBTableCommandWork",
        ),
        dict(
            kind="not",
            item=runtime(
                "btable_request_action_mask",
                "Accessor._Context._Em.BTable._IsBTableRequestActionMask；0x28→0x68→0x40→0x120→0x13",
            ),
        ),
    )
    details = dict(
        requestGuard=guard,
        semanticEvidence=deepcopy(row),
        requestImplementation=(
            "synchronous" if command.endswith("cRequestActionSync") else "normal"
        ),
        requestEffects=[
            dict(
                field="cEnemyContext._FlagArray[WAITING_REQUEST_ACTION_RANDOM_OPERATOR=14]",
                value=False,
                offset="0x308→0x2e",
            ),
            dict(
                field="cEnemyContext._FlagArray[NO_REQUEST_ACTION=50]",
                value=False,
                offset="0x308→0x52",
            ),
        ],
        implementationBoundary="动作请求 helper 的全部网络、同步、请求历史和动作执行副作用尚未全部恢复；本节点不保证请求成功或动作在游戏中完成",
    )
    if not command.endswith("cRequestActionSync"):
        details["actorRequestGuard"] = dict(
            kind="any",
            items=[
                dict(
                    kind="not",
                    item=runtime(
                        "request_actor_net_info_exists",
                        "请求 actor 的 Context._Em.NetInfo(0xf0) != null",
                    ),
                ),
                dict(
                    kind="compare",
                    operator="eq",
                    left=runtime(
                        "request_actor_host_member_index",
                        "请求 actor 的 NetInfo._HostMemberIndex(+0x24)",
                    ),
                    right=dict(kind="constant", value=-1),
                ),
                dict(
                    kind="compare",
                    operator="eq",
                    left=runtime(
                        "request_actor_host_member_index",
                        "请求 actor 的 NetInfo._HostMemberIndex(+0x24)",
                    ),
                    right=runtime(
                        "request_actor_self_member_index",
                        "请求 actor 的 NetInfo._SelfMemberIndex(+0x20)",
                    ),
                ),
            ],
        )
    return details
