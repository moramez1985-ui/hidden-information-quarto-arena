"""Game Arena Leaderboard & Elo Rating Aggregator for Hidden-Information Quarto."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _expected_score(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (r_b - r_a) / 400.0))


def build_arena_leaderboard(run_paths: list[Path], k_factor: float = 24.0) -> dict[str, Any]:
    ratings: dict[str, float] = {}
    stats: dict[str, dict[str, Any]] = {}
    match_records: list[dict[str, Any]] = []

    def _ensure(model: str) -> dict[str, Any]:
        ratings.setdefault(model, 1500.0)
        return stats.setdefault(model, {
            "model": model,
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "starter_games": 0,
            "starter_wins": 0,
            "second_games": 0,
            "second_wins": 0,
            "draft_accepted": 0,
            "draft_proposals": 0,
            "safe_selects": 0,
            "select_turns": 0,
            "immediate_wins_taken": 0,
            "immediate_win_opportunities": 0,
        })

    for rp in sorted(run_paths):
        raw = json.loads(rp.read_text(encoding="utf-8"))
        payload = raw
        if isinstance(raw, dict) and isinstance(raw.get("results"), list):
            for item in raw["results"]:
                if isinstance(item, dict) and isinstance(item.get("dictResult"), dict):
                    payload = item["dictResult"]
                    break
        if not isinstance(payload, dict) or "matches" not in payload:
            continue

        models_meta = payload.get("models", {})
        p1_default = str(models_meta.get("player_1", {}).get("model", "google/gemini-3.8-flash"))
        p2_default = str(models_meta.get("player_2", {}).get("model", "anthropic/claude-sonnet-4-6@default"))
        eval_matches = payload.get("evaluator", {}).get("matches", [])

        for idx, m in enumerate(payload.get("matches", [])):
            meta = m.get("match", {})
            assigns = meta.get("assignments", {})
            p1_model = str(assigns.get("player_1", p1_default))
            p2_model = str(assigns.get("player_2", p2_default))
            winner = meta.get("winner")
            starter = meta.get("starting_player", "player_1")
            if winner not in ("player_1", "player_2", "draw"):
                continue

            s1 = _ensure(p1_model)
            s2 = _ensure(p2_model)
            s1["games_played"] += 1
            s2["games_played"] += 1

            if starter == "player_1":
                s1["starter_games"] += 1
                s2["second_games"] += 1
            else:
                s2["starter_games"] += 1
                s1["second_games"] += 1

            if winner == "player_1":
                score1, score2 = 1.0, 0.0
                s1["wins"] += 1
                s2["losses"] += 1
                if starter == "player_1":
                    s1["starter_wins"] += 1
                else:
                    s1["second_wins"] += 1
            elif winner == "player_2":
                score1, score2 = 0.0, 1.0
                s2["wins"] += 1
                s1["losses"] += 1
                if starter == "player_2":
                    s2["starter_wins"] += 1
                else:
                    s2["second_wins"] += 1
            else:
                score1, score2 = 0.5, 0.5
                s1["draws"] += 1
                s2["draws"] += 1

            r1, r2 = ratings[p1_model], ratings[p2_model]
            e1 = _expected_score(r1, r2)
            e2 = _expected_score(r2, r1)
            ratings[p1_model] = round(r1 + k_factor * (score1 - e1), 2)
            ratings[p2_model] = round(r2 + k_factor * (score2 - e2), 2)

            if idx < len(eval_matches):
                ev_m = eval_matches[idx]
                for seat, st in (("player_1", s1), ("player_2", s2)):
                    dm = ev_m.get("draft_metrics", {}).get(seat, {})
                    pm = ev_m.get("piece_strategy_metrics", {}).get(seat, {})
                    st["draft_accepted"] += int(dm.get("draft_accepted", 0))
                    st["draft_proposals"] += int(dm.get("draft_proposals", 0))
                    st["safe_selects"] += int(pm.get("safe_selects", 0))
                    st["select_turns"] += int(pm.get("select_turns", 0))
                    st["immediate_wins_taken"] += int(pm.get("immediate_wins_taken", 0))
                    st["immediate_win_opportunities"] += int(pm.get("immediate_win_opportunities", 0))

            match_records.append({
                "source_file": rp.name,
                "game_index": idx + 1,
                "instance_id": meta.get("instance_id"),
                "starter": starter,
                "winner": winner,
                "p1_model": p1_model,
                "p2_model": p2_model,
            })

    leaderboard = []
    for model, st in stats.items():
        gp = max(1, st["games_played"])
        starter_wr = st["starter_wins"] / st["starter_games"] if st["starter_games"] else 0.0
        second_wr = st["second_wins"] / st["second_games"] if st["second_games"] else 0.0
        # Seat-adjusted win rate gives equal 50/50 weight to 1st-seat and 2nd-seat performance
        seat_adj_wr = 0.5 * (starter_wr + second_wr) if (st["starter_games"] and st["second_games"]) else (st["wins"] / gp)
        leaderboard.append({
            "model": model,
            "elo": ratings[model],
            "games": st["games_played"],
            "record": f"{st['wins']}W-{st['losses']}L-{st['draws']}D",
            "raw_win_rate": round(st["wins"] / gp, 4),
            "seat_adjusted_win_rate": round(seat_adj_wr, 4),
            "starter_win_rate": round(starter_wr, 4),
            "second_seat_win_rate": round(second_wr, 4),
            "draft_precision": round(st["draft_accepted"] / st["draft_proposals"], 4) if st["draft_proposals"] else None,
            "blunder_avoidance": round(st["safe_selects"] / st["select_turns"], 4) if st["select_turns"] else None,
            "win_conversion": round(st["immediate_wins_taken"] / st["immediate_win_opportunities"], 4) if st["immediate_win_opportunities"] else None,
        })

    leaderboard.sort(key=lambda row: row["elo"], reverse=True)
    return {
        "total_completed_games": len(match_records),
        "leaderboard": leaderboard,
        "matches": match_records,
    }


if __name__ == "__main__":
    files = sorted(Path(".").glob("kaggle_run_v*/**/*.run.json"))
    report = build_arena_leaderboard(files)
    print(json.dumps(report, indent=2))
