"""Check that every acceptance ID in the spec is mapped in the evidence map."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ACCEPTANCE_ID = re.compile(r"\[ACC-\d{3}\]")


def missing_acceptance_ids(spec_path: Path, evidence_path: Path) -> list[str]:
    """Return sorted acceptance IDs present in spec but absent from evidence."""
    required = set(ACCEPTANCE_ID.findall(spec_path.read_text(encoding="utf-8")))
    if not evidence_path.exists():
        return sorted(id_[1:-1] for id_ in required)
    mapped = set(ACCEPTANCE_ID.findall(evidence_path.read_text(encoding="utf-8")))
    return sorted(id_[1:-1] for id_ in required - mapped)


def main(argv: list[str] | None = None) -> int:
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("spec_path", type=Path)
    parser.add_argument("evidence_path", type=Path)
    args = parser.parse_args(argv)

    missing = missing_acceptance_ids(args.spec_path, args.evidence_path)
    if missing:
        print("Missing acceptance IDs:")
        for item in missing:
            print(f"  {item}")
        return 1
    print("OK: all acceptance IDs are mapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
