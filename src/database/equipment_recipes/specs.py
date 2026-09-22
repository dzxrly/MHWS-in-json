from config import WEAPON_TYPES

WORKBOOK_NAME = "EquipRecipeCollection.xlsx"
SHEETS = [
    ("Armor", "STM/GameDesign/Common/Equip/ArmorRecipeData.user.3.json"),
    *[
        (f"Wp_{name}", f"STM/GameDesign/Common/Weapon/{name}Recipe.user.3.json")
        for name in WEAPON_TYPES
    ],
]
