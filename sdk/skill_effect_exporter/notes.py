"""Hand-written notes for skills whose effect needs an explicit explanation.

Keys are HunterSkill IDs; each value is a list of Simplified Chinese
statements that are verified against the native code of the version named in
the statement. The extractor copies them into the link JSON unchanged; the
processed table shows them next to the automatically recovered effects.
Only write what the code or the exports show; mark anything else as unverified.
"""

NOTES = {
    "HunterSkill_219": [
        "1.42.0.2：SkillData 中本技能 3 级打开 HunterSkill_093（剥取名人），"
        "但代码 HunterSkillDef.createSkillToGroupSkill 把 HunterSkill_220 映射到本技能，"
        "没有 HunterSkill_093 的映射。原生代码读取的是 HunterSkill_220 一侧。",
    ],
}

# Groups and series: the level stored for the equipped skill is the number of
# equipped pieces; getSkillValue/getSkillLevelCore pick the SkillData row with
# the largest SkillLv not above it. This applies to every GROUP/SERIES skill.
GENERAL = [
    "组合技能与系列技能的等级是装备件数；读取数值时取 SkillLv 不超过件数的最大一行（getSkillValue / getSkillLevelCore，1.42.0.2）。",
    "打开技能（_openSkill）在代码中通过 HunterSkillDef.SkillToGroupSkill 换回组合/系列技能后再读取等级与数值。",
]
