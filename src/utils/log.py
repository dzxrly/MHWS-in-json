from datetime import datetime
from pathlib import Path
from time import perf_counter

_START = perf_counter()


def info(message: str) -> None:
    elapsed = perf_counter() - _START
    print(f"[{datetime.now():%H:%M:%S}] +{elapsed:8.2f}s {message}", flush=True)


def file_size(path: Path) -> str:
    return format_size(path.stat().st_size)


def format_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
