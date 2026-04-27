default:
    @just --list

install: bin
    @uv sync
    @just hooks
    @uv run life daemon restart

hooks:
    @git config core.hooksPath .githooks

bin:
    #!/bin/sh
    set -e
    mkdir -p ~/bin
    REPO=$(pwd)
    UV=$(which uv)
    for BIN in life comms steward; do
        SCRIPT=~/bin/$BIN
        printf '#!/bin/sh\n# managed by space launch\ncd %s || exit 1\nexec %s run "$(basename "$0")" "$@"\n' "$REPO" "$UV" > "$SCRIPT"
        chmod 755 "$SCRIPT"
    done

format:
    uv run ruff format . && uv run ruff check --fix . || true

lint:
    uv run ruff check .

typecheck:
    uv run pyright

test:
    @uv run python -m pytest tests

ci:
    #!/usr/bin/env bash
    set -uo pipefail
    log=$(mktemp -d); trap 'rm -rf "$log"' EXIT
    uv run ruff check .                                                        > "$log/lint" 2>&1 & lint=$!
    uv run pyright                                                             > "$log/tc"   2>&1 & tc=$!
    uv run pytest tests/unit/ tests/integration/ -q --tb=no                   > "$log/test" 2>&1 & tst=$!
    wait $lint; lint_rc=$?
    wait $tc;   tc_rc=$?
    wait $tst;  tst_rc=$?
    rc=0
    if [ "$lint_rc" -eq 0 ]; then echo "lint ✓"; else echo "lint ✗"; /bin/cat "$log/lint"; rc=1; fi
    if [ "$tc_rc"   -eq 0 ]; then echo "typecheck ✓"; else echo "typecheck ✗"; /bin/cat "$log/tc"; rc=1; fi
    if [ "$tst_rc"  -eq 0 ]; then echo "test ✓"; else echo "test ✗"; /bin/cat "$log/test"; rc=1; fi
    exit $rc

build:
    @uv build

clean:
    @rm -rf dist build .pytest_cache .ruff_cache __pycache__ .venv
    @find . -type d -name "__pycache__" -exec rm -rf {} +

commits:
    @git --no-pager log --pretty=format:"%h | %ar | %s"

health:
    @uv run python -m life.health
