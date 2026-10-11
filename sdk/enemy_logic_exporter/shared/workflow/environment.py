"""Locate local inputs on Windows and report what a fresh setup still lacks.

``check-env`` is the first command to run on a new machine: it lists the
Python packages, game files, research caches and optional Ghidra tools that
the other commands need, with the setting that points at each of them.
"""

import importlib.metadata
import os
from pathlib import Path
import sys

from ..config import AGENTS_DIR, ROOT, SUPPORTED_PROFILE, in_agents

GAME_FOLDER = Path("steamapps/common/MonsterHunterWilds/MonsterHunterWilds.exe")
DEFAULT_STEAM = Path("C:/Program Files (x86)/Steam")
DEFAULT_WORK_DIR = AGENTS_DIR / "enemy-logic-exporter"
DEFAULT_METADATA = ROOT / "src/data/il2cpp_dump.json"
DEFAULT_NATIVES = ROOT / "MHWS-in-json/natives"
# Research caches built by analyze / recover, relative to the work directory.
STANDARD_INPUTS = dict(
    index="full-run/native/index.json",
    helpers="per-monster/helpers/index.json",
    inventory="full-run/result/inventory.json",
    requests="full-run/result/action-requests.json",
)
REQUIRED_PACKAGES = {"capstone": "5.0.6"}
OPTIONAL_PACKAGES = {"pyghidra": "3.0.2"}


def steam_libraries():
    """Steam library roots from the registry and libraryfolders.vdf."""
    roots = []
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
    except (ImportError, OSError):
        pass
    roots.append(DEFAULT_STEAM)
    libraries = []
    for root in roots:
        libraries.append(root)
        folders = root / "steamapps/libraryfolders.vdf"
        if folders.is_file():
            for line in folders.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                parts = line.strip().split('"')
                if len(parts) >= 4 and parts[1] == "path":
                    libraries.append(Path(parts[3].replace("\\\\", "\\")))
    return list(dict.fromkeys(libraries))


def find_game_exe():
    """MHWS_EXE, else the game in any Steam library; None when not found."""
    if os.environ.get("MHWS_EXE"):
        return Path(os.environ["MHWS_EXE"])
    for library in steam_libraries():
        if (library / GAME_FOLDER).is_file():
            return library / GAME_FOLDER
    return None


def default_work_dir():
    return Path(os.environ.get("MHWS_SDK_WORK_DIR") or DEFAULT_WORK_DIR)


def fill_standard_inputs(args, work, names):
    """Default the research cache paths to the standard work-dir layout."""
    for name in names:
        if getattr(args, name, None) is None:
            candidate = work / STANDARD_INPUTS[name]
            if candidate.is_file():
                setattr(args, name, candidate)


def check_environment(exe=None, metadata=None, natives=None, work=None, verify=False):
    """Rows of (item, status, detail); status is ok, missing or optional."""
    from ..native.evidence import digest

    rows = []

    def add(item, ok, detail, required=True):
        rows.append(
            (item, "ok" if ok else ("missing" if required else "optional"), detail)
        )

    add(
        "Python",
        sys.version_info >= (3, 11),
        f"{sys.version.split()[0]}（需要 3.11 以上，已验证 3.13）",
    )
    for packages, required in ((REQUIRED_PACKAGES, True), (OPTIONAL_PACKAGES, False)):
        for name, pinned in packages.items():
            try:
                version = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                version = None
            add(
                name,
                version == pinned,
                (
                    f"已安装 {version}，需要 {pinned}"
                    if version
                    else f"未安装，需要 {pinned}"
                ),
                required,
            )
    exe = exe or find_game_exe()
    add(
        "游戏 EXE",
        bool(exe and Path(exe).is_file()),
        f"{exe}（--exe 或环境变量 MHWS_EXE）",
    )
    metadata = metadata or DEFAULT_METADATA
    add("IL2CPP dump", Path(metadata).is_file(), f"{metadata}（--metadata）")
    natives = natives or DEFAULT_NATIVES
    add(
        "资源导出",
        (Path(natives) / "STM/GameDesign/Enemy").is_dir(),
        f"{natives}（--natives）",
    )
    sample = next((Path(natives) / "STM/GameDesign/Enemy").rglob("*.user.3.json"), None)
    if sample is not None:
        original = b"\r\n" not in sample.read_bytes()[:4096]
        add(
            "资源换行",
            original,
            (
                "保持导出时的 LF 字节"
                if original
                else "被改成了 CRLF，摘要会与研究缓存不符；删除 MHWS-in-json 后执行"
                " git checkout -- MHWS-in-json 重新取出（.gitattributes 已设 -text）"
            ),
        )
    if verify:
        for item, path, key in (
            ("EXE 版本", exe, "exeSha256"),
            ("IL2CPP dump 版本", metadata, "metadataSha256"),
        ):
            same = (
                bool(path and Path(path).is_file())
                and digest(path) == SUPPORTED_PROFILE[key]
            )
            add(
                item,
                same,
                f"与 profile {SUPPORTED_PROFILE['gameVersion']} 的摘要"
                + ("一致" if same else "不一致"),
            )
    work = Path(work or default_work_dir())
    add(
        "工作目录",
        in_agents(work),
        f"{work}（--work-dir 或 MHWS_SDK_WORK_DIR；必须位于项目 .agents 内，可用目录联接指向其他磁盘）",
    )
    for name, relative in STANDARD_INPUTS.items():
        path = work / relative
        add(f"缓存 --{name}", path.is_file(), f"{path}（由 analyze / recover 生成）")
    for variable in ("GHIDRA_INSTALL_DIR", "JAVA_HOME"):
        value = os.environ.get(variable)
        add(
            variable,
            bool(value and Path(value).is_dir()),
            f"{value or '未设置'}（只有 decompile / analyze 需要）",
            required=False,
        )
    return rows
