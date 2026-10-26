"""python -m src.processed_data.skill_details --output ..."""

import argparse
from pathlib import Path

from config import NATIVES_DIR, OUTPUT_DIR
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource

from .exporter import export_skill_details, load_links, meanings_report


def main():
    parser = argparse.ArgumentParser(
        description="合并技能表与离线技能效果链路，生成 SkillDetails.xlsx；无需 EXE 或 il2cpp"
    )
    parser.add_argument("--natives", type=Path, default=NATIVES_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "processed_data")
    parser.add_argument(
        "--meanings-report",
        type=Path,
        help="只写出数值含义表核对清单（Markdown：每个效果的键、数值、含义与用途证据），不生成表格",
    )
    args = parser.parse_args()
    if args.meanings_report:
        text = meanings_report(load_links())
        args.meanings_report.write_text(text, encoding="utf-8")
        print(args.meanings_report)
        return
    path = export_skill_details(
        args.output,
        SourceRepository(args.natives),
        TextSource.from_natives(args.natives),
    )
    print(path)


if __name__ == "__main__":
    main()
