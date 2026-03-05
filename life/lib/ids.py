def short(prefix: str, full_id: str) -> str:
    """Display helper: short('t', 'a9b3c2d1-...') → 't/a9b3c2d1'"""
    return f"{prefix}/{full_id[:8]}"


def parse_ref(ref: str) -> tuple[str | None, str]:
    """Parse a prefixed reference: 't/a9b3' → ('t', 'a9b3'), 'a9b3' → (None, 'a9b3')"""
    if "/" in ref:
        prefix, fragment = ref.split("/", 1)
        return prefix, fragment
    return None, ref
