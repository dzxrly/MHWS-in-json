import ast
import unittest

from config import BASE_DIR


class ArchitectureTests(unittest.TestCase):
    def test_dependencies_follow_product_ownership(self):
        forbidden = {
            "shared": ("src.pipeline", "src.database", "src.processed_data"),
            "database": ("src.pipeline", "src.processed_data"),
            "processed_data": ("src.pipeline", "src.database"),
        }
        for area, prefixes in forbidden.items():
            for path in (BASE_DIR / "src" / area).rglob("*.py"):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    imports = []
                    if isinstance(node, ast.ImportFrom):
                        imports = [node.module or ""]
                    elif isinstance(node, ast.Import):
                        imports = [alias.name for alias in node.names]
                    for module in imports:
                        self.assertFalse(module.startswith(prefixes), f"{path}: forbidden import {module}")
