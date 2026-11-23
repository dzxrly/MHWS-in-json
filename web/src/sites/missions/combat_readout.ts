import type { CombatAction, CombatParty, CombatState, TargetCombat } from "./catalog";
import { rate } from "./format";
import { formatNumber } from "../../composables/numbers";

export const stateLabels = { normal: "常态", angry: "怒态", angrySuper: "狂龙化怒态", tired: "疲劳" } satisfies Record<CombatState, string>;

interface Calculation {
  value: number;
  expression: string;
  caption?: string;
  limit?: string;
}

function product(terms: [string, number][]) {
  return terms.map(([name, value]) => `${name} ${formatNumber(value)}`).join(" × ");
}

// Keep the calculation that produced each endpoint alongside its displayed value.
function metric(label: string, candidates: Calculation[]) {
  const sorted = candidates.sort((a, b) => a.value - b.value);
  const low = sorted[0], high = sorted[sorted.length - 1];
  const endpoints = rate(low.value) === rate(high.value) ? [low] : [low, high];
  return { label, endpoints, display: endpoints.map(line => rate(line.value)).join(" – ") };
}

export function combatReadout(combat: TargetCombat, party: CombatParty, state: CombatState, gradeIndex: number,
  actions: (CombatAction | undefined)[], phase: string) {
  const totals = party.states[state] ?? party.states.normal;
  const factors = combat.factors;
  const current = factors?.states[state] ?? factors?.states.normal;
  const form = ({ NONE: "普通形态", NORMAL: "历战", KING: "历战王" } as const)[factors?.form ?? "NONE"]
    + (factors?.hard ? "（强化档）" : "");
  const condition = `${factors?.upper ? "上位" : "下位"}${stateLabels[state]}`;
  const count = `${party.players} 人修正`;
  const phaseRate = combat.phases?.[phase] ?? 1;
  const motion = metric("行动速度（招式基准）", actions.map(action => {
    const raw = (action?.speed[state] ?? totals.speed) * phaseRate;
    const bounds = combat.speedBounds;
    const value = bounds ? Math.min(bounds[1], Math.max(bounds[0], raw)) : raw;
    const overrideState = state === "angrySuper" ? "angry" : state;
    const override = overrideState === "normal" ? undefined : action?.motionOverrides?.[overrideState];
    const terms: [string, number][] = [];
    if (factors && current) {
      terms.push([form, factors.formSpeed],
        [override == null ? condition : `${stateLabels[overrideState]}（招式覆盖）`, override ?? current.motion],
        ["招式速度", action?.speedRate ?? 1]);
      if (phase) terms.push([phase, phaseRate]);
    }
    return { caption: action?.name ?? "通用招式", value, expression: product(terms),
      limit: raw === value ? undefined : `原值 ${formatNumber(raw)}，取游戏${raw > value ? "上" : "下"}限` };
  }));
  function attack(channel: "physical" | "element") {
    return metric(channel === "physical" ? "怪物造成的物理伤害" : "怪物造成的属性伤害", actions.map(action => {
      const terms: [string, number][] = [];
      if (factors && current) {
        terms.push(["任务攻击", factors.questAttack], [count, party.scaling.attack],
          ["攻击档位", combat.grades[gradeIndex].rate],
          [form, channel === "physical" ? current.formPhysical : current.formElement],
          [state === "angrySuper" ? "怒态攻击" : condition, current.attack]);
        if (channel === "physical" && current.speciesPhysical != null) terms.push(["狂龙化攻击", current.speciesPhysical]);
        terms.push(["招式攻击", action?.attack ?? 1]);
      }
      return { value: totals[channel][gradeIndex] * (action?.attack ?? 1),
        caption: action?.name ?? "通用招式", expression: product(terms) };
    }));
  }
  function incoming(channel: "slash" | "shot") {
    return metric(channel === "slash" ? "斩击／打击对怪物的伤害" : "弹类攻击对怪物的伤害", [{
      value: totals[channel],
      expression: factors && current ? product([
        ["任务受伤", channel === "slash" ? factors.questSlash : factors.questShot],
        [count, party.scaling.damage], [`${stateLabels[state]}受伤`, current.received],
      ]) : "",
    }]);
  }
  const secondary = [
    metric("血量（相对单人）", [{ value: party.hp, expression: product([["单人基准", 1], [count, party.hp]]) }]),
    metric("公共部位耐久", [{ value: party.parts, expression: factors
      ? product([["任务耐久", factors.questParts], [count, party.scaling.parts], [form, factors.formParts]]) : "" }]),
    incoming("slash"), incoming("shot"),
  ];
  if (combat.sizes?.some(size => size !== 100)) {
    secondary.push(metric("导航移动时的体型修正", combat.sizes.map(size => ({
      value: 100 / size, expression: `标准体型 100% ÷ 实际体型 ${formatNumber(size)}%`,
    }))));
  }
  return { primary: [motion, attack("physical"), attack("element")], secondary };
}
