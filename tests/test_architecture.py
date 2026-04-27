"""Architecture enforcement: dependency DAG and import discipline."""

import ast
from collections import defaultdict
from pathlib import Path

LIFE_ROOT = Path(__file__).parent.parent / "life"

# Layered DAG — each package may only import from packages at its level or below.
# Lower number = lower layer. Peers (same level) may cross-reference.
_LAYERS = {
    "core": 0,
    "store": 1,
    "lib": 1,
    "domain": 2,
    "task": 2,
    "comms": 2,
    "ctx": 3,
    "daemon": 3,
    "steward": 3,
}

# Peer-level deferred imports are allowed (e.g. domain <-> task).
# Cross-layer deferred imports are not — fix the layering.
_SKIP_DIRS = {"__pycache__", "migrations", "identities", "skills", "wiki"}


def _collect_edges():
    """Return {(src_pkg, tgt_pkg): [(file, lineno, module)]}."""
    edges = defaultdict(list)
    for path in sorted(LIFE_ROOT.rglob("*.py")):
        if any(p in _SKIP_DIRS for p in path.parts):
            continue
        rel = path.relative_to(LIFE_ROOT)
        parts = rel.parts
        src_pkg = parts[0] if len(parts) >= 2 else "_root"
        if src_pkg not in _LAYERS:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            mod = node.module or ""
            if not mod.startswith("life."):
                continue
            tgt_pkg = mod.split(".")[1]
            if tgt_pkg == src_pkg or tgt_pkg not in _LAYERS:
                continue
            edges[(src_pkg, tgt_pkg)].append(
                (str(rel), node.lineno, mod)
            )
    return edges


def test_no_upward_imports():
    """Packages must not import from higher layers."""
    edges = _collect_edges()
    violations = []
    for (src, tgt), refs in sorted(edges.items()):
        src_layer = _LAYERS[src]
        tgt_layer = _LAYERS[tgt]
        if tgt_layer > src_layer:
            for file, lineno, mod in refs:
                violations.append(f"  {file}:{lineno}  {src}→{tgt} (layer {src_layer}→{tgt_layer}): {mod}")
    assert not violations, "upward imports violate layer DAG:\n" + "\n".join(violations)
