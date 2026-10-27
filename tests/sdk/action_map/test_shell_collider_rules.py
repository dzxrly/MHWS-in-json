from pathlib import Path
import unittest

from sdk.action_map_exporter.models import ShellCollisionReference, ShellEntryRecord
from sdk.action_map_exporter.shell_collider_rules import shell_collider_rules


def entry(fixed_name, collision_id, mini_class, **fields):
    references = (
        (
            ShellCollisionReference(
                collision_id, "primary", "_AttackCollisionID", "list"
            ),
        )
        if collision_id is not None
        else ()
    )
    return ShellEntryRecord(
        source_scope="Wp11",
        shell_list_path="list",
        entry_index=0,
        target_scope="Wp11",
        fixed_id=0,
        fixed_name=fixed_name,
        shell_name_hash=0,
        ammo_type_name="",
        prefab_path="shell.pfb",
        main_param_path="param.user",
        collision_ids=(collision_id,) if collision_id is not None else (),
        collision_references=references,
        mini_param_fields=tuple(
            (mini_class, name, value) for name, value in fields.items()
        ),
    )


def ids(rules):
    return {rule.marker: rule.collision_id for rule in rules}


ARROW = "app.cShellminiParamPlWp11Arrow"


class BowRuleTests(unittest.TestCase):
    def test_penetrate_bottle_adds_400_except_special_and_homing(self):
        normal = ids(
            shell_collider_rules(
                entry(
                    "NORMAL_LV2", 1, ARROW, _ArrowType="[0] NORMAL", _ArrowLv="[2] LV2"
                )
            )
        )
        self.assertEqual(normal["PENETRATE_BOTTLE"], 401)
        special = ids(
            shell_collider_rules(
                entry(
                    "SPECIAL", 12, ARROW, _ArrowType="[5] SPECIAL", _ArrowLv="[1] LV1"
                )
            )
        )
        self.assertNotIn("PENETRATE_BOTTLE", special)
        homing = ids(
            shell_collider_rules(
                entry(
                    "NORMAL_HOMING",
                    200,
                    ARROW,
                    _ArrowType="[0] NORMAL",
                    _ArrowLv="[5] HOMING",
                )
            )
        )
        self.assertEqual(homing, {"TSUGIYA_HOMING_SINGLE_HIT": 201})

    def test_gosha_homing_also_covers_jump_override(self):
        rules = ids(
            shell_collider_rules(
                entry(
                    "GOSHA_HOMING",
                    202,
                    ARROW,
                    _ArrowType="[2] GOSHA",
                    _ArrowLv="[5] HOMING",
                )
            )
        )
        self.assertEqual(
            rules,
            {"TSUGIYA_HOMING_SINGLE_HIT": 203, "JUMP_TSUGIYA_HOMING_SINGLE_HIT": 214},
        )

    def test_child_shells_map_parent_state_to_collider(self):
        body = ids(
            shell_collider_rules(
                entry(
                    "TSUGIYA_HOMING_BODY_HIT",
                    None,
                    ARROW,
                    _ArrowType="[99] HOMING_BODY_HIT",
                )
            )
        )
        self.assertEqual(body["NORMAL"], 500)
        self.assertEqual(body["JUMP"], 506)
        skill = ids(
            shell_collider_rules(
                entry(
                    "NORMAL_ASKILL_005", None, ARROW, _ArrowType="[50] NORMAL_ASKILL005"
                )
            )
        )
        self.assertEqual(skill, {"LV1": 600, "LV2": 601, "LV3": 602, "HOMING": 603})


class HornAndChargeBladeRuleTests(unittest.TestCase):
    def test_high_freq_request_ids(self):
        rules = ids(
            shell_collider_rules(
                entry(
                    "HIGH_FREQ",
                    0,
                    "app.cShellminiParamPlWp05",
                    _ShellType="[1985337088] HIGH_FREQ",
                )
            )
        )
        self.assertEqual(len(rules), 33)
        self.assertEqual(rules["BLOW_S"], 100)
        self.assertEqual(rules["ELEM_FIRE_M"], 107)
        self.assertEqual(rules["ELEM_BLAST_L"], 132)

    def test_hibiki_damage_types(self):
        rules = ids(
            shell_collider_rules(
                entry(
                    "HIBIKI_DAMAGE",
                    12,
                    "app.cShellminiParamPlWp05",
                    _ShellType="[984647488] HIBIKI_DAMAGE",
                )
            )
        )
        self.assertEqual(rules, {"DAMAGE_M": 7, "DAMAGE_S": 11})

    def test_charge_blade_uses_positive_phial_fields_only(self):
        rules = ids(
            shell_collider_rules(
                entry(
                    "AXE_ATTRIBUTE_BIN_BLAST",
                    0,
                    "app.cShellminiParamPlWp09",
                    _AttrColID=50,
                    _OverChargedAttrColID=55,
                    _OverChargedGrenadeColID=5,
                    _ComboDischarge_AttrColID=-1,
                    _ComboDischarge_GrenadeColID=-1,
                )
            )
        )
        self.assertEqual(
            rules,
            {
                "ELEMENT_PHIAL": 50,
                "ELEMENT_PHIAL_OVERCHARGED": 55,
                "GRENADE_PHIAL_OVERCHARGED": 5,
            },
        )


if __name__ == "__main__":
    unittest.main()
