import type { ElkExtendedEdge, ElkNode } from "elkjs/lib/elk.bundled.js";

export type Scalar = string | number | boolean;
export interface NumericRange {
  min: number;
  max: number | null;
}
export interface Interval extends NumericRange {
  minClosed: boolean;
  maxClosed: boolean;
}
export type InputValue = Scalar | Interval;
export type Inputs = Record<string, InputValue | null | undefined>;
export type Comparison = "eq" | "ne" | "lt" | "le" | "gt" | "ge";

export type Condition =
  | { op: "compare"; key: string; operator: Comparison; value: Scalar; otherKey?: string }
  | { op: "all" | "any"; items: Condition[] }
  | { op: "not"; item: Condition }
  | { op: "unknown"; reason: string }
  | { op: "table_history_interval"; drawKey: string; minKey: string; maxKey: string; modulus: number; threshold: number };

export interface InputField {
  label?: string;
  hint?: string;
  group?: string;
  options?: { label?: string; value: InputValue }[];
  numericRange?: NumericRange;
  number?: boolean;
  min?: number;
  max?: number | null;
}

interface Variable {
  variable: string;
  definitionStatus: string;
  readOnly: boolean;
}
type VariableUpdate = Variable & (
  | { kind: "bool"; operation: "assign"; value: boolean }
  | { kind: "float"; operation: "assign" | "add" | "sub"; value: number; min: number; max: number }
  | { kind: "timer"; operation: "activate" | "assign" | "activate_no_reset" | "deactivate"; default?: number; value?: number }
);
export interface NodeUpdates {
  variableUpdate?: VariableUpdate;
  updateGuard?: Condition;
  stateUpdates?: Record<string, InputValue | null>;
  fieldUpdates?: { key: string; sourceKey: string }[];
}

interface Presentation {
  title?: string;
  compact?: boolean;
  category?: string;
  trueLabel?: string;
  falseLabel?: string;
  snapshotGuard?: boolean;
}
interface PlayerNodeBase {
  sourceRef: string;
  title: string;
  presentation?: Presentation;
}
export type PlayerNode = PlayerNodeBase & (
  | { kind: "call"; target: string; resume: string; resultKey?: string }
  | { kind: "return" }
  | { kind: "condition"; condition: Condition; checks?: string; true: string; false: string }
  | { kind: "weighted_random"; candidates: { weight: number; filteringUnknown?: boolean; id: string; target: string }[]; fallback?: string }
  | { kind: "action"; resume: string; technicalName?: string; nameStatus?: string }
  | (NodeUpdates & { kind: "mutation" | "unknown"; invalidateSnapshot?: boolean; next?: string; dispatch?: string; resume?: string; dynamicAction?: boolean; continuationKind?: string })
);

export interface PlayerEntry {
  id: string;
  label: string;
  relation: string;
  group?: string;
  requestedBy?: string[];
  note?: string;
  slot?: string;
}
export interface PlayerView {
  scenario: { inputs: Inputs; persistent?: string[] };
  persistentState?: string[];
  inputs?: Record<string, InputField>;
  entries: PlayerEntry[];
  nodes: Record<string, PlayerNode>;
}

export interface PlayerState {
  key: string;
  stack: { key: string; resultKey?: string }[];
  inputs: Inputs;
  seen: string[];
  afterAction: boolean;
  assumptions: Record<string, boolean>;
}
export interface PlayerBranch {
  label: string;
  role?: "true" | "false" | "resume";
  slot?: string;
  state: PlayerState;
}
export type PlayerVisit =
  | { sourceRef: string; kind: "call" | "return" }
  | { sourceRef: string; kind: "mutation"; title: string; invalidateSnapshot?: boolean }
  | { sourceRef: string; kind: "check"; title: string; truth: boolean };
type Outcome = { kind: "unknown" | "loop"; title: string; sourceRef: string; presentation?: never };
export type PlayerStep = (PlayerNode | Outcome) & {
  key?: string;
  truth?: boolean | null;
  children: PlayerBranch[];
  via?: PlayerVisit[];
  afterAction?: boolean;
};

interface Coverage {
  localTables: number;
  nodes: number;
  completeLocalTables?: number;
  unknownFlowNodes?: number;
  unknownConditions?: number;
}
interface MonsterIdentity {
  enemyId: string;
  enemyName: string;
}
export interface MonsterIndex {
  releaseReady: boolean;
  monsters: (MonsterIdentity & { behaviorTables: number; actions: number })[];
}
export interface BattleTree extends MonsterIdentity {
  entry: string;
  coverage: Coverage;
  playerView?: PlayerView;
  actionNameCatalog?: {
    boundary: string;
    shellCatalog: { uniqueId: number; name: string; comment: string }[];
  };
}
interface TableNode {
  id: string;
  targetTable?: string;
  dispatchTarget?: string;
}
export interface BattleTable {
  tableGuid: string;
  nodes: TableNode[];
  evidence?: unknown;
}
export type BattleGraph = BattleTree & { tables: BattleTable[] };

export interface FlowEdge extends ElkExtendedEdge {
  role: string;
  continuation?: boolean;
}
export interface FlowNode extends ElkNode {
  kind: string;
  title: string;
  subtitle: string;
  localId: string;
  entry?: boolean;
  width: number;
  height: number;
}
export interface FlowGroup extends ElkNode {
  title: string;
  entry: string;
  children: FlowNode[];
}
interface FlowDetail {
  table: string;
  tableGuid: string;
  localId?: string;
  node?: TableNode;
  tableEvidence?: unknown;
}
export interface FlowDiagram {
  layout: Omit<ElkNode, "children" | "edges"> & { children: FlowGroup[]; edges: FlowEdge[] };
  details: Record<string, FlowDetail>;
  entry: string;
  entryPoints: { target: string; kind?: string; name?: string }[];
}
export interface FlowInspection {
  tableGuid: string;
  kicker: string;
  title: string;
  summary: string;
  detail: string;
  call: { label: string; target: string } | null;
}
