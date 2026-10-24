"""Regression suite; all temporary output stays under the project .tmp directory."""

from pathlib import Path
import tempfile

_TEMP = Path(__file__).resolve().parents[1] / ".tmp" / "tests"
_TEMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_TEMP)
