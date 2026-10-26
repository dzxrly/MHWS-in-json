<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, shallowRef, watch } from "vue";
import Icon from "../../components/Icon.vue";
import LoadState from "../../components/LoadState.vue";
import { loadJson } from "../../composables/data.js";
import { SITE_TITLE } from "../../router.js";
import { createDecisionTree } from "./decision_tree.js";
import { createTechnicalGraph } from "./technical_graph.js";
import "./graph.css";

const props = defineProps({ enemyId: { type: String, required: true } });

const payload = shallowRef(null);
const error = ref(null);
const mode = ref("tree");
let tree = null;
let flow = null;

// Decision tree view.
const treeViewport = ref();
const treeCanvas = ref();
const treeScene = ref();
const selection = ref();
const treeStatus = ref("");
const selected = ref(false);
const detailsOpen = ref(true);
const query = ref("");
const choices = reactive({});
const openHints = reactive(new Set());

// Flow chart view.
const flowViewport = ref();
const flowSvg = ref();
const flowScene = ref();
const minimap = ref();
const flowStatus = ref("正在排列子表…");
const flowZoom = ref(100);
const flowInfo = ref(null);
const table = ref("");
const entry = ref("");
const direction = ref("DOWN");

const graph = computed(() => payload.value?.graph);
const hasTree = computed(() => !!graph.value?.playerView);
const fields = computed(() =>
  Object.entries(graph.value?.playerView?.inputs ?? {})
    .filter(([, field]) => field.options?.length)
    .map(([key, field]) => ({ key, ...field, extra: field.group === "timer" || field.group === "variable" })),
);
const mainFields = computed(() => fields.value.filter((field) => !field.extra));
const extraFields = computed(() => fields.value.filter((field) => field.extra));
const tables = computed(() => payload.value?.diagram.layout.children ?? []);
const entryPoints = computed(() => {
  const diagram = payload.value?.diagram;
  if (!diagram) return [];
  return diagram.entryPoints.length ? diagram.entryPoints : [{ target: diagram.entry, name: "模型当前入口" }];
});
const scope = computed(() => {
  const coverage = graph.value?.coverage;
  if (!coverage) return "";
  return (
    `共 ${coverage.localTables} 个子表、${coverage.nodes} 个节点，` +
    `其中 ${coverage.completeLocalTables ?? 0} 个子表的流程已核实；` +
    `${coverage.unknownFlowNodes ?? 0} 处后继、${coverage.unknownConditions ?? 0} 处条件待核查。`
  );
});

function teardown() {
  flow?.destroy();
  tree = flow = null;
}

watch(
  () => props.enemyId,
  async (enemyId) => {
    teardown();
    payload.value = null;
    error.value = null;
    selected.value = false;
    flowInfo.value = null;
    for (const key of Object.keys(choices)) delete choices[key];
    try {
      const data = await loadJson(`enemy_battle_logic/${enemyId}.json`);
      if (enemyId !== props.enemyId) return;
      payload.value = data;
      document.title = `${data.graph.enemyName || enemyId} · 行动逻辑 · ${SITE_TITLE}`;
      mode.value = data.graph.playerView ? "tree" : "flow";
      await nextTick();
      if (mode.value === "tree") startTree();
      else startFlow();
    } catch (failure) {
      error.value = failure;
    }
  },
  { immediate: true },
);
onBeforeUnmount(teardown);

function startTree() {
  tree = createDecisionTree({
    graph: graph.value,
    viewport: treeViewport.value,
    canvas: treeCanvas.value,
    scene: treeScene.value,
    selection: selection.value,
    onStatus: (text) => (treeStatus.value = text),
    onSelect: () => {
      selected.value = true;
      detailsOpen.value = true;
    },
  });
}
function startFlow() {
  flow = createTechnicalGraph({
    graph: graph.value,
    diagram: payload.value.diagram,
    viewport: flowViewport.value,
    svg: flowSvg.value,
    scene: flowScene.value,
    mini: minimap.value,
    onStatus: (text) => (flowStatus.value = text),
    onZoom: (percent) => (flowZoom.value = percent),
    onInspect: (info) => {
      flowInfo.value = info;
      table.value = info.tableGuid;
    },
  });
  entry.value = entryPoints.value[0]?.target ?? "";
}
async function showMode(next) {
  mode.value = next;
  await nextTick();
  if (next === "flow" && !flow) startFlow();
}
function choose(field, value) {
  choices[field.key] = value;
  tree.setInput(field.key, value === "" ? null : Number(value));
}
function toggleHint(key) {
  if (openHints.has(key)) openHints.delete(key);
  else openHints.add(key);
}
</script>

<template>
  <LoadState v-if="!payload" :error="error" label="正在加载怪物数据，较大的怪物约 15 MB…" />
  <div v-else class="monster">
    <div class="monster-bar">
      <RouterLink class="icon-button small" to="/enemy_battle_logic/" aria-label="返回全部怪物"><Icon name="back" /></RouterLink>
      <div class="monster-title">
        <h1>{{ graph.enemyName || enemyId }}</h1>
        <span class="mono">{{ enemyId }}</span>
      </div>
      <div v-if="hasTree" class="segmented" role="tablist" aria-label="视图">
        <button type="button" role="tab" :aria-selected="mode === 'tree'" @click="showMode('tree')">
          <Icon name="tree" />决策树
        </button>
        <button type="button" role="tab" :aria-selected="mode === 'flow'" @click="showMode('flow')">
          <Icon name="flow" />原始流程图
        </button>
      </div>
    </div>

    <section v-if="hasTree" v-show="mode === 'tree'" class="workspace-card surface">
      <div class="bar">
        <form class="bar-group search" role="search" @submit.prevent="tree.search(query)">
          <label class="search-field small">
            <Icon name="search" />
            <input v-model="query" type="search" placeholder="搜索动作或条件" aria-label="搜索动作或条件" />
          </label>
          <button class="tonal-button" type="submit">查找</button>
        </form>
        <div class="button-group">
          <button class="tonal-button" type="button" title="展开一层" @click="tree.expandLevel()"><Icon name="unfold" /><span class="label">展开一层</span></button>
          <button class="tonal-button" type="button" title="全部收起" @click="tree.collapseAll()"><Icon name="fold" /><span class="label">全部收起</span></button>
        </div>
        <div class="bar-group">
          <button class="icon-button small standard" type="button" title="适应窗口" aria-label="适应窗口" @click="tree.fit()"><Icon name="fit" /></button>
          <button class="icon-button small standard" type="button" title="缩小" aria-label="缩小" @click="tree.zoom(1 / 1.2)"><Icon name="minus" /></button>
          <button class="icon-button small standard" type="button" title="放大" aria-label="放大" @click="tree.zoom(1.2)"><Icon name="plus" /></button>
        </div>
        <output class="bar-status" role="status">{{ treeStatus }}</output>
        <div class="bar-group end">
          <button class="tonal-button" type="button" title="详情" :aria-pressed="detailsOpen" @click="detailsOpen = !detailsOpen"><Icon name="panel" /><span class="label">详情</span></button>
          <button class="outlined-button" type="button" title="导出 SVG" @click="tree.exportSvg()"><Icon name="download" /><span class="label">导出 SVG</span></button>
        </div>
      </div>
      <details v-if="fields.length" class="scenario">
        <summary><Icon name="tune" />按情境筛选<span class="hint">选定后只保留符合条件的分支；“任意”表示不限</span></summary>
        <div class="inputs">
          <div v-for="field in mainFields" :key="field.key" class="input-field">
            <div class="input-head">
              <label :for="`input-${field.key}`">{{ field.label || field.key }}</label>
              <button
                v-if="field.hint"
                class="input-help"
                type="button"
                aria-label="说明"
                :title="field.hint"
                :aria-expanded="openHints.has(field.key)"
                @click="toggleHint(field.key)"
              >?</button>
            </div>
            <select :id="`input-${field.key}`" class="select-field" :value="choices[field.key] ?? ''" @change="choose(field, $event.target.value)">
              <option value="">任意</option>
              <option v-for="(option, index) in field.options" :key="index" :value="String(index)">{{ option.label ?? String(option.value) }}</option>
            </select>
            <p v-if="field.hint && openHints.has(field.key)" class="input-hint">{{ field.hint }}</p>
          </div>
        </div>
        <details v-if="extraFields.length" class="inputs-extra">
          <summary>计时器与行为表变量</summary>
          <div class="inputs">
            <div v-for="field in extraFields" :key="field.key" class="input-field">
              <div class="input-head">
                <label :for="`input-${field.key}`">{{ field.label || field.key }}</label>
                <button
                  v-if="field.hint"
                  class="input-help"
                  type="button"
                  aria-label="说明"
                  :title="field.hint"
                  :aria-expanded="openHints.has(field.key)"
                  @click="toggleHint(field.key)"
                >?</button>
              </div>
              <select :id="`input-${field.key}`" class="select-field" :value="choices[field.key] ?? ''" @change="choose(field, $event.target.value)">
                <option value="">任意</option>
                <option v-for="(option, index) in field.options" :key="index" :value="String(index)">{{ option.label ?? String(option.value) }}</option>
              </select>
              <p v-if="field.hint && openHints.has(field.key)" class="input-hint">{{ field.hint }}</p>
            </div>
          </div>
        </details>
      </details>
      <div class="graph-body" :class="{ 'no-details': !detailsOpen }">
        <div ref="treeViewport" class="canvas" tabindex="0" aria-label="怪物行动决策树，可拖动和缩放">
          <svg ref="treeCanvas" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="怪物行动决策树"><g ref="treeScene" /></svg>
          <div class="legend">
            <span class="k-condition">条件</span><span class="k-weighted_random">抽选</span><span class="k-action">动作</span
            ><span class="k-mutation">状态变化</span><span class="k-unknown">待核查</span><span class="k-ref">别处已展开</span>
          </div>
        </div>
        <aside class="side">
          <div v-if="!selected" class="selection">
            <h3>点击节点查看详情</h3>
            <p class="note">点圆钮或双击节点展开、收起分支。</p>
          </div>
          <div ref="selection" class="selection" />
          <details class="help" open>
            <summary>怎么读这棵树</summary>
            <ul>
              <li>从怪物出发，先按行为表分组，再按距离、角度、状态逐层分支，末端是动作。</li>
              <li>距离是游戏内部单位，还没有换算成米。</li>
              <li>权重只在同一次抽选的候选之间比较，不是整场战斗的出招概率。</li>
              <li>请求动作不等于一定出招，还要看当时的游戏状态。</li>
              <li>虚线框表示同一判断已在别处展开；“待核查”是还没确认的逻辑。</li>
            </ul>
          </details>
        </aside>
      </div>
    </section>

    <section v-show="mode === 'flow'" class="workspace-card surface">
      <div class="bar">
        <div class="bar-group">
          <button class="tonal-button" type="button" title="适应窗口" @click="flow?.fit()"><Icon name="fit" /><span class="label">适应窗口</span></button>
          <button class="tonal-button" type="button" title="回到入口" @click="flow?.focusEntry()"><Icon name="target" /><span class="label">回到入口</span></button>
        </div>
        <div class="bar-group">
          <button class="icon-button small standard" type="button" title="缩小" aria-label="缩小" @click="flow?.zoom(1 / 1.3)"><Icon name="minus" /></button>
          <button class="icon-button small standard" type="button" title="放大" aria-label="放大" @click="flow?.zoom(1.3)"><Icon name="plus" /></button>
          <output class="bar-status">{{ flowZoom }}%</output>
        </div>
        <label class="bar-field">入口
          <select v-model="entry" class="select-field" @change="flow?.focus(entry)">
            <option v-for="point in entryPoints" :key="point.target" :value="point.target">{{ point.name || point.kind }}</option>
          </select>
        </label>
        <label class="bar-field">子表
          <select v-model="table" class="select-field" @change="flow?.showTable(table)">
            <option v-for="group in tables" :key="group.id" :value="group.id">{{ group.title }}</option>
          </select>
        </label>
        <label class="bar-field">方向
          <select v-model="direction" class="select-field" @change="flow?.setDirection(direction)">
            <option value="DOWN">从上到下</option>
            <option value="RIGHT">从左到右</option>
          </select>
        </label>
        <div class="bar-group end">
          <button class="outlined-button" type="button" title="导出 SVG" @click="flow?.download()"><Icon name="download" /><span class="label">导出 SVG</span></button>
        </div>
      </div>
      <div class="graph-body">
        <div ref="flowViewport" class="canvas dotted" tabindex="0" aria-label="怪物行动逻辑原始流程图，可拖动和缩放">
          <svg ref="flowSvg" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="全部已恢复子表的流程图">
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
                <path d="M0,0 L10,5 L0,10 z" fill="context-stroke" />
              </marker>
            </defs>
            <g ref="flowScene" class="scene" />
          </svg>
          <div v-if="flowStatus" class="canvas-status" role="status">{{ flowStatus }}</div>
          <svg ref="minimap" class="minimap" aria-label="全图缩略图" xmlns="http://www.w3.org/2000/svg" />
          <div class="legend tech">
            <span class="role-true">成立</span><span class="role-false">不成立</span><span class="role-random">权重选择</span
            ><span class="role-call">调用</span><span class="role-resume">恢复位置</span><span class="kind-unknown">未核实</span>
          </div>
        </div>
        <aside class="side">
          <div class="selection">
            <small class="kicker">{{ flowInfo?.kicker ?? "节点详情" }}</small>
            <h3>{{ flowInfo?.title ?? "选择一个节点" }}</h3>
            <p class="note">{{ flowInfo?.summary ?? "这里按游戏行为表的原始结构画出全部子表，适合对照数据核查。" }}</p>
            <button v-if="flowInfo?.call" class="tonal-button" type="button" @click="flow.followCall(flowInfo.call.target)">
              {{ flowInfo.call.label }}
            </button>
            <details v-if="flowInfo">
              <summary>原始参数与证据</summary>
              <pre>{{ flowInfo.detail }}</pre>
            </details>
          </div>
          <details class="help" open>
            <summary>说明</summary>
            <ul>
              <li>{{ scope }}</li>
              <li>蓝线是跨表调用，虚线是调用结束后的恢复位置，不是直接跳转。</li>
              <li>权重只在当前抽选内有效；距离是游戏内部单位，目标不一定是玩家。</li>
            </ul>
          </details>
        </aside>
      </div>
    </section>

    <section class="about surface">
      <details v-if="graph.actionNameCatalog">
        <summary>动作名称对照表</summary>
        <p>{{ graph.actionNameCatalog.boundary }}</p>
        <div class="table-scroll">
          <table>
            <thead>
              <tr><th>Shell UID</th><th>原名</th><th>原注释</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in graph.actionNameCatalog.shellCatalog" :key="row.uniqueId">
                <td class="mono">{{ row.uniqueId }}</td><td>{{ row.name }}</td><td>{{ row.comment }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
      <p>
        原始流程图由
        <a href="https://github.com/kieler/elkjs" target="_blank" rel="noopener noreferrer">elkjs 0.11.1</a>
        自动布局（<a href="https://www.eclipse.org/legal/epl-2.0/" target="_blank" rel="noopener noreferrer">EPL-2.0</a>）。
      </p>
    </section>
  </div>
</template>
