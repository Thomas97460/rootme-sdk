"""Install both distribution formats in clean offline environments and check exports."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory


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
    return environment / "bin" / "python"


def check(artifact: Path) -> None:
    """Verify installation without accidentally importing the working-tree package."""
    with TemporaryDirectory() as directory:
        with Path("pyproject.toml").open("rb") as stream:
            version = tomllib.load(stream)["project"]["version"]
        environment = Path(directory) / "venv"
        python = runtime_environment(environment)
        subprocess.run(
            ["uv", "pip", "install", "--offline", "--python", str(python), str(artifact.resolve())],
            check=True,
        )
        source = (
            "from importlib.resources import files; "
            "from importlib.metadata import version; "
            "from rootme_sdk import RootMeClient, Session; "
            "assert files('rootme_sdk').joinpath('py.typed').is_file(); "
            f"assert version('rootme-sdk') == {version!r}; "
            "client = RootMeClient(api_key='synthetic-key'); "
            "assert client.session.api_key == 'synthetic-key'; client.close()"
        )
        subprocess.run([str(python), "-c", source], cwd=directory, check=True)


if __name__ == "__main__":
    artifacts = list(Path("dist").glob("*.whl")) + list(Path("dist").glob("*.tar.gz"))
    if len(artifacts) != 2:
        raise SystemExit("Expected exactly one wheel and one source archive")
    for artifact in artifacts:
        check(artifact)
