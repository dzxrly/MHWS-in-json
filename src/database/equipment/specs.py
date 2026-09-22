from config import WEAPON_TYPES

WORKBOOK_NAME = "EquipCollection.xlsx"
SHEETS = [
    ("Armor", "STM/GameDesign/Common/Equip/ArmorData.user.3.json"),
    *[
        (f"Wp_{name}", f"STM/GameDesign/Common/Weapon/{name}.user.3.json")
        for name in WEAPON_TYPES
    ],
]
