"""Git hooks: commit-msg enforcement and pre-commit guards."""

import re
import subprocess
import sys
from pathlib import Path

from lifeos.core.lib import frontmatter as fm

_VALID_TYPES = {
    "feat",
    "fix",
    "refactor",
    "test",
    "docs",
    "style",
    "chore",
    "ops",
    "copy",
    "revert",
    "release",
    "perf",
    "sec",
    "memory",
    "brr",
    "ctx",
}

_FRONTMATTER_SCHEMAS: dict[str, tuple[str, set[str] | None]] = {
    "steward/trails/": ("description", None),
}


def _commit_fail(subject: str, reason: str) -> None:
    print(f"BLOCKED — {reason}\n  got: {subject}\n  format: type(scope): verb object", file=sys.stderr)
    sys.exit(1)


def cmd_hook_commit() -> None:
    args = [a for a in sys.argv[1:] if a not in ("hook", "commit")]
    if not args:
        print("usage: life hook commit <msg-file>", file=sys.stderr)
        sys.exit(1)
    msg_file = Path(args[0])
    if not msg_file.exists():
        sys.exit(0)
    subject = msg_file.read_text().splitlines()[0]

    if subject.startswith(("Merge ", "fixup!", "squash!")):
        sys.exit(0)

    tag_pat = "|".join(_VALID_TYPES)
    if not re.match(rf"^({tag_pat})(\([a-z][a-z0-9_-]*\))?: .+", subject):
        _commit_fail(subject, "must be type(scope): verb object with a valid type")

    if re.match(rf"^({tag_pat})\([^)]*,[^)]*\):", subject):
        _commit_fail(subject, "multiple scopes — split into one commit per scope")

    msg_body = subject.split(": ", 1)[1] if ": " in subject else subject

    if msg_body.endswith("."):
        _commit_fail(subject, "no trailing period")
    if "," in msg_body:
        _commit_fail(subject, "no commas — split into atomic commits")
    if "+" in msg_body:
        _commit_fail(subject, "no + — split into atomic commits")
    if " - " in subject:
        _commit_fail(subject, "' - ' is an em-dash proxy — rewrite without it")
    if ": " in msg_body:
        _commit_fail(subject, "no colon-space in message body")

    em_dash = "—"
    en_dash = "–"  # noqa: RUF001
    if em_dash in subject or en_dash in subject:
        cleaned = subject.replace(em_dash, "-").replace(en_dash, "-")
        lines = msg_file.read_text().splitlines(keepends=True)
        lines[0] = cleaned + "\n"
        msg_file.write_text("".join(lines))
        subject = cleaned

    if len(subject) > 72:
        _commit_fail(subject, f"subject is {len(subject)} chars (max 72)")


def _frontmatter_guard(root: Path, staged_all: list[str]) -> None:
    failures: list[str] = []
    for rel in staged_all:
        if not rel.endswith(".md"):
            continue
        schema = next(((g, s) for g, s in _FRONTMATTER_SCHEMAS.items() if rel.startswith(g)), None)
        if schema is None:
            continue
        _glob, (field, valid) = schema
        path = root / rel
        if not path.exists():
            continue
        value = fm.field(path.read_text(), field)
        if value is None:
            failures.append(f"  {rel}: missing '{field}:' in frontmatter")
        elif valid is not None and value not in valid:
            failures.append(f"  {rel}: {field}={value!r} not in {sorted(valid)}")
    if failures:
        print("BLOCKED — frontmatter guard:\n" + "\n".join(failures), file=sys.stderr)
        sys.exit(1)


_WARN_BYTES = 4096
_BLOCK_BYTES = 16384


def _size_guard(root: Path, staged_all: list[str]) -> None:
    blocked: list[str] = []
    for rel in staged_all:
        path = root / rel
        if not path.is_file():
            continue
        size = path.stat().st_size
        old = subprocess.run(
            ["git", "cat-file", "-s", f"HEAD:{rel}"],
            capture_output=True,
            text=True,
        )
        old_size = int(old.stdout.strip()) if old.returncode == 0 else 0
        if size <= old_size:
            continue
        if size > _BLOCK_BYTES:
            blocked.append(f"  {rel} ({size // 1024}kb > 16kb)")
        elif size > _WARN_BYTES and old_size <= _WARN_BYTES:
            print(f"pre-commit: warning — {rel} is {size // 1024}kb (>4kb)", file=sys.stderr)
    if blocked:
        print("BLOCKED — file too large:\n" + "\n".join(blocked), file=sys.stderr)
        sys.exit(1)


def cmd_hook_pre_commit() -> None:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
    )
    staged_all = result.stdout.splitlines()
    root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    _size_guard(root, staged_all)
    _frontmatter_guard(root, staged_all)

    staged = [f for f in staged_all if f.endswith((".py", ".pyi"))]
    if not staged:
        return

    ruff = root / ".venv" / "bin" / "ruff"
    if not ruff.is_file():
        ruff = Path("ruff")

    if subprocess.run([str(ruff), "format", "--check", *staged]).returncode != 0:
        print("BLOCKED — run 'ruff format' first", file=sys.stderr)
        sys.exit(1)

    if subprocess.run([str(ruff), "check", *staged]).returncode != 0:
        print("BLOCKED — fix lint errors", file=sys.stderr)
        sys.exit(1)
