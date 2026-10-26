"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
const byId = new Map(DATA.skills.map((s) => [s.id, s]));
const state = { query: "", category: "", showEmpty: false };
const $ = (selector) => document.querySelector(selector);

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === false || value == null) continue;
    if (key === "class") node.className = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// Everything a search can match: names, descriptions, effects, weapons and situations.
for (const skill of DATA.skills) {
  skill.search = [
    skill.name, skill.ja, skill.id, skill.explain, skill.category,
    ...skill.levels.map((l) => l.explain),
    ...skill.effects.flatMap((e) => [
      e.name, e.code, ...Object.values(e.meaning),
      ...e.rows.flatMap((r) => [r.applies, r.situation]),
    ]),
  ].join("\n").toLocaleLowerCase();
}

function visible(skill) {
  if (!state.showEmpty && !skill.effects.length) return false;
  if (state.category && skill.category !== state.category) return false;
  return !state.query || skill.search.includes(state.query);
}

function renderCategories() {
  const box = $("#categories");
  for (const name of ["", ...DATA.categories]) {
    const button = el("button", { type: "button", "aria-pressed": String(name === state.category) }, name || "全部");
    button.addEventListener("click", () => {
      state.category = name;
      for (const b of box.children) b.setAttribute("aria-pressed", String(b === button));
      renderList();
    });
    box.append(button);
  }
}

function renderList() {
  const list = $("#list");
  list.replaceChildren();
  let shown = 0;
  for (const category of DATA.categories) {
    const skills = DATA.skills.filter((s) => s.category === category && visible(s));
    if (!skills.length) continue;
    shown += skills.length;
    list.append(el("h2", null, `${category} · ${skills.length}`));
    for (const skill of skills) {
      list.append(el("a", {
        href: `#${skill.id}`,
        class: skill.effects.length ? null : "empty",
        "aria-current": String(skill.id === currentId()),
        "data-id": skill.id,
      },
      el("span", { class: "name" }, skill.name),
      el("span", { class: "n" }, skill.effects.length ? `${skill.effects.length} 项` : "无数值")));
    }
  }
  if (!shown) list.append(el("p", { class: "none" }, "没有匹配的技能。"));
  const total = DATA.skills.filter((s) => state.showEmpty || s.effects.length).length;
  $("#count").textContent = shown === total ? `共 ${total} 个技能` : `${shown} / ${total} 个技能`;
}

function currentId() {
  const id = decodeURIComponent(location.hash.slice(1));
  if (byId.has(id)) return id;
  return (DATA.skills.find((s) => s.effects.length) || DATA.skills[0]).id;
}

const MEANING_FIELDS = ["作用于", "计算", "条件"];

function renderEffect(effect, levels) {
  const unit = effect.meaning["单位"];
  const head = el("div", { class: "effect-head" },
    el("h3", null, effect.name),
    unit && el("span", { class: "badge unit" }, unit),
    effect.written && el("span", { class: "badge", title: "技能发动等处理写入运行时字段的数值" }, "写入值"));
  const meaning = MEANING_FIELDS.filter((f) => effect.meaning[f]);
  const dl = meaning.length
    ? el("dl", { class: "meaning" }, meaning.flatMap((f) => [el("dt", null, f), el("dd", null, effect.meaning[f])]))
    : null;
  const plain = effect.rows.length === 1 && !effect.rows[0].applies && !effect.rows[0].situation;
  const header = el("tr", null,
    el("th", { class: "case", scope: "col" }, plain ? "适用" : "适用 / 情形"),
    levels.map((lv) => el("th", { scope: "col", "data-lv": lv, title: "点击高亮此等级" }, `Lv.${lv}`)));
  const body = effect.rows.map((row) => {
    let previous = null;
    const cells = levels.map((lv) => {
      const value = row.values[lv];
      if (!value) return el("td", { class: "v missing", "data-lv": lv }, "—");
      const kind = value.unsure ? "unsure" : previous === null ? "first" : value.text !== previous ? "changed" : "";
      previous = value.text;
      return el("td", {
        class: `v ${kind}`,
        "data-lv": lv,
        title: value.unsure ? "代码中找不到区分这几种取值的条件" : null,
      }, value.text);
    });
    return el("tr", null,
      el("td", { class: "case" },
        el("span", { class: "applies" }, row.applies || (row.situation ? "" : "全部")),
        row.situation && el("span", { class: "situation" }, row.situation)),
      cells);
  });
  const table = el("table", { class: "values" }, el("thead", null, header), el("tbody", null, body));
  table.addEventListener("click", (event) => {
    const th = event.target.closest("th[data-lv]");
    if (!th) return;
    const on = !th.classList.contains("hl");
    for (const cell of table.querySelectorAll("[data-lv]")) {
      cell.classList.toggle("hl", on && cell.dataset.lv === th.dataset.lv);
    }
  });
  const basis = [
    ["代码名称", effect.code],
    ["含义依据", effect.meaning["依据"]],
    ["条目键", effect.key],
  ].filter(([, v]) => v);
  return el("section", { class: "effect" },
    head, dl,
    el("div", { class: "table-wrap" }, table),
    el("details", { class: "basis" },
      el("summary", null, "依据"),
      el("dl", null, basis.flatMap(([k, v]) => [el("dt", null, k), el("dd", null, v)]))));
}

function renderDetail() {
  const skill = byId.get(currentId());
  const detail = $("#detail");
  document.title = `${skill.name} · 荒野技能效果数值`;
  const head = el("div", { class: "skill-head" },
    el("p", { class: "kicker" }, `${skill.category} · ${skill.id}`),
    el("h2", null, skill.name, skill.ja && el("span", { class: "ja" }, skill.ja)),
    skill.explain && el("p", { class: "explain" }, skill.explain),
    skill.openSkills && el("p", { class: "aside-note" }, `打开技能：${skill.openSkills}`),
    skill.notes.map((note) => el("p", { class: "aside-note" }, note)));
  const levels = skill.levels.some((l) => l.explain)
    ? el("ul", { class: "levels" }, skill.levels.map((l) =>
      el("li", null, el("b", null, `Lv.${l.level}`), el("span", null, l.explain))))
    : null;
  const effects = skill.effects.length
    ? el("div", { class: "effects" }, skill.effects.map((e) => renderEffect(e, skill.levelColumns)))
    : el("p", { class: "no-values" }, "未提取到数值：这个技能只有发动条件，或没有从游戏参数读取到效果数值。");
  detail.replaceChildren(head, levels || "", effects);
  for (const a of document.querySelectorAll("#list a")) {
    a.setAttribute("aria-current", String(a.dataset.id === skill.id));
  }
  revealCurrent();
}

function revealCurrent() {
  const list = $("#list"), current = list.querySelector('a[aria-current="true"]');
  if (!current) return;
  const top = current.offsetTop, bottom = top + current.offsetHeight;
  if (top < list.scrollTop + 30 || bottom > list.scrollTop + list.clientHeight) {
    list.scrollTop = top - list.clientHeight / 2;
  }
}

function init() {
  renderCategories();
  $("#reading-notes").replaceChildren(...DATA.notes.map((n) => el("li", null, n)));
  $("#general-notes").replaceChildren(...DATA.generalNotes.map((n) => el("li", null, n)));
  $("#search").addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLocaleLowerCase();
    renderList();
  });
  $("#show-empty").addEventListener("change", (event) => {
    state.showEmpty = event.target.checked;
    renderList();
  });
  window.addEventListener("hashchange", () => {
    renderDetail();
    $("#detail").focus({ preventScroll: true });
    // On narrow screens the list sits above the detail.
    if (matchMedia("(max-width: 820px)").matches) $("#detail").scrollIntoView();
    else window.scrollTo({ top: 0 });
  });
  if (!byId.get(currentId()).effects.length) state.showEmpty = $("#show-empty").checked = true;
  renderList();
  renderDetail();
}

init();
