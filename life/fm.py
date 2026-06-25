from pathlib import Path

from fncli import cli

from lifeos.core.lib.frontmatter import parse


def _collect(path: Path) -> list[Path]:
    p = Path(path).expanduser()
    if p.is_file():
        return [p]
    return sorted(p.rglob("*.md"))


@cli("life")
def fm(path: str = ".", require: str = "") -> None:
    """Inspect frontmatter on markdown files. --require field1,field2 flags missing fields."""
    required = [f.strip() for f in require.split(",") if f.strip()]
    files = _collect(Path(path))

    if not files:
        print(f"no .md files found in {path}")
        return

    failures: list[tuple[Path, list[str]]] = []

    for f in files:
        if not f.is_file():
            continue
        text = f.read_text()
        fields = parse(text)

        if required:
            missing = [r for r in required if r not in fields]
            if missing:
                failures.append((f, missing))
        else:
            if fields:
                rel = f.relative_to(Path(path).expanduser()) if Path(path).expanduser().is_dir() else f
                kv = "  ".join(f"{k}: {v}" for k, v in fields.items())
                print(f"{rel}  {kv}")

    if required:
        if failures:
            for f, missing in failures:
                rel = f.relative_to(Path(path).expanduser()) if Path(path).expanduser().is_dir() else f
                print(f"MISSING {','.join(missing)}  {rel}")
            raise SystemExit(1)
        ok = len(files)
        print(f"ok  {ok} file{'s' if ok != 1 else ''}  all have {','.join(required)}")
