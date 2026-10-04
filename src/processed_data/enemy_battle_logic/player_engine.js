/* Evaluate only SDK-declared JSON operations. Missing input stays unknown. */
(function (root) {
  "use strict";
  function compare(value, operator, expected) {
    if (value === undefined || value === null) return null;
    if (typeof value !== "object") {
      if (typeof value !== typeof expected || (typeof value === "number" && !Number.isFinite(value))) return null;
      switch (operator) {
        case "eq": return value === expected;
        case "ne": return value !== expected;
        case "lt": return value < expected;
        case "le": return value <= expected;
        case "gt": return value > expected;
        case "ge": return value >= expected;
        default: return null;
      }
    }
    if (typeof expected !== "number" || !Number.isFinite(value.min) || (value.max !== null && !Number.isFinite(value.max))) return null;
    const low = value.min, high = value.max === null ? Infinity : value.max;
    if (high < low || (high === low && !(value.minClosed && value.maxClosed))) return null;
    const lowAbove = low > expected || (low === expected && !value.minClosed);
    const highBelow = high < expected || (high === expected && !value.maxClosed);
    switch (operator) {
      case "lt": return highBelow ? true : low >= expected ? false : null;
      case "le": return high <= expected ? true : lowAbove ? false : null;
      case "gt": return lowAbove ? true : high <= expected ? false : null;
      case "ge": return low >= expected ? true : highBelow ? false : null;
      case "eq": return low === high && low === expected ? true : lowAbove || highBelow ? false : null;
      case "ne": { const same = compare(value, "eq", expected); return same === null ? null : !same; }
      default: return null;
    }
  }
  function evaluate(expression, inputs) {
    if (!expression) return null;
    if (expression.op === "compare") return compare(inputs[expression.key], expression.operator, expression.value);
    if (expression.op === "not") { const value = evaluate(expression.item, inputs); return value === null ? null : !value; }
    if (expression.op === "all" || expression.op === "any") {
      const values = expression.items.map(item => evaluate(item, inputs));
      if (expression.op === "all") return values.includes(false) ? false : values.includes(null) ? null : true;
      return values.includes(true) ? true : values.includes(null) ? null : false;
    }
    return null;
  }
  function initial(view, entry, values) {
    return { key: entry.id, stack: [], inputs: { ...view.scenario.inputs, ...values }, seen: [], afterAction: false, assumptions: {} };
  }
  function restrict(expression, truth, inputs, fields) {
    const result = { ...inputs };
    if (expression.op === "not") return restrict(expression.item, !truth, inputs, fields);
    if (expression.op === "all" || expression.op === "any") {
      const every = expression.op === "all" ? truth : !truth;
      const candidates = every ? expression.items : expression.items.filter(item => evaluate(item, inputs) === null);
      if (!every && (candidates.length !== 1 || expression.items.some(item => evaluate(item, inputs) === truth))) return result;
      let values = result;
      for (const item of candidates) values = restrict(item, truth, values, fields);
      return values;
    }
    if (expression.op !== "compare") return result;
    const { key, value } = expression;
    const opposites = { lt: "ge", le: "gt", gt: "le", ge: "lt", eq: "ne", ne: "eq" };
    const operator = truth ? expression.operator : opposites[expression.operator];
    if (operator === "eq") { result[key] = value; return result; }
    if (typeof value === "boolean" && operator === "ne") { result[key] = !value; return result; }
    const field = fields[key], bounds = field?.numericRange || (field?.number ? field : null);
    const current = result[key] ?? (bounds ? { min: bounds.min, max: bounds.max, minClosed: true, maxClosed: true } : null);
    if (typeof value !== "number" || !current || typeof current !== "object") return result;
    const domain = { ...current };
    if (["lt", "le"].includes(operator) && (domain.max === null || value <= domain.max)) {
      domain.maxClosed = operator === "le" && (domain.max === null || value < domain.max || domain.maxClosed);
      domain.max = value;
    }
    if (["gt", "ge"].includes(operator) && value >= domain.min) {
      domain.minClosed = operator === "ge" && (value > domain.min || domain.minClosed);
      domain.min = value;
    }
    result[key] = domain; return result;
  }
  function step(view, supplied) {
    let state = { ...supplied, stack: supplied.stack.slice(), seen: supplied.seen.slice(), assumptions: { ...supplied.assumptions } };
    const via = [];
    const next = (key, extras = {}) => ({ ...state, key, ...extras });
    for (let count = 0; count < 128; count++) {
      const node = view.nodes[state.key];
      if (!node) return { title: "此处的连接尚未恢复", kind: "unknown", children: [], sourceRef: state.key };
      const signature = JSON.stringify([state.key, state.stack, state.afterAction, state.inputs]);
      if (state.seen.includes(signature)) return { title: "回到此前判断，形成循环", kind: "loop", sourceRef: node.sourceRef, children: [] };
      state.seen.push(signature);
      if (node.kind === "call") {
        via.push({ sourceRef: node.sourceRef, kind: "call" });
        state = next(node.target, { stack: [...state.stack, { key: node.resume, resultKey: node.resultKey }] });
        continue;
      }
      if (node.kind === "return" && state.stack.length) {
        via.push({ sourceRef: node.sourceRef, kind: "return" });
        const stack = state.stack.slice(), position = stack.pop();
        state = next(position.key, { stack });
        continue;
      }
      if (node.kind === "mutation" && node.next && !node.dispatch) {
        via.push({ sourceRef: node.sourceRef, kind: "mutation", title: node.title, invalidateSnapshot: node.invalidateSnapshot });
        const stable = Object.fromEntries(Object.entries(state.assumptions).filter(([token]) => JSON.parse(token)[1] === null));
        state = next(node.next, node.invalidateSnapshot ? { inputs: {}, assumptions: {}, afterAction: true } : { assumptions: stable });
        continue;
      }
      const record = { ...node, key: state.key, afterAction: state.afterAction, via, children: [] };
      if (node.kind === "condition") {
        const truth = evaluate(node.condition, state.inputs);
        record.truth = truth;
        // Repeated tests of the same expression in one snapshot must agree.
        const hasUnknown = expression => expression.op === "unknown" || (expression.items || []).some(hasUnknown) || (expression.item && hasUnknown(expression.item));
        const token = JSON.stringify([node.condition, hasUnknown(node.condition) ? [node.sourceRef, state.stack] : null]);
        for (const [branch, value] of [["true", true], ["false", false]]) {
          if (truth !== null && truth !== value) continue;
          if (state.assumptions[token] !== undefined && state.assumptions[token] !== value) continue;
          let label = node.presentation ? node.presentation[value ? "trueLabel" : "falseLabel"] : value ? "满足" : "不满足";
          if (!value && state.afterAction && node.presentation?.snapshotGuard) label += "，或选招状态已变化";
          const inputs = restrict(node.condition, value, state.inputs, view.inputs || {});
          if (Object.entries(state.assumptions).some(([previous, expected]) => {
            const actual = evaluate(JSON.parse(previous)[0], inputs);
            return actual !== null && actual !== expected;
          })) continue;
          record.children.push({ label, role: branch, state: next(node[branch], { inputs, assumptions: { ...state.assumptions, [token]: value } }) });
        }
      } else if (node.kind === "weighted_random") {
        record.children = node.candidates.map(candidate => ({ label: `候选权重 ${candidate.weight}${candidate.filteringUnknown ? " · 能否入选待确认" : ""}`, slot: candidate.id, state: next(candidate.target) }));
        if (node.fallback && node.candidates.some(c => c.filteringUnknown)) record.children.push({ label: "候选全部被排除时", state: next(node.fallback) });
        if (!node.candidates.length && node.fallback) record.children.push({ label: "没有候选，进入回退流程", state: next(node.fallback) });
      } else if (node.kind === "action") {
        record.children.push({ label: "动作请求后恢复执行，条件重新判断", role: "resume", state: next(node.resume, { inputs: {}, assumptions: {}, afterAction: true }) });
      } else if (node.kind === "mutation" || node.kind === "unknown") {
        const extras = node.invalidateSnapshot ? { inputs: {}, assumptions: {}, afterAction: true } : {};
        if (node.next) record.children.push({ label: node.invalidateSnapshot ? "继续流程，相关状态待确认" : "随后", state: next(node.next, extras) });
        if (node.resume) record.children.push({ label: "动作身份待核查；恢复后按保存位置继续", role: "resume", state: next(node.resume, { inputs: {}, assumptions: {}, afterAction: true }) });
        if (node.dispatch) record.children.push({ label: "等待调度后，可能切换至此流程", state: next(node.dispatch, { inputs: {}, assumptions: {}, afterAction: true, stack: [] }) });
      }
      return record;
    }
    return { title: "此段调用或循环过深，需核查继续位置", kind: "unknown", sourceRef: state.key, children: [] };
  }
  root.BattlePlayer = Object.freeze({ compare, evaluate, initial, step });
})(typeof window === "undefined" ? globalThis : window);
