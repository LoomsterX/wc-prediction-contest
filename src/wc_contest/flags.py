"""Emoji flags + 3-letter FIFA codes for the 48 World Cup 2026 teams.

Used to render visual match cards. `chip(name)` returns a small HTML snippet
(flag + code + name) for use inside st.markdown(unsafe_allow_html=True).
"""

from __future__ import annotations

import html

# name -> (flag emoji, FIFA 3-letter code)
TEAM_META: dict[str, tuple[str, str]] = {
    "Mexico": ("🇲🇽", "MEX"),
    "South Africa": ("🇿🇦", "RSA"),
    "South Korea": ("🇰🇷", "KOR"),
    "Czech Republic": ("🇨🇿", "CZE"),
    "Canada": ("🇨🇦", "CAN"),
    "Bosnia and Herzegovina": ("🇧🇦", "BIH"),
    "Qatar": ("🇶🇦", "QAT"),
    "Switzerland": ("🇨🇭", "SUI"),
    "Brazil": ("🇧🇷", "BRA"),
    "Morocco": ("🇲🇦", "MAR"),
    "Haiti": ("🇭🇹", "HAI"),
    "Scotland": ("🏴󠁧󠁢󠁳󠁣󠁴󠁿", "SCO"),
    "United States": ("🇺🇸", "USA"),
    "Paraguay": ("🇵🇾", "PAR"),
    "Australia": ("🇦🇺", "AUS"),
    "Turkey": ("🇹🇷", "TUR"),
    "Germany": ("🇩🇪", "GER"),
    "Curaçao": ("🇨🇼", "CUW"),
    "Ivory Coast": ("🇨🇮", "CIV"),
    "Ecuador": ("🇪🇨", "ECU"),
    "Netherlands": ("🇳🇱", "NED"),
    "Japan": ("🇯🇵", "JPN"),
    "Sweden": ("🇸🇪", "SWE"),
    "Tunisia": ("🇹🇳", "TUN"),
    "Belgium": ("🇧🇪", "BEL"),
    "Egypt": ("🇪🇬", "EGY"),
    "Iran": ("🇮🇷", "IRN"),
    "New Zealand": ("🇳🇿", "NZL"),
    "Spain": ("🇪🇸", "ESP"),
    "Cape Verde": ("🇨🇻", "CPV"),
    "Saudi Arabia": ("🇸🇦", "KSA"),
    "Uruguay": ("🇺🇾", "URU"),
    "France": ("🇫🇷", "FRA"),
    "Senegal": ("🇸🇳", "SEN"),
    "Iraq": ("🇮🇶", "IRQ"),
    "Norway": ("🇳🇴", "NOR"),
    "Argentina": ("🇦🇷", "ARG"),
    "Algeria": ("🇩🇿", "ALG"),
    "Austria": ("🇦🇹", "AUT"),
    "Jordan": ("🇯🇴", "JOR"),
    "Portugal": ("🇵🇹", "POR"),
    "DR Congo": ("🇨🇩", "COD"),
    "Uzbekistan": ("🇺🇿", "UZB"),
    "Colombia": ("🇨🇴", "COL"),
    "England": ("🏴󠁧󠁢󠁥󠁮󠁧󠁿", "ENG"),
    "Croatia": ("🇭🇷", "CRO"),
    "Ghana": ("🇬🇭", "GHA"),
    "Panama": ("🇵🇦", "PAN"),
}


def flag(name: str | None) -> str:
    if not name:
        return "🏳️"
    return TEAM_META.get(name, ("🏳️", ""))[0]


def code(name: str | None) -> str:
    if not name:
        return ""
    return TEAM_META.get(name, ("", (name or "")[:3].upper()))[1] or name[:3].upper()


def chip(name: str | None, *, placeholder: str = "TBD") -> str:
    """flag + code + full name as inline HTML (safe for st.markdown)."""
    if not name:
        return (f'<span class="tchip tchip-tbd">🏳️ '
                f'<span class="tchip-name">{html.escape(placeholder)}</span></span>')
    fl, cd = TEAM_META.get(name, ("🏳️", name[:3].upper()))
    return (f'<span class="tchip"><span class="tchip-flag">{fl}</span>'
            f'<span class="tchip-code">{html.escape(cd)}</span>'
            f'<span class="tchip-name">{html.escape(name)}</span></span>')
