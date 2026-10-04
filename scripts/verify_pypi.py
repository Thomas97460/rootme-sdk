"""Verify published hashes and an isolated install from the production PyPI index."""

import hashlib
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from scripts.check_installed_package import check as check_installed


def verify_hashes(artifacts: list[Path], payload: dict[str, object]) -> None:
    """Reject missing, additional or different files for the published version."""
    expected = {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in artifacts}
    urls = payload.get("urls")
    if not isinstance(urls, list) or len(urls) != len(expected):
        raise ValueError("PyPI does not expose exactly the built distributions.")
    observed = {}
    for entry in urls:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("digests"), dict)
            or not isinstance(entry.get("filename"), str)
        ):
            raise ValueError("Invalid PyPI artifact metadata.")
        if entry.get("yanked") or entry.get("filename") in observed:
            raise ValueError("PyPI artifact is duplicated or yanked.")
        observed[entry.get("filename")] = entry["digests"].get("sha256")
    if observed != expected:
        raise ValueError("PyPI distributions differ from the validated build.")


def published_metadata(version: str) -> dict[str, object]:
    """Wait briefly for PyPI's version API, without retrying a publication."""
    url = f"https://pypi.org/pypi/rootme-sdk/{version}/json"
    for attempt in range(10):
        response = httpx.get(url, timeout=15, trust_env=False)
        if response.status_code != 404 or attempt == 9:
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Invalid PyPI response.")
            return payload
        time.sleep(5)
    raise RuntimeError("PyPI verification did not complete.")


def verify_install(version: str) -> None:
    """Resolve the exact published release and import it outside the working tree."""
    with TemporaryDirectory() as directory:
        environment = Path(directory) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        python = environment / "bin/python"
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-cache-dir",
                "--index-url",
                "https://pypi.org/simple",
                f"rootme-sdk=={version}",
            ],
            cwd=directory,
            check=True,
        )
        check_installed(python, directory, version)


if __name__ == "__main__":
    with Path("pyproject.toml").open("rb") as stream:
        release_version = tomllib.load(stream)["project"]["version"]
    distributions = list(Path("dist").glob("*.whl")) + list(Path("dist").glob("*.tar.gz"))
    if len(distributions) != 2:
        raise SystemExit("Expected the validated wheel and source archive")
    verify_hashes(distributions, published_metadata(release_version))
    verify_install(release_version)
