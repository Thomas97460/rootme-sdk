"""Validate distributable contents and publication metadata without extracting files."""

import tarfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def contents(artifact: Path) -> dict[str, bytes]:
    """Read regular archive members without writing untrusted paths to disk."""
    if artifact.suffix == ".whl":
        with ZipFile(artifact) as archive:
            # orig_filename preserves separators/NULs that ZipInfo normalizes on Windows.
            return {
                member.orig_filename: archive.read(member)
                for member in archive.infolist()
                if not member.is_dir()
            }
    with tarfile.open(artifact) as archive:
        result = {}
        for member in archive.getmembers():
            if not member.isfile():
                raise ValueError("Source archive contains a non-regular member.")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Source archive member is unreadable.")
            result[member.name] = stream.read()
        return result


def validate(artifact: Path, version: str) -> None:
    """Require typed SDK sources, the license and coherent public package metadata."""
    files = contents(artifact)
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or "\0" in name:
            raise ValueError("Unsafe archive path.")
        # Hatch includes this public VCS ignore file in source archives by default.
        if artifact.suffix != ".whl" and len(path.parts) == 2 and path.name == ".gitignore":
            continue
        if any(part.startswith(".") or part in {"dist", "build"} for part in path.parts):
            raise ValueError("Private or generated files in distribution.")
        if path.suffix == ".log":
            raise ValueError("Log file in distribution.")
    metadata_name = "/METADATA" if artifact.suffix == ".whl" else "/PKG-INFO"
    metadata = [body for name, body in files.items() if name.endswith(metadata_name)]
    if len(metadata) != 1:
        raise ValueError("Expected one package metadata file.")
    message = BytesParser().parsebytes(metadata[0])
    if message["Name"] != "rootme-sdk" or message["Version"] != version:
        raise ValueError("Distribution name or version disagrees with project metadata.")
    if message["License-Expression"] != "MIT" or message["License-File"] != "LICENSE":
        raise ValueError("Distribution must declare and include its MIT license.")
    for required in ("rootme_sdk/__init__.py", "rootme_sdk/py.typed", "LICENSE"):
        if not any(("/" + name).endswith("/" + required) for name in files):
            raise ValueError(f"Distribution is missing {required}.")
