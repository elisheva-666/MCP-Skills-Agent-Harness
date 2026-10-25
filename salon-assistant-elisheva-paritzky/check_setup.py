"""Checks the environment before running either version. Never prints secret values."""
import os
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def pinned_versions() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, ver = line.split("==")
            pins[name] = ver
    return pins


def main() -> int:
    ok = True
    print(f"python      {sys.version.split()[0]}")
    print(f"venv        {'yes' if sys.prefix != sys.base_prefix else 'NO - activate .venv first'}")
    ok &= sys.prefix != sys.base_prefix

    for name, want in pinned_versions().items():
        try:
            have = version(name)
        except PackageNotFoundError:
            have = "missing"
        mark = "ok" if have == want else f"MISMATCH (want {want})"
        ok &= have == want
        print(f"{name:<18}{have:<12}{mark}")

    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"API key     {'set' if has_key else 'not set'}  (needed for API/, removed for SDK/)")
    print(f"claude CLI  {'found' if shutil.which('claude') else 'not on PATH (SDK uses its bundled CLI)'}")

    print("\nREADY" if ok else "\nFIX THE LINES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
