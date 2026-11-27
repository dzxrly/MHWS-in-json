import type { MissionListTarget } from "./catalog";
import { formatNumber } from "../../composables/numbers";

const stateNames = { NONE: "", NORMAL: "历战", KING: "历战王" };

export const number = (value: number | null | undefined) => value == null ? "—" : formatNumber(value);
export const rate = (value: number | null | undefined) => value == null ? "—" : `×${formatNumber(value)}`;
export const targetName = (target: MissionListTarget) => `${stateNames[target.state]}${target.name}${target.count > 1 ? ` ×${target.count}` : ""}`;
