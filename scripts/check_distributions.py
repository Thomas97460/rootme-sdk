"""Install both distribution formats in clean offline environments and check exports."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.check_artifact_contents import validate
from scripts.check_installed_package import check as check_installed


def runtime_environment(environment: Path) -> Path:
    """Install locked runtime dependencies without assuming cached index metadata."""
    subprocess.run(
        [
            "uv",
            "sync",
            "--frozen",
            "--offline",
            "--no-dev",
            "--no-install-project",
            "--python",
            sys.executable,
        ],
        env={
            **os.environ,
            "UV_PROJECT_ENVIRONMENT": str(environment),
            "VIRTUAL_ENV": str(environment),
        },
        check=True,
    )
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def check(artifact: Path, version: str) -> None:
    """Verify installation without accidentally importing the working-tree package."""
    with TemporaryDirectory() as directory:
        validate(artifact, version)
        environment = Path(directory) / "venv"
        python = runtime_environment(environment)
        subprocess.run(
            ["uv", "pip", "install", "--offline", "--python", str(python), str(artifact.resolve())],
            check=True,
        )
        check_installed(python, directory, version)


if __name__ == "__main__":
    with Path("pyproject.toml").open("rb") as stream:
        release_version = tomllib.load(stream)["project"]["version"]
    artifacts = list(Path("dist").glob("*.whl")) + list(Path("dist").glob("*.tar.gz"))
    if len(artifacts) != 2:
        raise SystemExit("Expected exactly one wheel and one source archive")
    for artifact in artifacts:
        check(artifact, release_version)
