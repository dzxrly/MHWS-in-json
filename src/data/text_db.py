import json
import re
from pathlib import Path

ILLEGAL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")
REF_RE = re.compile(r"<[Rr][Ee][Ff] (.*?)>")
EMID_RE = re.compile(r"<EMID (.*?)>")
REJECTED = "<COLOR FF0000>#Rejected#</COLOR> "


class TextDB:
    def __init__(
        self,
        guid_text: dict[str, str],
        name_text: dict[str, str],
        rejected_guids: set[str] | None = None,
    ):
        self.guid_text = guid_text
        self.name_text = name_text
        self.rejected_guids = rejected_guids or set()
        self._resolve_all_refs()

    @classmethod
    def from_natives(cls, natives_dir: Path, lang_id: int) -> "TextDB":
        guid_text: dict[str, str] = {}
        name_text: dict[str, str] = {}
        rejected_guids: set[str] = set()
        for path in Path(natives_dir).rglob("*.msg.23.json"):
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("entries", []):
                text = _content_at(entry.get("content"), lang_id)
                guid = entry.get("guid")
                name = entry.get("name")
                if guid:
                    guid_text[guid] = text
                    _update_rejected(rejected_guids, guid, entry.get("content"), lang_id)
                if name:
                    name_text[name] = text
        return cls(guid_text, name_text, rejected_guids)

    def get(self, guid: str) -> str | None:
        return self.guid_text.get(guid)

    def is_rejected(self, guid: str) -> bool:
        return guid in self.rejected_guids

    def _resolve_all_refs(self) -> None:
        self.guid_text = {k: self._resolve_refs(v) for k, v in self.guid_text.items()}
        self.name_text = {k: self._resolve_refs(v) for k, v in self.name_text.items()}

    def _resolve_refs(self, text: str) -> str:
        for _ in range(8):
            new_text = REF_RE.sub(lambda m: self.name_text.get(m.group(1), m.group(0)), text)
            new_text = EMID_RE.sub(
                lambda m: self.name_text.get(f"EnemyText_NAME_{m.group(1)}", m.group(0)),
                new_text,
            )
            if new_text == text:
                return new_text
            text = new_text
        return text


class TextSource:
    def __init__(self, entries: list[tuple[str | None, str | None, list | None]], file_count: int = 0):
        self.entries = entries
        self.file_count = file_count

    @classmethod
    def from_natives(cls, natives_dir: Path) -> "TextSource":
        entries = []
        file_count = 0
        for path in Path(natives_dir).rglob("*.msg.23.json"):
            file_count += 1
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("entries", []):
                entries.append((entry.get("guid"), entry.get("name"), entry.get("content")))
        return cls(entries, file_count)

    def build(self, lang_id: int) -> TextDB:
        guid_text: dict[str, str] = {}
        name_text: dict[str, str] = {}
        rejected_guids: set[str] = set()
        for guid, name, content in self.entries:
            text = _content_at(content, lang_id)
            if guid:
                guid_text[guid] = text
                _update_rejected(rejected_guids, guid, content, lang_id)
            if name:
                name_text[name] = text
        return TextDB(guid_text, name_text, rejected_guids)


def discover_language_ids(natives_dir: Path) -> list[int]:
    supported: set[int] | None = None
    for path in Path(natives_dir).rglob("*.msg.23.json"):
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        available = {
            index
            for index, lang_id in enumerate(data.get("languages", []))
            if lang_id != -1
        }
        supported = available if supported is None else supported & available
    return sorted(supported or set()) or [13]


def _content_at(contents: list | None, lang_id: int) -> str:
    if not contents or lang_id >= len(contents) or contents[lang_id] is None:
        return ""
    text = str(contents[lang_id]).replace("\n", "").replace("\r", "")
    if text.startswith(REJECTED):
        text = text[len(REJECTED) :]
    return ILLEGAL_CHARS_RE.sub("", text)


def _update_rejected(
    rejected_guids: set[str],
    guid: str,
    contents: list | None,
    lang_id: int,
) -> None:
    if contents and lang_id < len(contents) and str(contents[lang_id] or "").startswith(REJECTED):
        rejected_guids.add(guid)
    else:
        rejected_guids.discard(guid)
