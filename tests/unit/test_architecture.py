"""Architecture enforcement: dependency DAG and import rules.

Rules:
1. Domain modules never import from CLI modules
2. Only life/store/ and life/db.py may import sqlite3
3. Only life/lib/store.py and life/store/ may call sqlite3.connect()
"""

import ast
from pathlib import Path

LIFE_ROOT = Path(__file__).parent.parent.parent / "life"

# Modules allowed to import sqlite3
SQLITE3_ALLOWED = {
    "life/store/connection.py",
    "life/store/sqlite.py",
    "life/db.py",
    "life/backup.py",
    "life/health.py",  # uses :memory: for analysis
}


def _all_py_files() -> list[Path]:
    return sorted(LIFE_ROOT.rglob("*.py"))


def _relative(path: Path) -> str:
    return str(path.relative_to(LIFE_ROOT.parent))


def _get_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_no_sqlite3_outside_store():
    violations = []
    for path in _all_py_files():
        rel = _relative(path)
        if rel in SQLITE3_ALLOWED:
            continue
        imports = _get_imports(path)
        if "sqlite3" in imports:
            violations.append(rel)
    assert not violations, f"sqlite3 imported outside store layer: {violations}"
