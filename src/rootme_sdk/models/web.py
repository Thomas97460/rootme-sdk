"""Web forms, HTML controls and page representation models."""

from dataclasses import dataclass, field

from .challenges import Resource


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
