"""Architecture enforcement: dependency DAG and import discipline."""

import ast
import warnings
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
            edges[(src_pkg, tgt_pkg)].append((str(rel), node.lineno, mod))
    return edges


_CODE_MAX = 16 * 1024  # 16kb
_MD_MAX = 4 * 1024  # 4kb
_SKIP_DIRS_SIZE = {"__pycache__", ".venv", ".git", ".pytest_cache", "seed"}


def test_file_size_limits():
    """No code file > 16kb, no markdown file > 4kb."""
    repo_root = LIFE_ROOT.parent
    violations = []
    for path in sorted(repo_root.rglob("*")):
        if any(p in _SKIP_DIRS_SIZE for p in path.parts):
            continue
        if not path.is_file():
            continue
        size = path.stat().st_size
        rel = path.relative_to(repo_root)
        if path.suffix == ".py" and size > _CODE_MAX:
            violations.append(f"  {rel}  {size // 1024}kb (max 16kb)")
        elif path.suffix == ".md" and size > _MD_MAX:
            violations.append(f"  {rel}  {size // 1024}kb (max 4kb)")
    # Known violations: tracked as initiatives, must not grow
    known = {
        "life/hook.py",
        "life/task/render.py",
    }
    new_violations = [v for v in violations if not any(k in v for k in known)]
    assert not new_violations, "files exceed size limits:\n" + "\n".join(new_violations)
    if violations:
        warnings.warn("known size violations still open:\n" + "\n".join(violations), stacklevel=1)


def test_markdown_has_description_frontmatter():
    """All tracked markdown files must have YAML frontmatter with a description field."""
    repo_root = LIFE_ROOT.parent
    violations = []
    for path in sorted(repo_root.rglob("*.md")):
        if any(p in _SKIP_DIRS_SIZE for p in path.parts):
            continue
        text = path.read_text()
        rel = path.relative_to(repo_root)
        if not text.startswith("---"):
            violations.append(f"  {rel}  missing frontmatter")
            continue
        end = text.find("---", 3)
        if end == -1 or "description:" not in text[3:end]:
            violations.append(f"  {rel}  missing description: in frontmatter")
    assert not violations, "markdown files missing description frontmatter:\n" + "\n".join(violations)


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
