"""python -m sdk.enemy_logic_exporter --help"""

import argparse
import json
import os
from pathlib import Path

from .native import digest, verify_rows
from .evidence import method_rows

ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_PROFILE = {
    "gameVersion": "1.42.0.2",
    "exeSha256": "aa38eb46ae1f3c6c94fb2dd94af59b4665bd4c8ccee56bc36b88cf82397a5b4a",
    "metadataSha256": "01ab8f96c9786f3707fc0fc0376eb2e34124eea2d61b749354cac6e124b323d1",
}


def read_rows(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return method_rows(document)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def verify_profile(exe, metadata, profile):
    if (
        digest(exe) != profile["exeSha256"]
        or digest(metadata) != profile["metadataSha256"]
    ):
        raise ValueError(
            "Source version changed; review recipes before freezing. Do not merely replace hashes."
        )


def parser():
    result = argparse.ArgumentParser(
        description="离线提取原生证据；正式行动树构建无需 EXE"
    )
    result.add_argument(
        "--work-dir", type=Path, default=ROOT / ".agents/enemy-logic-exporter"
    )
    commands = result.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser(
        "manifest", help="从当前元数据重新定位方法并计算原生字节摘要"
    )
    manifest.add_argument("--exe", type=Path, required=True)
    manifest.add_argument(
        "--metadata", type=Path, default=ROOT / "src/data/il2cpp_dump.json"
    )
    manifest.add_argument("--enemy", default="Em0001_00")
    manifest.add_argument(
        "--selection", choices=("base", "upstream", "all"), default="all"
    )
    manifest.add_argument("--version", required=True)
    manifest.add_argument(
        "--helper", type=lambda value: int(value, 0), action="append", default=[]
    )
    manifest.add_argument("--output", type=Path)
    decompile = commands.add_parser("decompile", help="用 PyGhidra 按清单提取方法")
    decompile.add_argument("--exe", type=Path, required=True)
    decompile.add_argument("--manifest", type=Path, required=True)
    decompile.add_argument(
        "--ghidra", type=Path, default=os.environ.get("GHIDRA_INSTALL_DIR")
    )
    decompile.add_argument("--project-dir", type=Path)
    decompile.add_argument("--project-name")
    decompile.add_argument("--output", type=Path)
    decompile.add_argument("--limit", type=int)
    decompile.add_argument("--timeout", type=int, default=30)
    decompile.add_argument(
        "--cache-dir", type=Path, help="在 .agents 按原生字节身份压缩缓存，支持续跑"
    )
    decompile.add_argument(
        "--reuse",
        type=Path,
        action="append",
        default=[],
        help="复用已经校验且带控制流的研究证据",
    )
    verify = commands.add_parser("verify", help="核对证据摘要与当前 EXE")
    verify.add_argument("--exe", type=Path, required=True)
    verify.add_argument("--evidence", type=Path, required=True)
    index = commands.add_parser(
        "index", help="去重的全怪物原生研究索引，只输出到 .agents"
    )
    index.add_argument("--exe", type=Path, required=True)
    index.add_argument(
        "--metadata", type=Path, default=ROOT / "src/data/il2cpp_dump.json"
    )
    index.add_argument("--version", required=True)
    index.add_argument("--output", type=Path)
    requests = commands.add_parser(
        "requests", help="从压缩原生证据发现显式动作请求及参数变体；不推断完整控制流"
    )
    requests.add_argument("--index", type=Path, required=True)
    requests.add_argument("--inventory", type=Path, required=True)
    requests.add_argument("--exe", type=Path, required=True)
    requests.add_argument(
        "--metadata", type=Path, default=ROOT / "src/data/il2cpp_dump.json"
    )
    requests.add_argument("--natives", type=Path, default=ROOT / "MHWS-in-json/natives")
    requests.add_argument("--output", type=Path)
    analyze = commands.add_parser(
        "analyze",
        help="完整运行全部大型怪物的资源、原生证据及动作请求分析，保留语义发布验收",
    )
    analyze.add_argument("--exe", type=Path, required=True)
    analyze.add_argument("--version", required=True)
    analyze.add_argument(
        "--metadata", type=Path, default=ROOT / "src/data/il2cpp_dump.json"
    )
    analyze.add_argument("--natives", type=Path, default=ROOT / "MHWS-in-json/natives")
    analyze.add_argument(
        "--ghidra", type=Path, default=os.environ.get("GHIDRA_INSTALL_DIR")
    )
    analyze.add_argument("--project-dir", type=Path)
    analyze.add_argument("--project-name")
    analyze.add_argument("--index", type=Path, help="复用来源摘要已匹配的全量索引")
    analyze.add_argument("--cache-dir", type=Path)
    analyze.add_argument("--output", type=Path)
    freeze = commands.add_parser(
        "freeze",
        help="执行已人工核实的固化配方；全怪物必须提供语义模型，不能生成占位索引",
    )
    freeze.add_argument("--exe", type=Path, required=True)
    freeze.add_argument(
        "--metadata", type=Path, default=ROOT / "src/data/il2cpp_dump.json"
    )
    freeze.add_argument("--natives", type=Path, default=ROOT / "MHWS-in-json/natives")
    freeze.add_argument("--output", type=Path)
    freeze.add_argument(
        "--all",
        action="store_true",
        help="核查工作目录 reviewed 中全部 34 个怪物的语义模型后固化",
    )
    return result


def main():
    args = parser().parse_args()
    work = args.work_dir.resolve()
    if args.command == "manifest":
        from .manifest import build_manifest

        value = build_manifest(
            args.exe,
            args.metadata,
            args.enemy,
            args.selection,
            args.version,
            args.helper,
        )
        write_json(args.output or work / "manifest.json", value)
        print(
            json.dumps(
                {
                    "methods": len(value["methods"]),
                    "skipped": len(value["skipped"]),
                    "profile": value["profile"],
                }
            )
        )
    elif args.command == "decompile":
        from .decompile import extract

        if (
            not args.ghidra
            or args.timeout <= 0
            or args.limit is not None
            and args.limit <= 0
        ):
            raise ValueError(
                "Supply --ghidra (or GHIDRA_INSTALL_DIR) and positive timeout/limit"
            )
        value = json.loads(args.manifest.read_text(encoding="utf-8"))
        if args.cache_dir:
            from .streaming import extract_cached

            if args.limit is not None:
                raise ValueError("全量缓存提取不接受 --limit，请提供所需范围的清单")
            extract_cached(
                value,
                args.exe,
                args.cache_dir,
                args.project_dir or work / "ghidra-projects",
                args.ghidra,
                project_name=args.project_name,
                timeout=args.timeout,
                reuse=args.reuse,
            )
            return
        extract(
            value,
            args.exe,
            args.output or work / "decompiled.json",
            args.project_dir or work / "ghidra-projects",
            args.ghidra,
            project_name=args.project_name,
            timeout=args.timeout,
            limit=args.limit,
        )
    elif args.command == "verify":
        rows = read_rows(args.evidence)
        verify_rows(args.exe, rows, require_completed=True)
        print("VERIFIED", len(rows), "native method bodies")
    elif args.command == "index":
        from .batch import export_native_index

        result = export_native_index(
            args.exe,
            args.metadata,
            args.output or work / "native-index.v2.json",
            args.version,
        )
        print(
            "INDEXED",
            len(result["methods"]),
            "bindings",
            len(result["nativeCode"]),
            "unique code ranges",
        )
    elif args.command == "analyze":
        from .full_run import run_all

        if not args.ghidra:
            raise ValueError("完整离线分析需要 --ghidra")
        run_all(
            args.exe,
            args.metadata,
            args.natives,
            args.output or work / "full-run",
            args.version,
            args.ghidra,
            args.project_dir or work / "ghidra-projects",
            project_name=args.project_name,
            index_path=args.index,
            cache_dir=args.cache_dir,
        )
    elif args.command == "requests":
        from .requests import discover_requests

        discover_requests(
            args.index,
            args.inventory,
            args.exe,
            args.metadata,
            args.natives,
            args.output or work / "action-requests.json",
        )
    elif args.command == "freeze":
        from .freeze import freeze_current_preview

        if args.all:
            from .freeze import freeze_reviewed_models

            freeze_reviewed_models(
                work / "reviewed",
                args.output or ROOT / "src/processed_data/enemy_battle_logic/models",
                args.exe,
                args.metadata,
                args.natives,
                SUPPORTED_PROFILE,
            )
            return

        output = args.output or work / "frozen"
        freeze_current_preview(
            output, args.exe, args.metadata, args.natives, SUPPORTED_PROFILE
        )
        print("FROZEN OUTPUT", output)


if __name__ == "__main__":
    main()
