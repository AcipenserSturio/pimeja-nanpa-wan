"""Download the two source datasets used by the reproducible pipeline.

Run with ``pdm run download-flag-sources``.  This is intentionally the only
place that performs network I/O: no manually downloaded input is required.
"""

from __future__ import annotations

import json
import subprocess
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
DATA = ROOT / "data"
# jsDelivr mirrors the public GitHub repository and is considerably more
# reliable than raw.githubusercontent.com in restricted build environments.
MAP_URL = "https://cdn.jsdelivr.net/gh/datasets/geo-countries@master/data/countries.geojson"
def fetch(url: str) -> bytes:
    """Fetch via curl, invoked only by this documented pipeline script."""
    return subprocess.run(
        ["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "120", url],
        check=True,
        capture_output=True,
    ).stdout


UN_MEMBER_ISO3 = """AFG ALB DZA AND AGO ATG ARG ARM AUS AUT AZE BHS BHR BGD BRB BLR BEL BLZ BEN BTN BOL BIH BWA BRA BRN BGR BFA BDI CPV KHM CMR CAN CAF TCD CHL CHN COL COM COG COD CRI CIV HRV CUB CYP CZE DNK DJI DMA DOM ECU EGY SLV GNQ ERI EST SWZ ETH FJI FIN FRA GAB GMB GEO DEU GHA GRC GRD GTM GIN GNB GUY HTI HND HUN ISL IND IDN IRN IRQ IRL ISR ITA JAM JPN JOR KAZ KEN KIR PRK KOR KWT KGZ LAO LVA LBN LSO LBR LBY LIE LTU LUX MDG MWI MYS MDV MLI MLT MHL MRT MUS MEX FSM MDA MCO MNG MNE MAR MOZ MMR NAM NRU NPL NLD NZL NIC NER NGA MKD NOR OMN PAK PLW PAN PNG PRY PER PHL POL PRT QAT ROU RUS RWA KNA LCA VCT WSM SMR STP SAU SEN SRB SYC SLE SGP SVK SVN SLB SOM ZAF SSD ESP LKA SDN SUR SWE CHE SYR TJK TZA THA TLS TGO TON TTO TUN TUR TKM TUV UGA UKR ARE GBR USA URY UZB VUT VEN VNM YEM ZMB ZWE""".split()


def property_of(properties: dict, *names: str) -> str:
    for name in names:
        if properties.get(name):
            return str(properties[name])
    raise KeyError(f"None of {names!r} is present in map properties")


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--start", type=int, default=0, help="zero-based member index")
    parser.add_argument("--count", type=int, default=193, help="number of flags to fetch")
    args = parser.parse_args()
    ASSETS.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    # The fixed ISO list makes the definition of country visible and avoids an
    # API key or a vendor's changing membership field.
    if len(UN_MEMBER_ISO3) != 193 or len(set(UN_MEMBER_ISO3)) != 193:
        raise RuntimeError("The UN member list must contain exactly 193 unique codes")
    map_target = DATA / "countries.geojson"
    if not map_target.exists():
        print("Downloading world boundaries...", flush=True)
        map_target.write_bytes(fetch(MAP_URL))
    features = json.loads(map_target.read_text())["features"]
    by_iso3 = {
        property_of(feature["properties"], "ISO_A3", "ISO3166-1-Alpha-3", "iso_a3"): feature["properties"]
        for feature in features
    }
    # This boundary release carries -99 placeholders for these two otherwise
    # ordinary UN members. Its display names are unambiguous.
    for feature in features:
        properties = feature["properties"]
        if properties.get("name") == "France":
            by_iso3["FRA"] = {**properties, "ISO3166-1-Alpha-2": "FR"}
        if properties.get("name") == "Norway":
            by_iso3["NOR"] = {**properties, "ISO3166-1-Alpha-2": "NO"}
    missing = set(UN_MEMBER_ISO3) - set(by_iso3)
    if missing:
        raise RuntimeError(f"Map is missing member codes: {sorted(missing)}")

    manifest = []
    pending: list[tuple[int, str, Path, str]] = []
    members = sorted(UN_MEMBER_ISO3)
    selection = members[args.start : args.start + args.count]
    print(f"Processing flags {args.start + 1}–{args.start + len(selection)} of 193...", flush=True)
    for index, code in enumerate(selection, start=args.start + 1):
        properties = by_iso3[code]
        iso2 = property_of(properties, "ISO_A2", "ISO3166-1-Alpha-2", "iso_a2").lower()
        name = property_of(properties, "ADMIN", "name", "NAME")
        filename = f"{code}.svg"
        target = ASSETS / filename
        source_url = f"https://flagcdn.com/{iso2}.svg"
        if not target.exists():
            pending.append((index, code, target, source_url))
        manifest.append(
            {
                "name": name,
                "iso2": iso2.upper(),
                "iso3": code,
                "flag": filename,
                "source_url": source_url,
            }
        )
    # A small fixed pool is markedly faster on restricted CI networks while
    # remaining modest towards the CDN. Existing files make every batch safe to
    # rerun.
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch, source_url): (index, code, target)
            for index, code, target, source_url in pending
        }
        for future in as_completed(futures):
            index, code, target = futures[future]
            target.write_bytes(future.result())
            print(f"[{index:3}/193] {code}", flush=True)

    # Only write a complete manifest; batch mode never advertises a partial set.
    if len(selection) == 193:
        (ASSETS / "index.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print("Saved 193 flag SVGs, manifest, and world-boundary GeoJSON.")
    else:
        print("Batch complete; rerun with the next --start value.")


if __name__ == "__main__":
    main()
