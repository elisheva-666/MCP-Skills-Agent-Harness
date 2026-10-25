"""Prints every runtime action tagged with the harness file that performed it."""
import sys

VERBOSE = True


def log(source: str, message: str) -> None:
    if VERBOSE:
        print(f"  [{source:<14}] {message}", file=sys.stderr, flush=True)
