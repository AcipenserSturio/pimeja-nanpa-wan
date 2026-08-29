"""Render a map SVG to PNG solely for local visual checking."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import subprocess


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("colour", choices=("red", "blue", "green", "yellow", "black", "white", "orange", "purple", "brown"))
    parser.add_argument("--output", type=Path, default=Path("/tmp/flag-colour-map-preview.png"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    subprocess.run(["rsvg-convert", "--width", "1440", "--output", str(args.output), str(root / "maps" / f"{args.colour}.svg")], check=True)
    print(args.output)


if __name__ == "__main__":
    main()
