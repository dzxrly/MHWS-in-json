"""Validate the catalogue and diagram inventory embedded in a single HTML."""

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path

from src.processed_data.enemy_action_logic.graph import validate_graph
from src.processed_data.enemy_action_logic.layout import place
from src.processed_data.enemy_action_logic.source import ENEMY_ID


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.payload_parts = []
        self.digest = None
        self.in_payload = False
        self.diagrams = {}
        self.current = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "table" or (tag == "script" and "src" in attrs):
            raise ValueError(
                "Flowchart HTML must be self-contained and contain no tables"
            )
        if tag == "script" and attrs.get("id") == "enemy-catalog":
            if self.digest is not None or attrs.get("type") != "application/json":
                raise ValueError("Duplicate/invalid embedded enemy catalogue")
            self.digest = attrs.get("data-sha256", "")
            self.in_payload = True
        if tag == "section" and attrs.get("class") == "diagram":
            key = (attrs.get("data-enemy"), attrs.get("data-phase"))
            if key in self.diagrams:
                raise ValueError("Duplicate phase diagram")
            self.diagrams[key] = []
            self.current = key
        if tag == "g" and attrs.get("class") == "node" and self.current is not None:
            self.diagrams[self.current].append(attrs.get("data-node"))

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_payload = False
        elif tag == "section":
            self.current = None

    def handle_data(self, value):
        if self.in_payload:
            self.payload_parts.append(value)


def read_document(document: str | Path) -> tuple[dict, DocumentParser]:
    text = (
        document.read_text(encoding="utf-8") if isinstance(document, Path) else document
    )
    parser = DocumentParser()
    parser.feed(text)
    raw = "".join(parser.payload_parts)
    if not raw or hashlib.sha256(raw.encode("utf-8")).hexdigest() != parser.digest:
        raise ValueError("Embedded enemy catalogue hash mismatch or missing payload")
    payload = json.loads(raw)
    if (
        payload.get("schemaVersion") != 1
        or payload.get("format") != "mhws_enemy_action_logic"
    ):
        raise ValueError("Unsupported action logic HTML schema")
    return payload, parser


def validate_document(document: str | Path) -> dict:
    payload, parser = read_document(document)
    enemies = payload.get("enemies", [])
    ids, expected = set(), {}
    for enemy in enemies:
        enemy_id = enemy["enemyId"]
        match = ENEMY_ID.fullmatch(enemy_id)
        if not match or int(match[2]) >= 1000 or enemy_id in ids:
            raise ValueError("Invalid or duplicate action logic enemy ID")
        ids.add(enemy_id)
        graphs = enemy["graphs"]
        if not graphs or len({g["id"] for g in graphs}) != len(graphs):
            raise ValueError("No phase graphs or duplicate phases")
        for index, graph in enumerate(graphs):
            validate_graph(graph)
            place(graph)
            expected[(enemy_id, str(index))] = [node["id"] for node in graph["nodes"]]
    if not ids or expected != parser.diagrams:
        raise ValueError("HTML phase diagrams do not match the embedded catalogue")
    return payload
