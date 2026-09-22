from config import LANGUAGES


def language_code(language_id: int) -> str:
    language = LANGUAGES.get(language_id)
    return language.code if language else f"lang-{language_id:02d}"
