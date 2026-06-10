"""Official 2026 FIFA World Cup draw data (drawn 5 December 2025).

Source: 2026 FIFA World Cup final draw. Group composition is accurate.
Group-stage match dates use each group's confirmed first-match date; the
2nd and 3rd matchday dates are spaced approximately and should be confirmed
against the official FIFA schedule before launch (edit data/fixtures.csv).

48 teams, 12 groups (A-L). Top 2 of each group + 8 best 3rd-placed teams
advance to a Round of 32, then R16, QF, SF and Final (104 matches total).
"""

from __future__ import annotations

# group -> list of (team_name, confederation, is_host)
# Position in the list is the "seed slot" 1..4 used to build the round-robin.
GROUPS: dict[str, list[tuple[str, str, bool]]] = {
    "A": [("Mexico", "CONCACAF", True), ("South Africa", "CAF", False),
          ("South Korea", "AFC", False), ("Czech Republic", "UEFA", False)],
    "B": [("Canada", "CONCACAF", True), ("Bosnia and Herzegovina", "UEFA", False),
          ("Qatar", "AFC", False), ("Switzerland", "UEFA", False)],
    "C": [("Brazil", "CONMEBOL", False), ("Morocco", "CAF", False),
          ("Haiti", "CONCACAF", False), ("Scotland", "UEFA", False)],
    "D": [("United States", "CONCACAF", True), ("Paraguay", "CONMEBOL", False),
          ("Australia", "AFC", False), ("Turkey", "UEFA", False)],
    "E": [("Germany", "UEFA", False), ("Curaçao", "CONCACAF", False),
          ("Ivory Coast", "CAF", False), ("Ecuador", "CONMEBOL", False)],
    "F": [("Netherlands", "UEFA", False), ("Japan", "AFC", False),
          ("Sweden", "UEFA", False), ("Tunisia", "CAF", False)],
    "G": [("Belgium", "UEFA", False), ("Egypt", "CAF", False),
          ("Iran", "AFC", False), ("New Zealand", "OFC", False)],
    "H": [("Spain", "UEFA", False), ("Cape Verde", "CAF", False),
          ("Saudi Arabia", "AFC", False), ("Uruguay", "CONMEBOL", False)],
    "I": [("France", "UEFA", False), ("Senegal", "CAF", False),
          ("Iraq", "AFC", False), ("Norway", "UEFA", False)],
    "J": [("Argentina", "CONMEBOL", False), ("Algeria", "CAF", False),
          ("Austria", "UEFA", False), ("Jordan", "AFC", False)],
    "K": [("Portugal", "UEFA", False), ("DR Congo", "CAF", False),
          ("Uzbekistan", "AFC", False), ("Colombia", "CONMEBOL", False)],
    "L": [("England", "UEFA", False), ("Croatia", "UEFA", False),
          ("Ghana", "CAF", False), ("Panama", "CONCACAF", False)],
}

# Confirmed first-match date for each group's matchday 1.
GROUP_MD1_DATE = {
    "A": "2026-06-11", "B": "2026-06-12", "C": "2026-06-13", "D": "2026-06-12",
    "E": "2026-06-14", "F": "2026-06-14", "G": "2026-06-15", "H": "2026-06-15",
    "I": "2026-06-16", "J": "2026-06-16", "K": "2026-06-17", "L": "2026-06-17",
}

# Round-robin pairing pattern by seed slot (each team plays 3 games).
# (home_slot, away_slot) per matchday.
ROUND_ROBIN = {
    1: [(1, 2), (3, 4)],
    2: [(1, 3), (4, 2)],
    3: [(2, 3), (4, 1)],
}

# Knockout structure: (stage, count). Teams are filled by the admin as the
# tournament progresses; rows are created as placeholders so match-by-match
# predictions can be opened round by round.
KNOCKOUT_STAGES = [
    ("Round of 32", 16, "2026-06-28"),
    ("Round of 16", 8, "2026-07-04"),
    ("Quarter-final", 4, "2026-07-09"),
    ("Semi-final", 2, "2026-07-14"),
    ("Third place", 1, "2026-07-18"),
    ("Final", 1, "2026-07-19"),
]

# Goal-total bins for the "total goals" wildcard (W01): "<100", then 10-wide
# bands 100-109 ... 290-299, then "300+".
TOTAL_GOALS_BINS = (
    ["<100"]
    + [f"{s}-{s + 9}" for s in range(100, 300, 10)]
    + ["300+"]
)

# Predefined wildcard questions. Columns mirror data/wildcards.csv.
# type: number | boolean | choice | team | bin | text
#   bin  -> player picks a band from `options`; admin enters the actual NUMBER
#           as the result and full points are awarded if it falls in the band.
#   text -> free-text answer (e.g. a player's name); case-insensitive match.
WILDCARDS = [
    {
        "wildcard_id": "W01",
        "question": "Total goals scored in the entire tournament",
        "type": "bin",
        "options": "|".join(TOTAL_GOALS_BINS),
        "points": 6,
        "hint": "104 matches. Pick the band you think the final total lands in.",
    },
    {
        "wildcard_id": "W02",
        "question": "Will the Final be decided by a penalty shootout?",
        "type": "boolean",
        "options": "Yes|No",
        "points": 4,
        "hint": "",
    },
    {
        "wildcard_id": "W03",
        "question": "Golden Boot winner's number of goals",
        "type": "number",
        "options": "",
        "points": 5,
        "hint": "Top scorer's final goal tally.",
    },
    {
        "wildcard_id": "W04",
        "question": "Which host nation (USA, Mexico, Canada) will go furthest in the competition?",
        "type": "choice",
        "options": "United States|Mexico|Canada",
        "points": 4,
        "hint": ("If two host nations exit at the same stage, the one knocked "
                 "out by the higher-ranked team counts as having gone furthest."),
    },
    {
        "wildcard_id": "W05",
        "question": "Which confederation will the champion come from?",
        "type": "choice",
        "options": "UEFA|CONMEBOL|CONCACAF|CAF|AFC|OFC",
        "points": 5,
        "hint": "",
    },
    {
        "wildcard_id": "W06",
        "question": "Most goals scored by a single team in one match",
        "type": "number",
        "options": "",
        "points": 4,
        "hint": "The biggest single-team goal haul of the tournament.",
    },
    {
        "wildcard_id": "W07",
        "question": "Dark horse: name a team NOT in the world top 10 that reaches the quarter-finals",
        "type": "team",
        "options": "",
        "points": 8,
        "hint": "High risk, high reward. 0 points if they don't make the QF.",
    },
    {
        "wildcard_id": "W08",
        "question": "Total number of red cards shown in the group stage",
        "type": "number",
        "options": "",
        "points": 4,
        "hint": "Straight reds and second-yellow reds both count.",
    },
    {
        "wildcard_id": "W09",
        "question": "Golden Boot winner (top scorer)",
        "type": "text",
        "options": "",
        "points": 8,
        "hint": "Name the player you think finishes as the tournament's top scorer.",
    },
    {
        "wildcard_id": "W10",
        "question": "Total corner kicks in the entire tournament",
        "type": "number",
        "options": "",
        "points": 4,
        "hint": "All 104 matches combined. Closest gets the most (banded).",
    },
    {
        "wildcard_id": "W11",
        "question": "Total goals scored by defenders in the tournament",
        "type": "number",
        "options": "",
        "points": 5,
        "hint": "Only goals scored by players listed as defenders count (banded).",
    },
    {
        "wildcard_id": "W12",
        "question": "Total goals scored by goalkeepers in the tournament",
        "type": "number",
        "options": "",
        "points": 6,
        "hint": "Rare! Penalties and open play both count (banded).",
    },
    {
        "wildcard_id": "W13",
        "question": "Highest ball-possession % by a team in a single match",
        "type": "number",
        "options": "",
        "points": 4,
        "hint": "The biggest possession share any team records in one match (banded).",
    },
]
