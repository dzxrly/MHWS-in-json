"""Selective Python decompilation; Ghidra/JVM are optional research dependencies."""

import json
from pathlib import Path
from .evidence import digest, method_rows, pack_methods
from .pe import verify_rows
from .control_flow import high_function_evidence


def extract(
    manifest,
    exe,
    output,
    project_dir,
    ghidra,
    *,
    project_name=None,
    timeout=30,
    limit=None,
):
    profile = manifest["profile"]
    if digest(exe) != profile["exeSha256"]:
        raise ValueError("EXE does not match manifest")
    methods = method_rows(manifest)
    rows = methods[:limit] if limit is not None else methods
    verify_rows(exe, rows)
    import pyghidra
    from jpype import JLong

    pyghidra.start(install_dir=ghidra)
    from ghidra.app.cmd.disassemble import DisassembleCommand
    from ghidra.app.decompiler import DecompInterface
    from ghidra.program.flatapi import FlatProgramAPI
    from ghidra.program.model.address import AddressSet
    from ghidra.program.model.symbol import SourceType
    from ghidra.util.task import TaskMonitor

    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    name = project_name or "MHWS_" + profile["exeSha256"][:16]
    program_path = "/" + Path(exe).name
    result_rows = []
    with pyghidra.open_project(project_dir, name, create=True) as project:
        if project.getProjectData().getFile(program_path) is None:
            loader = (
                pyghidra.program_loader()
                .project(project)
                .source(str(Path(exe).resolve()))
            )
            with loader.load() as results:
                results.save(TaskMonitor.DUMMY)
        with pyghidra.program_context(project, program_path) as program:
            if str(program.getExecutableSHA256()).lower() != profile["exeSha256"]:
                raise ValueError("Cached Ghidra program does not match manifest EXE")
            api = FlatProgramAPI(program, TaskMonitor.DUMMY)
            with pyghidra.transaction(program, "MHWS bounded evidence extraction"):
                for row in rows:
                    start = api.toAddr(JLong(int(row["address"], 16)))
                    end = api.toAddr(JLong(int(row["end"], 16) - 1))
                    DisassembleCommand(start, AddressSet(start, end), True).applyTo(
                        program, TaskMonitor.DUMMY
                    )
                    function = api.getFunctionAt(start) or api.createFunction(
                        start, row["label"]
                    )
                    if function is not None:
                        function.setName(row["label"], SourceType.USER_DEFINED)
                        try:
                            function.setBody(AddressSet(start, end))
                        except Exception as error:
                            raise ValueError(
                                f"Overlapping function body at {row['address']}"
                            ) from error
            decompiler = DecompInterface()
            try:
                decompiler.openProgram(program)
                for source in rows:
                    row = dict(source)
                    function = api.getFunctionAt(
                        api.toAddr(JLong(int(row["address"], 16)))
                    )
                    row.update(completed=False, error="function not recovered")
                    if function is not None:
                        result = decompiler.decompileFunction(
                            function, timeout, TaskMonitor.DUMMY
                        )
                        row.update(
                            completed=bool(result.decompileCompleted()),
                            error=str(result.getErrorMessage()),
                        )
                        if result.getDecompiledFunction() is not None:
                            row["code"] = str(result.getDecompiledFunction().getC())
                        if result.getHighFunction() is not None:
                            row["controlFlow"] = high_function_evidence(
                                result.getHighFunction()
                            )
                    result_rows.append(row)
                    print(
                        "EXTRACTED",
                        row["type"],
                        row["method"],
                        row["completed"],
                        flush=True,
                    )
            finally:
                decompiler.dispose()
            program.save("MHWS bounded evidence extraction", TaskMonitor.DUMMY)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        json.dumps(
            pack_methods(result_rows, profile),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    if any(not row["completed"] for row in result_rows):
        raise RuntimeError(
            "Some methods failed; output retains explicit failure records"
        )
