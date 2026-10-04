"""Check a distribution's installed public interface outside the source checkout."""

import subprocess
from pathlib import Path


def check(python: Path, directory: str, version: str) -> None:
    """Verify metadata, all exported names and typing without network or browser startup."""
    source = (
        "from importlib.resources import files; from importlib.metadata import version; "
        "import rootme_sdk; from rootme_sdk import RootMeClient; "
        "assert all(hasattr(rootme_sdk, name) for name in rootme_sdk.__all__); "
        "assert files('rootme_sdk').joinpath('py.typed').is_file(); "
        f"assert version('rootme-sdk') == {version!r}; "
        "client = RootMeClient(); client.close()"
    )
    subprocess.run([str(python), "-c", source], cwd=directory, check=True)
