"""Run the maintained suite without importing old local audit scripts."""

import sys
import unittest
from config import BASE_DIR


def main() -> int:
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for area in ("database", "processed_data", "shared", "pipeline", "release"):
        suite.addTests(loader.discover(str(BASE_DIR / "tests" / area), top_level_dir=str(BASE_DIR)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
