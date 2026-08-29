# Flag colour atlas

This project measures the flag coverage of every one of the 193 full UN member
states and makes a world SVG for each named colour.

## Reproduce

```bash
pdm install
pdm run download-flag-sources
pdm run analyse-flags
```

On a short-lived CI shell, run the analysis in batches such as
`pdm run analyse-flags --start 0 --count 20`, then increment `--start`; finish
with `pdm run analyse-flags --finalize`. Each country result is safely cached in
`data/analysis_cache/`.

For a local visual check, `pdm run render-map-preview red` renders a PNG preview
to `/tmp/flag-colour-map-preview.png`.

The first command script (which invokes the standard `curl` utility) downloads FlagCDN SVGs for a fixed, reviewed list of the
193 full UN-member ISO codes into `assets/`, plus a boundary GeoJSON from the open
`datasets/geo-countries` repository. The second script writes
`flag_colour_percentages.csv` and `maps/*.svg`. Both remote URLs are recorded in
`download_sources.py` (and each flag URL is also recorded in `assets/index.json`).

## Palette and method

The columns and maps use the nine named flag colour families: red, blue, green,
yellow (gold), black, white (silver), orange, purple, and brown. This includes the
traditional heraldic colours/metals and the three modern flag colours commonly
treated as distinct. Grey is folded into black or white because it is not a distinct
heraldic flag colour.

Flags are rasterised at 1200 × 800 pixels by librsvg (available on the development
machine; it and ImageMagick are the only system prerequisites). RGB is classified by HSV colour family,
which keeps shades of a heraldic colour together. Tiny histogram clusters (fewer
than 12 pixels) are ignored before normalising. The renderer's result is further
limited to colour families explicitly present in the source SVG paint values, so a
red/yellow join cannot create orange coverage on a flag that contains no orange.
Transparent pixels outside a flag's shape are ignored.

Each map is an equirectangular SVG. Member states run from white (0%) to the named
map colour (100%); non-members remain white but retain their boundary outline.
