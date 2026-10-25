"""Settings shared by the API and SDK versions.

Both versions import from here, so the comparison is fair by construction:
same model, same effort, same business data.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODEL = "claude-opus-5-5"
EFFORT = "medium"

BUSINESS = "nechami"
BUSINESS_DIR = ROOT / "shared" / "businesses" / BUSINESS

# Each version keeps its runtime state (memory, history, bookings) in its own folder,
# so the two runs never see each other's data.
STATE_ROOT = ROOT / "state"


def state_dir(version: str) -> Path:
    """Return the state folder for 'api' or 'sdk', creating it if needed."""
    path = STATE_ROOT / version
    path.mkdir(parents=True, exist_ok=True)
    return path
