"""Shared source identity for the two calculator exports."""

import hashlib
import json
import re
from pathlib import Path


SOURCE_FILES = (
    "STM/GameDesign/Common/Equip/SkillCommonData.user.3.json",
    "STM/GameDesign/Common/Equip/SkillData.user.3.json",
    "STM/GameDesign/Player/ActionData/Common/GlobalParam/Part/PlayerSkillParam.user.3.json",
    "STM/GameDesign/Player/ActionData/Common/GlobalParam/Part/PlayerStatusParam.user.3.json",
)


def source_contract(natives_dir: Path) -> dict:
    hashes = {path: hashlib.sha256((natives_dir / path).read_bytes()).hexdigest()
              for path in SOURCE_FILES}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"id": identity, "sourceHashes": hashes}


def validate_source_contract(contract: dict) -> None:
    hashes = contract.get("sourceHashes", {})
    if set(hashes) != set(SOURCE_FILES) or any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in hashes.values()
    ):
        raise ValueError("Invalid calculator source contract hashes")
    expected = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    if contract.get("id") != expected:
        raise ValueError("Calculator source contract identity mismatch")
