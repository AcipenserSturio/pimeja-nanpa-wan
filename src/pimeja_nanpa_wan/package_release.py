"""Package the generated public dataset for a GitHub Release asset."""

from __future__ import annotations

import hashlib
import re
import zipfile
from argparse import ArgumentParser
from pathlib import Path


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--version", required=True, help="release label, for example 'latest'")
    args = parser.parse_args()
    version = re.sub(r"[^A-Za-z0-9._-]+", "-", args.version).strip(".-")
    if not version:
        raise ValueError("version must contain at least one letter or digit")

    root = Path(__file__).resolve().parents[2]
    files = [
        root / "flag_colour_percentages.csv",
        root / "assets" / "index.json",
        *sorted((root / "maps").glob("*.svg")),
    ]
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise RuntimeError(f"Cannot package missing generated files: {missing}")

    output = root / "dist" / f"flag-colour-atlas-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    # SVG maps are already highly repetitive. Level 1 keeps CI packaging quick
    # while still producing a portable compressed release download.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for source in files:
            archive.write(source, Path("flag-colour-atlas") / source.relative_to(root))

    checksum = output.with_suffix(output.suffix + ".sha256")
    with output.open("rb") as archive:
        digest = hashlib.file_digest(archive, "sha256").hexdigest()
    checksum.write_text(f"{digest}  {output.name}\n")
    print(output)
    print(checksum)


if __name__ == "__main__":
    main()
