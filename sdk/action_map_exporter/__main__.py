"""Independent static ActionMap extraction from native dump and JSON resources."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

from .builder import ActionMapOptions, build_action_map

ROOT = Path(__file__).resolve().parents[2]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m sdk.action_map_exporter",
        description="离线构建带精确 requestSet 身份与原生证据的 ActionMap v2。",
    )
    commands = result.add_subparsers(dest="command", required=True)
    extract = commands.add_parser(
        "extract", help="从当前 dump 与 natives JSON 生成 ActionMap"
    )
    extract.add_argument(
        "-e",
        "--exe",
        type=Path,
        default=os.environ.get("MHWS_EXE"),
        required=not bool(os.environ.get("MHWS_EXE")),
        help="dump EXE 路径；也可设置 MHWS_EXE",
    )
    extract.add_argument(
        "-i",
        "--il2cpp",
        type=Path,
        default=os.environ.get("MHWS_IL2CPP"),
        required=not bool(os.environ.get("MHWS_IL2CPP")),
        help="IL2CPP JSON 路径；也可设置 MHWS_IL2CPP",
    )
    extract.add_argument(
        "-n", "--natives", type=Path, default=ROOT / "MHWS-in-json" / "natives"
    )
    extract.add_argument(
        "-o", "--output", type=Path, default=ROOT / "MHWS-in-json" / "ActionMap.json"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    command = parser()
    args = command.parse_args(argv)
    try:
        result = build_action_map(
            ActionMapOptions(
                executable_path=args.exe,
                il2cpp_dump_path=args.il2cpp,
                natives_directory=args.natives,
                output_path=args.output,
            ),
            log=print,
        )
    except (OSError, ValueError) as error:
        command.exit(1, f"ActionMap 生成失败：{error}\n")
    summary = asdict(result)
    summary["output_path"] = str(result.output_path)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
