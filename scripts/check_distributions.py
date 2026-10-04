"""Install both distribution formats in clean offline environments and check exports."""

import subprocess
import sys
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory


def check(artifact: Path) -> None:
    """Verify installation without accidentally importing the working-tree package."""
    with TemporaryDirectory() as directory:
        with Path("pyproject.toml").open("rb") as stream:
            version = tomllib.load(stream)["project"]["version"]
        environment = Path(directory) / "venv"
        subprocess.run(["uv", "venv", "--python", sys.executable, str(environment)], check=True)
        python = environment / "bin" / "python"
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
