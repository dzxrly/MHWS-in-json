"""Progress bars for long SDK commands, shared by both tools.

``track`` wraps a loop in a rich progress bar (count, elapsed and remaining
time). On a terminal the bar redraws in place and ``print`` output appears
above it; when output goes to a file or pipe, rich prints the bar only when the
loop ends, so logs stay readable.
"""

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


def track(items, description, total=None):
    """Yield ``items`` while advancing a progress bar labelled ``description``."""
    items = list(items) if total is None and not hasattr(items, "__len__") else items
    columns = (
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("用时"),
        TimeElapsedColumn(),
        TextColumn("剩余"),
        TimeRemainingColumn(),
    )
    with Progress(*columns) as bar:
        task = bar.add_task(description, total=len(items) if total is None else total)
        for item in items:
            yield item
            bar.advance(task)
