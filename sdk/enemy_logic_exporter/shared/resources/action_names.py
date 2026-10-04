"""Bind explanatory names to exact action identities and retain raw Shell names."""

from .reader import typed

CLASS_EXPLANATIONS = {
    "cTakeoff": "起飞",
    "cQuickTurn": "快速转身",
    "cWait": "等待",
    "cWaitFly": "空中等待",
    "cWalk": "行走",
    "cDash": "快速移动",
    "cBackDash": "向后快速移动",
    "cSideDash": "向侧面快速移动",
    "cGlide": "滑翔",
    "cGlideNavi": "沿导航路径滑翔",
    "cSearch": "寻找目标",
    "cRoarShort": "短咆哮",
    "cRoar": "咆哮",
    "cBackStepFly": "空中后退",
    "cMoveIdleAdjustFly": "空中调整位置",
    "cTakeoffDashTurn": "起飞并快速转向",
    "cAreaMoveTakeoff": "区域移动起飞",
    "cJabAttack": "刺拳",
    "cDoubleJabAttack": "双刺拳",
    "cJabAttackDouble": "双刺拳",
    "cStrongJabFront": "向前强力刺拳",
    "cStrongJabBack": "向后强力刺拳",
    "cBodyPress": "身体下压攻击",
    "cBodyPressFly": "空中下压攻击",
    "cFlameThrower": "喷火",
    "cFlameThrowerCross": "交叉喷火",
    "cFlameThrowerTriple": "喷火（三连版本）",
    "cFlameThrowerCrossTriple": "交叉喷火（三连版本）",
    "cMultiMissile": "多导弹攻击",
    "cAreaMoveWallMissile": "区域移动壁面导弹动作",
    "cMiniSummon": "召唤小型单位",
    "cRushAttack": "突进攻击",
    "cRushAttackTriple": "突进攻击（三连版本）",
    "cRushAttackTripleTwo": "突进攻击（三连第二段）",
    "cRushAttackTripleThree": "突进攻击（三连第三段）",
    "cLandingFromGlide": "滑翔后落地",
    "cTurnGlideL": "向左转向滑翔",
    "cTurnGlideR": "向右转向滑翔",
    "cAdjustStepNearB": "向后近距调整",
    "cAdjustStepNearF": "向前近距调整",
    "cAdjustStepNearL": "向左近距调整",
    "cAdjustStepNearR": "向右近距调整",
    "cFixedStepB": "向后步移",
    "cFixedStepF": "向前步移",
    "cFixedStepL": "向左步移",
    "cFixedStepR": "向右步移",
    "cRideBumpHead": "骑乘头部碰撞动作",
    "cRideRampageBody": "骑乘躯干挣扎动作",
    "cRideRampageHead": "骑乘头部挣扎动作",
    "cJabLaser": "刺拳激光",
    "cRocketPunch": "火箭拳",
    "cUpperLaser": "上向激光",
    "cRushAttackTurn": "突进攻击转向",
    "cAdjustStepFarB": "向后调整距离",
    "cAdjustStepFarL": "向左调整距离",
    "cAdjustStepFarR": "向右调整距离",
    "cAdjustStepFarF": "向前调整距离",
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
    "cTakeOff": "起飞",
    "cTakeOffDash": "快速移动起飞",
    "cTurn": "转身",
    "cTurnQuick": "快速转身",
    "cJumpTurn": "跳跃转身",
    "cQuickTurnFly": "空中快速转身",
    "cBackStep": "后退步移",
    "cBackStepShort": "短距离后退步移",
    "cSideStep": "侧向步移",
    "cBite": "啃咬",
    "cBreathAttackFly": "空中吐息",
    "cTiredBreathAttack": "疲劳时的吐息动作",
    "cJetBreath": "喷射吐息",
    "cPoisonBreath": "毒吐息",
    "cGasBreath": "气体吐息",
    "cGasEmission": "释放气体",
    "cGasEmissionBack": "向后释放气体",
    "cChargeBreathFront": "向前蓄力吐息",
    "cDiveToGround": "向地面俯冲",
    "cLandingFourLeg": "四足落地",
    "cLandingSixLeg": "六足落地",
    "cRiseFly": "起身飞行",
    "cSysIdle": "待机",
    "cSearchCombat": "战斗中寻找目标",
    "cCautionGrowl": "警戒低吼",
    "cJawAttack": "下颚攻击",
    "cWingArmWideAttack": "翼臂大范围攻击",
    "cVerticalKickFly": "空中竖向踢击",
    "cPredationHoldTakeOff": "捕食抓持时起飞",
    "cPredationHoldGlide": "捕食抓持时滑翔",
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
