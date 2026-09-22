"""Quest text policy: preserve line breaks and apply explicit fallbacks."""

from src.shared.text.catalog import ILLEGAL_CHARS_RE, TextPolicy, TextSource, content_at, resolve_refs


def clean_text(value: str) -> str:
    return ILLEGAL_CHARS_RE.sub("", value).replace("\r\n", "\n").replace("\r", "\n")


def mission_content(contents: list | None, language_id: int) -> str:
    return content_at(contents, language_id, TextPolicy.MISSION)


class MissionTextResolver:
    def __init__(self, source: TextSource, language_id: int):
        self.source = source
        self.language_id = language_id

    def get_guid(self, guid: str) -> str:
        return self.resolve(self.source.text(guid, self.language_id) or self.source.text(guid, 1))

    def get_name(self, name: str) -> str:
        return self.resolve(self.source.text(name, self.language_id, named=True)
                            or self.source.text(name, 1, named=True))

    def local_name(self, name: str) -> str:
        return self.resolve(self.source.text(name, self.language_id, named=True))

    def english_name(self, name: str) -> str:
        return self.resolve(self.source.text(name, 1, named=True))

    def enemy_name(self, guid: str | None, enemy_id: str) -> str:
        if guid:
            value = self.source.text(guid, self.language_id) or self.source.text(guid, 1) or self.source.text(guid, None)
            if value:
                return self.resolve(value)
        return self.resolve(self._enemy_name_raw(enemy_id))

    def resolve(self, value: str) -> str:
        return resolve_refs(clean_text(value), self._name_raw, self._enemy_name_raw)

    def _name_raw(self, name: str) -> str:
        value = self.source.text(name, self.language_id, named=True) or self.source.text(name, 1, named=True)
        if name.startswith("EnemyText_NAME_EM"):
            return value or self.source.text(name, None, named=True) or name.removeprefix("EnemyText_NAME_")
        return value

    def _enemy_name_raw(self, enemy_id: str) -> str:
        name = f"EnemyText_NAME_{enemy_id}"
        return (self.source.text(name, self.language_id, named=True)
                or self.source.text(name, 1, named=True)
                or self.source.text(name, None, named=True) or enemy_id)
