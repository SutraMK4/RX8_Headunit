#!/usr/bin/env python3
"""
tools/fetch_figma_assets.py
---------------------------
Downloads the SVG assets of a Figma frame into assets/<screen>/.

Claude reads the design through the Figma connector, but its cloud
workspace cannot download from figma.com. Your machine can, so this
script does that step. The asset URLs from Figma expire after 7 days.

Run from the repo root:
    py tools/fetch_figma_assets.py home_v2

Uses only the Python standard library.
"""

import os
import sys
import urllib.request

BASE = "https://www.figma.com/api/mcp/asset/{}.svg"

# Asset sets per screen: local file name -> Figma asset id.
# Source: Figma file CBKo9oyYbDV1pKuGCFEcy5, frame 2:2
# "RX-8 · Night drive startup" (read 3 Nov 2026).
ASSETS = {
    "home_v2": {
        "rotary_schematic":    "652cf123-ec81-43c0-8607-e3af1db69a43",
        "tile_surface_active": "90f0d723-3c76-4420-97e9-43cfb47a240c",
        "tile_surface":        "47ac623a-ef7f-44d4-a424-0238b3d15164",
        "arrow_dark":          "9ddff8a1-7292-4562-bda9-ede404a85e80",
        "arrow_light":         "52ffdcee-77b4-4ba6-ba2c-c66649d76b51",
        "icon_gauges_tile":    "175efdc2-61b6-42e9-a261-1d9ea6784f8a",
        "icon_nav_tile":       "8602245f-bada-46ac-bb1a-be0c1ba197d2",
        "icon_audio_tile":     "28a32ecf-332b-489f-b905-734ef8b44319",
        "icon_settings_tile":  "6aa8db05-e906-43c3-9555-72349896c0c4",
        "icon_home_nav":       "df839417-d0a9-4340-9902-1f67291186f9",
        "icon_gauges_nav":     "21b68de0-fa78-4538-9a4a-6cb66126578e",
        "icon_nav_nav":        "aca1caff-6129-4631-b621-3bac7869d7d7",
        "icon_audio_nav":      "462a30d9-2605-452c-afec-fdd3143662b5",
        "icon_settings_nav":   "f818b857-b7a5-4ecc-be29-1c8c608b3d84",
    },
}


def main():
    screen = sys.argv[1] if len(sys.argv) > 1 else "home_v2"
    if screen not in ASSETS:
        print(f"Unknown asset set '{screen}'. Known: {', '.join(ASSETS)}")
        sys.exit(1)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "assets", screen)
    os.makedirs(out_dir, exist_ok=True)

    ok = failed = 0
    for name, asset_id in ASSETS[screen].items():
        path = os.path.join(out_dir, name + ".svg")
        try:
            req = urllib.request.Request(BASE.format(asset_id),
                                         headers={"User-Agent": "rx8-headunit-asset-fetch"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if b"<svg" not in data[:2000]:
                raise ValueError("response is not an SVG (link expired?)")
            with open(path, "wb") as f:
                f.write(data)
            print(f"  ok      {name}.svg  ({len(data)} bytes)")
            ok += 1
        except Exception as e:
            print(f"  FAILED  {name}.svg  {e}")
            failed += 1

    print(f"\n{ok} downloaded, {failed} failed -> {out_dir}")
    if failed:
        print("If the links expired (after 7 days), ask Claude to read the frame again.")


if __name__ == "__main__":
    main()
