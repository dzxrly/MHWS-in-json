"""Copy validated monster HTML to Pages; frozen JSON stays in models."""

import argparse
from datetime import datetime, timezone
from html import escape
import os
from pathlib import Path
import shutil
import subprocess
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
    commit = (
        os.environ.get("CF_PAGES_COMMIT_SHA")
        or subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    )
    deployed_on = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    commit_url = escape(f"https://github.com/{repository}/commit/{commit}", quote=True)
    footer = (
        '<footer style="text-align:center;padding:20px;color:var(--faint);font-size:12px">'
        f'部署日期：{deployed_on}（<a href="{commit_url}">{escape(commit[:7])}</a>）'
        "</footer>"
    )
    for page in destination.rglob("*.html"):
        before, after = page.read_text(encoding="utf-8").rsplit("</body>", 1)
        page.write_text(f"{before}{footer}</body>{after}", encoding="utf-8")
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
