"""Style ratchet: enforces import conventions across the codebase."""

import ast
from pathlib import Path

LIFE_ROOT = Path(__file__).parent.parent / "life"

# Legitimate X as _X aliases that survive the ratchet.
# Each entry is (file_suffix, import_name, alias_name).
EXEMPTIONS = {
    # stdlib signal collision: `import signal as _signal` avoids shadowing
    # life.comms.messages.signal used elsewhere in the same file
    ("daemon/cli.py", "signal", "_signal"),
    # circular dep noqa'd separately; alias is load-bearing for fncli dispatch
    ("task/cli.py", "add", "_add"),
}


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
