"""Invariants: runtime-correctness rules that don't fit style or architecture."""

import ast
import re
from pathlib import Path

LIFE_ROOT = Path(__file__).parent.parent / "life"
TESTS_ROOT = Path(__file__).parent

_TEST_FN_RE = re.compile(r"^def (test[a-z]\w+)", re.MULTILINE)

# Silent catch budget: except Exception/bare except without any logging call.
# Files that had violations at introduction. Shrink only — never add.
_SILENT_CATCH_BUDGET: dict[str, int] = {
    "backup.py": 1,
    "comms/accounts_cli.py": 1,
    "comms/config.py": 1,
    "comms/email/gmail.py": 9,
    "comms/email/outlook.py": 1,
    "comms/email/resend.py": 2,
    "comms/messages/telegram.py": 2,
    "comms/messages/telegram_sync.py": 2,
    "comms/services.py": 1,
    "ctx/assemble.py": 1,
    "ctx/sections.py": 8,
    "doctor.py": 2,
    "health.py": 2,
    "hooks/__init__.py": 1,
    "lib/tags.py": 1,
    "ref.py": 1,
    "store/connection.py": 2,
    "store/migrations.py": 2,
    "utterances.py": 1,
}


def _has_logging(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in {
                "warning",
                "error",
                "exception",
                "critical",
                "info",
                "debug",
            }:
                return True
            if isinstance(func, ast.Name) and func.id == "print":
                return True
    return False


def test_no_new_silent_catches():
    """Every bare/Exception catch in life/ must have a logging call.

    Silent catches hide failures. Known violations are budgeted. Shrink only.
    """
    actual: dict[str, int] = {}
    for path in sorted(LIFE_ROOT.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        silent = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            exc = node.type
            if exc is not None and not (isinstance(exc, ast.Name) and exc.id == "Exception"):
                continue
            if not _has_logging(node):
                silent += 1
        if silent:
            rel = str(path.relative_to(LIFE_ROOT))
            actual[rel] = silent

    violations = []
    for path, count in sorted(actual.items()):
        budget = _SILENT_CATCH_BUDGET.get(path, 0)
        if count > budget:
            violations.append(f"  {path}: {count} silent catches (budget: {budget})")
    assert not violations, (
        "Silent except-Exception handlers (no logging call):\n"
        + "\n".join(violations)
        + "\n\nFix: add logger.warning/error or raise."
    )


def test_all_test_functions_use_underscore_separator():
    """Test functions must use test_ prefix (test_foo, not testfoo).

    Prevents pytest discovery failures when renaming functions under test
    causes the separator to be dropped (test_run_foo -> testrun_foo).
    """
    violations = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if "__pycache__" in str(path) or not path.name.startswith("test_"):
            continue
        text = path.read_text()
        for match in _TEST_FN_RE.finditer(text):
            name = match.group(1)
            if not name.startswith("test_"):
                rel = str(path.relative_to(TESTS_ROOT))
                violations.append(f"  {rel}: {name} (should be test_{name[4:]})")
    assert not violations, (
        "Test functions without underscore separator (pytest won't discover them):\n"
        + "\n".join(violations)
        + "\n\nRename: testfoo -> test_foo"
    )
