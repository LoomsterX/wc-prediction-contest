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
# Finer grid → smaller pixels (silhouette defined in normalised coords so the
# resolution is easy to tune).
_GW, _GH = 24, 24


def _jersey_region(col: int, row: int) -> str | None:
    u = (col + 0.5) / _GW          # 0..1 across, 0..1 down
    v = (row + 0.5) / _GH
    # collar notch at the very top centre
    if v <= 0.12 and 0.42 <= u <= 0.58:
        return "collar"
    # short sleeves: top band, outer fifth on each side
    if v <= 0.30 and (u < 0.20 or u > 0.80):
        return "sleeve"
    # torso (centre column, full height) incl. shoulders
    if 0.20 <= u <= 0.80 and v <= 0.98:
        return "body"
    return None


def _body_fill(col, row, pat, p, s):
    if pat == "stripes":
        return s if (col // 2) % 2 == 0 else p        # 2-px vertical stripes
    if pat == "halves":
        return s if col >= _GW // 2 else p
    if pat == "sash":
        return s if (_GW - 10) <= (col + row) <= (_GW - 5) else p
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
            fill = s if reg in ("sleeve", "collar") else _body_fill(col, row, pat, p, s)
            cells.append(
                f'<rect x="{col}" y="{row}" width="1" height="1" fill="{fill}"/>')
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {_GW} {_GH}" '
            f'xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges" '
            f'role="img" aria-label="player jersey">{"".join(cells)}</svg>')


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
