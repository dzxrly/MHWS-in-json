"""python -m src.processed_data.enemy_battle_logic --natives ... --output ..."""

import argparse
import json
from pathlib import Path

from .exporter import export_battle_logic
from .definitions import INDEX_NAME


def main():
    parser = argparse.ArgumentParser(
        description="由固化模型和资源 JSON 构建已核实的局部行动逻辑，无 EXE 输入"
    )
    root = Path(__file__).resolve().parents[3]
    parser.add_argument("--natives", type=Path, default=root / "MHWS-in-json/natives")
    parser.add_argument(
        "--template",
        type=Path,
        help="指定单个固化模板；默认导出 models 中的全部正式模型",
    )
    parser.add_argument("--output", type=Path, default=root / "output/processed_data")
    parser.add_argument("--rules", type=Path, help="待审核或已发布的固化规则 JSON")
    metadata = root / "src/data/il2cpp_dump.json"
    parser.add_argument(
        "--metadata",
        type=Path,
        default=metadata if metadata.exists() else None,
        help="可选元数据 JSON；存在时核对固化规则的来源版本，不读取 EXE",
    )
    args = parser.parse_args()
    paths = export_battle_logic(
        args.output,
        args.natives,
        template_path=args.template,
        metadata_path=args.metadata,
        rules_path=args.rules,
    )
    index = json.loads((args.output / INDEX_NAME).read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "files": [path.relative_to(args.output).as_posix() for path in paths],
                "monsters": index["monsters"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
