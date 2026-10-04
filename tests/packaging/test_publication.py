import hashlib
import io
import tarfile
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest

from scripts.check_artifact_contents import contents, validate
from scripts.verify_pypi import published_metadata, verify_hashes


def wheel(tmp_path: Path, *, extra: str | None = None, version: str = "0.3.0") -> Path:
    artifact = tmp_path / "rootme_sdk-0.3.0-py3-none-any.whl"
    with ZipFile(artifact, "w") as archive:
        archive.writestr("rootme_sdk/__init__.py", "")
        archive.writestr("rootme_sdk/py.typed", "")
        archive.writestr("rootme_sdk-0.3.0.dist-info/licenses/LICENSE", "MIT")
        archive.writestr(
            "rootme_sdk-0.3.0.dist-info/METADATA",
            f"Name: rootme-sdk\nVersion: {version}\n"
            "License-Expression: MIT\nLicense-File: LICENSE\n",
        )
        if extra:
            archive.writestr(extra, "synthetic")
    return artifact


def test_valid_wheel_and_version_guard(tmp_path: Path) -> None:
    validate(wheel(tmp_path), "0.3.0")
    with pytest.raises(ValueError, match="version"):
        validate(wheel(tmp_path, version="0.2.0"), "0.3.0")


@pytest.mark.parametrize(
    "name",
    [
        ".secrets/credentials.json",
        "../escape",
        "/absolute",
        "x\\y",
        "debug.log",
        "build/output",
        "package/.env",
    ],
)
def test_reject_private_generated_and_unsafe_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        validate(wheel(tmp_path, extra=name), "0.3.0")


def test_source_archive_and_symlink_guard(tmp_path: Path) -> None:
    artifact = tmp_path / "example.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        member = tarfile.TarInfo("package/README.md")
        member.size = 3
        archive.addfile(member, io.BytesIO(b"sdk"))
    assert contents(artifact) == {"package/README.md": b"sdk"}
    with tarfile.open(artifact, "w:gz") as archive:
        member = tarfile.TarInfo("package/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/private"
        archive.addfile(member)
    with pytest.raises(ValueError, match="non-regular"):
        contents(artifact)


def test_source_archive_keeps_public_ignore_file_but_not_nested_secrets(tmp_path: Path) -> None:
    artifact = wheel(tmp_path)
    source = tmp_path / "source.tar.gz"
    with ZipFile(artifact) as wheel_archive, tarfile.open(source, "w:gz") as source_archive:
        for name in wheel_archive.namelist():
            body = wheel_archive.read(name)
            member = tarfile.TarInfo("package/" + name.replace("METADATA", "PKG-INFO"))
            member.size = len(body)
            source_archive.addfile(member, io.BytesIO(body))
        member = tarfile.TarInfo("package/.gitignore")
        member.size = 10
        source_archive.addfile(member, io.BytesIO(b".secrets/\n"))
    validate(source, "0.3.0")


def test_pypi_hashes_must_match_both_build_artifacts(tmp_path: Path) -> None:
    artifacts = [wheel(tmp_path), tmp_path / "rootme_sdk-0.3.0.tar.gz"]
    artifacts[1].write_bytes(b"synthetic source distribution")
    urls = [
        {
            "filename": file.name,
            "digests": {"sha256": hashlib.sha256(file.read_bytes()).hexdigest()},
            "yanked": False,
        }
        for file in artifacts
    ]
    verify_hashes(artifacts, {"urls": urls})
    urls[0]["digests"] = {"sha256": "different"}
    with pytest.raises(ValueError, match="differ"):
        verify_hashes(artifacts, {"urls": urls})


@pytest.mark.parametrize(
    "urls",
    [
        None,
        [],
        [None, None],
        [{"filename": "x"}, {}],
        [{"yanked": True, "digests": {}}, {}],
        [{"filename": "x", "digests": {}}, {"filename": "x", "digests": {}}],
    ],
)
def test_reject_incomplete_or_unsafe_pypi_metadata(tmp_path: Path, urls: object) -> None:
    artifacts = [wheel(tmp_path), tmp_path / "source.tar.gz"]
    artifacts[1].write_bytes(b"source")
    with pytest.raises(ValueError):
        verify_hashes(artifacts, {"urls": urls})


def test_wait_for_index_visibility_without_republishing(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            httpx.Response(404, request=httpx.Request("GET", "https://pypi.org")),
            httpx.Response(
                200, json={"urls": []}, request=httpx.Request("GET", "https://pypi.org")
            ),
        ]
    )
    delays = []
    monkeypatch.setattr("scripts.verify_pypi.httpx.get", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("scripts.verify_pypi.time.sleep", delays.append)
    assert published_metadata("0.3.0") == {"urls": []}
    assert delays == [5]


def test_index_errors_are_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.verify_pypi.httpx.get",
        lambda *args, **kwargs: httpx.Response(
            403, request=httpx.Request("GET", "https://pypi.org")
        ),
    )
    with pytest.raises(httpx.HTTPStatusError):
        published_metadata("0.3.0")
