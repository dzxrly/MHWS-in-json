"""Bundled JSON paths and reviewed source identity, independent of the cwd."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EVIDENCE_DIR = DATA_DIR / "evidence"
MODEL_DIR = DATA_DIR / "models"
RULES_PATH = DATA_DIR / "rules.v1.json"


SUPPORTED_PROFILE = {
    "gameVersion": "1.42.0.2",
    "exeSha256": "aa38eb46ae1f3c6c94fb2dd94af59b4665bd4c8ccee56bc36b88cf82397a5b4a",
    "metadataSha256": "01ab8f96c9786f3707fc0fc0376eb2e34124eea2d61b749354cac6e124b323d1",
}
