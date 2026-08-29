"""Classify flag pixels and make CSV and per-colour SVG world maps."""

from __future__ import annotations

import colorsys
import csv
import json
import re
import subprocess
from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from xml.sax.saxutils import escape

from .colours import COLOURS

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
DATA = ROOT / "data"
MAPS = ROOT / "maps"
CSV_PATH = ROOT / "flag_colour_percentages.csv"
CACHE = DATA / "analysis_cache"
# This is intentionally a moderate image rather than a screenshot.  The source
# SVG is rendered by librsvg, then ImageMagick emits an exact colour histogram.
RENDER_WIDTH = 1200
HISTOGRAM_LINE = re.compile(r"\s*(\d+): \((\d+),(\d+),(\d+)(?:,(\d+))?\)")
SVG_HEX_COLOUR = re.compile(
    r"(?<![\w-])#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})(?![\w-])"
)
SVG_NAMED_COLOUR = re.compile(
    r"(?:fill|stroke|stop-color)\s*(?:=|:)\s*[\"']?([A-Za-z]+)", re.IGNORECASE
)
MINIMUM_COLOUR_PIXELS = 12
ANALYSIS_VERSION = 4
SVG_NAMED_FAMILIES = {
    "black": "black",
    "white": "white",
    "silver": "white",
    "grey": "black",
    "gray": "black",
    "red": "red",
    "blue": "blue",
    "green": "green",
    "yellow": "yellow",
    "gold": "yellow",
    "orange": "orange",
    "purple": "purple",
    "brown": "brown",
}


def named_colour(red: int, green: int, blue: int) -> str:
    """Return a heraldic family using HSV ranges, including flag shades."""
    hue, saturation, value = colorsys.rgb_to_hsv(
        red / 255, green / 255, blue / 255
    )
    hue *= 360
    if value < 0.22:
        return "black"
    if saturation < 0.12:
        return "white" if value >= 0.55 else "black"
    # Flag gold is commonly #FECB00 (hue 47.95°), while the orange family
    # occupies the clearly warmer 15–45° band. Keep that standard gold with
    # yellow rather than splitting it at an arbitrary near-identical hue.
    if 15 <= hue < 45:
        return "brown" if value < 0.65 else "orange"
    if hue < 15 or hue >= 330:
        return "red"
    if hue < 75:
        return "yellow"
    if hue < 170:
        return "green"
    if hue < 265:
        return "blue"
    if hue < 330:
        return "purple"
    return "red"


def svg_colour_families(svg_path: Path) -> set[str]:
    """Identify colour families present in SVG paint values.

    SVG's initial value for the ``fill`` property is black. It therefore belongs
    in every allow-list even when no element spells it out, as on Germany's and
    Estonia's black stripes.
    """
    families = {"black"}
    svg = svg_path.read_text(errors="ignore")
    for value in SVG_HEX_COLOUR.findall(svg):
        if len(value) == 3:
            value = "".join(part * 2 for part in value)
        families.add(
            named_colour(
                *(int(value[index : index + 2], 16) for index in (0, 2, 4))
            )
        )
    for value in SVG_NAMED_COLOUR.findall(svg):
        family = SVG_NAMED_FAMILIES.get(value.lower())
        if family:
            families.add(family)
    return families


def percentages(svg_path: Path) -> dict[str, float]:
    """Rasterise and classify substantial non-transparent RGB colour groups."""
    rendered = subprocess.run(
        # Supplying a width but no height makes librsvg calculate the height
        # from each flag's intrinsic SVG dimensions/viewBox. No 3:2 canvas is
        # imposed, and no flag is cropped or stretched.
        ["rsvg-convert", "--width", str(RENDER_WIDTH), str(svg_path)],
        check=True,
        capture_output=True,
    ).stdout
    histogram = subprocess.run(
        ["magick", "png:-", "-format", "%c", "histogram:info:-"],
        input=rendered,
        check=True,
        capture_output=True,
    ).stdout.decode()
    allowed_families = svg_colour_families(svg_path)
    count: Counter[str] = Counter()
    for line in histogram.splitlines():
        match = HISTOGRAM_LINE.match(line)
        if not match:
            continue
        pixels, red, green, blue, alpha = (
            int(part or 255) for part in match.groups()
        )
        family = named_colour(red, green, blue)
        if (
            pixels >= MINIMUM_COLOUR_PIXELS
            and alpha >= 128
            and (not allowed_families or family in allowed_families)
        ):
            count[family] += pixels
    total = sum(count.values())
    return {colour: round(100 * count[colour] / total, 4) for colour in COLOURS}


def svg_path(rings: list[list[list[float]]]) -> str:
    parts = []
    for ring in rings:
        if not ring:
            continue
        coords = [(2 * (point[0] + 180), 2 * (90 - point[1])) for point in ring]
        parts.append(
            "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in coords) + " Z"
        )
    return " ".join(parts)


def interpolate(
    hex_colour: str, fraction: float, *, start: str = "#ffffff"
) -> str:
    fraction = max(0.0, min(1.0, fraction / 100))
    source = tuple(int(start[index : index + 2], 16) for index in (1, 3, 5))
    target = tuple(
        int(hex_colour[index : index + 2], 16) for index in (1, 3, 5)
    )
    rgb = tuple(
        round(first + (last - first) * fraction)
        for first, last in zip(source, target, strict=True)
    )
    return "#" + "".join(f"{channel:02x}" for channel in rgb)


def make_maps(rows: list[dict[str, str]]) -> None:
    geojson = json.loads((DATA / "countries.geojson").read_text())
    values = {row["iso3"]: row for row in rows}
    MAPS.mkdir(exist_ok=True)
    for colour, display in COLOURS.items():
        # White needs contrast at the zero end: a white-to-white scale conveys
        # no data. The muted blue-grey reads as "no white" while remaining
        # clearly distinct from the pale-blue ocean background.
        zero_colour = "#587582" if colour == "white" else "#ffffff"
        sea_colour = "#b8ceda" if colour == "white" else "#dcecf5"
        paths = []
        for feature in geojson["features"]:
            props = feature["properties"]
            iso3 = (
                props.get("ISO_A3")
                or props.get("ISO3166-1-Alpha-3")
                or props.get("iso_a3")
            )
            if iso3 == "-99":
                iso3 = {"France": "FRA", "Norway": "NOR"}.get(
                    props.get("name"), iso3
                )
            value = float(values[iso3][colour]) if iso3 in values else 0
            geometry = feature["geometry"]
            polygons = (
                [geometry["coordinates"]]
                if geometry["type"] == "Polygon"
                else geometry["coordinates"]
            )
            d = " ".join(svg_path(polygon) for polygon in polygons)
            fill = (
                interpolate(display, value, start=zero_colour)
                if iso3 in values
                else "#f2f2f2"
            )
            paths.append(f'<path d="{d}" fill="{fill}"/>')
        title = f"Flag coverage: {colour}"
        content = "\n  ".join(paths)
        (MAPS / f"{colour}.svg").write_text(
            f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 360" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">Each UN member is shaded from {"blue-grey" if colour == "white" else "white"} (0%) to {escape(colour)} (100%) according to the share of its flag classified as {escape(colour)}.</desc>
  <rect width="720" height="360" fill="{sea_colour}"/>
  <g stroke="#6f7880" stroke-width="0.22" fill-rule="evenodd">
  {content}
  </g>
</svg>\n"""
        )


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument(
        "--start", type=int, default=0, help="zero-based manifest index"
    )
    parser.add_argument(
        "--count", type=int, default=193, help="number of flags to analyse"
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="assemble CSV/maps from cached rows only",
    )
    args = parser.parse_args()
    manifest = json.loads((ASSETS / "index.json").read_text())
    CACHE.mkdir(exist_ok=True)

    def analyse_one(index: int, country: dict[str, str]) -> None:
        cache_path = CACHE / f"{country['iso3']}.json"
        cached = (
            json.loads(cache_path.read_text()) if cache_path.exists() else {}
        )
        if cached.get("_analysis_version") != ANALYSIS_VERSION:
            result = percentages(ASSETS / country["flag"])
            row = {
                "country": country["name"],
                "iso2": country["iso2"],
                "iso3": country["iso3"],
            }
            row.update(
                {colour: f"{value:.4f}" for colour, value in result.items()}
            )
            row["_analysis_version"] = ANALYSIS_VERSION
            cache_path.write_text(json.dumps(row) + "\n")
        print(f"[{index:3}/193] {country['iso3']}", flush=True)

    if not args.finalize:
        selection = list(
            enumerate(
                manifest[args.start : args.start + args.count],
                start=args.start + 1,
            )
        )
        print(
            f"Analysing {args.start + 1}–{args.start + len(selection)} of 193...",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(analyse_one, index, country)
                for index, country in selection
            ]
            for future in as_completed(futures):
                future.result()
        if args.start != 0 or args.count != 193:
            print("Batch complete; rerun with the next --start value.")
            return

    missing = [
        country["iso3"]
        for country in manifest
        if not (CACHE / f"{country['iso3']}.json").exists()
    ]
    if missing:
        raise RuntimeError(
            f"Cannot finalize: {len(missing)} cached rows missing (e.g. {missing[:5]})"
        )
    rows: list[dict[str, str]] = []
    for country in manifest:
        row = json.loads((CACHE / f"{country['iso3']}.json").read_text())
        row.pop("_analysis_version", None)
        rows.append(row)
    with CSV_PATH.open("w", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=["country", "iso2", "iso3", *COLOURS]
        )
        writer.writeheader()
        writer.writerows(rows)
    make_maps(rows)
    print(f"Wrote {CSV_PATH.name} and {len(COLOURS)} SVG maps to {MAPS.name}/.")


if __name__ == "__main__":
    main()
