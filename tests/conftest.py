"""@fileoverview Pytest configuration to expose project modules to tests."""

from __future__ import annotations

import sys
from pathlib import Path

# WHY: Tests import project modules directly without a package install step.
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))
