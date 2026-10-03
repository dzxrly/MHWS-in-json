"""Read original typed JSON, retaining enum numbers, GUIDs and action variants."""

import hashlib
import json
from pathlib import Path, PurePosixPath

from .predicates import scalar


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
            if typed(r)[1]["_InstanceGuid"].casefold() == str(guid).casefold()
        ]
        if len(matches) != 1:
            raise ValueError(f"动作 GUID 无法唯一绑定：{guid}")
        parameter_source = self.reference(asset["_ParamAsset"])
        parameter_asset = self.read(parameter_source)
        parameter_matches = [
            (i, typed(r)[1])
            for i, r in enumerate(parameter_asset["_ActionInfoList"])
            if typed(r)[1]["_ActionGuid"].casefold() == str(guid).casefold()
        ]
        if len(parameter_matches) != 1:
            raise ValueError("动作参数无法通过动作 GUID 唯一绑定")
        parameter_index, info = parameter_matches[0]
        if str(variant) == "00000000-0000-0000-0000-000000000000":
            selected = parameter_asset["_ActionClassList"][parameter_index]
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
        if parameter_type.split(".")[-1] != matches[0]["_Class"]:
            raise ValueError("动作 ID 与参数类型不一致")
        return {
            "assetIndex": index,
            "actionGuid": guid,
            "parameterVariantGuid": variant,
            "actionClass": matches[0]["_Class"],
            "source": source,
            "parameterAsset": parameter_source,
            "parameterBodyPointer": parameter_pointer,
            "parameterInfo": info,
            "parameterType": parameter_type,
            "parameters": parameters,
            "parameterOverridesResolved": info["_OverrideSourceActionParamGuid"]
            == "00000000-0000-0000-0000-000000000000",
        }
