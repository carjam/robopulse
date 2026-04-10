from __future__ import annotations

import os
from pathlib import Path


def shimi_root() -> Path:
    """Resolve the Shimi package root for loading sample data or editable installs."""
    env = os.environ.get("ROBOPULSE_SHIMI_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    # Default: sibling `shimi` next to the robopulse repo root (parent of `src/`).
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    return (repo_root.parent / "shimi").resolve()


def robopulse_repo_root() -> Path:
    """Directory containing `config/`, `src/`, etc."""
    return Path(__file__).resolve().parents[2]
