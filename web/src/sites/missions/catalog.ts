import { shallowRef } from "vue";
import { loadJson } from "../../composables/data";

interface StateRates {
  speed: number;
  physical: number[];
  element: number[];
  slash: number;
  shot: number;
}

export interface CombatParty {
  players: number;
  hp: number;
  health: { hp: number; probability: number }[];
  parts: number;
  scaling: { attack: number; parts: number; damage: number };
  states: { normal: StateRates; angry?: StateRates; angrySuper?: StateRates; tired?: StateRates };
}

export type CombatState = keyof CombatParty["states"];
interface AttackGrade {
  grade: number;
  probability: number;
  rate: number;
}
export interface CombatAction {
  name: string;
  speed: Partial<Record<CombatState, number>>;
  attack: number;
  speedRate: number;
  motionOverrides: Partial<Record<"angry" | "tired", number>>;
}
interface StateFactors {
  motion: number;
  attack: number;
  formPhysical: number;
  formElement: number;
  speciesPhysical?: number;
  received: number;
}
export interface TargetCombat {
  factors?: {
    form: "NONE" | "NORMAL" | "KING";
    hard: boolean;
    upper: boolean;
    rewardRank: number;
    formSpeed: number;
    formParts: number;
    questAttack: number;
    questParts: number;
    questSlash: number;
    questShot: number;
    states: Partial<Record<CombatState, StateFactors>>;
  };
  speedBounds?: [number, number];
  actions?: CombatAction[];
  phases?: Record<string, number>;
  sizes?: [number, number];
  shells?: { id: number; name: string; attack: number; ignoreAction: boolean; sources?: { name: string; attack: number }[] }[];
  damageConditions?: { name: string; physical: number; element: number }[];
  incomingConditions?: { name: string; slash: number; shot: number }[];
  grades: [AttackGrade, ...AttackGrade[]];
  parties: [CombatParty, ...CombatParty[]];
}

export interface MissionTarget {
  id: string | null;
  name: string;
  icon: number | null;
  state: "NONE" | "NORMAL" | "KING";
  count: number;
  objective: string;
  spawn: string;
  combat: TargetCombat | null;
}

interface RewardItem {
  name: string;
  quantity: number;
}
export interface MissionReward extends RewardItem {
  group: string;
  probability: number;
}
interface RankReward {
  rank: "A" | "B" | "C";
  money: number;
  points: number;
  hrPoints: number;
  items: RewardItem[];
}
export interface Mission {
  id: string;
  name: string;
  client: string;
  description: string;
  category: string;
  type: string;
  rank: "上位" | "下位";
  stars: number;
  hr: number;
  maxPlayers: number;
  timeLimit: number;
  faints: number;
  money: number;
  points: number;
  hrPoints: number;
  stage: string;
  prerequisite: string;
  targets: MissionTarget[];
  rewards: MissionReward[];
  rewardSlots: { count: number; probability: number }[];
  rankRewards: RankReward[];
}
interface MissionCatalog {
  categories: string[];
  quests: Mission[];
}

export const catalog = shallowRef<MissionCatalog | null>(null);
export const catalogError = shallowRef<Error | null>(null);

loadJson<MissionCatalog>("missions/quests.json").then(
  (data) => { catalog.value = data; },
  (error: unknown) => { catalogError.value = error instanceof Error ? error : new Error(String(error)); },
);
