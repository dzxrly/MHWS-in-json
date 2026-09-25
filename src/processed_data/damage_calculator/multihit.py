"""Export physical ammo curves verified against native code and runtime traces."""

import json
import math
import struct
from pathlib import Path

ELEMENT_CURVE = "GameDesign/Player/ActionData/WpGunCommon/Collision/Collider/WpGunElement_MultiHitCurve.user"
PENETRATE_CURVE = "GameDesign/Player/ActionData/WpGunCommon/Collision/Collider/WpGunPenetrate_MultiHitCurve.user"


def physical_curve_points(natives_dir: Path, path: str) -> list[dict] | None:
    # Other curves retain their source reference until their use is audited.
    if path not in {ELEMENT_CURVE, PENETRATE_CURVE}:
        return None
    document = json.loads((natives_dir / "STM" / (path + ".3.json")).read_text(encoding="utf-8"))
    curve = document[0]["app.user_data.MultiHitRateCurve"]["_Curve"]["via.AnimationCurve"]
    points = []
    for entry in curve["v0"]:
        raw = bytes.fromhex(entry["raw"])
        if len(raw) != 16:
            raise ValueError("Unexpected multi-hit curve record size")
        # Native AnimationCurve evaluation: float value, uint16 interpolation,
        # float16 time. Mode 1 is linear (EXE 1.42.0.2, 0x14B0913C7).
        value, interpolation, time = struct.unpack_from("<fHe", raw)
        if interpolation != 1 or not all(math.isfinite(v) and v >= 0 for v in (value, time)):
            raise ValueError("Unsupported ammo curve interpolation")
        if points and time <= points[-1]["count"]:
            raise ValueError("Non-increasing multi-hit curve counts")
        points.append({"count": time, "rate": value})
    if not points or points[0]["count"] != 0:
        raise ValueError("Multi-hit curve must start at zero")
    return points
