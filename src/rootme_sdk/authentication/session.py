"""Scoped authentication state and explicit private-file persistence."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from time import time

from ..errors import UnexpectedResponseError

WEB_HOST = "www.root-me.org"
API_HOST = "api.www.root-me.org"
DEFAULT_AGENT = "rootme-sdk/0.1 (+https://github.com/Thomas97460/rootme-sdk)"


@dataclass(frozen=True)
class SessionCookie:
    """A secret cookie limited to the Root-Me platform hosts."""

    name: str
    value: str = field(repr=False)
    domain: str = WEB_HOST
    path: str = "/"
    expires: float | None = None

    def __post_init__(self) -> None:
        """Reject unsafe cookie syntax and non-platform domains at construction."""
        if not self.name or any(c in self.name + self.value for c in "\r\n;\0"):
            raise ValueError("Invalid cookie syntax.")
        if not (self.name + self.value).isascii() or not _web_domain(self.domain):
            raise ValueError("Invalid platform cookie.")
        if (
            not self.path.startswith("/")
            or self.expires is not None
            and not math.isfinite(self.expires)
        ):
            raise ValueError("Invalid cookie path or expiry.")

    def valid(self) -> bool:
        """Indicate whether the cookie is unexpired."""
        return self.expires is None or self.expires > time()


@dataclass
class Session:
    """Reusable state containing credentials but never a login password."""

    cookies: tuple[SessionCookie, ...] = field(default=(), repr=False)
    user_agent: str = DEFAULT_AGENT

    def __post_init__(self) -> None:
        """Validate secret header values without including them in an error."""
        if not self.user_agent.isascii() or any(c in self.user_agent for c in "\r\n\0"):
            raise ValueError("Invalid user agent.")

    @property
    def spip_session(self) -> str | None:
        """Return a valid web login cookie if one has been supplied."""
        return next((c.value for c in self.cookies if c.name == "spip_session" and c.valid()), None)

    def cookie_header(self, host: str, path: str) -> str:
        """Build cookies for approved exact hosts, never challenge servers."""
        if host == API_HOST:
            return f"spip_session={self.spip_session}" if self.spip_session else ""
        if host != WEB_HOST:
            return ""
        return "; ".join(
            f"{c.name}={c.value}"
            for c in self.cookies
            if c.valid()
            and (path == c.path or path.startswith(c.path.rstrip("/") + "/"))
            and _web_domain(c.domain)
        )

    def save(self, path: str | Path) -> None:
        """Atomically persist state in a file readable only by its owner."""
        target = Path(path)
        payload = {
            "version": 1,
            "user_agent": self.user_agent,
            "cookies": [
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                    "expires": c.expires,
                }
                for c in self.cookies
            ],
        }
        descriptor, temporary = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(payload, stream)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @classmethod
    def load(cls, path: str | Path) -> Session:
        """Read and validate an SDK state file without echoing invalid contents."""
        try:
            data = json.loads(Path(path).read_text())
            if data["version"] != 1:
                raise ValueError
            return _state(data)
        except (KeyError, TypeError, ValueError):
            raise UnexpectedResponseError("Invalid SDK session file.") from None

    @classmethod
    def from_browser_state(cls, path: str | Path, *, user_agent: str) -> Session:
        """Import Playwright cookies while discarding all non-platform cookies."""
        try:
            data = json.loads(Path(path).read_text())
            return cls(cookies=_cookies(data["cookies"]), user_agent=user_agent)
        except (KeyError, TypeError, ValueError):
            raise UnexpectedResponseError("Invalid browser session file.") from None


def _web_domain(domain: str) -> bool:
    """Accept domains applicable to the website without granting other hosts access."""
    return domain.lstrip(".") in {"root-me.org", WEB_HOST}


def _cookies(data: object) -> tuple[SessionCookie, ...]:
    """Validate an external list of cookies and constrain their scope."""
    if not isinstance(data, list):
        raise ValueError
    result = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError
        name, value, domain = item["name"], item["value"], item["domain"]
        path, expires = item.get("path", "/"), item.get("expires")
        if not all(isinstance(v, str) for v in (name, value, domain, path)):
            raise ValueError
        if expires is not None and not isinstance(expires, (int, float)):
            raise ValueError
        if any(ch in name + value for ch in "\r\n;"):
            raise ValueError
        if _web_domain(domain):
            result.append(
                SessionCookie(
                    name,
                    value,
                    domain,
                    path,
                    expires if expires != -1 else None,
                )
            )
    return tuple(result)


def _state(data: object) -> Session:
    """Validate the remaining fields of a saved SDK session."""
    if not isinstance(data, dict):
        raise ValueError
    agent = data["user_agent"]
    if not isinstance(agent, str):
        raise ValueError
    return Session(cookies=_cookies(data["cookies"]), user_agent=agent)
