"""User profile and progression data models."""

from dataclasses import dataclass, field

from .collections import JSONObject


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
