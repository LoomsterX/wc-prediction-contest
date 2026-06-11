# TODO log

## Done (this round)

1. **Home — points progress bar.** Earned points vs total possible (fixed
   ceiling = `104 × MATCH_EXACT_SCORE` + sum of wildcard points). Fills as the
   admin enters results; caption shows how many matches have results in.
2. **Home — today's matches.** Lists matches kicking off today in Norwegian
   time (Europe/Oslo, +2 CEST fallback), with the user's prediction. Knockout
   match-ups use the player's derived bracket.
3. **Home — ranking summary.** Rank, points, and deficit to the leader.
4. **Admin — per-stage locks.** Replaced the single global "Predictions locked"
   toggle with: 12 per-group toggles + a knockout toggle + a wildcards toggle.
   Locking a stage freezes it for everyone; open stages stay editable so late
   registrants can still enter them. Per-player final submit still applies on
   top.

### How locking now works
- `db.py`: `group_pred_locked` / `knockout_pred_locked` / `wildcards_pred_locked`
  (+ setters), `any_group_pred_locked`, `any_stage_locked`. Stored as settings
  `glock_group_<X>` / `glock_knockout` / `glock_wildcards`.
- App helpers: `group_editable(g, pid)`, `knockout_editable(pid)`,
  `wildcards_editable(pid)`, `reveal_others()`. The old `editing_open` /
  `player_locked` / single `predictions_locked` toggle were removed from the UI
  (the `predictions_locked` DB helper is kept but unused).
- "Compare everyone" on the Predictions page unlocks once any stage is locked.

## Notes / context
- Knockout matchups derive per-player from group predictions
  (`src/wc_contest/knockout.py` + `data/knockout_bracket.json`).
- Per-player lock-in state: `pred_locks` table (`group:<X>`, `ko:<stage>`,
  `final`); helpers in `db.py`.
- Scoring: `src/wc_contest/scoring.py` (`leaderboard_rows`, `compute_scores`).

## Possible follow-ups (not requested)
- Centered visual knockout bracket (still a simple per-round grid).
- Wildcard lock currently independent; confirm desired lock *timing* vs kickoff.
