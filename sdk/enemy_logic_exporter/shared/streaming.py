"""Resumable native extraction with one compressed body per byte identity."""

import gzip
import hashlib
import json
from pathlib import Path
import time

from .control_flow import high_function_evidence
from .evidence import evidence_key, method_rows, pack_methods
from .native import digest, verify_rows


def _read_cache(path, row, profile):
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf8") as stream:
        data = json.load(stream)
    if data.get("profile") != profile:
        raise ValueError("缓存来源版本不匹配")
    for field in ("address", "end", "nativeSha256"):
        if data[field] != row[field]:
            raise ValueError("缓存原生范围或字节身份不匹配")
    return data


def _write_cache(path, data):
    temporary = path.with_suffix(".pending")
    with gzip.open(temporary, "wt", encoding="utf8", compresslevel=6) as stream:
        json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
    temporary.replace(path)


def extract_cached(
    manifest,
    exe,
    output,
    project_dir,
    ghidra,
    *,
    project_name=None,
    timeout=30,
    reuse=()
):
    """Retain every method context; decompile identical native bodies once.

    A completed native extraction remains unreviewed evidence. No semantic model
    or release eligibility is inferred from decompiler success.
    """
    output = Path(output).resolve()
    root = Path(__file__).resolve().parents[3]
    if not output.is_relative_to(root / ".agents"):
        raise ValueError("原生缓存只允许写入项目 .agents")
    if timeout <= 0:
        raise ValueError("反编译超时必须大于零")
    profile = manifest["profile"]
    if digest(exe) != profile["exeSha256"]:
        raise ValueError("EXE does not match manifest")
    rows = method_rows(manifest)
    verify_rows(exe, rows)
    output.mkdir(parents=True, exist_ok=True)
    bodies = output / "bodies"
    bodies.mkdir(exist_ok=True)
    unique = {}
    for row in rows:
        unique.setdefault(evidence_key(row), row)
    reused = 0
    for source in reuse:
        document = json.loads(Path(source).read_text(encoding="utf8"))
        if isinstance(document, dict) and document.get("profile") != profile:
            raise ValueError("复用证据版本不匹配")
        candidates = [
            r
            for r in method_rows(document)
            if evidence_key(r) in unique
            and r.get("completed")
            and r.get("code")
            and r.get("controlFlow")
        ]
        if candidates:
            verify_rows(exe, candidates, require_completed=True)
        for row in candidates:
            key = evidence_key(row)
            path = bodies / (key + ".json.gz")
            if not path.exists():
                _write_cache(
                    path,
                    dict(
                        profile=profile,
                        **{
                            k: row[k]
                            for k in (
                                "address",
                                "end",
                                "nativeSha256",
                                "code",
                                "controlFlow",
                                "completed",
                            )
                        },
                        error=row.get("error", ""),
                        reviewStatus="unreviewed_native_control_flow"
                    ),
                )
                reused += 1
    started = time.monotonic()
    status = {}
    pending = []
    for key, row in unique.items():
        data = _read_cache(bodies / (key + ".json.gz"), row, profile)
        if data and data.get("completed") and data.get("controlFlow"):
            status[key] = {
                "completed": data["completed"],
                "error": data.get("error", ""),
            }
        else:
            pending.append((key, row))

    def checkpoint():
        references = {}
        for key, data in status.items():
            path = bodies / (key + ".json.gz")
            references[key] = dict(
                path="bodies/" + path.name,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size,
                completed=data["completed"],
                error=data.get("error", ""),
            )
        index = pack_methods(
            rows,
            profile,
            nativeBodyArtifacts=references,
            scope="原生证据提取；未经人工语义审核，不是行动模型",
        )
        (output / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, separators=(",", ":")),
            encoding="utf8",
        )
        receipt = dict(
            methodBindings=len(rows),
            uniqueNativeBodies=len(unique),
            processedBodies=len(status),
            completedBodies=sum(x["completed"] for x in status.values()),
            failedBodies=sum(not x["completed"] for x in status.values()),
            pendingBodies=len(unique) - len(status),
            reusedBodies=reused,
            compressedBodyBytes=sum(x["bytes"] for x in references.values()),
            elapsedSeconds=round(time.monotonic() - started, 1),
            semanticReviewCompleted=False,
        )
        (output / "receipt.json").write_text(
            json.dumps(receipt, indent=2), encoding="utf8"
        )
        print("NATIVE BATCH", json.dumps(receipt), flush=True)
        return receipt

    checkpoint()
    if pending:
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
        with pyghidra.open_project(project_dir, name, create=False) as project:
            with pyghidra.program_context(project, program_path) as program:
                if str(program.getExecutableSHA256()).lower() != profile["exeSha256"]:
                    raise ValueError(
                        "Cached Ghidra program does not match manifest EXE"
                    )
                api = FlatProgramAPI(program, TaskMonitor.DUMMY)
                decompiler = DecompInterface()
                try:
                    decompiler.openProgram(program)
                    for number, (key, row) in enumerate(pending, 1):
                        data = dict(
                            profile=profile,
                            **{k: row[k] for k in ("address", "end", "nativeSha256")},
                            completed=False,
                            error="",
                            reviewStatus="unreviewed_native_control_flow"
                        )
                        try:
                            start = api.toAddr(JLong(int(row["address"], 16)))
                            end = api.toAddr(JLong(int(row["end"], 16) - 1))
                            with pyghidra.transaction(
                                program, "MHWS streamed bounded evidence"
                            ):
                                DisassembleCommand(
                                    start, AddressSet(start, end), True
                                ).applyTo(program, TaskMonitor.DUMMY)
                                function = api.getFunctionAt(
                                    start
                                ) or api.createFunction(start, row["label"])
                                if function is None:
                                    raise ValueError("function not recovered")
                                function.setBody(AddressSet(start, end))
                                function.setName(row["label"], SourceType.USER_DEFINED)
                            result = decompiler.decompileFunction(
                                function, timeout, TaskMonitor.DUMMY
                            )
                            data.update(
                                completed=bool(result.decompileCompleted()),
                                error=str(result.getErrorMessage()),
                            )
                            if result.getDecompiledFunction() is not None:
                                data["code"] = str(
                                    result.getDecompiledFunction().getC()
                                )
                            if result.getHighFunction() is not None:
                                data["controlFlow"] = high_function_evidence(
                                    result.getHighFunction()
                                )
                            data["completed"] = bool(
                                data["completed"]
                                and data.get("code")
                                and data.get("controlFlow")
                            )
                        except Exception as error:
                            data["error"] = type(error).__name__ + ": " + str(error)
                        _write_cache(bodies / (key + ".json.gz"), data)
                        status[key] = data
                        # Bodies are on disk; retain only completion state in memory.
                        status[key] = {k: data[k] for k in ("completed", "error")}
                        if number % 50 == 0:
                            checkpoint()
                    program.save("MHWS streamed evidence", TaskMonitor.DUMMY)
                finally:
                    decompiler.dispose()
    receipt = checkpoint()
    if receipt["failedBodies"]:
        raise RuntimeError("部分原生方法提取失败；索引保留失败记录，可重试续跑")
    return receipt
