"""One offline HTML index linking every generated monster HTML."""

from html import escape
import json

STYLE = """
:root {
  --font: "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", system-ui, sans-serif;
  --mono: ui-monospace, "Cascadia Mono", Consolas, monospace;
  --bg: #f3f2ee; --surface: #ffffff; --surface-2: #f8f7f4; --ink: #1e2227; --muted: #60666e;
  --faint: #8b9098; --line: #e1dfd9; --line-strong: #c9c6be; --accent: #9d4a1f; --accent-soft: #f5e6dc;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #15171a; --surface: #1d2024; --surface-2: #23272c; --ink: #e5e7ea; --muted: #a3a9b1;
    --faint: #7d838b; --line: #2f343a; --line-strong: #444a52; --accent: #d9824f; --accent-soft: #3a2a20;
    color-scheme: dark;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.6 var(--font); }
.wrap { max-width: 1120px; margin: 0 auto; padding: 0 24px; }
header.wrap { padding-top: 56px; padding-bottom: 28px; }
.eyebrow { margin: 0; color: var(--faint); font-size: 13px; }
h1 { margin: 6px 0 10px; font-size: 34px; font-weight: 700; letter-spacing: .5px; }
.lede { margin: 0; max-width: 40em; color: var(--muted); }
.controls { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 14px; padding: 14px 0; background: var(--bg); }
input {
  flex: 0 1 340px; height: 38px; padding: 0 14px; font: inherit; color: inherit;
  background: var(--surface); border: 1px solid var(--line-strong); border-radius: 8px;
}
input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
#count { color: var(--faint); font-size: 13px; white-space: nowrap; }
.grid { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); }
.grid li[hidden] { display: none; }
a.card {
  display: flex; flex-direction: column; gap: 2px; height: 100%; padding: 16px 18px 14px;
  color: inherit; text-decoration: none; background: var(--surface);
  border: 1px solid var(--line); border-radius: 10px; transition: border-color .15s, transform .15s;
}
a.card:hover { border-color: var(--accent); transform: translateY(-1px); }
a.card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.id { font: 12px var(--mono); color: var(--faint); }
.name { font-size: 19px; font-weight: 650; line-height: 1.35; }
.stats { margin-top: auto; padding-top: 10px; display: flex; gap: 14px; font-size: 12.5px; color: var(--muted); }
.stats b { color: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }
.empty { padding: 40px 0; color: var(--muted); }
section.notes { margin: 48px 0 0; padding: 22px 0 0; border-top: 1px solid var(--line); }
h2 { font-size: 16px; margin: 0 0 8px; }
.notes ul { margin: 0; padding-left: 20px; color: var(--muted); font-size: 14px; }
.notes li + li { margin-top: 4px; }
footer.wrap { padding-top: 28px; padding-bottom: 40px; color: var(--faint); font-size: 12.5px; }
@media (max-width: 560px) {
  header.wrap { padding-top: 32px; }
  h1 { font-size: 27px; }
  .wrap { padding: 0 16px; }
  .grid { grid-template-columns: 1fr 1fr; gap: 8px; }
  a.card { padding: 12px 14px; }
  .name { font-size: 16px; }
  .stats { flex-direction: column; gap: 0; }
}
"""

SCRIPT = """
const input = document.querySelector("#search"), cards = [...document.querySelectorAll(".grid > li")];
const count = document.querySelector("#count"), empty = document.querySelector(".empty");
function filter() {
  const query = input.value.trim().toLocaleLowerCase();
  let shown = 0;
  for (const card of cards) {
    card.hidden = !card.dataset.search.toLocaleLowerCase().includes(query);
    if (!card.hidden) shown++;
  }
  count.textContent = query ? `${shown} / ${cards.length}` : `共 ${cards.length} 只`;
  empty.hidden = shown > 0;
}
input.addEventListener("input", filter);
filter();
"""


def render_card(record):
    name, enemy_id = escape(record["enemyName"]), escape(record["enemyId"])
    stats = ""
    if record.get("behaviorTables"):
        stats = (
            f'<span class="stats"><span><b>{record["behaviorTables"]}</b> 张行为表</span>'
            f'<span><b>{record["actions"]}</b> 个动作</span></span>'
        )
    return (
        f'<li data-search="{name} {enemy_id}"><a class="card" href="{escape(record["html"])}">'
        f'<span class="id">{enemy_id}</span><span class="name">{name}</span>{stats}</a></li>'
    )


def render_index(records, *, release_ready=False):
    versions = sorted({record["profile"]["gameVersion"] for record in records})
    data = json.dumps(
        dict(schemaVersion=1, releaseReady=release_ready, monsters=records),
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>荒野怪物行动逻辑</title><link rel="icon" href="data:,"><style>{STYLE}</style></head><body>
<header class="wrap"><p class="eyebrow">怪物猎人：荒野 · 游戏版本 {escape("、".join(versions))}</p><h1>怪物行动逻辑</h1><p class="lede">从游戏数据整理出的怪物出招决策树：在什么距离、角度和状态下，怪物会从哪些招式里选择。</p></header>
<main class="wrap"><div class="controls"><input id="search" type="search" placeholder="搜索名称或编号" aria-label="搜索怪物名称或编号" autocomplete="off"><span id="count" aria-live="polite"></span></div>
<ul class="grid">{''.join(render_card(record) for record in records)}</ul><p class="empty" hidden>没有匹配的怪物。</p>
<section class="notes"><h2>阅读前须知</h2><ul><li>每只怪物一页，从行为表开始，按距离、角度、状态逐层展开到具体动作，可按情境筛选分支。</li><li>距离是游戏内部单位，还没有换算成米；权重只在同一次抽选内比较，不是整场战斗的出招概率。</li><li>请求动作不等于一定出招。还没确认的逻辑标为“待核查”，保留在图中。</li></ul></section></main>
<footer class="wrap">所有页面都是单个 HTML 文件，下载后可离线打开。</footer>
<script id="bundle" type="application/json">{data}</script><script>{SCRIPT}</script></body></html>"""
