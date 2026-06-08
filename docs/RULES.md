# World Cup 2026 Prediction Contest — Rules & Scoring

A friendly office prediction competition for the 2026 FIFA World Cup
(11 June – 19 July 2026, hosted by the USA, Canada and Mexico — 48 teams,
12 groups, 104 matches).

There are **three ways to score points**: match-by-match predictions,
one-off tournament-outcome predictions, and wildcards. Your total is the sum
of all three.

---

## 1. Match-by-match predictions

Predict the **scoreline** of every match. You can edit a pick any time up to
that match's kickoff; it locks when the match starts. You score the best
single tier you reach:

| You got… | Example (you / actual) | Points |
|---|---|---|
| The exact scoreline | 2–1 / 2–1 | **5** |
| Correct result **and** goal difference | 2–1 / 3–2 | **3** |
| Correct result only (win / draw / loss) | 2–0 / 4–1 | **2** |
| Wrong result | 2–0 / 0–1 | **0** |

For knockout matches, predict the 90-minute scoreline as usual. If you also
correctly name the team that advances (e.g. you predicted a draw but picked
the right side to go through on penalties), you get a **+1 bonus**.

There are 72 group-stage matches plus 32 knockout matches. Group fixtures are
known now; knockout fixtures open for prediction as each round's teams are
confirmed.

## 2. Tournament-outcome predictions (the "bracket")

Submitted once, locked at the opening match (11 June 2026). Predict who goes
how far:

| Prediction | Points (each) |
|---|---|
| Champion | 25 |
| Runner-up | 15 |
| Third place | 8 |
| Each correct finalist (2 teams) | 10 |
| Each correct semi-finalist (4 teams) | 6 |
| Each correct quarter-finalist (8 teams) | 3 |
| Each correct group winner (12 groups) | 3 |
| Golden Boot (tournament top scorer) | 10 |

Finalists, semi-finalists and quarter-finalists are scored on membership:
if a team you named reaches that stage, you score — the exact slot doesn't
matter. Group winners must match the specific group.

## 3. Wildcards

A handful of fun, one-off side bets, locked at the opening match. Points are
fixed per question (shown in the app). For the numeric "closest guess"
wildcards, points are awarded in bands by how close you are:

| Absolute error | Share of the question's points |
|---|---|
| Exact | 100% |
| Within 3 | 70% |
| Within 7 | 50% |
| Within 15 | 25% |
| Further off | 0% |

The default wildcards:

1. **Total goals** in the whole tournament (number) — 6 pts
2. **Penalty shootout in the Final?** (yes/no) — 4 pts
3. **Golden Boot winner's goal count** (number) — 5 pts
4. **Will a host nation reach the semis?** (yes/no) — 4 pts
5. **Champion's confederation** (UEFA / CONMEBOL / …) — 5 pts
6. **Most goals by one team in a single match** (number) — 4 pts
7. **Dark horse**: a team outside the world top 10 that reaches the QF
   (team) — 8 pts
8. **Total red cards in the group stage** (number) — 4 pts

You can change any of these in `data/wildcards.csv` before launch.

---

## Deadlines

- **Tournament outcomes & wildcards:** lock at the opening match, **11 June 2026**.
- **Match predictions:** each match locks individually at its own kickoff,
  so you can keep predicting later rounds throughout the tournament.

## Tie-breakers

If two players finish level on total points, they are separated by, in order:

1. Most **exact scoreline** hits.
2. Most points from the **tournament-outcome** bracket.
3. Earliest first submission.

## Running the contest

The organiser enters actual results in the app's **Admin** tab as matches
finish, then clicks **Refresh dashboards**. The leaderboard and both
dashboards update automatically. Only results that have been entered count,
so scores build up naturally as the tournament goes on.

*All point values live in `src/wc_contest/config.py` — change them there and
nothing else needs editing.*
