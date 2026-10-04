"""python -m src.processed_data.enemy_battle_logic --models ... --output ..."""

import argparse
import json
from pathlib import Path

from .exporter import export_battle_logic
from .definitions import MODEL_DIR
from .validation import validate_bundle


def main():
    parser = argparse.ArgumentParser(
        description="从离线图 JSON 构建 HTML；无需资源、IL2CPP、EXE 或 SDK"
    )
    root = Path(__file__).resolve().parents[3]
    parser.add_argument(
        "--models", type=Path, default=MODEL_DIR, help="SDK 离线提取的正式图目录"
    )
    parser.add_argument("--template", type=Path, help="单独导出一个已提取图")
    parser.add_argument("--output", type=Path, default=root / "output/processed_data")
    parser.add_argument(
        "--preview-all",
        action="store_true",
        help="导出目录内的图，允许只包含部分怪物",
    )
    args = parser.parse_args()
    paths = export_battle_logic(
        args.output,
        models_dir=args.models,
        template_path=args.template,
        research_preview=args.preview_all,
    )
    index = validate_bundle(
        args.output, require_release=args.template is None and not args.preview_all
    )
    print(
        json.dumps(
            dict(
                output=str(args.output.resolve()),
                files=[path.relative_to(args.output).as_posix() for path in paths],
                monsters=index["monsters"],
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
