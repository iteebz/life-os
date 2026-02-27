import re
from collections.abc import Callable
from dataclasses import dataclass
from zlib import crc32

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_MD_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


@dataclass(frozen=True)
class Theme:
    red: str = "\033[38;5;203m"
    green: str = "\033[38;5;114m"
    yellow: str = "\033[38;5;221m"
    blue: str = "\033[38;5;111m"
    magenta: str = "\033[38;5;176m"
    cyan: str = "\033[38;5;117m"
    gray: str = "\033[38;5;245m"
    white: str = "\033[38;5;252m"
    orange: str = "\033[38;5;208m"
    pink: str = "\033[38;5;212m"
    lime: str = "\033[38;5;155m"
    teal: str = "\033[38;5;80m"
    gold: str = "\033[38;5;220m"
    coral: str = "\033[38;5;209m"
    purple: str = "\033[38;5;141m"
    sky: str = "\033[38;5;67m"
    mint: str = "\033[38;5;121m"
    peach: str = "\033[38;5;217m"
    lavender: str = "\033[38;5;183m"
    slate: str = "\033[38;5;103m"
    sage: str = "\033[38;5;108m"
    forest: str = "\033[38;5;65m"
    amber: str = "\033[38;5;137m"
    mauve: str = "\033[38;5;139m"
    muted: str = "\033[90m"  # dim gray for secondary text
    bold: str = "\033[1m"
    dim: str = "\033[2m"
    strikethrough: str = "\033[9m"
    reset: str = "\033[0m"


DEFAULT = Theme()
_active: Theme = DEFAULT


def use(theme: Theme) -> None:
    global _active
    _active = theme


_COLORS = {
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "gray",
    "white",
    "orange",
    "pink",
    "lime",
    "teal",
    "gold",
    "coral",
    "purple",
    "sky",
    "mint",
    "peach",
    "lavender",
    "slate",
    "sage",
    "forest",
    "amber",
    "mauve",
    "muted",
}

POOL: list[tuple[str, str]] = [
    ("\033[38;5;209m", "coral"),  # orange-red   ~15°
    ("\033[38;5;215m", "apricot"),  # orange       ~30°
    ("\033[38;5;185m", "butter"),  # warm yellow  ~65°
    ("\033[38;5;149m", "lime"),  # yellow-green ~80°
    ("\033[38;5;113m", "spring"),  # spring green ~100°
    ("\033[38;5;158m", "pale-mint"),  # mint-green   ~150°
    ("\033[38;5;116m", "seafoam"),  # teal         ~175°
    ("\033[38;5;81m", "sky"),  # cyan-blue    ~195°
    ("\033[38;5;69m", "cornflower"),  # periwinkle   ~225°
    ("\033[38;5;134m", "orchid"),  # violet       ~280°
    ("\033[38;5;204m", "rose"),  # hot pink     ~320°
    ("\033[38;5;217m", "peach"),  # soft pink    ~340°
]


def __getattr__(name: str) -> Callable[[str], str]:
    if name in _COLORS:

        def _wrap(text: str) -> str:
            return f"{getattr(_active, name)}{text}{_active.reset}"

        _wrap.__name__ = name
        return _wrap
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def bold(text: str) -> str:
    return f"{_active.bold}{text}{_active.reset}"


def dim(text: str) -> str:
    return f"{_active.dim}{text}{_active.reset}"


def strikethrough(text: str) -> str:
    struck = "".join(c + "\u0336" for c in text)
    return f"{_active.muted}{struck}{_active.reset}"


def strip(text: str) -> str:
    return _ANSI_RE.sub("", text)


def strip_markdown(text: str) -> str:
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_ITALIC_RE.sub(r"\1", text)
    text = _MD_CODE_RE.sub(r"\1", text)
    text = _MD_HEADING_RE.sub("", text)
    return _MD_LINK_RE.sub(r"\1", text)


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
    return f"{_active.bold}{color}@{name}{_active.reset}"


def highlight_references(text: str, base_color: str | None = None) -> str:
    base = base_color or _active.reset

    def _color_ref(m: re.Match[str]) -> str:
        return f"{_active.bold}{_active.cyan}{m.group(1)}/{m.group(2)}{_active.reset}{base}"

    return _REFERENCE_RE.sub(_color_ref, text)


def highlight_path(text: str, base_color: str | None = None) -> str:
    base = base_color or _active.reset

    def _color_path(m: re.Match[str]) -> str:
        return f"{_active.blue}{m.group(1)}{base}"

    result = _PATH_RE.sub(_color_path, text)
    if base_color:
        return f"{base_color}{result}"
    return result
