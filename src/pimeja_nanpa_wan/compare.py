"""Report material changes between two generated flag-colour CSVs."""

from __future__ import annotations

import csv
from argparse import ArgumentParser
from pathlib import Path

from .colours import COLOURS


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--minimum", type=float, default=0.1, help="minimum percentage-point change")
    args = parser.parse_args()
    before = {row["iso3"]: row for row in csv.DictReader(args.before.open())}
    after = {row["iso3"]: row for row in csv.DictReader(args.after.open())}
    changes = []
    for iso3 in sorted(before.keys() & after.keys()):
        for colour in COLOURS:
            difference = float(after[iso3][colour]) - float(before[iso3][colour])
            if abs(difference) >= args.minimum:
                changes.append((abs(difference), iso3, colour, difference))
    for _, iso3, colour, difference in sorted(changes, reverse=True):
        print(f"{iso3},{colour},{difference:+.4f}")
    print(f"{len(changes)} changes at or above {args.minimum:g} percentage points")


if __name__ == "__main__":
    main()
