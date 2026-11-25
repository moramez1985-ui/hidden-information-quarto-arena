"""Game Arena Leaderboard & Elo Rating Aggregator for Hidden-Information Quarto."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _expected_score(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (r_b - r_a) / 400.0))


def _extract_result_payload(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("results"), list):
        for item in raw["results"]:
            if isinstance(item, dict) and isinstance(item.get("dictResult"), dict):
                return item["dictResult"]
    if "matches" in raw and isinstance(raw["matches"], list):
        return raw
    return None


def _new_model_stats(model: str) -> dict[str, Any]:
    return {
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
        "blunder_selects": 0,
        "placement_blunders": 0,
        "place_turns": 0,
        "immediate_wins_taken": 0,
        "immediate_win_opportunities": 0,
        "composite_sum": 0.0,
        "composite_weight": 0,
        "discovery_sum": 0.0,
        "discovery_weight": 0,
    }


def _summarize_bucket(stats: dict[str, dict[str, Any]], ratings: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model, st in stats.items():
        gp = max(1, st["games_played"])
        starter_wr = st["starter_wins"] / st["starter_games"] if st["starter_games"] else 0.0
        second_wr = st["second_wins"] / st["second_games"] if st["second_games"] else 0.0
        seat_adj_wr = (
            0.5 * (starter_wr + second_wr)
            if (st["starter_games"] and st["second_games"])
            else (st["wins"] / gp)
        )
        tot_decisions = st["select_turns"] + st["place_turns"]
        tot_blunders = st["blunder_selects"] + st["placement_blunders"]
        blunder_avoid = (
            round((tot_decisions - tot_blunders) / tot_decisions, 4)
            if tot_decisions > 0
            else (round(st["safe_selects"] / st["select_turns"], 4) if st["select_turns"] else None)
        )
        rows.append({
            "model": model,
            "elo": ratings[model],
            "games": st["games_played"],
            "record": f"{st['wins']}W-{st['losses']}L-{st['draws']}D",
            "raw_win_rate": round(st["wins"] / gp, 4),
            "seat_adjusted_win_rate": round(seat_adj_wr, 4),
            "starter_win_rate": round(starter_wr, 4),
            "second_seat_win_rate": round(second_wr, 4),
            "arena_composite_index": round(st["composite_sum"] / st["composite_weight"], 2) if st["composite_weight"] else None,
            "draft_precision": round(st["draft_accepted"] / st["draft_proposals"], 4) if st["draft_proposals"] else None,
            "blunder_avoidance": blunder_avoid,
            "hidden_trait_discovery": round(st["discovery_sum"] / st["discovery_weight"], 4) if st["discovery_weight"] else None,
            "win_conversion": round(st["immediate_wins_taken"] / st["immediate_win_opportunities"], 4) if st["immediate_win_opportunities"] else None,
        })
    rows.sort(key=lambda row: (row["elo"], row["arena_composite_index"] or 0.0), reverse=True)
    return rows


def build_arena_leaderboard(run_paths: list[Path], k_factor: float = 24.0) -> dict[str, Any]:
    overall_ratings: dict[str, float] = {}
    overall_stats: dict[str, dict[str, Any]] = {}
    mode_ratings: dict[str, dict[str, float]] = {}
    mode_stats: dict[str, dict[str, dict[str, Any]]] = {}
    match_records: list[dict[str, Any]] = []
    seen_match_ids: set[str] = set()

    def _ensure(bucket_stats: dict[str, dict[str, Any]], bucket_ratings: dict[str, float], model: str) -> dict[str, Any]:
        bucket_ratings.setdefault(model, 1500.0)
        return bucket_stats.setdefault(model, _new_model_stats(model))

    for rp in sorted(run_paths):
        raw = json.loads(rp.read_text(encoding="utf-8"))
        payload = _extract_result_payload(raw)
        if not payload:
            continue

        models_meta = payload.get("model_metadata") or payload.get("models") or {}
        p1_default = str((models_meta.get("player_1") or {}).get("model", "google/gemini-3.8-flash"))
        p2_default = str((models_meta.get("player_2") or {}).get("model", "anthropic/claude-sonnet-4-6@default"))
        evaluator_block = payload.get("evaluator") or {}
        eval_matches = evaluator_block.get("matches", [])
        series_players = (evaluator_block.get("series_aggregate") or {}).get("players") or {}

        matches_list = payload.get("matches", [])
        series_mode = str(payload.get("mode") or "")
        for idx, m in enumerate(matches_list):
            meta = m.get("match", {})
            mid = str(meta.get("match_id") or f"{rp.name}:{idx}")
            if mid in seen_match_ids:
                continue
            seen_match_ids.add(mid)

            assigns = meta.get("harness_model_tags") or meta.get("assignments") or {}
            p1_model = str(assigns.get("player_1", p1_default))
            p2_model = str(assigns.get("player_2", p2_default))
            mode = str(meta.get("mode") or series_mode or "classic")
            winner = meta.get("winner")
            if winner is None and meta.get("outcome") == "draw":
                winner = "draw"
            starter = str(meta.get("starting_player", "player_1"))
            if winner not in ("player_1", "player_2", "draw"):
                continue

            m_ratings = mode_ratings.setdefault(mode, {})
            m_stats = mode_stats.setdefault(mode, {})

            s1 = _ensure(overall_stats, overall_ratings, p1_model)
            s2 = _ensure(overall_stats, overall_ratings, p2_model)
            ms1 = _ensure(m_stats, m_ratings, p1_model)
            ms2 = _ensure(m_stats, m_ratings, p2_model)

            for a1, a2 in ((s1, s2), (ms1, ms2)):
                a1["games_played"] += 1
                a2["games_played"] += 1
                if starter == "player_1":
                    a1["starter_games"] += 1
                    a2["second_games"] += 1
                else:
                    a2["starter_games"] += 1
                    a1["second_games"] += 1

            if winner == "player_1":
                score1, score2 = 1.0, 0.0
                for a1, a2 in ((s1, s2), (ms1, ms2)):
                    a1["wins"] += 1
                    a2["losses"] += 1
                    if starter == "player_1":
                        a1["starter_wins"] += 1
                    else:
                        a1["second_wins"] += 1
            elif winner == "player_2":
                score1, score2 = 0.0, 1.0
                for a1, a2 in ((s1, s2), (ms1, ms2)):
                    a2["wins"] += 1
                    a1["losses"] += 1
                    if starter == "player_2":
                        a2["starter_wins"] += 1
                    else:
                        a2["second_wins"] += 1
            else:
                score1, score2 = 0.5, 0.5
                for a1, a2 in ((s1, s2), (ms1, ms2)):
                    a1["draws"] += 1
                    a2["draws"] += 1

            r1, r2 = overall_ratings[p1_model], overall_ratings[p2_model]
            overall_ratings[p1_model] = round(r1 + k_factor * (score1 - _expected_score(r1, r2)), 2)
            overall_ratings[p2_model] = round(r2 + k_factor * (score2 - _expected_score(r2, r1)), 2)

            mr1, mr2 = m_ratings[p1_model], m_ratings[p2_model]
            m_ratings[p1_model] = round(mr1 + k_factor * (score1 - _expected_score(mr1, mr2)), 2)
            m_ratings[p2_model] = round(mr2 + k_factor * (score2 - _expected_score(mr2, mr1)), 2)

            if idx < len(eval_matches):
                ev_m = eval_matches[idx]
                for seat, st_all, st_mode in (("player_1", s1, ms1), ("player_2", s2, ms2)):
                    dm = ev_m.get("draft_metrics", {}).get(seat, {})
                    pm = ev_m.get("piece_strategy_metrics", {}).get(seat, {})
                    for target in (st_all, st_mode):
                        target["draft_accepted"] += int(dm.get("accepted", dm.get("draft_accepted", 0)))
                        target["draft_proposals"] += int(dm.get("proposals", dm.get("draft_proposals", 0)))
                        target["safe_selects"] += int(pm.get("safe_selects", 0))
                        target["select_turns"] += int(pm.get("select_turns", 0))
                        target["blunder_selects"] += int(pm.get("blunder_selects", 0))
                        target["placement_blunders"] += int(pm.get("placement_blunders", 0))
                        target["place_turns"] += int(pm.get("place_turns", 0))
                        target["immediate_wins_taken"] += int(pm.get("immediate_wins_taken", 0))
                        target["immediate_win_opportunities"] += int(pm.get("immediate_win_opportunities", 0))

            for seat, st_all, st_mode in (("player_1", s1, ms1), ("player_2", s2, ms2)):
                sp = series_players.get(seat) or {}
                comp = sp.get("arena_composite_index")
                disc = sp.get("hidden_trait_discovery_rate")
                for target in (st_all, st_mode):
                    if isinstance(comp, (int, float)):
                        target["composite_sum"] += float(comp)
                        target["composite_weight"] += 1
                    if isinstance(disc, (int, float)):
                        target["discovery_sum"] += float(disc)
                        target["discovery_weight"] += 1

            match_records.append({
                "source_file": rp.name,
                "mode": mode,
                "game_index": idx + 1,
                "match_id": mid,
                "instance_id": meta.get("instance_id"),
                "starter": starter,
                "winner": winner,
                "p1_model": p1_model,
                "p2_model": p2_model,
            })

    by_mode = {
        mode: {
            "games": sum(1 for r in match_records if r["mode"] == mode),
            "leaderboard": _summarize_bucket(mode_stats[mode], mode_ratings[mode]),
        }
        for mode in sorted(mode_stats)
    }

    return {
        "total_completed_games": len(match_records),
        "modes_included": sorted(mode_stats),
        "unified_leaderboard": _summarize_bucket(overall_stats, overall_ratings),
        "by_mode": by_mode,
        "matches": match_records,
    }


def discover_default_result_files(root: Path = Path(".")) -> list[Path]:
    candidates: list[Path] = []
    for pattern in (
        "final_release_v*/quarto_arena_results.json",
        "final_release_v*/*.run.json",
        "kaggle_run_v*/**/*.run.json",
    ):
        candidates.extend(root.glob(pattern))
    unique = sorted({p.resolve() for p in candidates})
    return unique


if __name__ == "__main__":
    files = discover_default_result_files()
    report = build_arena_leaderboard(files)
    print(json.dumps(report, indent=2))
