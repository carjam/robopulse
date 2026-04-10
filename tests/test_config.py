from pathlib import Path

from robopulse.config import load_config
from robopulse.paths import robopulse_repo_root


def test_load_default_config() -> None:
    cfg = load_config(robopulse_repo_root() / "config" / "default.json")
    assert cfg.reevaluation_every_n_loans >= 1
    assert cfg.data.lenders_csv.exists(), "Point lenders_csv at Shimi sample data (see README)."
