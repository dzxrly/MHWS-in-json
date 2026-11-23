import enemyBattleLogic from "./sites/enemy_battle_logic";
import skillDetails from "./sites/skill_details";
import missions from "./sites/missions";
import type { SiteDefinition } from "./site_types";

// Every information site lives under its own route. To add one, create
// sites/<id>/index.ts (title, card text, routes) and list it here; its JSON
// comes from src/site_data and is read from /data/<id>/.
export const sites: SiteDefinition[] = [missions, enemyBattleLogic, skillDetails];
