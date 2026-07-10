from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Language:
    code: str
    native_name: str


BASE_DIR = Path(__file__).resolve().parent

JSON_ROOT = BASE_DIR / "MHWS-in-json"
NATIVES_DIR = JSON_ROOT / "natives"
ENUMS_PATH = JSON_ROOT / "Enums_Internal.json"
OUTPUT_DIR = BASE_DIR / "output"

LANGUAGE_IDS = None
VERSION = None
VERSION_ENV_VAR = "RELEASE_VERSION"
ZIP_PREFIX = "DATABASE"
PROCESSED_ZIP_PREFIX = "PROCESSED_DATA"
SOURCE_ZIP_PREFIX = JSON_ROOT.name
PROCESSED_DIR_NAME = "processed_data"
FULL_TEXT_WORKBOOK = "FullText.xlsx"
MAX_COLUMN_WIDTH = 80.0
FULL_TEXT_MAX_COLUMN_WIDTH = 300.0

LANGUAGES: dict[int, Language] = {
    0: Language("ja-JP", "日本語"),
    1: Language("en-US", "English"),
    2: Language("fr-FR", "Français"),
    3: Language("it-IT", "Italiano"),
    4: Language("de-DE", "Deutsch"),
    5: Language("es-ES", "Español"),
    6: Language("ru-RU", "Русский"),
    7: Language("pl-PL", "Polski"),
    8: Language("nl-NL", "Nederlands"),
    9: Language("pt-PT", "Português (Portugal)"),
    10: Language("pt-BR", "Português (Brasil)"),
    11: Language("ko-KR", "한국어"),
    12: Language("zh-Hant", "繁體中文"),
    13: Language("zh-Hans", "简体中文"),
    14: Language("fi-FI", "Suomi"),
    15: Language("sv-SE", "Svenska"),
    16: Language("da-DK", "Dansk"),
    17: Language("no-NO", "Norsk"),
    18: Language("cs-CZ", "Čeština"),
    19: Language("hu-HU", "Magyar"),
    20: Language("sk-SK", "Slovenčina"),
    21: Language("ar-SA", "العربية"),
    22: Language("tr-TR", "Türkçe"),
    23: Language("bg-BG", "Български"),
    24: Language("el-GR", "Ελληνικά"),
    25: Language("ro-RO", "Română"),
    26: Language("es-419", "Español (Latinoamérica)"),
    27: Language("vi-VN", "Tiếng Việt"),
    28: Language("id-ID", "Bahasa Indonesia"),
    29: Language("uk-UA", "Українська"),
    30: Language("hi-IN", "हिन्दी"),
    31: Language("ms-MY", "Bahasa Melayu"),
    32: Language("th-TH", "ไทย"),
}

SUPPORT_FILES = {
    "armor_series": "STM/GameDesign/Common/Equip/ArmorSeriesData.user.3.json",
    "armor": "STM/GameDesign/Common/Equip/ArmorData.user.3.json",
    "enemy": "STM/GameDesign/Common/Enemy/EnemyData.user.3.json",
    "item": "STM/GameDesign/Common/Item/itemData.user.3.json",
    "skill_common": "STM/GameDesign/Common/Equip/SkillCommonData.user.3.json",
}

WEAPON_TYPES = [
    "LongSword",
    "ShortSword",
    "TwinSword",
    "Tachi",
    "Hammer",
    "Whistle",
    "Lance",
    "Gunlance",
    "SlashAxe",
    "ChargeAxe",
    "Rod",
    "Bow",
    "HeavyBowgun",
    "LightBowgun",
]

WORKBOOKS = {
    "ItemDataCollection.xlsx": [
        ("ItemData", "STM/GameDesign/Common/Item/itemData.user.3.json"),
        ("ItemRecipeData", "STM/GameDesign/Common/Item/ItemRecipe.user.3.json"),
    ],
    "SkillCollection.xlsx": [
        ("SkillCommonData", "STM/GameDesign/Common/Equip/SkillCommonData.user.3.json"),
        ("SkillData", "STM/GameDesign/Common/Equip/SkillData.user.3.json"),
        ("AccessoryData", "STM/GameDesign/Common/Equip/AccessoryData.user.3.json"),
    ],
    "EquipCollection.xlsx": [
        ("Armor", "STM/GameDesign/Common/Equip/ArmorData.user.3.json"),
        *[
            (f"Wp_{name}", f"STM/GameDesign/Common/Weapon/{name}.user.3.json")
            for name in WEAPON_TYPES
        ],
    ],
    "EquipRecipeCollection.xlsx": [
        ("Armor", "STM/GameDesign/Common/Equip/ArmorRecipeData.user.3.json"),
        *[
            (f"Wp_{name}", f"STM/GameDesign/Common/Weapon/{name}Recipe.user.3.json")
            for name in WEAPON_TYPES
        ],
    ],
}
