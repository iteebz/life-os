"""Style ratchet: enforces import conventions across the codebase."""

import ast
import re
from functools import cache
from pathlib import Path

LIFE_ROOT = Path(__file__).parent.parent / "life"

# Legitimate X as _X aliases that survive the ratchet.
# Each entry is (file_suffix, import_name, alias_name).
EXEMPTIONS = {
    # stdlib signal collision: `import signal as _signal` avoids shadowing
    # lifeos.core.comms.messages.signal used elsewhere in the same file
    ("daemon/cli.py", "signal", "_signal"),
    # circular dep noqa'd separately; alias is load-bearing for fncli dispatch
    ("task/cli.py", "add", "_add"),
}

# Barrel re-export ratchet.
# `from .foo import Bar` in __init__.py destroys import traceability and causes
# circular import hell. Budget covers all life/ __init__.py files. Drive to zero.
# Known violators: task/__init__.py (23), lib/providers/__init__.py (1). Shrink only.
_BARREL_REEXPORT_BUDGET = 24


@cache
def _barrel_exports() -> dict[str, list[str]]:
    """Return {module: [exported_names]} for all __init__.py barrel re-exports."""
    exports: dict[str, list[str]] = {}
    for init in sorted(LIFE_ROOT.rglob("__init__.py")):
        try:
            tree = ast.parse(init.read_text())
        except SyntaxError:
            continue
        rel = init.relative_to(LIFE_ROOT)
        module = "life." + ".".join(rel.parts[:-1]) if rel.parts[:-1] else "life"
        imported: list[str] = []
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            is_relative = node.level and node.level > 0
            is_intra = not is_relative and node.module and node.module.startswith(module + ".")
            if is_relative or is_intra:
                for alias in node.names:
                    name = alias.asname or alias.name
                    if not name.startswith("_") and name != "*":
                        imported.append(name)
        if imported:
            exports[module] = imported
    return exports


def test_no_new_barrel_reexports():
    """Ratchet: barrel re-exports in __init__.py destroy import traceability.

    Import from where things live: `from life.task.domain import add_task`,
    not `from life.task import add_task`. Budget only goes down.
    """
    all_exports = _barrel_exports()
    total = sum(len(names) for names in all_exports.values())
    violations = [
        f"  {mod}: {len(names)} re-exports ({', '.join(names[:5])}{'...' if len(names) > 5 else ''})"
        for mod, names in sorted(all_exports.items())
    ]
    assert total <= _BARREL_REEXPORT_BUDGET, (
        f"Barrel re-exports: {total} (budget: {_BARREL_REEXPORT_BUDGET})\n"
        + "\n".join(violations)
        + "\n\nFix: import from the defining module, not the package __init__."
    )


def _noise_aliases(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, description) for any X as _X import aliases."""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []

    violations = []
    rel = str(path.relative_to(LIFE_ROOT.parent))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    base = alias.name.split(".")[-1]
                    if alias.asname == "_" + base:
                        key = (rel.removeprefix("life/"), alias.name.split(".")[-1], alias.asname)
                        if key not in EXEMPTIONS:
                            violations.append((node.lineno, f"import {alias.name} as {alias.asname}"))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname and alias.asname == "_" + alias.name:
                    key = (rel.removeprefix("life/"), alias.name, alias.asname)
                    if key not in EXEMPTIONS:
                        violations.append((node.lineno, f"from ... import {alias.name} as {alias.asname}"))

    return violations


def test_no_underscore_prefix_import_aliases():
    """No import should use `X as _X` (underscore prefix of the same name).

    This pattern adds noise without value — it hides the module under
    a private name when the original name was already fine.

    Exemptions for legitimate collision avoidance are in EXEMPTIONS above.
    """
    failures = []
    for path in sorted(LIFE_ROOT.rglob("*.py")):
        for lineno, desc in _noise_aliases(path):
            failures.append(f"  {path.relative_to(LIFE_ROOT.parent)}:{lineno}  {desc}")

    assert not failures, "underscore-prefix import aliases found:\n" + "\n".join(failures)


# ─ (U+2500), ━ (U+2501), ═ (U+2550) box-drawing chars plus ASCII hyphens
_sep_pattern = re.compile(r"#[^\n]*[─━═\-]{4,}")


def test_no_separator_comments():
    """No filler separator comments like `# ──────` or `# ----`.

    These eat context without adding signal. Use blank lines or just
    nothing — the code structure speaks for itself.
    """
    failures = []
    for path in sorted(LIFE_ROOT.rglob("*.py")):
        lines = path.read_text().splitlines()
        for lineno, line in enumerate(lines, 1):
            if _sep_pattern.search(line):
                failures.append(f"  {path.relative_to(LIFE_ROOT.parent)}:{lineno}  {line.strip()}")

    assert not failures, "separator comments found (delete them):\n" + "\n".join(failures)
