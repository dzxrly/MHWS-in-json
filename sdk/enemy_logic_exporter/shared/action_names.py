"""Bind explanatory names to exact action identities and retain raw Shell names."""

from .resources import typed
from .action_name_schema import action_identity, validate_action_names

CLASS_EXPLANATIONS = {
    "cTurningBite": "转身啃咬",
    "cDashBite": "突进啃咬",
    "cBreathAttack": "吐息",
    "cBreathAttackNoWeakPoint": "吐息（NoWeakPoint 版本）",
    "cLanding": "落地",
    "cDashCombat": "战斗突进移动",
    "cKeepDistance": "保持距离",
    "cDamageWingL": "左翼受创反应",
    "cDamageWingR": "右翼受创反应",
    "cSomersaultDashCancel": "后空翻（DashCancel 版本）",
}


class ActionNames:
    def __init__(self, resources, enemy_id, reviewed=()):
        self.resources = resources
        self.enemy_id = enemy_id
        self.reviewed = {}
        self.bindings = {}
        for entry in reviewed:
            key = (
                entry["enemyId"],
                resources.resolve(entry["actionAsset"]),
                entry["actionGuid"].casefold(),
                entry["parameterVariantGuid"].casefold(),
            )
            if (
                key[0] != enemy_id
                or not entry.get("displayName")
                or not entry.get("evidence")
            ):
                raise ValueError("审核动作名称缺少对应怪物、名称或证据")
            if key in self.reviewed:
                raise ValueError("动作及参数变体的审核名称重复")
            self.reviewed[key] = entry
        self.shell_catalog, self.shell_status = self._shell_catalog()

    def _shell_catalog(self):
        prefix = "Em" + self.enemy_id[2:9]
        path = (
            f"STM/GameDesign/Enemy/{prefix[:6]}/{prefix[7:]}/Data/"
            f"{prefix}_ParamPack.user.3.json"
        )
        try:
            pack = self.resources.read(path)
        except FileNotFoundError:
            return [], "param_pack_not_available"
        holder = pack.get("_ShellCreatorInfoData")
        if not holder or not typed(holder)[1].get("path"):
            return [], "shell_reference_not_available"
        source = self.resources.reference(holder)
        body = self.resources.read(source)
        entries, ids = [], set()
        for index, wrapper in enumerate(body.get("_ShellCreatorInfos", [])):
            typename, item = typed(wrapper)
            uid = item["_UniqueID"]
            if uid in ids:
                raise ValueError("同一 Shell 名称资源中的 UID 重复")
            ids.add(uid)
            entries.append(
                dict(
                    source=source,
                    sourceSha256=self.resources.hashes[source],
                    sourceBodyPointer=f"/_ShellCreatorInfos/{index}/{typename}",
                    uniqueId=uid,
                    shellListNo=item["_ShellListNo"],
                    name=item.get("_Name", ""),
                    comment=item.get("_Comment", ""),
                )
            )
        return entries, "source_reference_verified"

    def bind(self, action):
        key = action_identity(self.enemy_id, action)
        reviewed = self.reviewed.get(key)
        if reviewed and reviewed.get("actionClass") != action["actionClass"]:
            raise ValueError("审核名称的动作类与 ActionID 资源不一致")
        name = (
            reviewed["displayName"]
            if reviewed
            else CLASS_EXPLANATIONS.get(action["actionClass"])
        )
        binding = dict(
            enemyId=self.enemy_id,
            actionAsset=action["source"],
            actionGuid=action["actionGuid"],
            instanceActionGuid=action["instanceActionGuid"],
            actionGuidBinding=action["actionGuidBinding"],
            parameterVariantGuid=action["parameterVariantGuid"],
            actionClass=action["actionClass"],
            displayName=name or action["actionClass"],
            origin=(
                "reviewed_binding"
                if reviewed
                else "action_class_explanation" if name else "technical_class_name"
            ),
            identityVerified=True,
            officialLocalizedName=False,
            shellTriggerBindingVerified=False,
        )
        if reviewed:
            binding["evidence"] = reviewed["evidence"]
        self.bindings[key] = binding
        action["displayName"] = binding["displayName"]
        action["nameBinding"] = binding
        return action

    def catalog(self):
        return dict(
            bindings=list(self.bindings.values()),
            shellCatalog=self.shell_catalog,
            shellSourceStatus=self.shell_status,
            boundary="中文说明名与原始类名同时保留；Shell 原名和注释按资源及 UID 保存，未证明触发关系的条目不绑定到具体动作。",
        )
