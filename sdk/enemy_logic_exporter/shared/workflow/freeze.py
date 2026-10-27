"""Extract one monster through its module and verify its native evidence."""

from .extraction import extract_model
from ..native.pe import verify_rows
from ..models.io import encode_model


def native_evidence(value):
    rows = {}

    def collect(item):
        if isinstance(item, dict):
            if all(key in item for key in ("address", "end", "type", "method")):
                rows[(item["type"], item["method"], item["address"])] = item
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    if not rows:
        raise ValueError("离线模型没有可核对的原生方法证据")
    return list(rows.values())


def freeze_native_model(
    enemy_id,
    exe,
    metadata,
    natives,
    native_index,
    helper_index,
    *,
    requests_path=None,
    rules_path=None,
    inventory_path=None,
):
    """Build an EM's reviewed recipe and verify every embedded native method."""
    from ...monster import get_monster

    module = get_monster(enemy_id)
    recipe = getattr(module, "build_model", None)
    if recipe is None:
        raise ValueError(f"{enemy_id} 尚无可执行的原生语义配方；不能生成占位图")
    model = recipe(
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        requests_path=requests_path,
        **({"inventory_path": inventory_path} if inventory_path is not None else {}),
    )
    graph = extract_model(enemy_id, natives, rules_path=rules_path, model=model)
    verify_rows(exe, native_evidence(graph))
    graph["nativeVerification"] = "matched"
    from .runtime_log import record_graph

    record_graph(graph)
    return encode_model(graph)
