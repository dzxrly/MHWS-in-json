"""Project paths independent of working directory."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT / "sdk/enemy_logic_exporter/monster/models"
