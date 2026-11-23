export interface Effect {
  name: string;
  key: string;
  code: string;
  written: boolean;
  meaning: Record<string, string>;
  rows: {
    applies: string;
    situation: string;
    values: Record<string, { text: string; unsure: boolean }>;
  }[];
}

export interface Skill {
  id: string;
  name: string;
  category: string;
  ja: string;
  explain: string;
  openSkills: string;
  notes: string[];
  levels: { level: number; explain: string }[];
  levelColumns: number[];
  effects: Effect[];
  mappedSkill?: { id: string; name: string };
  resourceOpenSkills?: { id: string; name: string; level: number }[];
}
