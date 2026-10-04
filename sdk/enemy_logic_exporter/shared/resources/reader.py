"""Read original typed JSON, retaining enum numbers, GUIDs and action variants."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from ..logic.values import scalar

EMPTY_GUID = "00000000-0000-0000-0000-000000000000"

# The native selector passes a uniquely owned default or branched _ActionClass to the
# requested action's applyActionParam virtual method without a class-name test.
# This proves parameter selection, not all fields that the action will apply.
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


class ActionBindingError(ValueError):
    """A known action request has no unique serialized parameter definition."""

    def __init__(self, message, *, reason, context):
        super().__init__(message)
        self.reason = reason
        self.context = {"reason": reason, **context}


def action_request_guid(record):
    """Reviewed cID.ActionGuid getter: nonempty base GUID, otherwise instance GUID."""
    base = record.get("_BaseActionGuid", EMPTY_GUID)
    return record["_InstanceGuid"] if base.casefold() == EMPTY_GUID else base


def typed(value):
    if not isinstance(value, dict) or len(value) != 1:
        raise ValueError("资源不是单一类型包装")
    name, body = next(iter(value.items()))
    if not isinstance(body, dict):
        raise ValueError("资源类型内容不是对象")
    return name, body


def structure_signature(body, factories):
    """Lock native slot layout, permitting edits to resource parameter values."""
    shape = {
        "exportType": body["_ExportBTableType"],
        "guid": body["_ThisGuid"],
        "useExportArgData": body["_UseExportArgData"],
        "argumentTypes": [typed(arg)[0] for arg in body["_CommandArgArray"]],
        "factories": [
            {k: f.get(k) for k in ("_OrderType", "_ArgumentType")} for f in factories
        ],
        "imports": body["_ImportBTableList"],
    }
    return hashlib.sha256(
        json.dumps(
            shape, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


class Resources:
    def __init__(self, natives):
        self.root = Path(natives).resolve()
        self.paths = {
            p.relative_to(self.root).as_posix().casefold(): p
            for p in self.root.rglob("*.json")
        }
        self.cache = {}
        self.hashes = {}
        self.accessed = set()

    def resolve(self, relative):
        raw = str(relative).replace("\\", "/")
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or ":" in raw:
            raise ValueError("资源引用不能越出 natives 根目录")
        raw = path.as_posix()
        if not raw.startswith("STM/"):
            raw = "STM/" + raw
        if raw.endswith(".user"):
            raw += ".3.json"
        if not raw.endswith(".json"):
            raise ValueError("构建器只读取资源 JSON")
        key = raw.casefold()
        if key not in self.paths:
            raise FileNotFoundError(raw)
        actual = self.paths[key]
        if not actual.resolve().is_relative_to(self.root):
            raise ValueError("资源实际路径越出 natives 根目录")
        return actual.relative_to(self.root).as_posix()

    def read(self, relative):
        relative = self.resolve(relative)
        self.accessed.add(relative)
        if relative not in self.cache:
            raw = self.paths[relative.casefold()].read_bytes()
            data = json.loads(raw)
            if isinstance(data, list):
                if len(data) != 1:
                    raise ValueError("预期一个资源根对象")
                data = data[0]
            self.cache[relative] = typed(data)[1]
            self.hashes[relative] = hashlib.sha256(raw).hexdigest()
        return self.cache[relative]

    def reference(self, wrapper):
        return self.resolve(typed(wrapper)[1]["path"])

    def large_enemy_ids(self):
        from ..models.catalog import TRAINING_ENEMY_ID

        source = "STM/GameDesign/Common/Enemy/EnemyData.user.3.json"
        identities = []
        for wrapper in self.read(source)["_Values"]:
            enemy_id = typed(wrapper)[1]["_enemyId"].split()[-1]
            match = re.fullmatch(r"EM(\d{4})_\d{2}_\d+", enemy_id)
            if match and int(match[1]) < 1000 and enemy_id != TRAINING_ENEMY_ID:
                identities.append(enemy_id)
        if len(identities) != len(set(identities)):
            raise ValueError("EnemyData 中的大型怪物身份重复")
        return set(identities)

    def enemy_name(self, enemy_id, *, language=13):
        """Bind the name GUID to the game's Simplified Chinese message column."""
        data_source = "STM/GameDesign/Common/Enemy/EnemyData.user.3.json"
        entries = [typed(v)[1] for v in self.read(data_source)["_Values"]]
        matches = [v for v in entries if v["_enemyId"].split()[-1] == enemy_id]
        if len(matches) != 1:
            raise ValueError("EnemyData 无法唯一绑定怪物名称：" + enemy_id)
        source = self.resolve("STM/GameDesign/Text/Excel_Data/EnemyText.msg.23.json")
        self.accessed.add(source)
        raw = self.paths[source.casefold()].read_bytes()
        self.hashes[source] = hashlib.sha256(raw).hexdigest()
        messages = json.loads(raw)
        columns = [
            i for i, value in enumerate(messages["languages"]) if value == language
        ]
        rows = [
            v
            for v in messages["entries"]
            if v["guid"].casefold() == matches[0]["_EnemyName"].casefold()
        ]
        if len(columns) != 1 or len(rows) != 1 or not rows[0]["content"][columns[0]]:
            raise ValueError("游戏消息的怪物名称或语言列无法唯一绑定")
        return dict(
            displayName=rows[0]["content"][columns[0]],
            guid=rows[0]["guid"],
            languageId=language,
            source=source,
            enemyDataSource=data_source,
        )

    def table_references(self, value, *, allow_missing=False):
        if isinstance(value, dict):
            for name, body in value.items():
                if (
                    name == "ace.btable.user_data.BTable"
                    and isinstance(body, dict)
                    and body.get("path")
                ):
                    try:
                        yield self.resolve(body["path"])
                    except FileNotFoundError:
                        if not allow_missing:
                            raise
                else:
                    yield from self.table_references(body, allow_missing=allow_missing)
        elif isinstance(value, list):
            for item in value:
                yield from self.table_references(item, allow_missing=allow_missing)

    def factories(self, table):
        bank = self.read(self.reference(table["_OrderBank"]))
        result = []
        for item in bank["_OrderLists"]:
            orders = self.read(self.reference(typed(item)[1]["_OrderList"]))
            result.extend(typed(f)[1] for f in orders["_CommandFactories"])
        return result

    def timer(self, table, guid):
        bank = self.read(self.reference(table["_OrderBank"]))
        sources = set()
        asset = typed(bank["_VariableAsset"])[1]
        if asset.get("path"):
            sources.add(self.reference(bank["_VariableAsset"]))
        listed = typed(bank["_VariableListAsset"])[1]
        if listed.get("path"):
            variable_list = self.read(self.reference(bank["_VariableListAsset"]))
            for item in variable_list["_VariableList"]:
                sources.add(self.reference(typed(item)[1]["_Variable"]))
        matches = []
        for source in sorted(sources):
            asset = self.read(source)
            for index, item in enumerate(asset.get("TimerValueInfoList", [])):
                type_name, body = typed(item)
                if str(body["InstanceGUID"]).casefold() == str(guid).casefold():
                    matches.append(
                        {
                            "source": source,
                            "sourceBodyPointer": f"/TimerValueInfoList/{index}/{type_name}",
                            "definition": body,
                        }
                    )
        if len(matches) != 1:
            raise ValueError("计时器 GUID 无法唯一绑定")
        return matches[0]

    def action_parameter_entry(self, source, guid, visited=()):
        """Resolve serialized base-action placeholders along their declared owner link."""
        source = self.resolve(source)
        if source in visited:
            raise ValueError("基础动作参数引用成环")
        asset = self.read(source)
        matches = [
            (i, typed(r)[1])
            for i, r in enumerate(asset["_ActionInfoList"])
            if typed(r)[1]["_ActionGuid"].casefold() == str(guid).casefold()
        ]
        if not matches:
            raise ActionBindingError(
                "动作参数无法通过动作 GUID 唯一绑定",
                reason="missing_action_parameter_guid",
                context={
                    "actionGuid": guid,
                    "parameterAsset": source,
                    "parameterResolutionChain": [*visited, source],
                    "baseActionParamReference": asset.get("_BaseActionParam"),
                    "matchingParameterEntries": 0,
                    "parameterBindingEvidence": [dict(PARAMETER_SELECTION_EVIDENCE[1])],
                },
            )
        if len(matches) != 1:
            raise ValueError("动作参数无法通过动作 GUID 唯一绑定")
        index, info = matches[0]
        base = asset.get("_BaseActionParam")
        if (
            base
            and typed(base)[1].get("path")
            and info.get("_IsBaseAction")
            and not info.get("_OverrideOwnerAction")
        ):
            return self.action_parameter_entry(
                self.reference(base), guid, (*visited, source)
            )
        return source, asset, index, info, [*visited, source]

    def action(self, table, argument):
        index = scalar(argument["_EditAssetIndex"])
        guid = scalar(argument["_EditActionGuid"])
        variant = scalar(argument["_EditBranchedParamGuid"])
        bank = self.read(self.reference(table["_OrderBank"]))
        settings = [
            typed(s)[1]
            for s in bank["_CommandArgumentSettingList"]
            if typed(s)[0] == "app.btable.AppBTableUtil.cSelectActionArgSetting"
        ]
        if len(settings) != 1 or type(index) is not int:
            raise ValueError("动作资产索引无法唯一绑定")
        assets = settings[0]["_AssetDataList"]
        if not 0 <= index < len(assets):
            raise ValueError("动作资产索引越界")
        asset = typed(assets[index])[1]
        holder = typed(asset["_Asset"])[1]
        source = self.reference(holder["_ActionID"])
        data = self.read(source)
        records = typed(data["_ActionIDArray"])[1]["_DataArray"]
        matches = [
            typed(r)[1]
            for r in records
            if action_request_guid(typed(r)[1]).casefold() == str(guid).casefold()
        ]
        if len(matches) != 1:
            raise ValueError(f"动作 GUID 无法唯一绑定：{guid}")
        declared_parameter_source = self.reference(asset["_ParamAsset"])
        try:
            (
                parameter_source,
                parameter_asset,
                parameter_index,
                info,
                parameter_chain,
            ) = self.action_parameter_entry(declared_parameter_source, guid)
        except ActionBindingError as error:
            error.context.update(
                assetIndex=index,
                source=source,
                actionGuid=guid,
                parameterVariantGuid=variant,
                declaredParameterAsset=declared_parameter_source,
                actionIdRecord=dict(matches[0]),
                rawArgument=dict(argument),
                tableGuid=table.get("_ThisGuid"),
            )
            raise
        default_parameter = parameter_asset["_ActionClassList"][parameter_index]
        default_parameter_type, _ = typed(default_parameter)
        action_id_class = matches[0]["_Class"]
        requested_variant = str(variant).casefold() != EMPTY_GUID
        use_branched = parameter_asset.get("_IsUseBranchedParam")
        if requested_variant and type(use_branched) is not bool:
            raise ValueError("参数资产缺少已核实的变体启用状态")
        uses_variant = requested_variant and use_branched
        if not uses_variant:
            selected = default_parameter
            parameter_pointer = f"/_ActionClassList/{parameter_index}"
        else:
            variants = typed(parameter_asset["_BranchedParamsList"][parameter_index])[
                1
            ]["_Params"]
            selected_variants = [
                (i, typed(v)[1])
                for i, v in enumerate(variants)
                if typed(v)[1]["_Guid"].casefold() == str(variant).casefold()
            ]
            if len(selected_variants) != 1:
                raise ValueError("所选参数变体不属于请求的动作")
            variant_index, selected_variant = selected_variants[0]
            selected = selected_variant["_ActionClass"]
            parameter_pointer = (
                f"/_BranchedParamsList/{parameter_index}/_Params/{variant_index}"
            )
        parameter_type, parameters = typed(selected)
        parameter_class = parameter_type.split(".")[-1]
        classes_match = parameter_class == action_id_class
        result = {
            "assetIndex": index,
            "actionGuid": guid,
            "instanceActionGuid": matches[0]["_InstanceGuid"],
            "actionGuidBinding": (
                "instance_guid"
                if matches[0].get("_BaseActionGuid", EMPTY_GUID).casefold()
                == EMPTY_GUID
                else "base_guid"
            ),
            "parameterVariantGuid": variant,
            "actionClass": action_id_class,
            "actionIdClass": action_id_class,
            "parameterClass": parameter_class,
            "defaultParameterType": default_parameter_type,
            "parameterClassRelation": (
                "same_class"
                if classes_match
                else (
                    "distinct_branched_parameter_class"
                    if uses_variant
                    else "distinct_default_parameter_class"
                )
            ),
            "parameterSelection": "branched" if uses_variant else "default",
            "parameterBindingEvidence": (
                [dict(row) for row in PARAMETER_SELECTION_EVIDENCE]
                if uses_variant
                else (
                    [dict(PARAMETER_SELECTION_EVIDENCE[1])]
                    if requested_variant or not classes_match
                    else []
                )
            ),
            "source": source,
            "parameterAsset": parameter_source,
            "declaredParameterAsset": declared_parameter_source,
            "parameterResolutionChain": parameter_chain,
            "parameterBodyPointer": parameter_pointer,
            "parameterInfo": info,
            "parameterType": parameter_type,
            "parameters": parameters,
            "parameterOverridesResolved": info["_OverrideSourceActionParamGuid"]
            == "00000000-0000-0000-0000-000000000000",
        }
        if not classes_match:
            result["parameterApplicationReviewed"] = False
        return result
