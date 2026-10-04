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


@dataclass(frozen=True)
class Challenge:
    """Challenge metadata and statement; unavailable API fields remain absent."""

    id: int | None
    title: str
    score: int | None = None
    category_id: int | None = None
    url: str | None = None
    statement_html: str = field(default="", repr=False)
    statement: str = field(default="", repr=False)
    resources: tuple[Resource, ...] = ()
    data: JSONObject = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class UserProfile:
    """User data and solved challenge references supplied by the platform."""

    id: int | None
    name: str
    score: int | None
    position: int | None
    data: JSONObject = field(repr=False)


@dataclass(frozen=True)
class RankingEntry:
    """One entry of the public ranking."""

    position: int
    name: str
    score: int


@dataclass(frozen=True)
class Environment:
    """Virtual-environment data without inventing undocumented attributes."""

    id: int | None
    name: str
    data: JSONObject = field(repr=False)


@dataclass(frozen=True)
class Category:
    """A category link discovered in the challenge catalogue."""

    title: str
    url: str


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
