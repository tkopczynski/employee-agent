"""`uv run python -m evals` — load → build → run → score → print → exit.

A malformed dataset is a hard error with a nonzero exit, never a silent skip
(PRD US-19): `DatasetError` is caught here and turned into a clean message +
exit 1, the same failing exit code as a breached floor.
"""

import sys
from pathlib import Path

from .loader import DatasetError
from .runner import run

DATASET = Path(__file__).parent / "dataset.yaml"


def main() -> int:
    try:
        return run(DATASET)
    except DatasetError as e:
        print(f"malformed dataset: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
