"""python -m sdk.skill_effect_exporter --help"""

import argparse
import json
from pathlib import Path

from sdk.enemy_logic_exporter.shared.workflow.environment import (
    find_game_exe,
    find_il2cpp,
)

from ...config import DEFAULT_NATIVES, DEFAULT_OUTPUT


def parser():
    exe, il2cpp = find_game_exe(), find_il2cpp()
    result = argparse.ArgumentParser(
        description="离线提取技能到效果数值的链路；数据库构建不需要 EXE"
    )
    commands = result.add_subparsers(dest="command", required=True)
    extract = commands.add_parser(
        "extract", help="扫描 EXE 中使用技能的函数并按技能等级求值，写出链路 JSON"
    )
    extract.add_argument(
        "-e",
        "--exe",
        type=Path,
        default=exe,
        required=exe is None,
        help="dump 出的游戏 EXE（如 MonsterHunterWilds_dump.exe）；未指定时取环境变量 MHWS_EXE",
    )
    extract.add_argument(
        "-i",
        "--il2cpp",
        type=Path,
        default=il2cpp,
        required=il2cpp is None,
        help="REFramework 导出的 il2cpp_dump.json；未指定时取环境变量 MHWS_IL2CPP",
    )
    extract.add_argument(
        "-n",
        "--natives",
        type=Path,
        default=DEFAULT_NATIVES,
        help="解包 JSON 的 natives 目录",
    )
    extract.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="链路分片目录，默认 src/processed_data/skill_details/data/skill_links",
    )
    extract.add_argument(
        "-s",
        "--skill",
        action="append",
        help="只处理指定 HunterSkill ID（调试用，可重复）",
    )
    extract.add_argument(
        "--all-links",
        action="store_true",
        help="也求值技能模块 SKIPPED_FUNCTIONS 中跳过的函数（游戏更新后核对跳过是否仍成立）",
    )
    annotate = commands.add_parser(
        "annotate",
        help="只用技能模块（skills/<id>.py）更新链路目录 index.json 中的数值含义与说明，不重新求值",
    )
    annotate.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="链路分片目录，默认 src/processed_data/skill_details/data/skill_links",
    )
    new_skill = commands.add_parser(
        "new-skill", help="为技能表中新增的技能生成空的技能模块，不覆盖已有模块"
    )
    new_skill.add_argument("-s", "--skill", required=True, help="HunterSkill ID")
    new_skill.add_argument("--name", default="", help="写进模块说明的技能名称")
    return result


def main():
    args = parser().parse_args()
    if args.command == "extract":
        if args.skill and args.output == DEFAULT_OUTPUT:
            raise SystemExit(
                "按技能筛选的调试结果不能写入正式位置，请用 -o 指定 .tmp 下的目录"
            )
        from .extract import extract

        document = extract(
            args.exe,
            args.il2cpp,
            args.natives,
            skills=set(args.skill or ()),
            all_links=args.all_links,
        )
        from .shards import write_shards

        written = write_shards(document, args.output)
        print(
            json.dumps(
                dict(
                    output=str(args.output),
                    files=len(written),
                    links=len(document["links"]),
                    **document["stats"]
                ),
                ensure_ascii=False,
            )
        )
    elif args.command == "annotate":
        from .annotate import annotate_directory

        index, missing, extra = annotate_directory(args.output)
        print(
            json.dumps(
                dict(
                    output=str(args.output),
                    meanings=sum(len(v) for v in index["meanings"].values()),
                    notes=len(index["notes"]["skills"]),
                    missingModules=missing,
                    unknownModules=extra,
                ),
                ensure_ascii=False,
            )
        )
    elif args.command == "new-skill":
        from ...skills import new_skill as write

        print(write(args.skill, args.name))
