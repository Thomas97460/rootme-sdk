"""Typed public data returned by the API and web adapters."""

from dataclasses import dataclass, field
from enum import StrEnum

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]


@dataclass(frozen=True)
class Resource:
    """A link to a challenge attachment, documentation or service."""

    url: str = field(repr=False)
    label: str = ""


class Category(StrEnum):
    """Supported Root-Me challenge categories."""

    APP_SCRIPT = "app-script"
    APP_SYSTEM = "app-system"
    CRACKING = "cracking"
    CRYPTANALYSIS = "cryptanalysis"
    FORENSIC = "forensic"
    PROGRAMMING = "programming"
    REALISTIC = "realistic"
    NETWORK = "network"
    STEGANOGRAPHY = "steganography"
    WEB_CLIENT = "web-client"
    WEB_SERVER = "web-server"

    @property
    def label(self) -> str:
        """Human-readable category label."""
        return _CATEGORY_TITLES.get(self, self.value)


_CATEGORY_TITLES: dict[Category, str] = {
    Category.APP_SCRIPT: "App - Script",
    Category.APP_SYSTEM: "App - Système",
    Category.CRACKING: "Cracking",
    Category.CRYPTANALYSIS: "Cryptanalyse",
    Category.FORENSIC: "Forensic",
    Category.PROGRAMMING: "Programmation",
    Category.REALISTIC: "Réaliste",
    Category.NETWORK: "Réseau",
    Category.STEGANOGRAPHY: "Stéganographie",
    Category.WEB_CLIENT: "Web - Client",
    Category.WEB_SERVER: "Web - Serveur",
}


CATEGORY_RUBRIQUES: dict[Category, int] = {
    Category.APP_SCRIPT: 189,
    Category.APP_SYSTEM: 203,
    Category.CRACKING: 69,
    Category.CRYPTANALYSIS: 18,
    Category.FORENSIC: 208,
    Category.PROGRAMMING: 17,
    Category.REALISTIC: 70,
    Category.NETWORK: 182,
    Category.STEGANOGRAPHY: 67,
    Category.WEB_CLIENT: 16,
    Category.WEB_SERVER: 68,
}

RUBRIQUE_CATEGORIES: dict[int, Category] = {
    189: Category.APP_SCRIPT,
    203: Category.APP_SYSTEM,
    69: Category.CRACKING,
    13: Category.CRACKING,
    18: Category.CRYPTANALYSIS,
    4: Category.CRYPTANALYSIS,
    208: Category.FORENSIC,
    17: Category.PROGRAMMING,
    70: Category.REALISTIC,
    182: Category.NETWORK,
    12: Category.NETWORK,
    67: Category.STEGANOGRAPHY,
    16: Category.WEB_CLIENT,
    68: Category.WEB_SERVER,
}


class Difficulty(StrEnum):
    """Standardized challenge difficulty levels."""

    VERY_EASY = "very-easy"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    VERY_HARD = "very-hard"


DIFFICULTY_SCORES: dict[Difficulty, tuple[int, ...]] = {
    Difficulty.VERY_EASY: (5, 10),
    Difficulty.EASY: (15, 20),
    Difficulty.MEDIUM: (25, 30, 35),
    Difficulty.HARD: (40, 45, 50),
    Difficulty.VERY_HARD: (60, 75, 100),
}


@dataclass(frozen=True)
class ChallengeSummary:
    """Summary of a challenge returned in search or listing queries."""

    id: int
    title: str
    category: Category | None = None
    difficulty: Difficulty | None = None
    score: int | None = None
    solved: bool = False
    url: str | None = None


@dataclass(frozen=True)
class Challenge:
    """Challenge metadata and statement; unavailable API fields remain absent."""

    id: int | None
    title: str
    category: Category | None = None
    difficulty: Difficulty | None = None
    score: int | None = None
    solved: bool = False
    category_id: int | None = None
    url: str | None = None
    statement_html: str = field(default="", repr=False)
    statement: str = field(default="", repr=False)
    authors: tuple[str, ...] = ()
    date: str | None = None
    validations_count: int | None = None
    resources: tuple[Resource, ...] = ()
    data: JSONObject = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class UserProfile:
    """User data and solved challenge references supplied by the platform."""

    id: int | None
    name: str
    score: int | None = None
    position: int | None = None
    rank: int | None = None
    solved_challenges_count: int = 0
    data: JSONObject = field(default_factory=dict, repr=False)

    @property
    def username(self) -> str:
        """Alias for name."""
        return self.name


@dataclass(frozen=True)
class FormField:
    """A discovered HTML control, including allowed select/radio options."""

    name: str
    kind: str
    value: str = field(default="", repr=False)
    options: tuple[str, ...] = ()
    required: bool = False
    checked: bool = False


@dataclass(frozen=True)
class Upload:
    """A caller-supplied file to upload through a discovered file control."""

    filename: str
    content: bytes = field(repr=False)
    content_type: str = "application/octet-stream"


@dataclass(frozen=True)
class Collection[T]:
    """One official API page plus its server-provided continuation URL."""

    items: tuple[T, ...]
    next_url: str | None = None


@dataclass(frozen=True)
class WebForm:
    """A server-rendered form; hidden values are intentionally absent from repr."""

    page_url: str = field(repr=False)
    action: str = field(repr=False)
    method: str
    name: str
    fields: tuple[FormField, ...] = field(repr=False)


@dataclass(frozen=True)
class WebPage:
    """A readable platform page with links and discovered forms."""

    url: str
    title: str
    text: str = field(repr=False)
    links: tuple[Resource, ...] = field(repr=False)
    forms: tuple[WebForm, ...] = field(repr=False)
    html: str = field(repr=False)


class SubmissionStatus(StrEnum):
    """Conservative answer outcomes; only explicit success is accepted."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ALREADY_SOLVED = "already_solved"
    BLOCKED = "blocked"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class SubmissionResult:
    """A server-confirmed answer outcome or an explicit uncertain result."""

    status: SubmissionStatus
    message: str = field(default="", repr=False)
    retry_after: float | None = None
