"""Validate in-memory credentials or a local JSON credential file."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Credentials:
    """Transient login values that never reveal the password in their representation."""

    username: str
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        """Require nonempty strings without including invalid values in errors."""
        if not isinstance(self.username, str) or not self.username:
            raise ValueError("Login must be a nonempty string.")
        if not isinstance(self.password, str) or not self.password:
            raise ValueError("Password must be a nonempty string.")

    @classmethod
    def load(
        cls,
        username: str | None,
        password: str | None,
        credentials_file: str | Path | None,
    ) -> Credentials:
        """Read exactly one credential source without retaining its file path."""
        if credentials_file is not None:
            if username is not None or password is not None:
                raise ValueError("Supply a credentials file or login/password, not both.")
            return cls._from_file(credentials_file)
        if username is None or password is None:
            raise ValueError("Supply both login and password.")
        return cls(username, password)

    @classmethod
    def _from_file(cls, path: str | Path) -> Credentials:
        """Parse a JSON object containing login and password, keeping errors private."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError("Cannot read a valid JSON credentials file.") from None
        if not isinstance(data, dict) or set(data) != {"login", "password"}:
            raise ValueError("Credentials file must contain only login and password.")
        return cls(data["login"], data["password"])
