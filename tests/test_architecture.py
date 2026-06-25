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
_SKIP_DIRS_SIZE = {"__pycache__", ".venv", ".git", ".pytest_cache", "seed", "ctx"}


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
    assert not new_violations, "files exceed size limits (split by module or extract helpers):\n" + "\n".join(
        new_violations
    )
    if violations:
        warnings.warn("known size violations still open:\n" + "\n".join(violations), stacklevel=1)


# ~/life/ markdown size guard. Same 4kb ceiling as life-os, applied across the whole tree.
# Ratchet: shrink a file, remove it from _LIFE_MD_KNOWN. New violations fail hard.
_LIFE_ROOT = LIFE_ROOT.parent.parent
_LIFE_SKIP_DIRS = {
    "__pycache__",
    ".venv",
    ".git",
    ".pytest_cache",
    "seed",
    "node_modules",
    "archive",
    "human",  # human/ is tyson's writing, off-limits
}
_LIFE_MD_KNOWN = {
    "CLAUDE.md",
    "taxing/docs/architecture.md",
    "taxing/docs/phases.md",
    "taxing/docs/audit.md",
    "taxing/README.md",
    "taxing/docs/cli.md",
    "taxing/docs/tax.md",
    "taxing/docs/mining.md",
    "tynice/cosmo-house-rules.md",
    # old paths (pre-notes/ rename)
    "steward/arch/ctx-layering.md",
    "steward/arch/memory.md",
    "steward/arch/rsi.md",
    "steward/initiatives/financial-position-dashboard.md",
    "steward/initiatives/prompt-layering.md",
    "steward/people/janice-manual.md",
    "steward/tyson/cognition.md",
    "steward/tyson/operating-manual.md",
    "steward/tyson/traumas.md",
    # new paths (post-notes/ rename)
    "notes/steward/model/tyson/operating-manual.md",
    "notes/steward/model/tyson/traumas.md",
    "notes/steward/model/tyson/cognition.md",
    "notes/steward/model/people/janice-manual.md",
    "notes/steward/work/initiatives/prompt-layering.md",
    "notes/steward/work/initiatives/financial-position-dashboard.md",
}

# ~/life/ python size guard. Same 16kb ceiling as life-os, applied across the whole tree.
_LIFE_PY_KNOWN = {
    "life-os/life/hook.py",
    "taxing/tests/unit/core/test_mining.py",
    "taxing/tests/unit/core/test_trades.py",
    "taxing/taxing/core/mining.py",
}


def test_life_markdown_size_limits():
    """No markdown file in ~/life/ > 4kb. Known violators grandfathered, ratchet down."""
    if not (_LIFE_ROOT / "LIFE.md").exists():
        return  # not running inside ~/life checkout
    violations = []
    for path in sorted(_LIFE_ROOT.rglob("*.md")):
        if any(p in _LIFE_SKIP_DIRS for p in path.parts):
            continue
        if path.suffix != ".md":
            continue
        size = path.stat().st_size
        if size <= _MD_MAX:
            continue
        rel = str(path.relative_to(_LIFE_ROOT))
        violations.append((rel, size))
    new = [f"  {r}  {s // 1024}kb (max 4kb)" for r, s in violations if r not in _LIFE_MD_KNOWN]
    assert not new, "new ~/life/ markdown size violations (split by topic):\n" + "\n".join(new)
    stale = _LIFE_MD_KNOWN - {r for r, _ in violations}
    assert not stale, "files in _LIFE_MD_KNOWN no longer violate — remove from set:\n  " + "\n  ".join(sorted(stale))


def test_life_python_size_limits():
    """No python file in ~/life/ > 16kb. Known violators grandfathered, ratchet down."""
    if not (_LIFE_ROOT / "LIFE.md").exists():
        return
    violations = []
    for path in sorted(_LIFE_ROOT.rglob("*.py")):
        if any(p in _LIFE_SKIP_DIRS for p in path.parts):
            continue
        size = path.stat().st_size
        if size <= _CODE_MAX:
            continue
        rel = str(path.relative_to(_LIFE_ROOT))
        violations.append((rel, size))
    new = [f"  {r}  {s // 1024}kb (max 16kb)" for r, s in violations if r not in _LIFE_PY_KNOWN]
    assert not new, "new ~/life/ python size violations (split by module or extract helpers):\n" + "\n".join(new)
    stale = _LIFE_PY_KNOWN - {r for r, _ in violations}
    assert not stale, "files in _LIFE_PY_KNOWN no longer violate — remove from set:\n  " + "\n  ".join(sorted(stale))


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
