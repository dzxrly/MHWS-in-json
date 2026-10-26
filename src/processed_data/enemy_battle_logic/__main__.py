"""Legacy first step of the Cloudflare Pages build command: write the site JSON.

The Pages dashboard still runs ``python -m src.processed_data.enemy_battle_logic
--output <dir>`` followed by ``.github/scripts/build_pages.py``. Both stay until
the dashboard runs the commands in the README section "Website"; this step only
writes the website JSON (``src.site_data``) into ``--output``.
"""

import argparse
from pathlib import Path

from config import NATIVES_DIR
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource
from src.site_data import export_site_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_site_data(
        args.output,
        SourceRepository(NATIVES_DIR),
        TextSource.from_natives(NATIVES_DIR),
    )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
