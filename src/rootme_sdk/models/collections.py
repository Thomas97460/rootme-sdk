"""Generic collection and JSON value models for paginated API responses."""

from dataclasses import dataclass

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]


@dataclass(frozen=True)
class Collection[T]:
    """One official API page plus its server-provided continuation URL."""

    items: tuple[T, ...]
    next_url: str | None = None
