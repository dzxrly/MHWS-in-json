# IL2CPP 构建数据上传与获取工具
#
# 在项目根目录运行（需要已登录的 GitHub CLI）：
#   python -m sdk.il2cpp upload --dump "完整路径/il2cpp_dump.json"
#   python -m sdk.il2cpp upload --dump "完整路径/il2cpp_dump.json" --dry-run
#   python -m sdk.il2cpp download
#   python -m sdk.il2cpp download --output "其他路径/il2cpp_dump.json"
#
# 默认读取／下载到 src/data/il2cpp_dump.json；临时文件位于项目根目录 .agents/il2cpp。
# --repo owner/name 可指定仓库，默认从 GITHUB_REPOSITORY 或 origin 自动识别。
# --tag build-data 可指定 Release；默认上传 gzip 文件和 SHA-256 校验文件。
# 下载先校验压缩包，再解压替换目标文件；失败时保留已有目标文件。
# 上传会更新同名附件；build-data 不设为最新正式 Release。
# --dry-run 仅压缩并计算校验值，不执行上传。
#
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "src"
DEFAULT_DUMP_NAME = "il2cpp_dump.json"
DEFAULT_DUMP_PATH = SRC_DIR / "data" / DEFAULT_DUMP_NAME
DEFAULT_TAG = "build-data"
DEFAULT_WORK_DIR = PROJECT_DIR / ".agents" / "il2cpp"
DEFAULT_RELEASE_TITLE = "Build Data / 构建数据（普通用户无需下载）"
DEFAULT_RELEASE_NOTES = """## 构建数据 / Build Data

> [!IMPORTANT]
> 该 Release 保存 MHWS 的 IL2CPP 元数据，供自动构建和本地行动逻辑解析使用。普通用户无需下载。
>
> MHWS IL2CPP metadata for automated builds and local behavior analysis. Regular users do not need these files.

数据库与处理后的数据请前往正式 Release 页面下载。

Download the database and processed data from the normal Releases page.
"""
CHUNK_SIZE = 1024 * 1024
GH_RETRIES = 3


def compressed_asset_name(dump_name: str) -> str:
    return f"{dump_name}.gz"


def checksum_asset_name(asset_name: str) -> str:
    return f"{asset_name}.sha256"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_command(args: list[str]) -> str:
    formatted = []
    for arg in args:
        if "\n" in arg:
            formatted.append("<multiline>")
        elif len(arg) > 120:
            formatted.append(f"{arg[:117]}...")
        else:
            formatted.append(arg)
    return " ".join(formatted)


def run_command(
    args: list[str],
    *,
    capture_output: bool = False,
    allow_failure: bool = False,
    retries: int | None = None,
) -> subprocess.CompletedProcess[str]:
    attempts = (
        retries if retries is not None else (GH_RETRIES if args[:1] == ["gh"] else 1)
    )
    for attempt in range(1, attempts + 1):
        retry_note = f" (attempt {attempt}/{attempts})" if attempts > 1 else ""
        print("+", format_command(args), retry_note)
        result = subprocess.run(
            args,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=capture_output or allow_failure,
        )
        if allow_failure or result.returncode == 0:
            return result
        if attempt < attempts:
            print(f"Command failed with exit code {result.returncode}; retrying...")
            time.sleep(2 * attempt)

    raise subprocess.CalledProcessError(result.returncode, args)


def parse_github_remote(remote_url: str) -> str | None:
    patterns = (
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
        r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
        r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.match(pattern, remote_url.strip())
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    return None


def detect_repo(explicit_repo: str | None) -> str:
    if explicit_repo:
        return explicit_repo

    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo

    result = run_command(
        ["git", "config", "--get", "remote.origin.url"],
        capture_output=True,
        allow_failure=True,
    )
    if result.returncode == 0 and result.stdout:
        repo = parse_github_remote(result.stdout)
        if repo:
            return repo

    result = run_command(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        allow_failure=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    raise RuntimeError(
        "GitHub repository could not be detected; pass --repo owner/name."
    )


def compress_file(src_path: Path, dst_path: Path, compresslevel: int) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with src_path.open("rb") as src_file, dst_path.open("wb") as raw_dst:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_dst,
            compresslevel=compresslevel,
            mtime=0,
        ) as gz_dst:
            shutil.copyfileobj(src_file, gz_dst, length=CHUNK_SIZE)


def decompress_file(src_path: Path, dst_path: Path) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_WORK_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="unpack-", dir=DEFAULT_WORK_DIR) as work:
        staged = Path(work) / "il2cpp_dump.json"
        with gzip.open(src_path, "rb") as src_file, staged.open("wb") as dst_file:
            shutil.copyfileobj(src_file, dst_file, length=CHUNK_SIZE)
        staged.replace(dst_path)


def write_checksum(checksum_path: Path, digest: str, asset_name: str) -> None:
    checksum_path.write_text(
        f"{digest}  {asset_name}\n", encoding="utf-8", newline="\n"
    )


def read_expected_checksum(checksum_path: Path) -> str:
    line = checksum_path.read_text(encoding="utf-8").splitlines()[0].strip()
    if not line:
        raise ValueError(f"empty checksum file: {checksum_path}")
    return line.split()[0]


def verify_checksum(asset_path: Path, checksum_path: Path) -> None:
    expected = read_expected_checksum(checksum_path)
    actual = sha256_file(asset_path)
    if actual.lower() != expected.lower():
        raise RuntimeError(
            f"checksum mismatch for {asset_path.name}: expected {expected}, got {actual}"
        )
    print(f"sha256 verified: {actual}")


def release_view_not_found(result: subprocess.CompletedProcess[str]) -> bool:
    output = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    return "not found" in output or "could not find" in output


def run_release_notes_command(args: list[str], notes: str) -> None:
    DEFAULT_WORK_DIR.mkdir(parents=True, exist_ok=True)
    fd, notes_file_name = tempfile.mkstemp(
        prefix="build-data-notes-", suffix=".md", dir=DEFAULT_WORK_DIR
    )
    os.close(fd)
    notes_file = Path(notes_file_name)
    try:
        notes_file.write_text(notes, encoding="utf-8", newline="\n")
        run_command([*args, "--notes-file", str(notes_file)])
    finally:
        notes_file.unlink(missing_ok=True)


def ensure_release(repo: str, tag: str, title: str, notes: str) -> None:
    result = run_command(
        ["gh", "release", "view", tag, "--repo", repo],
        allow_failure=True,
    )
    if result.returncode == 0:
        run_release_notes_command(
            [
                "gh",
                "release",
                "edit",
                tag,
                "--latest=false",
                "--repo",
                repo,
                "--title",
                title,
            ],
            notes,
        )
        return
    if not release_view_not_found(result):
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )

    run_release_notes_command(
        [
            "gh",
            "release",
            "create",
            tag,
            "--latest=false",
            "--repo",
            repo,
            "--title",
            title,
        ],
        notes,
    )


def upload_assets(repo: str, tag: str, asset_path: Path, checksum_path: Path) -> None:
    run_command(
        [
            "gh",
            "release",
            "upload",
            tag,
            str(asset_path),
            str(checksum_path),
            "--repo",
            repo,
            "--clobber",
        ]
    )


def download_asset(repo: str, tag: str, asset_name: str, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_path = dst_dir / asset_name
    if dst_path.exists():
        dst_path.unlink()

    run_command(
        [
            "gh",
            "release",
            "download",
            tag,
            "--repo",
            repo,
            "--pattern",
            asset_name,
            "--dir",
            str(dst_dir),
        ]
    )
    if not dst_path.is_file():
        raise FileNotFoundError(f"release asset was not downloaded: {dst_path}")
    return dst_path


def upload_command(args: argparse.Namespace) -> None:
    repo = detect_repo(args.repo)
    dump_path = args.dump.resolve()
    if not dump_path.is_file():
        raise FileNotFoundError(f"il2cpp dump not found: {dump_path}")

    asset_name = args.asset or compressed_asset_name(dump_path.name)
    checksum_name = checksum_asset_name(asset_name)

    DEFAULT_WORK_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="upload-", dir=DEFAULT_WORK_DIR
    ) as temp_dir:
        temp_path = Path(temp_dir)
        asset_path = temp_path / asset_name
        checksum_path = temp_path / checksum_name

        print(f"Compressing {dump_path} -> {asset_path}")
        compress_file(dump_path, asset_path, args.compresslevel)

        digest = sha256_file(asset_path)
        write_checksum(checksum_path, digest, asset_name)

        print(f"repo: {repo}")
        print(f"tag: {args.tag}")
        print(f"{asset_name}: {asset_path.stat().st_size:,} bytes")
        print(f"sha256: {digest}")

        if args.dry_run:
            print("Dry run complete; release assets were not uploaded.")
            return

        ensure_release(repo, args.tag, args.release_title, args.release_notes)
        upload_assets(repo, args.tag, asset_path, checksum_path)


def download_command(args: argparse.Namespace) -> None:
    repo = detect_repo(args.repo)
    output_path = args.output.resolve()
    asset_name = args.asset or compressed_asset_name(output_path.name)
    checksum_name = checksum_asset_name(asset_name)
    work_dir = args.work_dir.resolve()

    print(f"repo: {repo}")
    print(f"tag: {args.tag}")
    asset_path = download_asset(repo, args.tag, asset_name, work_dir)
    checksum_path = download_asset(repo, args.tag, checksum_name, work_dir)
    verify_checksum(asset_path, checksum_path)

    print(f"Decompressing {asset_path} -> {output_path}")
    decompress_file(asset_path, output_path)


def add_common_release_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo", help="GitHub repository as owner/name. Defaults to env or git remote."
    )
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument(
        "--asset", help="Compressed release asset name. Defaults to <dump-name>.gz."
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload or download build-only data assets."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload_parser = subparsers.add_parser(
        "upload", help="Compress and upload the build data asset."
    )
    add_common_release_args(upload_parser)
    upload_parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP_PATH)
    upload_parser.add_argument(
        "--compresslevel", type=int, choices=range(1, 10), default=9
    )
    upload_parser.add_argument("--dry-run", action="store_true")
    upload_parser.add_argument("--release-title", default=DEFAULT_RELEASE_TITLE)
    upload_parser.add_argument("--release-notes", default=DEFAULT_RELEASE_NOTES)
    upload_parser.set_defaults(func=upload_command)

    download_parser = subparsers.add_parser(
        "download", help="Download and unpack the build data asset."
    )
    add_common_release_args(download_parser)
    download_parser.add_argument("--output", type=Path, default=DEFAULT_DUMP_PATH)
    download_parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    download_parser.set_defaults(func=download_command)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        args.func(args)
    except subprocess.CalledProcessError as exc:
        print(
            f"[ERROR] command failed with exit code {exc.returncode}: {format_command(exc.cmd)}",
            file=sys.stderr,
        )
        if exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        return exc.returncode
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
