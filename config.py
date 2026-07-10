from pathlib import Path

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
FULL_TEXT_MAX_COLUMN_WIDTH = 120.0

LANGUAGE_NAMES = {
    0: "ja-JP",
    1: "en-US",
    2: "fr-FR",
    3: "it-IT",
    4: "de-DE",
    5: "es-ES",
    6: "ru-RU",
    7: "pl-PL",
    8: "nl-NL",
    9: "pt-PT",
    10: "pt-BR",
    11: "ko-KR",
    12: "zh-Hant",
    13: "zh-Hans",
    14: "fi-FI",
    15: "sv-SE",
    16: "da-DK",
    17: "no-NO",
    18: "cs-CZ",
    19: "hu-HU",
    20: "sk-SK",
    21: "ar-SA",
    22: "tr-TR",
    23: "bg-BG",
    24: "el-GR",
    25: "ro-RO",
    26: "es-419",
    27: "vi-VN",
    28: "id-ID",
    29: "uk-UA",
    30: "hi-IN",
    31: "ms-MY",
    32: "th-TH",
}

LANGUAGE_NATIVE_NAMES = {
    "ja-JP": "日本語",
    "en-US": "English",
    "fr-FR": "Français",
    "it-IT": "Italiano",
    "de-DE": "Deutsch",
    "es-ES": "Español",
    "ru-RU": "Русский",
    "pl-PL": "Polski",
    "nl-NL": "Nederlands",
    "pt-PT": "Português (Portugal)",
    "pt-BR": "Português (Brasil)",
    "ko-KR": "한국어",
    "zh-Hant": "繁體中文",
    "zh-Hans": "简体中文",
    "fi-FI": "Suomi",
    "sv-SE": "Svenska",
    "da-DK": "Dansk",
    "no-NO": "Norsk",
    "cs-CZ": "Čeština",
    "hu-HU": "Magyar",
    "sk-SK": "Slovenčina",
    "ar-SA": "العربية",
    "tr-TR": "Türkçe",
    "bg-BG": "Български",
    "el-GR": "Ελληνικά",
    "ro-RO": "Română",
    "es-419": "Español (Latinoamérica)",
    "vi-VN": "Tiếng Việt",
    "id-ID": "Bahasa Indonesia",
    "uk-UA": "Українська",
    "hi-IN": "हिन्दी",
    "ms-MY": "Bahasa Melayu",
    "th-TH": "ไทย",
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
