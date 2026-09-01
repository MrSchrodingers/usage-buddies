#!/usr/bin/env python3
"""Write the widget's header mascots from the sprite grids.

The header used to carry its own flat one-colour silhouette while the desktop
companion carried a shaded animated character. Two drawings of the same
creature is not a style, it is a drift, so both come off the same grid now.

Vector rather than PNG because the header scales with the Plasma theme's icon
size; `shape-rendering="crispEdges"` keeps the pixel boundaries hard at any of
them. Horizontal runs are merged into single rects, which is what keeps the
file small enough to read.

Run after changing a sprite grid; tests/test_sprites.py fails if the committed
files fall behind.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buddy_sprites as sprites

ICONS = Path(__file__).resolve().parent.parent / "plasmoid" / "contents" / "icons"
MASCOTS = {"clawd.svg": "claude", "rex.svg": "codex"}
FRAME = "stand_open"


def to_svg(brand, frame=FRAME):
    grid = sprites.build_frames(brand)[frame]
    pal = sprites.PALETTES[brand]

    rows = [i for i, r in enumerate(grid) if set(r) != {"."}]
    cols = [c for r in grid for c, ch in enumerate(r) if ch != "."]
    top, bottom, left, right = rows[0], rows[-1], min(cols), max(cols)
    w, h = right - left + 1, bottom - top + 1

    parts = []
    for r in range(top, bottom + 1):
        c = left
        while c <= right:
            ch = grid[r][c]
            if ch == ".":
                c += 1
                continue
            run = c
            while run <= right and grid[r][run] == ch:
                run += 1
            parts.append(f'<rect x="{c - left}" y="{r - top}" '
                         f'width="{run - c}" height="1" fill="{pal[ch]}"/>')
            c = run

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * 2}" '
            f'height="{h * 2}" viewBox="0 0 {w} {h}" '
            f'shape-rendering="crispEdges">' + "".join(parts) + "</svg>\n")


def main():
    for name, brand in MASCOTS.items():
        path = ICONS / name
        path.write_text(to_svg(brand))
        print(f"{path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}"
              f"  {len(path.read_text())} B")


if __name__ == "__main__":
    main()
