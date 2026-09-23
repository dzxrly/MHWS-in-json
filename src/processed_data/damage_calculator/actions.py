"""Player-readable action labels tied to exact hit records."""

import re
from pathlib import Path

from config import ACTION_MAP_PATH, ZH_HANS_LANGUAGE_ID
from src.database.action_values.build import load_action_value_catalog
from src.shared.text.catalog import TextSource

CHINESE = re.compile(r"[\u3400-\u9fff]")


def action_labels(natives_dir: Path, text_source: TextSource) -> dict:
    """Only use localized, proven action names bound to exact request sets."""
    catalog = load_action_value_catalog(natives_dir, ACTION_MAP_PATH)
    texts = text_source.build(ZH_HANS_LANGUAGE_ID)
    labels = {}
    for key, bindings in catalog.bindings.items():
        names = set()
        for binding in bindings:
            if binding.kind != "Action" or binding.confidence != "proven" or not binding.name_guid:
                continue
            name = (texts.get(binding.name_guid) or "").strip()
            if name and CHINESE.search(name):
                names.add(name)
        if names:
            labels[key] = sorted(names)
    return labels
