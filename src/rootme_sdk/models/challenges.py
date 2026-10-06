"""Challenge, category, difficulty and submission domain models."""

from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import unquote, urlsplit

from ..transport.urls import sanitize_url
from .collections import JSONObject


@dataclass(frozen=True)
class Resource:
    """A link to a challenge attachment, documentation or service."""

    url: str
    label: str = ""

    def __post_init__(self) -> None:
        """Encode unescaped characters in the resource URL."""
        object.__setattr__(self, "url", sanitize_url(self.url))

    @property
    def title(self) -> str:
        """Alias for label."""
        return self.label

    @property
    def filename(self) -> str:
        """Return the decoded last URL path segment, rejecting names unsafe as a local file."""
        name = unquote(urlsplit(self.url).path.rsplit("/", 1)[-1])
        if name in {"", ".", ".."} or any(c in name for c in "/\\:\0"):
            raise ValueError("Resource URL does not name a file.")
        return name


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
    """Challenge metadata and statement; unavailable API fields remain absent.

    ``files`` holds the challenge's own downloadable material (binaries, archives,
    captures) attached to the statement. ``resources`` holds the remaining links:
    documentation and references that Root-Me associates with the challenge.
    """

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
    files: tuple[Resource, ...] = ()
    data: JSONObject = field(default_factory=dict, repr=False)


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
