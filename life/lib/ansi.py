import re
from typing import ClassVar
from zlib import crc32

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_MD_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


class ANSI:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    GREY = "\033[90m"
    RESET = "\033[0m"

    MUTED = "\033[90m"
    SECONDARY = "\033[38;5;245m"

    LIME = "\033[38;5;155m"
    TEAL = "\033[38;5;80m"
    GOLD = "\033[38;5;220m"
    CORAL = "\033[38;5;209m"
    PURPLE = "\033[38;5;141m"
    SKY = "\033[38;5;67m"
    BLUE = "\033[38;5;111m"
    GREEN = "\033[38;5;114m"
    RED = "\033[38;5;203m"
    GRAY = "\033[38;5;245m"
    WHITE = "\033[38;5;252m"
    FOREST = "\033[38;5;65m"
    SLATE = "\033[38;5;103m"
    PEACH = "\033[38;5;217m"
    ORANGE = "\033[38;5;173m"
    MAGENTA = "\033[38;5;139m"
    CYAN = "\033[38;5;109m"
    YELLOW = "\033[38;5;179m"
    PINK = "\033[38;5;175m"
    LAVENDER = "\033[38;5;146m"
    APRICOT = "\033[38;5;216m"
    MINT = "\033[38;5;122m"
    BERRY = "\033[38;5;163m"
    SAGE = "\033[38;5;151m"
    INDIGO = "\033[38;5;99m"

    POOL: ClassVar[list[str]] = [
        "\033[38;5;223m",  # pale-gold
        "\033[38;5;215m",  # apricot
        "\033[38;5;210m",  # salmon
        "\033[38;5;219m",  # pale-pink
        "\033[38;5;177m",  # orchid
        "\033[38;5;111m",  # cornflower
        "\033[38;5;158m",  # pale-mint
        "\033[38;5;116m",  # seafoam
    ]


_R = ANSI.RESET
_B = ANSI.BOLD


def strip(text: str) -> str:
    return _ANSI_RE.sub("", text)


def strip_markdown(text: str) -> str:
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_ITALIC_RE.sub(r"\1", text)
    text = _MD_CODE_RE.sub(r"\1", text)
    text = _MD_HEADING_RE.sub("", text)
    return _MD_LINK_RE.sub(r"\1", text)


def bold(text: str) -> str:
    return f"{_B}{text}\033[22m{_R}"


def dim(text: str) -> str:
    return f"\033[2m{text}\033[22m{_R}"


def gold(text: str) -> str:
    return f"{ANSI.GOLD}{text}{_R}"


def coral(text: str) -> str:
    return f"{ANSI.CORAL}{text}{_R}"


def green(text: str) -> str:
    return f"{ANSI.GREEN}{text}{_R}"


def red(text: str) -> str:
    return f"{ANSI.RED}{text}{_R}"


def gray(text: str) -> str:
    return f"{ANSI.GRAY}{text}{_R}"


def white(text: str) -> str:
    return f"{ANSI.WHITE}{text}{_R}"


def cyan(text: str) -> str:
    return f"{ANSI.CYAN}{text}{_R}"


_REFERENCE_RE = re.compile(r"(?<![a-zA-Z0-9_.:/-])([a-z])/([a-f0-9]{8})(?![a-zA-Z0-9_])")
_MENTION_RE = re.compile(r"@(\w+)")

_PATH_SEGMENT = r"[a-zA-Z0-9_.][a-zA-Z0-9_.-]*"
_PATH_RE = re.compile(
    rf"(?<![a-zA-Z0-9_.*:/])"
    rf"("
    rf"~/{_PATH_SEGMENT}(?:/{_PATH_SEGMENT})*"
    rf"|\.\..?/{_PATH_SEGMENT}(?:/{_PATH_SEGMENT})*"
    rf"|/{_PATH_SEGMENT}(?:/{_PATH_SEGMENT})+"
    rf"|(?![itdr]/[a-f0-9]{{8}})[a-zA-Z0-9_][a-zA-Z0-9_.-]*(?:/{_PATH_SEGMENT})+"
    rf")"
    rf"(?![a-zA-Z0-9_])"
)

_AGENT_COLORS: list[int] = [
    60,
    61,
    62,
    66,
    67,
    68,
    72,
    73,
    74,
    96,
    97,
    98,
    102,
    103,
    104,
    108,
    109,
    110,
    132,
    133,
    134,
    138,
    139,
    140,
    144,
    145,
    146,
    168,
    169,
    170,
    174,
    175,
    176,
    180,
    181,
    182,
]


def agent_color(identity: str) -> str:
    lower = identity.lower()
    idx = crc32(lower.encode()) % len(_AGENT_COLORS)
    return f"\033[38;5;{_AGENT_COLORS[idx]}m"


def mention(name: str) -> str:
    color = agent_color(name)
    return f"{_B}{color}@{name}\033[22m{_R}"


def highlight_references(text: str, base_color: str | None = None) -> str:
    base = base_color or _R

    def _color_ref(m: re.Match[str]) -> str:
        return f"{_B}{ANSI.CYAN}{m.group(1)}/{m.group(2)}\033[22m{base}"

    return _REFERENCE_RE.sub(_color_ref, text)


def highlight_path(text: str, base_color: str | None = None) -> str:
    base = base_color or _R

    def _color_path(m: re.Match[str]) -> str:
        return f"{ANSI.BLUE}{m.group(1)}{base}"

    result = _PATH_RE.sub(_color_path, text)
    if base_color:
        return f"{base_color}{result}"
    return result
