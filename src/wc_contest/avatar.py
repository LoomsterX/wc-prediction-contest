"""Render a customizable football-kit (jersey) avatar as inline SVG.

Two colours + a pattern (solid / stripes / halves / sash). Used in the app
sidebar, the profile page and the leaderboard podium.
"""

from __future__ import annotations

import html

PATTERNS = ["solid", "stripes", "halves", "sash"]

# Shirt silhouette (torso + shoulders). Sleeves drawn separately so they can
# take the secondary colour. viewBox is 0 0 100 100.
_BODY = ("M50 14 C44 14 40 17 35 17 L18 24 L11 41 L24 48 L32 43 "
         "L32 88 C32 90 33 91 35 91 L65 91 C67 91 68 90 68 88 "
         "L68 43 L76 48 L89 41 L82 24 L65 17 C60 17 56 14 50 14 Z")
_LSLEEVE = "M35 17 L18 24 L11 41 L24 48 L32 43 L34 26 Z"
_RSLEEVE = "M65 17 L82 24 L89 41 L76 48 L68 43 L66 26 Z"
_COLLAR = "M40 17 Q50 27 60 17 L56 15 Q50 20 44 15 Z"


def jersey_svg(primary: str = "#2f81f7", secondary: str = "#ffffff",
               pattern: str = "solid", size: int = 64,
               number: str | None = None) -> str:
    p = html.escape(primary or "#2f81f7")
    s = html.escape(secondary or "#ffffff")
    pat = pattern if pattern in PATTERNS else "solid"
    cid = f"clip{abs(hash((p, s, pat, size))) % 100000}"

    overlay = ""
    if pat == "stripes":
        for x in range(14, 86, 12):
            overlay += f'<rect x="{x}" y="10" width="6" height="85" fill="{s}"/>'
    elif pat == "halves":
        overlay = f'<rect x="50" y="10" width="50" height="90" fill="{s}"/>'
    elif pat == "sash":
        overlay = f'<polygon points="14,40 30,90 46,90 22,32" fill="{s}"/>'

    stroke = 'stroke="rgba(0,0,0,0.28)" stroke-width="1.6"'
    return f'''<svg width="{size}" height="{size}" viewBox="0 0 100 100" \
xmlns="http://www.w3.org/2000/svg" role="img" aria-label="player jersey">
<defs><clipPath id="{cid}"><path d="{_BODY}"/></clipPath></defs>
<path d="{_LSLEEVE}" fill="{s}" {stroke}/>
<path d="{_RSLEEVE}" fill="{s}" {stroke}/>
<path d="{_BODY}" fill="{p}" {stroke}/>
<g clip-path="url(#{cid})">{overlay}</g>
<path d="{_BODY}" fill="none" {stroke}/>
<path d="{_COLLAR}" fill="{s}" {stroke}/>
{_number_svg(number, p, s)}
</svg>'''


def _number_svg(number, primary, secondary):
    if not number:
        return ""
    n = html.escape(str(number))[:2]
    return (f'<text x="50" y="68" text-anchor="middle" font-size="26" '
            f'font-family="Arial, sans-serif" font-weight="700" '
            f'fill="{secondary}" stroke="rgba(0,0,0,0.25)" '
            f'stroke-width="0.6">{n}</text>')


def data_uri(primary, secondary, pattern, size=64) -> str:
    """SVG as a data URI (handy for <img> tags / Streamlit markdown)."""
    import base64
    svg = jersey_svg(primary, secondary, pattern, size)
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"
