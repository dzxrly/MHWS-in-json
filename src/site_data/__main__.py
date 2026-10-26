"""python -m src.site_data: regenerate the committed website JSON.

A preview of models the SDK has not published goes elsewhere, so the committed
data stays the release data, e.g.
``python -m src.site_data --enemy-models <dir> --preview --output .tmp/site-preview``.
"""

import argparse
import json
from pathlib import Path

from config import NATIVES_DIR
from src.processed_data.enemy_battle_logic.definitions import MODEL_DIR
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource

from . import DEFAULT_DIR, export_site_data


def main():
    parser = argparse.ArgumentParser(
        description="从仓库内的数据生成网站读取的 JSON；无需资源、IL2CPP、EXE 或 SDK"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--natives", type=Path, default=NATIVES_DIR)
    parser.add_argument(
        "--enemy-models", type=Path, default=MODEL_DIR, help="SDK 离线提取的正式图目录"
    )
    parser.add_argument("--enemy-template", type=Path, help="只导出一个已提取图")
    parser.add_argument(
        "--preview", action="store_true", help="允许怪物图只包含部分怪物"
    )
    args = parser.parse_args()
    preview = args.preview or args.enemy_template or args.enemy_models != MODEL_DIR
    if preview and args.output.resolve() == DEFAULT_DIR.resolve():
        parser.error("预览数据不能写入已提交的网站数据目录，请用 --output 指定其他目录")
    site = export_site_data(
        args.output,
        SourceRepository(args.natives),
        TextSource.from_natives(args.natives),
        models_dir=args.enemy_models,
        template_path=args.enemy_template,
        preview=args.preview,
    )
    print(
        json.dumps(dict(output=str(args.output.resolve()), **site), ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
