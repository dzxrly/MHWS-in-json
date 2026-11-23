"""Species-specific damage modifiers for a particular hit or combat condition."""


def damage_conditions(enemy: str, unique: dict, option_tag: int) -> list[dict]:
    if enemy == "EM0153_00_0":
        # adjustAttackParam 0x143ab9660 clears only FIRE and its element value.
        return [{"name": "水中点火弹体状态下的火属性攻击", "physical": 1, "element": 0}]
    if enemy == "EM0156_00_0":
        # adjustAttackParam 0x14755c290 picks the attack collider's wing/tail
        # and its current charge level. Only cAttackParamBase._Attack changes.
        return [
            {"name": name, "physical": unique[field], "element": 1}
            for name, field in (
                ("翼部攻击命中 · 翼部中度带电", "EnchantAttackRateWingMiddle"),
                ("翼部攻击命中 · 翼部完全带电", "EnchantAttackRateWingMax"),
                ("尾部攻击命中 · 尾部中度带电", "EnchantAttackRateTailMiddle"),
                ("尾部攻击命中 · 尾部完全带电", "EnchantAttackRateTailMax"),
            )
        ]
    if enemy == "EM0166_00_0":
        # doAwake 0x143ddc0d5 sets _IsHighLevel from OptionTag bit zero.
        # adjustAttackParam 0x143ddaff0 then applies the selected scalar to
        # _Attack and _AttrValue while _IsSpAtkMissed is active.
        field = (
            "_SpAtkMissedAtkUpRate_HL" if option_tag & 1 else "_SpAtkMissedAtkUpRate"
        )
        return [
            {
                "name": "特殊攻击失败后的攻击强化期间",
                "physical": unique[field],
                "element": unique[field],
            }
        ]
    return []


def incoming_conditions(enemy: str, unique: dict, upper: bool) -> list[dict]:
    if enemy == "EM0164_50_0":
        # adjustDamageParam 0x1490a1610 multiplies incoming _Attack only for
        # HEAD_ROBE/WING_L_ROBE/WING_R_ROBE with a positive old-scar count.
        rate = unique[
            "_OldScarEnchantDamageRate_EX" if upper else "_OldScarEnchantDamageRate"
        ]
        return [{"name": "击中留有旧伤的头部或翼部护壳", "slash": rate, "shot": rate}]
    return []
