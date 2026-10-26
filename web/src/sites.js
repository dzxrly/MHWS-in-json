import enemyBattleLogic from "./sites/enemy_battle_logic/index.js";
import skillDetails from "./sites/skill_details/index.js";

// Every information site lives under its own route. To add one, create
// sites/<id>/index.js (title, card text, routes) and list it here; its JSON
// comes from src/site_data and is read from /data/<id>/.
export const sites = [enemyBattleLogic, skillDetails];
