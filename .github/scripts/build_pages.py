"""Legacy second step of the Cloudflare Pages build command: build web/.

The Pages dashboard still runs this after
``python -m src.processed_data.enemy_battle_logic --output <dir>``. It builds
the website from the JSON in ``--processed-dir`` into ``--output``. Remove both
once the dashboard runs the commands in the README section "Website".
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


def build_pages(processed_dir, destination):
    npm = shutil.which("npm")
    if npm is None:
        raise FileNotFoundError("构建网站需要 Node.js 与 npm")
    environment = dict(os.environ, MHWS_SITE_DATA=str(Path(processed_dir).resolve()))
    subprocess.run([npm, "ci"], cwd=WEB_DIR, check=True)
    subprocess.run(
        [npm, "run", "build", "--", "--outDir", str(Path(destination).resolve())]
        + ["--emptyOutDir"],
        cwd=WEB_DIR,
        env=environment,
        check=True,
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    # Accepted for the dashboard command; the site reads them from site.json.
    parser.add_argument("--version")
    parser.add_argument("--repository")
    args = parser.parse_args()
    print(build_pages(args.processed_dir, args.output))
