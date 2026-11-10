"""Shared test helpers. Importing this module also makes ``src/`` importable."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
DEMO_SUITE = ROOT / "suites" / "demo_suite.json"


def minimal_suite_dict(**overrides):
    suite = {
        "id": "t", "name": "Test suite", "version": "1",
        "tests": [{"id": "T-1", "title": "First", "steps": [], "verify": "Check it."}],
    }
    suite.update(overrides)
    return suite
