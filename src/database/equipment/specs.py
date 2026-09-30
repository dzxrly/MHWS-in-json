from config import WEAPON_FILE_STEMS, WEAPON_TYPES

WORKBOOK_NAME = "EquipCollection.xlsx"
SHEETS = [
    ("Armor", "STM/GameDesign/Common/Equip/ArmorData.user.3.json"),
    *[
        (
            f"Wp_{name}",
            f"STM/GameDesign/Common/Weapon/{WEAPON_FILE_STEMS[name]}.user.3.json",
        )
        for name in WEAPON_TYPES
    ],
]
