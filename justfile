default:
    @just --list

install: bin
    @uv sync
    @just hooks
    @uv run life daemon start

hooks:
    @cp scripts/hooks/pre-commit .git/hooks/pre-commit
    @chmod +x .git/hooks/pre-commit

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
        echo "installed ~/bin/$BIN"
    done

lint:
    #!/bin/bash
    set -e
    uv run ruff format .
    uv run ruff check . --fix
    uv run pyright || true

ci: lint
    @uv run pytest tests --tb=short

test:
    @uv run pytest tests

build:
    @uv build

clean:
    @rm -rf dist build .pytest_cache .ruff_cache __pycache__ .venv
    @find . -type d -name "__pycache__" -exec rm -rf {} +

commits:
    @git --no-pager log --pretty=format:"%h | %ar | %s"

health:
    @uv run python -m life.health
