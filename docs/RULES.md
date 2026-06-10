# World Cup 2026 Prediction Contest — Rules & Scoring

A friendly office prediction competition for the 2026 FIFA World Cup
(11 June – 19 July 2026, hosted by the USA, Canada and Mexico — 48 teams,
12 groups, 104 matches).

There are **two ways to score points**: match-by-match predictions and
wildcards. Your total is the sum of both.

---

## 1. Match-by-match predictions

Predict the **scoreline** of every match. You score the best single tier you
reach:

| You got… | Example (you / actual) | Points |
|---|---|---|
| The exact scoreline | 2–1 / 2–1 | **5** |
| Correct result **and** goal difference | 2–1 / 3–2 | **3** |
| Correct result only (win / draw / loss) | 2–0 / 4–1 | **2** |
| Wrong result | 2–0 / 0–1 | **0** |

For knockout matches, predict the 90-minute scoreline as usual. If you also
correctly name the team that advances (e.g. you predicted a draw but picked
the right side to go through on penalties), you get a **+1 bonus**.

There are 72 group-stage matches plus 32 knockout matches.

### Locking in and submitting

- Fill in a group's six scorelines and press **🔒 Lock in Group X picks** —
  that group's filter button turns **green**.
- The **Knockout** tab unlocks only once all **12 groups** are locked in.
- Lock in every knockout round to reveal the **✅ Submit predictions** button.
  Submitting **freezes all of your picks** (groups and knockout).
- Need to change something after submitting? Ask the organiser — they can
  unlock you from **Admin → Manage users**.

## 2. Wildcards

A handful of fun, one-off side bets. Points are fixed per question (shown in
the app). For the numeric "closest guess" wildcards, points are awarded in
bands by how close you are:

| Absolute error | Share of the question's points |
|---|---|
| Exact | 100% |
| Within 3 | 70% |
| Within 7 | 50% |
| Within 15 | 25% |
| Further off | 0% |

The wildcards:

1. **Total goals** in the whole tournament — pick a **band** (`<100`,
   `100–109`, … `300+`). Full points if the actual total lands in your band — 6 pts
2. **Penalty shootout in the Final?** (yes/no) — 4 pts
3. **Golden Boot winner's goal count** (number) — 5 pts
4. **Which host nation (USA, Mexico, Canada) goes furthest?** (choice) — 4 pts.
   If two host nations exit at the same stage, the one knocked out by the
   higher-ranked team counts as having gone furthest.
5. **Champion's confederation** (UEFA / CONMEBOL / …) — 5 pts
6. **Most goals by one team in a single match** (number) — 4 pts
7. **Dark horse**: a team outside the world top 10 that reaches the QF
   (team) — 8 pts
8. **Total red cards in the group stage** (number) — 4 pts
9. **Golden Boot winner** — name the top scorer (text) — 8 pts
10. **Total corner kicks** in the tournament (number) — 4 pts
11. **Goals scored by defenders** (number) — 5 pts
12. **Goals scored by goalkeepers** (number) — 6 pts
13. **Highest single-match possession %** (number) — 4 pts

You can change any of these in `data/wildcards.csv` before launch.

---

## Deadlines

- **Wildcards:** lock at the opening match, **11 June 2026** (or when you press
  **Submit predictions**).
- **Match predictions:** locked when you submit, or when the organiser flips
  the global prediction lock.

## Tie-breakers

If two players finish level on total points, they are separated by, in order:

1. Most **exact scoreline** hits.
2. Most points from **wildcards**.
3. Earliest first submission.

## Running the contest

The organiser enters actual results in the app's **Admin** tab as matches
finish, then clicks **Refresh dashboards**. The leaderboard and both
dashboards update automatically. Only results that have been entered count,
so scores build up naturally as the tournament goes on.

*Match-scoring values live in `src/wc_contest/config.py`; wildcard questions
and their points live in `data/wildcards.csv` (and `seed_data.py`).*
