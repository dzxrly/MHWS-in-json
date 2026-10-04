"""One offline HTML index linking every generated monster HTML."""

from html import escape
import json


def render_index(records, *, release_ready=False):
    cards = []
    for record in records:
        name, enemy_id = escape(record["enemyName"]), escape(record["enemyId"])
        coverage = record["coverage"]
        status = f"{coverage['localTables']} 个子表，{coverage['nodes']} 个节点；{coverage['unknownFlowNodes']} 处控制流边界"
        cards.append(
            f'<article data-search="{name} {enemy_id}"><h2>{name}</h2><p>{enemy_id}</p><p>{status}</p><a href="{record["html"]}">打开怪物行动逻辑页面</a></article>'
        )
    data = json.dumps(
        dict(schemaVersion=1, releaseReady=release_ready, monsters=records),
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>荒野怪物行动逻辑</title><link rel="icon" href="data:,"><style>body{{margin:0;background:#101722;color:#e7edf5;font:16px/1.6 system-ui}}main{{max-width:1200px;margin:auto;padding:32px 24px}}input{{box-sizing:border-box;width:100%;padding:14px;margin:20px 0;font:inherit}}section{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}}article{{background:#182334;padding:20px;border:1px solid #354359;border-radius:10px}}article[hidden]{{display:none}}a{{color:#9fceff}}h2{{margin-top:0}}</style></head><body><main><h1>《怪物猎人：荒野》怪物行动逻辑</h1><p>当前展示 {len(records)} 个怪物行动图；未知处保留在图内。</p><label for="search">按怪物名称或 EM 编号查找</label><input id="search" type="search" autocomplete="off"><p id="count" aria-live="polite"></p><section>{''.join(cards)}</section></main><script id="bundle" type="application/json">{data}</script><script>const input=document.querySelector('#search'),cards=[...document.querySelectorAll('article')];function filter(){{const q=input.value.trim().toLocaleLowerCase();let n=0;for(const c of cards){{c.hidden=!c.dataset.search.toLocaleLowerCase().includes(q);if(!c.hidden)n++;}}document.querySelector('#count').textContent=`显示 ${{n}} / ${{cards.length}} 个对象`;}}input.addEventListener('input',filter);filter();</script></body></html>"""
