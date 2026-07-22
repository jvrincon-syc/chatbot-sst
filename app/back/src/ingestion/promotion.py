from __future__ import annotations

import shutil
from pathlib import Path
from typing import Mapping


class PromotionError(RuntimeError):
    pass


def promote_candidate(candidate_root: Path, live_root: Path, manifest: Mapping[str, object]) -> None:
    # Require structural validation to have passed. Golden validation is
    # optional for promotion in workflows that don't rely on golden metrics.
    if manifest.get("structural_status") != "passed":
        raise PromotionError("candidate cannot be promoted until structural validation passes")
    if not candidate_root.exists() or not candidate_root.is_dir():
        raise PromotionError("candidate root does not exist")

    backup_root = live_root.with_name(f".{live_root.name}.backup")
    if backup_root.exists():
        shutil.rmtree(backup_root)
    if live_root.exists():
        live_root.rename(backup_root)
    try:
        shutil.copytree(candidate_root, live_root)
    except BaseException:
        if live_root.exists():
            shutil.rmtree(live_root)
        if backup_root.exists():
            backup_root.rename(live_root)
        raise
    else:
        if backup_root.exists():
            shutil.rmtree(backup_root)
