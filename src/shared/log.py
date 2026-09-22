from datetime import datetime
from pathlib import Path
import sys
from time import perf_counter

_START = perf_counter()


def _configure_stream(stream) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, OSError, ValueError):
        try:
            reconfigure(errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass


_configure_stream(sys.stdout)
_configure_stream(sys.stderr)


def info(message: str) -> None:
    elapsed = perf_counter() - _START
    _print(f"[{datetime.now():%H:%M:%S}] +{elapsed:8.2f}s {message}")


def _print(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_message = message.encode(encoding, errors="backslashreplace").decode(
            encoding,
            errors="replace",
        )
        print(safe_message, flush=True)


def file_size(path: Path) -> str:
    return format_size(path.stat().st_size)


def format_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
