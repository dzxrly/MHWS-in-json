"""Publish the validated release bundle without rebuilding or reading source assets."""

import argparse
from html import escape
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.processed_data.enemy_battle_logic.definitions import INDEX_NAME
from src.processed_data.enemy_battle_logic.validation import validate_bundle


def build_pages(processed_dir, destination, *, version, repository):
    source = Path(processed_dir).resolve()
    destination = Path(destination).resolve()
    if (
        source == destination
        or source in destination.parents
        or destination in source.parents
    ):
        raise ValueError("Pages 输出不能覆盖或包含 processed_data 输入")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Pages 输出目录必须为空，避免发布旧版本文件")
    validate_bundle(source)
    index = json.loads((source / INDEX_NAME).read_text(encoding="utf-8"))
    destination.mkdir(parents=True, exist_ok=True)
    bundle = destination / "enemy_battle_logic"
    bundle.mkdir()
    files = ["index.json"]
    cards = []
    for item in index["monsters"]:
        files.append(item["json"])
        if item["html"]:
            files.append(item["html"])
        name = escape(item["enemyName"])
        enemy_id = escape(item["enemyId"])
        summary = item["resourceSummary"]
        training = " · 训练对象" if item["objectKind"] == "training" else ""
        status = "局部控制流已恢复" if item["html"] else "控制流待恢复"
        graph_link = (
            f'<a href="enemy_battle_logic/{item["html"]}">查看行动图</a>'
            if item["html"]
            else "<span>暂无已恢复行动图</span>"
        )
        cards.append(
            f"""<article data-search="{name} {enemy_id}"><h2>{name}</h2><p class="id">{enemy_id}{training}</p><p class="status">{status}</p><p>{summary["tableCount"]} 个资源表 · {summary["argumentCount"]} 个参数槽位 · {summary["verifiedPredicates"]} 个已绑定通用判断</p><nav>{graph_link}<a download href="enemy_battle_logic/{item["json"]}">下载 JSON</a></nav></article>"""
        )
    for name in files:
        shutil.copyfile(source / "enemy_battle_logic" / name, bundle / name)
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>荒野怪物行动逻辑</title><link rel="icon" href="data:,">
<style>body{{margin:0;background:#101722;color:#e7edf5;font:16px/1.65 system-ui,sans-serif}}main{{max-width:1200px;margin:auto;padding:36px 24px}}h1{{font-size:32px;margin:0}}.intro{{max-width:850px;color:#b8c7d9}}a{{color:#9fceff}}input{{box-sizing:border-box;width:100%;padding:14px;margin:24px 0;border:1px solid #43536c;border-radius:8px;background:#182334;color:white;font:inherit}}section{{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:18px}}article{{padding:22px;background:#182334;border:1px solid #354359;border-radius:12px}}article[hidden]{{display:none}}h2{{margin:0;font-size:23px}}.id{{color:#97abc5;font-family:monospace}}.status{{color:#efce85}}nav{{display:flex;flex-wrap:wrap;gap:18px}}nav span{{color:#97abc5}}footer{{margin-top:30px;color:#97abc5}}</style></head>
<body><main><h1>《怪物猎人：荒野》怪物行动逻辑</h1><div class="intro"><p>共 {len(index["monsters"])} 个大型怪物与训练对象。资源清单保留当前可核实的动作和判断参数；参数槽位不能当作执行顺序或选招概率。已有模型仍是局部流程，未知逻辑保持未知。</p><p>版本：{escape(version)} · <a href="enemy_battle_logic/index.json">机器可读索引</a> · <a href="https://github.com/{escape(repository)}">项目源码与发布压缩包</a></p></div><label for="search">查找怪物名称或 EM 编号</label><input id="search" type="search" placeholder="例如：雌火龙、EM0001" autocomplete="off"><p id="count" aria-live="polite"></p><section>{''.join(cards)}</section><footer>Pages 与 PROCESSED_DATA 使用同一份已校验 JSON/HTML。当前数据未进行游戏内行为验证。</footer></main>
<script>const search=document.querySelector('#search'),cards=[...document.querySelectorAll('article')],count=document.querySelector('#count');function filter(){{let n=0;const q=search.value.trim().toLocaleLowerCase();for(const card of cards){{card.hidden=!card.dataset.search.toLocaleLowerCase().includes(q);if(!card.hidden)n++;}}count.textContent=`显示 ${{n}} / ${{cards.length}} 个对象`;}}search.addEventListener('input',filter);filter();</script></body></html>"""
    (destination / "index.html").write_text(html, encoding="utf-8")
    (destination / ".nojekyll").touch()
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--processed-dir", type=Path, default=ROOT / "output/processed_data"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    print(
        build_pages(
            args.processed_dir,
            args.output,
            version=args.version,
            repository=args.repository,
        )
    )
