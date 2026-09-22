"""Message loading, indexed text policies and bounded language views."""

from collections import OrderedDict
from enum import Enum
import json
import re
from pathlib import Path
from typing import Callable

ILLEGAL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")
REF_RE = re.compile(r"<[Rr][Ee][Ff] (.*?)>")
EMID_RE = re.compile(r"<EMID (.*?)>")
REJECTED = "<COLOR FF0000>#Rejected#</COLOR> "


class TextPolicy(Enum):
    DATABASE = "database"
    MISSION = "mission"


def content_at(contents: list | None, language_id: int, policy: TextPolicy) -> str:
    if not contents or language_id < 0 or language_id >= len(contents) or contents[language_id] is None:
        return ""
    value = str(contents[language_id])
    if policy is TextPolicy.DATABASE:
        value = value.replace("\n", "").replace("\r", "")
    if value.startswith(REJECTED):
        if policy is TextPolicy.MISSION:
            return ""
        value = value[len(REJECTED):]
    value = ILLEGAL_CHARS_RE.sub("", value)
    if policy is TextPolicy.DATABASE:
        return value
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return value if value.strip() else ""


def resolve_refs(text: str, name: Callable[[str], str | None], enemy: Callable[[str], str | None]) -> str:
    for _ in range(8):
        updated = REF_RE.sub(lambda match: name(match.group(1)) or match.group(0), text)
        updated = EMID_RE.sub(lambda match: enemy(match.group(1)) or match.group(0), updated)
        if updated == text:
            break
        text = updated
    return text


class TextDB:
    def __init__(self, guid_text: dict[str, str], name_text: dict[str, str], rejected_guids: set[str] | None = None):
        self.guid_text = guid_text
        self.name_text = name_text
        self.rejected_guids = rejected_guids or set()
        self._resolve_all_refs()

    @classmethod
    def from_natives(cls, natives_dir: Path, lang_id: int) -> "TextDB":
        return TextSource.from_natives(natives_dir).build(lang_id)

    def get(self, guid: str) -> str | None:
        return self.guid_text.get(guid)

    def is_rejected(self, guid: str) -> bool:
        return guid in self.rejected_guids

    def _resolve_all_refs(self) -> None:
        self.guid_text = {key: self._resolve_refs(value) for key, value in self.guid_text.items()}
        self.name_text = {key: self._resolve_refs(value) for key, value in self.name_text.items()}

    def _resolve_refs(self, text: str) -> str:
        # Database text distinguishes present-empty names from absent names.
        for _ in range(8):
            updated = REF_RE.sub(lambda match: self.name_text.get(match.group(1), match.group(0)), text)
            updated = EMID_RE.sub(
                lambda match: self.name_text.get(f"EnemyText_NAME_{match.group(1)}", match.group(0)), updated,
            )
            if updated == text:
                return updated
            text = updated
        return text


class TextSource:
    def __init__(self, entries: list[tuple[str | None, str | None, list | None]], file_count: int = 0,
                 language_ids: tuple[int, ...] = (13,)):
        self.entries = entries
        self.file_count = file_count
        self.language_ids = language_ids
        self.guid_contents = {guid: contents for guid, _, contents in entries if guid}
        self.name_contents = {name: contents for _, name, contents in entries if name}
        self._views: OrderedDict[int, TextDB] = OrderedDict()
        self._text_cache: dict[tuple[bool, str, int | None, TextPolicy], str] = {}

    @classmethod
    def from_natives(cls, natives_dir: Path) -> "TextSource":
        entries = []
        file_count = 0
        supported: set[int] | None = None
        for path in Path(natives_dir).rglob("*.msg.23.json"):
            file_count += 1
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            available = {index for index, value in enumerate(data.get("languages", [])) if value != -1}
            supported = available if supported is None else supported & available
            entries.extend((entry.get("guid"), entry.get("name"), entry.get("content")) for entry in data.get("entries", []))
        return cls(entries, file_count, tuple(sorted(supported or set())) or (13,))

    def build(self, lang_id: int) -> TextDB:
        if lang_id not in self._views:
            guids = {guid: content_at(contents, lang_id, TextPolicy.DATABASE) for guid, contents in self.guid_contents.items()}
            names = {name: content_at(contents, lang_id, TextPolicy.DATABASE) for name, contents in self.name_contents.items()}
            rejected = {
                guid for guid, contents in self.guid_contents.items()
                if contents and 0 <= lang_id < len(contents) and str(contents[lang_id] or "").startswith(REJECTED)
            }
            self._views[lang_id] = TextDB(guids, names, rejected)
        self._views.move_to_end(lang_id)
        while len(self._views) > 2:
            self._views.popitem(last=False)
        return self._views[lang_id]

    def text(self, key: str, language_id: int | None, *, named: bool = False,
             policy: TextPolicy = TextPolicy.MISSION) -> str:
        cache_key = (named, key, language_id, policy)
        if cache_key not in self._text_cache:
            contents = (self.name_contents if named else self.guid_contents).get(key)
            if language_id is None:
                value = next((text for index in range(len(contents or [])) if (text := content_at(contents, index, policy))), "")
            else:
                value = content_at(contents, language_id, policy)
            self._text_cache[cache_key] = value
        return self._text_cache[cache_key]


def discover_language_ids(natives_dir: Path) -> list[int]:
    return list(TextSource.from_natives(natives_dir).language_ids)
