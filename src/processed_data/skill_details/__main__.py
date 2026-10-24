"""python -m src.processed_data.skill_details --output ..."""

import argparse
from pathlib import Path

from config import NATIVES_DIR, OUTPUT_DIR
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource

from .exporter import export_skill_details


def main():
    parser = argparse.ArgumentParser(
        description="合并技能表与离线技能效果链路，生成 SkillDetails.xlsx；无需 EXE 或 il2cpp"
    )
    parser.add_argument("--natives", type=Path, default=NATIVES_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "processed_data")
    args = parser.parse_args()
    path = export_skill_details(
        args.output,
        SourceRepository(args.natives),
        TextSource.from_natives(args.natives),
    )
    print(path)


if __name__ == "__main__":
    main()
