"""Build in isolation and replace the published directory only after validation."""

from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from src.shared.log import info


class ExportTransaction:
    def __init__(self, output_dir: Path, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.runs = self.workspace / ".agents" / "export-runs"
        if not self.runs.resolve().is_relative_to(self.workspace):
            raise ValueError(f"Staging directory must be inside the workspace: {self.runs}")
        if self.output_dir.exists() and not self.output_dir.is_dir():
            raise ValueError(f"Export destination is not a directory: {self.output_dir}")
        if (not self.output_dir.is_relative_to(self.workspace) or self.output_dir == self.workspace
                or self.output_dir == self.runs or self.output_dir.is_relative_to(self.runs)
                or self.runs.is_relative_to(self.output_dir)):
            raise ValueError(f"Unsafe export destination: {self.output_dir}")
        self.run_dir = self.runs / uuid4().hex
        self.stage = self.run_dir / "output"
        self.backup = self.run_dir / "previous"
        self.published = False

    def __enter__(self):
        self.stage.mkdir(parents=True)
        temp_dir = self.run_dir / "tmp"
        temp_dir.mkdir()
        self.previous_temp = tempfile.tempdir
        tempfile.tempdir = str(temp_dir)
        return self

    def publish(self) -> None:
        if self.published:
            raise RuntimeError("Export already published")
        self.output_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self.output_dir.exists():
                self.output_dir.replace(self.backup)
            self.stage.replace(self.output_dir)
        except BaseException:
            # Also restore on Ctrl+C between the two directory renames.
            if self.backup.exists():
                try:
                    self.backup.replace(self.output_dir)
                except OSError as rollback_error:
                    raise RuntimeError(f"Restore previous output manually from {self.backup}") from rollback_error
            raise
        self.published = True

    def __exit__(self, exc_type, exc, traceback):
        tempfile.tempdir = self.previous_temp
        if self.published:
            # All recursive cleanup is restricted to this transaction's private directory.
            target = self.run_dir.resolve()
            if target.parent != self.runs.resolve():
                raise ValueError(f"Unsafe cleanup target: {target}")
            try:
                shutil.rmtree(target)
            except OSError as error:
                info(f"Published output; temporary cleanup deferred: {target}: {error}")
        else:
            info(f"Export failed; previous output preserved. Diagnostic files: {self.run_dir}")
