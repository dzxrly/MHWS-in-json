"""Copy validated monster HTML to Pages; frozen JSON stays in models."""

import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.processed_data.enemy_battle_logic.definitions import INDEX_NAME
from src.processed_data.enemy_battle_logic.validation import validate_bundle


def build_pages(processed_dir, destination, *, version, repository):
    source = Path(processed_dir).resolve()
    destination = Path(destination).resolve()
    if (
        source == destination
        or source in destination.parents
        or destination in source.parents
    ):
        raise ValueError("Pages 输出不能覆盖或包含 processed_data 输入")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Pages 输出目录必须为空，避免发布旧版本文件")
    validate_bundle(source)
    destination.mkdir(parents=True, exist_ok=True)
    folder = source / Path(INDEX_NAME).parent
    shutil.copytree(folder, destination / "enemy_battle_logic")
    # This root index links into the identical HTML bundle; no models are copied.
    homepage = (
        (source / INDEX_NAME)
        .read_text(encoding="utf-8")
        .replace("<head>", '<head><base href="enemy_battle_logic/">', 1)
    )
    (destination / "index.html").write_text(homepage, encoding="utf-8")
    (destination / ".nojekyll").touch()
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--processed-dir", type=Path, default=ROOT / "output/processed_data"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    print(
        build_pages(
            args.processed_dir,
            args.output,
            version=args.version,
            repository=args.repository,
        )
    )
