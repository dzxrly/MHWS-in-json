"""Notes that hold for every skill (Simplified Chinese, verified against the
native code of the version named in the statement). Notes on one skill are in
its module, skills/<id>.py NOTES. The extractor copies both into the link JSON.
"""

# Groups and series: the level stored for the equipped skill is the number of
# equipped pieces; getSkillValue/getSkillLevelCore pick the SkillData row with
# the largest SkillLv not above it. This applies to every GROUP/SERIES skill.
GENERAL = [
    "组合技能与系列技能的等级是装备件数；读取数值时取 SkillLv 不超过件数的最大一行（getSkillValue / getSkillLevelCore，1.42.0.2）。",
    "打开技能（_openSkill）在代码中通过 HunterSkillDef.SkillToGroupSkill 换回组合/系列技能后再读取等级与数值。",
]
