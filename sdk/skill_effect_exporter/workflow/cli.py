"""python -m sdk.skill_effect_exporter --help"""

import argparse
import json
from pathlib import Path

from sdk.enemy_logic_exporter.shared.workflow.environment import (
    find_game_exe,
    find_il2cpp,
)

from ..config import DEFAULT_NATIVES, DEFAULT_OUTPUT


def parser():
    exe = find_game_exe()
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
        help="游戏 EXE；默认取环境变量 MHWS_EXE，其次在 Steam 库中查找",
    )
    extract.add_argument(
        "-i",
        "--il2cpp",
        type=Path,
        help="与 EXE 同版本的 il2cpp_dump.json；默认取环境变量 MHWS_IL2CPP，其次取 EXE 同目录的文件",
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
    return result


def main():
    args = parser().parse_args()
    il2cpp = args.il2cpp or find_il2cpp(args.exe)
    if il2cpp is None or not Path(il2cpp).is_file():
        raise SystemExit(
            "缺少 il2cpp dump：用 -i/--il2cpp 指定，或设环境变量 MHWS_IL2CPP，或把 il2cpp_dump.json 放在 EXE 同目录"
        )
    if args.command == "extract":
        if args.skill and args.output == DEFAULT_OUTPUT:
            raise SystemExit(
                "按技能筛选的调试结果不能写入正式位置，请用 -o 指定 .agents 下的目录"
            )
        from .extract import extract

        document = extract(args.exe, il2cpp, args.natives, skills=set(args.skill or ()))
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
