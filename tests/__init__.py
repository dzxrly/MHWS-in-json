"""Regression suite; all temporary output stays under the project .agents directory."""

from pathlib import Path
import tempfile

_TEMP = Path(__file__).resolve().parents[1] / ".agents" / "tests"
_TEMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_TEMP)
