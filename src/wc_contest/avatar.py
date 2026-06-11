"""Render a customizable football-kit (jersey) avatar as pixel-art SVG, plus
tiny neon pixel "players" used for the retro 90's-game background.

Two colours + a pattern (solid / stripes / halves / sash). Used in the app
sidebar, the profile page and the leaderboard podium.
"""

from __future__ import annotations

import base64
import html

PATTERNS = ["solid", "stripes", "halves", "sash"]

# --------------------------------------------------------------------------- #
# Pixel-art jersey on a 12-wide grid (chunky on purpose). Region per cell is
# decided in `_jersey_region`; the pattern recolours body cells.
# --------------------------------------------------------------------------- #
_GW, _GH = 12, 11


def _jersey_region(col: int, row: int) -> str | None:
    # collar notch at the very top centre
    if row == 0 and col in (5, 6):
        return "collar"
    # short sleeves: top 3 rows, outer two columns each side
    if 1 <= row <= 3 and (col in (0, 1) or col in (10, 11)):
        return "sleeve"
    # shoulders (top row over the torso) + torso block (cols 2..9)
    if row == 0 and 2 <= col <= 9:
        return "body"
    if 1 <= row <= 10 and 2 <= col <= 9:
        return "body"
    return None


def _body_fill(col, row, pat, p, s):
    if pat == "stripes":
        return s if col % 2 == 0 else p
    if pat == "halves":
        return s if col >= 6 else p
    if pat == "sash":
        d = (col - 2) - (row * 8 // _GH)
        return s if 0 <= d <= 1 else p
    return p


def jersey_svg(primary: str = "#1801B4", secondary: str = "#ffffff",
               pattern: str = "solid", size: int = 64,
               number: str | None = None) -> str:
    p = html.escape(primary or "#1801B4")
    s = html.escape(secondary or "#ffffff")
    pat = pattern if pattern in PATTERNS else "solid"

    cells = []
    for row in range(_GH):
        for col in range(_GW):
            reg = _jersey_region(col, row)
            if reg is None:
                continue
            if reg in ("sleeve", "collar"):
                fill = s
            else:
                fill = _body_fill(col, row, pat, p, s)
            cells.append(
                f'<rect x="{col}" y="{row}" width="1" height="1" fill="{fill}"/>')
    # faint dark pixel-grid outline so the blocks read as distinct pixels
    grid = (f'<rect x="{col}" y="{row}" width="1" height="1" fill="none" '
            f'stroke="rgba(0,0,0,0.22)" stroke-width="0.06"/>'
            for col in range(_GW) for row in range(_GH)
            if _jersey_region(col, row) is not None)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {_GW} {_GH}" '
            f'xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges" '
            f'role="img" aria-label="player jersey">'
            f'{"".join(cells)}{"".join(grid)}</svg>')


def data_uri(primary, secondary, pattern, size=64) -> str:
    """SVG as a data URI (handy for <img> tags / Streamlit markdown)."""
    svg = jersey_svg(primary, secondary, pattern, size)
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


# --------------------------------------------------------------------------- #
# Tiny neon pixel footballer sprites for the retro background.
# --------------------------------------------------------------------------- #
# X = player silhouette (neon colour), O = ball (white). 9 wide x 11 tall.
_PLAYER_ROWS = [
    "...XX....",
    "...XX....",
    "..XXXX...",
    "XXXXXXXX.",   # arms out
    "..XXXX...",
    "..XXXX...",
    "..X..X...",   # legs split (running)
    ".X....X..",
    ".X.....X.",
    "X.......X",   # feet
    "OO.......",   # ball at the front foot
]


def pixel_player_uri(color: str = "#29f0ff", opacity: float = 0.42) -> str:
    """A small neon pixel footballer as a base64 SVG data URI (for CSS
    backgrounds). `color` is the neon silhouette; a soft blur gives the glow."""
    w = len(_PLAYER_ROWS[0])
    h = len(_PLAYER_ROWS)
    rects = []
    for y, line in enumerate(_PLAYER_ROWS):
        for x, ch in enumerate(line):
            if ch == ".":
                continue
            fill = "#ffffff" if ch == "O" else color
            rects.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{fill}"/>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}" shape-rendering="crispEdges">'
        f'<defs><filter id="g" x="-60%" y="-60%" width="220%" height="220%">'
        f'<feGaussianBlur stdDeviation="0.4" result="b"/>'
        f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter></defs>'
        f'<g filter="url(#g)" opacity="{opacity}">{"".join(rects)}</g></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
