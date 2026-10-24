"""python -m sdk.enemy_logic_exporter --help"""

import argparse
import json
import os
from pathlib import Path
from ..native.evidence import method_rows
from ..native.pe import verify_rows
from ..config import ACTIVE_PROFILE_PATH, ROOT, in_agents

MODEL_DIR_WEB = ROOT / "src/processed_data/enemy_battle_logic/models"
DEFAULT_NATIVES = ROOT / "MHWS-in-json/natives"
from ...monster import get_monster


def read_rows(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return method_rows(document)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parser():
    from .environment import default_work_dir, find_game_exe, find_il2cpp

    result = argparse.ArgumentParser(
        description="离线提取原生证据；正式行动树构建无需 EXE"
    )
    result.add_argument(
        "-w",
        "--work-dir",
        type=Path,
        default=default_work_dir(),
        help="研究缓存目录，默认 .agents/enemy-logic-exporter 或环境变量 MHWS_SDK_WORK_DIR",
    )
    exe, il2cpp = find_game_exe(), find_il2cpp()

    def add_exe(command):
        command.add_argument(
            "-e",
            "--exe",
            type=Path,
            default=exe,
            required=exe is None,
            help="dump 出的游戏 EXE（如 MonsterHunterWilds_dump.exe）；未指定时取环境变量 MHWS_EXE",
        )

    def add_il2cpp(command):
        command.add_argument(
            "-i",
            "--il2cpp",
            type=Path,
            default=il2cpp,
            required=il2cpp is None,
            help="REFramework 导出的 il2cpp_dump.json；未指定时取环境变量 MHWS_IL2CPP",
        )

    def add_natives(command):
        command.add_argument(
            "-n",
            "--natives",
            type=Path,
            default=DEFAULT_NATIVES,
            help="解包 JSON 的 natives 目录",
        )

    def add_output(command, **options):
        command.add_argument("-o", "--output", type=Path, **options)

    def add_models(command):
        command.add_argument("-m", "--models", type=Path, required=True)

    commands = result.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "check-env", help="检查新环境缺少的依赖、游戏文件、研究缓存与 Ghidra 设置"
    )
    check.add_argument("-e", "--exe", type=Path)
    check.add_argument("-i", "--il2cpp", type=Path)
    check.add_argument("-n", "--natives", type=Path)
    player = commands.add_parser(
        "player-view", help="为已提取的图 JSON 整理玩家条件与路径，不重新提取原生数据"
    )
    add_models(player)
    add_output(player, required=True)
    uncertainty = commands.add_parser(
        "uncertainty", help="统计玩家战斗树中在全部玩家输入已知时仍无法判定的条件"
    )
    add_models(uncertainty)
    uncertainty.add_argument("--top", type=int, default=30)
    census = commands.add_parser(
        "census", help="按命令与原因统计全部含未知部分的条件，找出最大的待确认类别"
    )
    add_models(census)
    census.add_argument("--top", type=int, default=40)
    roster = commands.add_parser(
        "roster", help="从 EnemyData 与 BTableList 重新生成大型怪物名单并报告新增/移除"
    )
    add_natives(roster)
    roster.add_argument("--write", action="store_true")
    scaffold = commands.add_parser(
        "new-monster", help="为名单中的新怪物生成独立入口模块"
    )
    scaffold.add_argument("--enemy", required=True)
    resolve = commands.add_parser(
        "resolve-symbols",
        help="按符号定义为当前 EXE/il2cpp 重新生成 profile（默认写入 data/profile.json）",
    )
    add_exe(resolve)
    add_il2cpp(resolve)
    resolve.add_argument("--previous", type=Path, default=ACTIVE_PROFILE_PATH)
    add_output(resolve)
    migrate = commands.add_parser(
        "migrate-evidence",
        help="把规范化代码未变的证据行迁移到新版本，其余列入人工复核",
    )
    add_exe(migrate)
    add_il2cpp(migrate)
    migrate.add_argument("--previous", type=Path, default=ACTIVE_PROFILE_PATH)
    migrate.add_argument("--profile", type=Path, required=True)
    migrate.add_argument("--apply", action="store_true")
    publish = commands.add_parser(
        "publish", help="把 .agents 中的完整研究模型写成网页使用的精简模型"
    )
    add_models(publish)
    add_output(publish, default=MODEL_DIR_WEB)
    slots = commands.add_parser(
        "scheduler-slots", help="从 EXE 恢复 AI 状态/中断请求的行为表槽并写入证据"
    )
    add_exe(slots)
    add_il2cpp(slots)
    manifest = commands.add_parser(
        "manifest", help="从当前 il2cpp 重新定位方法并计算原生字节摘要"
    )
    add_exe(manifest)
    add_il2cpp(manifest)
    manifest.add_argument("--enemy", default="Em0001_00")
    manifest.add_argument(
        "--selection", choices=("base", "upstream", "all"), default="all"
    )
    manifest.add_argument(
        "--helper", type=lambda value: int(value, 0), action="append", default=[]
    )
    add_output(manifest)
    decompile = commands.add_parser("decompile", help="用 PyGhidra 按清单提取方法")
    add_exe(decompile)
    decompile.add_argument("--manifest", type=Path, required=True)
    decompile.add_argument(
        "--ghidra", type=Path, default=os.environ.get("GHIDRA_INSTALL_DIR")
    )
    decompile.add_argument("--project-dir", type=Path)
    decompile.add_argument("--project-name")
    add_output(decompile)
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
    add_exe(verify)
    verify.add_argument("--evidence", type=Path, required=True)
    index = commands.add_parser(
        "index", help="去重的全怪物原生研究索引，只输出到 .agents"
    )
    add_exe(index)
    add_il2cpp(index)
    add_output(index)
    requests = commands.add_parser(
        "requests", help="从压缩原生证据发现显式动作请求及参数变体；不推断完整控制流"
    )
    requests.add_argument("--index", type=Path, required=True)
    requests.add_argument("--inventory", type=Path, required=True)
    add_exe(requests)
    add_il2cpp(requests)
    add_natives(requests)
    add_output(requests)
    recover = commands.add_parser(
        "recover", help="逐怪物恢复原生参数、条件与状态注释，只输出离线 JSON"
    )
    recover.add_argument("--index", type=Path, required=True)
    recover.add_argument("--helpers", type=Path, required=True)
    recover.add_argument("--inventory", type=Path, required=True)
    recover.add_argument("--requests", type=Path, required=True)
    add_exe(recover)
    add_il2cpp(recover)
    add_natives(recover)
    add_output(recover)
    analyze = commands.add_parser(
        "analyze",
        help="完整运行全部大型怪物的资源、原生证据及动作请求分析，保留语义发布验收",
    )
    add_exe(analyze)
    add_il2cpp(analyze)
    add_natives(analyze)
    analyze.add_argument(
        "--ghidra", type=Path, default=os.environ.get("GHIDRA_INSTALL_DIR")
    )
    analyze.add_argument("--project-dir", type=Path)
    analyze.add_argument("--project-name")
    analyze.add_argument("--index", type=Path, help="复用已有的全量原生索引")
    analyze.add_argument("--cache-dir", type=Path)
    analyze.add_argument(
        "--helpers", type=Path, help="命令/静态初始化索引，供独立怪物配方构图"
    )
    add_output(analyze)
    extraction = commands.add_parser(
        "extract", help="通过独立怪物模块核对三种输入，输出已解析的行动图 JSON"
    )
    extraction.add_argument(
        "--enemy", required=True, help="完整怪物 ID，如 EM0001_00_0"
    )
    add_exe(extraction)
    add_il2cpp(extraction)
    add_natives(extraction)
    extraction.add_argument(
        "--rules", type=Path, help="判断规则（默认 data/rules.v1.json）"
    )
    extraction.add_argument(
        "--index",
        type=Path,
        help="原生 BTable 证据索引（默认取工作目录标准位置）",
    )
    extraction.add_argument(
        "--helpers", type=Path, help="命令与静态初始化证据索引（同上）"
    )
    extraction.add_argument(
        "--requests", type=Path, help="独立发现的动作请求 JSON，用于核对恢复覆盖"
    )
    add_output(extraction)
    extraction.add_argument("--inventory", type=Path, help="实际槽和导入闭包发现 JSON")
    all_models = commands.add_parser(
        "extract-all", help="按34个独立怪物模块构图并输出覆盖回执；保留真实未知边界"
    )
    add_exe(all_models)
    add_il2cpp(all_models)
    add_natives(all_models)
    for name in ("index", "helpers", "inventory", "requests"):
        # Defaults to the standard layout under --work-dir (environment.py).
        all_models.add_argument("--" + name, type=Path)
    all_models.add_argument(
        "--enemy", action="append", help="只核查指定完整ID；省略则运行全部34只"
    )
    all_models.add_argument("--rules", type=Path)
    add_output(all_models)
    return result


def main():
    args = parser().parse_args()
    work = args.work_dir.resolve()
    if args.command in ("extract", "extract-all"):
        from .environment import STANDARD_INPUTS, fill_standard_inputs

        fill_standard_inputs(args, work, STANDARD_INPUTS)
        required = ("index", "helpers") + (
            ("inventory", "requests") if args.command == "extract-all" else ()
        )
        missing = [name for name in required if getattr(args, name) is None]
        if missing:
            raise SystemExit(
                "缺少研究缓存："
                + "、".join("--" + n for n in missing)
                + "；先运行 check-env 查看标准位置"
            )
    if args.command == "check-env":
        from .environment import check_environment

        rows = check_environment(args.exe, args.il2cpp, args.natives, work)
        for item, status, detail in rows:
            print(f"[{status:8}] {item}: {detail}")
        raise SystemExit(any(status == "missing" for _, status, _ in rows))
    if args.command == "player-view":
        from ..models.player_view import enrich_models

        enrich_models(args.models, args.output)
    elif args.command == "uncertainty":
        from ..models.uncertainty import uncertainty_report

        print(
            json.dumps(
                uncertainty_report(args.models, args.top), ensure_ascii=False, indent=2
            )
        )
    elif args.command == "census":
        from ..models.uncertainty import unknown_census

        print(
            json.dumps(
                unknown_census(args.models, args.top), ensure_ascii=False, indent=2
            )
        )
    elif args.command == "roster":
        from ..models.roster import (
            ROSTER_PATH,
            build_roster,
            load_roster,
            roster_changes,
        )
        from ..resources.reader import Resources

        new = build_roster(Resources(args.natives))
        changes = roster_changes(load_roster(), new)
        if args.write:
            write_json(ROSTER_PATH, new)
        print(json.dumps(changes, ensure_ascii=False, indent=2))
    elif args.command == "new-monster":
        from ..models.roster import scaffold_monster

        print(scaffold_monster(args.enemy))
    elif args.command == "resolve-symbols":
        from .version_update import resolve_profile

        print(
            json.dumps(
                resolve_profile(args.exe, args.il2cpp, args.previous, args.output),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "migrate-evidence":
        from .version_update import migrate_evidence

        report = migrate_evidence(
            args.exe, args.il2cpp, args.previous, args.profile, apply=args.apply
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report["review"]:
            raise SystemExit(1)
    elif args.command == "publish":
        from ..models.publish import publish_models

        for row in publish_models(args.models, args.output):
            print(json.dumps(row, ensure_ascii=False))
    elif args.command == "scheduler-slots":
        from ..logic.scheduler_slots import write_slot_evidence

        value = write_slot_evidence(args.exe, args.il2cpp)
        print(
            json.dumps(
                {
                    "requests": len(value["requests"]),
                    "boundaries": len(value["boundaries"]),
                    "scannedMethods": value["scannedMethods"],
                }
            )
        )
    elif args.command == "manifest":
        from ..native.manifest import build_manifest

        value = build_manifest(
            args.exe,
            args.il2cpp,
            args.enemy,
            args.selection,
            args.helper,
        )
        write_json(args.output or work / "manifest.json", value)
        print(
            json.dumps(
                {
                    "methods": len(value["methods"]),
                    "skipped": len(value["skipped"]),
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
            args.il2cpp,
            args.output or work / "native-index.v2.json",
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
            args.il2cpp,
            args.natives,
            args.output or work / "full-run",
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
            args.il2cpp,
            args.natives,
            args.output or work / "action-requests.json",
        )
    elif args.command == "recover":
        from ..logic.command_catalog import export_commands
        from .semantic_recovery import recover_all

        output = (args.output or work / "per-monster").resolve()
        if not in_agents(output):
            raise ValueError("逐怪物研究只能输出到 .agents")
        inventory = json.loads(args.inventory.read_text(encoding="utf8"))
        export_commands(
            args.helpers,
            args.il2cpp,
            output / "commands",
            exe=args.exe,
            inventory=inventory,
        )
        recover_all(
            args.index,
            args.inventory,
            args.exe,
            args.il2cpp,
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
            args.il2cpp,
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
        from .freeze import freeze_native_model

        get_monster(args.enemy)
        content = freeze_native_model(
            args.enemy,
            args.exe,
            args.il2cpp,
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
