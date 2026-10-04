import json
import os
from pathlib import Path

import pytest

from rootme_sdk import Session, SessionCookie, UnexpectedResponseError
from rootme_sdk.authentication.session import API_HOST, WEB_HOST, _cookies, _state


def test_host_scoping_expiry_and_secret_repr() -> None:
    state = Session(
        cookies=(
            SessionCookie("spip_session", "test-session"),
            SessionCookie("old", "expired", expires=0),
            SessionCookie("restricted", "value", path="/private"),
        ),
    )
    assert state.spip_session == "test-session"
    assert state.cookie_header(API_HOST, "/") == "spip_session=test-session"
    assert state.cookie_header(WEB_HOST, "/") == "spip_session=test-session"
    assert "restricted=value" in state.cookie_header(WEB_HOST, "/private/page")
    assert not state.cookie_header("challenge01.root-me.org", "/")
    assert "test-session" not in repr(state)
    assert "test-session" not in repr(state.cookies[0])
    assert SessionCookie("a", "b", expires=10**12).valid()
    assert not Session(cookies=(SessionCookie("spip_session", "expired", expires=0),)).spip_session


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "", "value": "x"},
        {"name": "a", "value": "x\n"},
        {"name": "a", "value": "é"},
        {"name": "a", "value": "x", "domain": "evil.example"},
        {"name": "a", "value": "x", "path": "relative"},
        {"name": "a", "value": "x", "expires": float("inf")},
    ],
)
def test_cookie_boundary_validation(fields: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        SessionCookie(**fields)


@pytest.mark.parametrize("agent", ["bad\nagent", "é"])
def test_invalid_agent(agent: str) -> None:
    with pytest.raises(ValueError):
        Session(user_agent=agent)


def test_round_trip_private_atomic_file(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("old")
    os.chmod(path, 0o644)
    state = Session(
        cookies=(SessionCookie("spip_session", "test-session"),), user_agent="Example/1"
    )
    state.save(path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert Session.load(path) == state
    assert list(tmp_path.iterdir()) == [path]


def test_failed_save_cleans_temporary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object) -> None:
        raise OSError("example failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        Session().save(tmp_path / "session.json")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        '{"version":2}',
        '{"version":1}',
        '{"version":1,"user_agent":false,"cookies":[]}',
        '{"version":1,"user_agent":"ok","cookies":false}',
    ],
)
def test_invalid_saved_state(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "state.json"
    path.write_text(payload)
    with pytest.raises(UnexpectedResponseError, match="Invalid SDK session"):
        Session.load(path)


def test_browser_import_discards_external_cookies(tmp_path: Path) -> None:
    path = tmp_path / "browser.json"
    path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "spip_session",
                        "value": "test-session",
                        "domain": ".www.root-me.org",
                        "expires": -1,
                    },
                    {"name": "other", "value": "discarded", "domain": "evil.example"},
                ]
            }
        )
    )
    state = Session.from_browser_state(path, user_agent="Browser/1")
    assert state.spip_session == "test-session"
    assert len(state.cookies) == 1
    assert state.user_agent == "Browser/1"
    path.write_text("{}")
    with pytest.raises(UnexpectedResponseError):
        Session.from_browser_state(path, user_agent="Browser/1")


@pytest.mark.parametrize(
    "data",
    [
        None,
        [None],
        [{}],
        [{"name": 1, "value": "x", "domain": "www.root-me.org"}],
        [{"name": "a", "value": "x", "domain": "www.root-me.org", "expires": "bad"}],
        [{"name": "a", "value": "x;bad", "domain": "www.root-me.org"}],
    ],
)
def test_cookie_json_validation(data: object) -> None:
    with pytest.raises((ValueError, KeyError)):
        _cookies(data)


def test_invalid_state_object() -> None:
    with pytest.raises(ValueError):
        _state(None)
