import json
from pathlib import Path

import pytest

from rootme_sdk.authentication.credentials import Credentials


def test_memory_and_file_credentials(tmp_path: Path) -> None:
    credentials = Credentials.load("Example", "synthetic-password", None)
    assert credentials.username == "Example" and credentials.password == "synthetic-password"
    assert "synthetic-password" not in repr(credentials)
    source = tmp_path / "credentials.json"
    source.write_text(json.dumps({"login": "Example", "password": "synthetic-password"}))
    assert Credentials.load(None, None, source) == credentials


@pytest.mark.parametrize(
    ("username", "password"),
    [(None, "x"), ("", "x"), (1, "x"), ("Example", ""), ("Example", 1)],
)
def test_invalid_values_are_private(username: object, password: object) -> None:
    with pytest.raises(ValueError) as error:
        Credentials(username, password)
    assert "Example" not in str(error.value)


@pytest.mark.parametrize(
    ("username", "password", "file"),
    [
        ("Example", None, None),
        (None, "x", None),
        ("Example", None, "credentials.json"),
        (None, "x", "credentials.json"),
    ],
)
def test_ambiguous_or_incomplete_sources(
    username: str | None, password: str | None, file: str | None
) -> None:
    with pytest.raises(ValueError):
        Credentials.load(username, password, file)


@pytest.mark.parametrize(
    "content",
    [
        "{synthetic-password",
        "[]",
        "null",
        "{}",
        '{"login":"Example"}',
        '{"login":"Example","password":"x","extra":true}',
        '{"login":"Example","password":1}',
    ],
)
def test_invalid_json_file_does_not_echo_contents(tmp_path: Path, content: str) -> None:
    path = tmp_path / "credentials.json"
    path.write_text(content)
    with pytest.raises(ValueError) as error:
        Credentials.load(None, None, path)
    assert "synthetic-password" not in str(error.value) and "Example" not in str(error.value)


def test_unreadable_or_empty_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="credentials file"):
        Credentials.load(None, None, tmp_path / "missing")
