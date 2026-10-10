"""Validate JSON references without recovering any SDK or game semantics."""


def validate_player_view(graph):
    view = graph.get("playerView")
    if view is None:
        return
    if (
        view.get("schemaVersion") != 1
        or not view.get("entries")
        or not isinstance(view.get("inputs"), dict)
    ):
        raise ValueError("玩家行动树格式无效")
    originals = {
        f"{t['tableGuid']}/{n['id']}": n for t in graph["tables"] for n in t["nodes"]
    }
    table_entries = {
        t["tableGuid"]: f"{t['tableGuid']}/{t['entry']}" for t in graph["tables"]
    }
    scenario = view.get("scenario", {})
    if not set(scenario.get("persistent", ())) <= set(scenario.get("inputs", {})):
        raise ValueError("常驻情境前提必须是情境输入")
    nodes = view["nodes"]
    if set(nodes) != set(originals):
        raise ValueError("玩家行动树遗漏或新增了无来源节点")

    def expression(value):
        op = value.get("op")
        if op in ("all", "any"):
            if not value.get("items"):
                raise ValueError("玩家组合条件不能为空")
            for item in value["items"]:
                expression(item)
        elif op == "not":
            expression(value["item"])
        elif op == "compare":
            if (
                value.get("operator") not in ("eq", "ne", "lt", "le", "gt", "ge")
                or not value.get("key")
                or "value" not in value
            ):
                raise ValueError("玩家条件比较无效")
        elif op != "unknown" or not value.get("reason"):
            raise ValueError("玩家条件包含未支持的操作")

    for key, node in nodes.items():
        source = originals[key]
        table = key.rsplit("/", 1)[0]
        if (
            node.get("sourceRef") != key
            or node.get("kind") != source["kind"]
            or not node.get("title")
        ):
            raise ValueError("玩家节点身份与原始节点不一致")
        for role in ("true", "false", "next", "resume", "fallback"):
            expected = f"{table}/{source[role]}" if role in source else None
            if node.get(role) != expected:
                raise ValueError("玩家连接改变了原始继续位置")
        for role, original_role in (
            ("target", "targetTable"),
            ("dispatch", "dispatchTarget"),
        ):
            expected = (
                table_entries[source[original_role]]
                if original_role in source
                else None
            )
            if node.get(role) != expected:
                raise ValueError("玩家跨表连接改变了实际调用目标")
        if node["kind"] == "condition":
            expression(node["condition"])
            display = node.get("presentation", {})
            if (
                display.get("category")
                not in ("distance", "angle", "phase", "state", "internal", "random")
                or any(
                    not isinstance(display.get(k), str) or not display[k]
                    for k in ("title", "trueLabel", "falseLabel")
                )
                or type(display.get("snapshotGuard")) is not bool
                or type(display.get("compact")) is not bool
            ):
                raise ValueError("玩家树条件缺少分支说明")
        if node["kind"] == "action" and node.get("identity") != [
            source["action"][k]
            for k in ("source", "actionGuid", "parameterVariantGuid")
        ]:
            raise ValueError("玩家动作身份与参数变体不一致")
        if node["kind"] == "weighted_random":
            expected = [
                (c["id"], f"{table}/{c.get('nodeId', c['id'])}", c["weight"])
                for c in source["candidates"]
            ]
            actual = [(c["id"], c["target"], c["weight"]) for c in node["candidates"]]
            if actual != expected:
                raise ValueError("玩家候选槽或权重改变")
    for entry in view["entries"]:
        if entry.get("id") not in nodes or entry.get("relation") not in (
            "local_verified",
            "scheduler_slot",
            "unknown",
        ):
            raise ValueError("玩家入口缺少来源或接入状态")
