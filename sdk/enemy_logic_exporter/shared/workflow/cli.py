"""python -m sdk.enemy_logic_exporter --help"""

import argparse
import json
import os
from pathlib import Path
from ..native.evidence import digest, method_rows
from ..native.pe import verify_rows
from ..config import ROOT, MODEL_DIR, SUPPORTED_PROFILE
from ...monster import get_monster


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
    player = commands.add_parser(
        "player-view", help="为已提取的图 JSON 整理玩家条件与路径，不重新提取原生数据"
    )
    player.add_argument("--models", type=Path, required=True)
    player.add_argument("--output", type=Path, required=True)
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
    recover = commands.add_parser(
        "recover", help="逐怪物恢复原生参数、条件与状态注释，只输出离线 JSON"
    )
    recover.add_argument("--index", type=Path, required=True)
    recover.add_argument("--helpers", type=Path, required=True)
    recover.add_argument("--inventory", type=Path, required=True)
    recover.add_argument("--requests", type=Path, required=True)
    recover.add_argument("--exe", type=Path, required=True)
    recover.add_argument(
        "--metadata", type=Path, default=ROOT / "src/data/il2cpp_dump.json"
    )
    recover.add_argument("--natives", type=Path, default=ROOT / "MHWS-in-json/natives")
    recover.add_argument("--output", type=Path)
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
    analyze.add_argument(
        "--helpers", type=Path, help="同版本命令/静态初始化索引，供独立怪物配方构图"
    )
    analyze.add_argument("--output", type=Path)
    extraction = commands.add_parser(
        "extract", help="通过独立怪物模块核对三种输入，输出已解析的行动图 JSON"
    )
    extraction.add_argument(
        "--enemy", required=True, help="完整怪物 ID，如 EM0001_00_0"
    )
    extraction.add_argument("--exe", type=Path, required=True)
    extraction.add_argument(
        "--metadata", type=Path, default=ROOT / "src/data/il2cpp_dump.json"
    )
    extraction.add_argument(
        "--natives", type=Path, default=ROOT / "MHWS-in-json/natives"
    )
    extraction.add_argument(
        "--model", type=Path, help="待核实或已维护的语义输入；默认使用 data/models"
    )
    extraction.add_argument("--rules", type=Path, help="对应来源版本的判断规则")
    extraction.add_argument(
        "--index", type=Path, help="匹配来源的原生 BTable 证据索引，调用本怪物专项配方"
    )
    extraction.add_argument(
        "--helpers",
        type=Path,
        help="同版本的命令与静态初始化证据索引；与 --index 一起指定",
    )
    extraction.add_argument(
        "--requests", type=Path, help="独立发现的动作请求 JSON，用于核对恢复覆盖"
    )
    extraction.add_argument("--output", type=Path)
    extraction.add_argument(
        "--inventory", type=Path, help="同版本实际槽和导入闭包发现 JSON"
    )
    all_models = commands.add_parser(
        "extract-all", help="按34个独立怪物模块构图并输出覆盖回执；保留真实未知边界"
    )
    all_models.add_argument("--exe", type=Path, required=True)
    all_models.add_argument(
        "--metadata", type=Path, default=ROOT / "src/data/il2cpp_dump.json"
    )
    all_models.add_argument(
        "--natives", type=Path, default=ROOT / "MHWS-in-json/natives"
    )
    for name in ("index", "helpers", "inventory", "requests"):
        all_models.add_argument("--" + name, type=Path, required=True)
    all_models.add_argument(
        "--enemy", action="append", help="只核查指定完整ID；省略则运行全部34只"
    )
    all_models.add_argument("--rules", type=Path)
    all_models.add_argument("--output", type=Path)
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
    if args.command == "player-view":
        from ..models.player_view import enrich_models

        enrich_models(args.models, args.output)
    elif args.command == "manifest":
        from ..native.manifest import build_manifest

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
        from ..native.decompile import extract

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
            from ..native.streaming import extract_cached

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
            helper_index=args.helpers,
        )
    elif args.command == "requests":
        from ..resources.requests import discover_requests

        discover_requests(
            args.index,
            args.inventory,
            args.exe,
            args.metadata,
            args.natives,
            args.output or work / "action-requests.json",
        )
    elif args.command == "recover":
        from ..logic.command_catalog import export_commands
        from .semantic_recovery import recover_all

        output = (args.output or work / "per-monster").resolve()
        if not output.is_relative_to(ROOT / ".agents"):
            raise ValueError("逐怪物研究只能输出到 .agents")
        inventory = json.loads(args.inventory.read_text(encoding="utf8"))
        export_commands(
            args.helpers,
            args.metadata,
            output / "commands",
            exe=args.exe,
            inventory=inventory,
        )
        recover_all(
            args.index,
            args.inventory,
            args.exe,
            args.metadata,
            args.natives,
            output / "annotations",
            command_catalog=output / "commands/command-catalog.json",
            requests_path=args.requests,
        )
    elif args.command == "extract-all":
        from .batch_models import extract_all_models
        from ..models.catalog import EXPECTED_ENEMY_IDS

        result = extract_all_models(
            args.exe,
            args.metadata,
            args.natives,
            args.index,
            args.helpers,
            args.inventory,
            args.requests,
            args.output or work / "semantic-graphs",
            enemy_ids=tuple(args.enemy) if args.enemy else EXPECTED_ENEMY_IDS,
            rules_path=args.rules,
        )
        print(
            json.dumps(
                {k: v for k, v in result.items() if k != "semanticModels"},
                ensure_ascii=False,
            )
        )
    elif args.command == "extract":
        from .freeze import freeze_models, freeze_native_model

        get_monster(args.enemy)
        if bool(args.index) != bool(args.helpers):
            raise ValueError("--index 与 --helpers 必须同时提供")
        if args.index and args.model:
            raise ValueError("原生专项配方与 --model 不能同时指定")
        if args.requests and not args.index:
            raise ValueError("--requests 仅用于原生专项配方")
        if args.index:
            content = freeze_native_model(
                args.enemy,
                args.exe,
                args.metadata,
                args.natives,
                args.index,
                args.helpers,
                requests_path=args.requests,
                rules_path=args.rules,
                inventory_path=args.inventory,
            )
            output = args.output or work / "extracted"
            output.mkdir(parents=True, exist_ok=True)
            target = output / (args.enemy.lower() + ".v1.json")
            target.write_text(content, encoding="utf8")
            print(
                json.dumps(
                    dict(enemyId=args.enemy, graphs=[str(target)]), ensure_ascii=False
                )
            )
            return
        paths = freeze_models(
            MODEL_DIR,
            args.output or work / "extracted",
            args.exe,
            args.metadata,
            args.natives,
            SUPPORTED_PROFILE,
            enemy_id=args.enemy,
            template_path=args.model,
            rules_path=args.rules,
        )
        print(
            json.dumps(
                dict(enemyId=args.enemy, graphs=[str(path) for path in paths]),
                ensure_ascii=False,
            )
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
