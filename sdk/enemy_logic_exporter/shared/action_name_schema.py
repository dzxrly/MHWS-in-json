"""Validate names against frozen action identities; no resource loading."""


def action_identity(enemy_id, action):
    return (
        enemy_id,
        action["source"],
        action["actionGuid"].casefold(),
        action["parameterVariantGuid"].casefold(),
    )


def validate_action_names(graph):
    catalog = graph.get("actionNameCatalog")
    if catalog is None:
        return
    expected = {}
    for table in graph["tables"]:
        for node in table["nodes"]:
            if node["kind"] != "action":
                continue
            action = node["action"]
            binding = action.get("nameBinding", {})
            if any(
                binding.get(key) != value
                for key, value in {
                    "enemyId": graph["enemyId"],
                    "actionAsset": action["source"],
                    "actionGuid": action["actionGuid"],
                    "parameterVariantGuid": action["parameterVariantGuid"],
                    "actionClass": action["actionClass"],
                    "instanceActionGuid": action["instanceActionGuid"],
                    "actionGuidBinding": action["actionGuidBinding"],
                    "displayName": action.get("displayName"),
                }.items()
            ):
                raise ValueError("动作名称与动作资源、GUID 或参数变体不一致")
            if (
                binding.get("officialLocalizedName") is not False
                or binding.get("shellTriggerBindingVerified") is not False
            ):
                raise ValueError("说明名或未核实 Shell 触发关系不能标记为官方或已核实")
            identity = action_identity(graph["enemyId"], action)
            if identity in expected and expected[identity] != binding:
                raise ValueError("同一动作身份具有冲突名称")
            expected[identity] = binding
    declared = {}
    for binding in catalog["bindings"]:
        identity = (
            binding["enemyId"],
            binding["actionAsset"],
            binding["actionGuid"].casefold(),
            binding["parameterVariantGuid"].casefold(),
        )
        if identity in declared:
            raise ValueError("动作名称目录的身份重复")
        declared[identity] = binding
    if declared != expected:
        raise ValueError("动作名称目录与图中的请求不一致")
    uids = set()
    for row in catalog["shellCatalog"]:
        identity = (row["source"], row["uniqueId"])
        if (
            identity in uids
            or graph["sourceHashes"].get(row["source"]) != row["sourceSha256"]
        ):
            raise ValueError("Shell 名称 UID 重复或来源摘要不匹配")
        uids.add(identity)
