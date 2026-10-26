"""Menu front end for the SDK commands: python -m sdk

Every action runs the matching command line (python -m sdk.<tool> ...) in a
child process with this interpreter, so the menu adds no behaviour of its own;
the command it runs is printed first and can be copied into scripts. The
PROCESSED_DATA builders are started the same way: the SDK does not import src.
"""

import os
import subprocess
import sys
from pathlib import Path

import questionary

from sdk.enemy_logic_exporter.shared.workflow.environment import (
    find_game_exe,
    find_il2cpp,
)

ROOT = Path(__file__).resolve().parents[1]
ENEMY = "sdk.enemy_logic_exporter"
SKILL = "sdk.skill_effect_exporter"
TRY_DIR = ".tmp/skill-effects"
ENEMY_DIR = ".tmp/enemy-logic-exporter/tui"


class Session:
    """The dumped EXE and il2cpp dump of this session; None until given.

    Only MHWS_EXE / MHWS_IL2CPP are read at start; no path is guessed.
    """

    def __init__(self):
        self.exe = find_game_exe()
        self.il2cpp = find_il2cpp()

    def inputs(self):
        args = []
        if self.exe:
            args += ["-e", str(self.exe)]
        if self.il2cpp:
            args += ["-i", str(self.il2cpp)]
        return args


def run(module, *args):
    command = [sys.executable, "-B", "-m", module, *map(str, args)]
    print("\n>", " ".join(command[1:]), flush=True)
    code = subprocess.call(command, cwd=ROOT, env=dict(os.environ, PYTHONUTF8="1"))
    print(f"\n退出码 {code}" if code else "\n完成")
    questionary.press_any_key_to_continue("按任意键返回菜单").ask()


def ask_text(message, default=""):
    answer = questionary.text(message, default=default).ask()
    return answer.strip() if answer else None


def choose(message, choices):
    return questionary.select(message, choices=choices).ask()


def skill_menu(session):
    action = choose(
        "技能效果 SDK",
        [
            "全量提取（写入 src/processed_data/skill_details/data，约 30 分钟）",
            "调试指定技能（输出到 .tmp）",
            "更新数值含义与说明（技能模块 → index.json，不重新求值）",
            "重建 SkillDetails.xlsx",
            "返回",
        ],
    )
    if action is None or action == "返回":
        return
    if action.startswith("全量"):
        run(SKILL, "extract", *session.inputs())
    elif action.startswith("调试"):
        skills = ask_text("技能 ID，多个用空格分隔", "HunterSkill_019")
        if not skills:
            return
        output = ask_text("输出目录", f"{TRY_DIR}/try")
        flags = [arg for skill in skills.split() for arg in ("-s", skill)]
        run(SKILL, "extract", *session.inputs(), *flags, "-o", output)
    elif action.startswith("更新"):
        run(SKILL, "annotate")
    else:
        run("src.processed_data.skill_details")


def enemy_menu(session):
    action = choose(
        "怪物行动逻辑 SDK",
        [
            "提取一只怪物",
            "提取全部怪物并生成玩家视图",
            "统计未知条件（census / uncertainty）",
            "发布到网页模型目录（publish）",
            "构建怪物行动逻辑网页",
            "返回",
        ],
    )
    if action is None or action == "返回":
        return
    full, view = f"{ENEMY_DIR}/models", f"{ENEMY_DIR}/player-view"
    if action == "提取一只怪物":
        enemy = ask_text("怪物 ID", "EM0002_00_0")
        if enemy:
            run(
                ENEMY,
                "extract",
                *session.inputs(),
                "--enemy",
                enemy,
                "-o",
                f"{ENEMY_DIR}/one",
            )
    elif action.startswith("提取全部"):
        run(ENEMY, "extract-all", *session.inputs(), "-o", full)
        run(ENEMY, "player-view", "-m", full, "-o", view)
    elif action.startswith("统计"):
        run(ENEMY, "census", "-m", view)
        run(ENEMY, "uncertainty", "-m", view)
    elif action.startswith("发布"):
        if questionary.confirm(
            f"用 {view} 覆盖 src 中的网页模型？", default=False
        ).ask():
            run(ENEMY, "publish", "-m", view)
    else:
        run("src.processed_data.enemy_battle_logic", "--output", f"{ENEMY_DIR}/site")


def ask_path(message, current):
    """A file path typed or pasted by the user (quotes from "Copy as path" removed)."""
    answer = ask_text(message, str(current or ""))
    return Path(answer.strip('"')) if answer else current


def settings_menu(session):
    session.exe = ask_path(
        "dump 出的游戏 EXE 路径（如 …\\MonsterHunterWilds_dump.exe）", session.exe
    )
    session.il2cpp = ask_path(
        "REFramework 导出的 il2cpp_dump.json 路径", session.il2cpp
    )


def main():
    session = Session()
    if session.exe is None or session.il2cpp is None:
        print(
            "尚未指定 dump 出的 EXE 或 il2cpp_dump.json，请先填写（也可设环境变量 MHWS_EXE、MHWS_IL2CPP）"
        )
        settings_menu(session)
    while True:
        print(f"\nEXE：{session.exe or '未设置'}\nil2cpp：{session.il2cpp or '未设置'}")
        action = choose(
            "MHWS SDK",
            [
                "检查环境",
                "技能效果",
                "怪物行动逻辑",
                "设置 EXE 与 il2cpp 路径",
                "运行 SDK 测试",
                "退出",
            ],
        )
        if action is None or action == "退出":
            return
        if action == "检查环境":
            run(ENEMY, "check-env", *session.inputs())
        elif action == "技能效果":
            skill_menu(session)
        elif action == "怪物行动逻辑":
            enemy_menu(session)
        elif action.startswith("设置"):
            settings_menu(session)
        else:
            run("unittest", "discover", "-s", "tests/sdk", "-t", ".")


if __name__ == "__main__":
    main()
