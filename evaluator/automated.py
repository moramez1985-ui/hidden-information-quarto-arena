from __future__ import annotations
import re

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from quarto_engine import find_winning_lines

from quarto_engine import WINNING_LINES, legal_actions, new_game, place_piece, select_piece


AUTOMATED_REPORT_SCHEMA_VERSION = 1


def _extract_payload(data: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if "results" in data and isinstance(data["results"], list) and data["results"]:
        first = data["results"][0]
        if isinstance(first, Mapping) and isinstance(first.get("dictResult"), Mapping):
            return "kaggle_run", dict(first["dictResult"])
    if "matches" in data and isinstance(data["matches"], list):
        return "restricted_log", dict(data)
    if "match_id" in data and ("audit_snapshot" in data or "public_replay" in data):
        if "audit_snapshot" in data:
            return "restricted_log", {"matches": [dict(data)]}
        return "kaggle_run", dict(data)
    raise ValueError("Unsupported input format for automated evaluator.")


def _evaluate_draft(draft_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_player: dict[str, dict[str, Any]] = {
        "player_1": {"proposals": 0, "accepted": 0, "rejected": 0, "owned_features": []},
        "player_2": {"proposals": 0, "accepted": 0, "rejected": 0, "owned_features": []},
    }
    for entry in draft_history:
        player = entry.get("player")
        if player not in by_player:
            continue
        by_player[player]["proposals"] += 1
        if entry.get("accepted") is True:
            by_player[player]["accepted"] += 1
            feat = entry.get("attribute_id") or entry.get("feature_id")
            if isinstance(feat, str):
                by_player[player]["owned_features"].append(feat)
        else:
            by_player[player]["rejected"] += 1

    for p_data in by_player.values():
        props = p_data["proposals"]
        p_data["draft_precision"] = round(p_data["accepted"] / props, 4) if props > 0 else 0.0
    return by_player


def _evaluate_piece_strategy(
    *,
    starting_player: str,
    public_history: Sequence[Mapping[str, Any]],
    entity_to_piece: Mapping[str, int],
    bit_owners: Mapping[int, str],
) -> dict[str, Any]:
    state = new_game("classic", starting_player=starting_player, bit_owners=bit_owners)
    stats: dict[str, dict[str, int]] = {
        "player_1": {
            "select_turns": 0,
            "safe_selects": 0,
            "trap_selects": 0,
            "blunder_selects": 0,
            "placement_blunders": 0,
            "place_turns": 0,
            "self_bit_aligned_places": 0,
            "immediate_win_opportunities": 0,
            "immediate_wins_taken": 0,
        },
        "player_2": {
            "select_turns": 0,
            "safe_selects": 0,
            "trap_selects": 0,
            "blunder_selects": 0,
            "placement_blunders": 0,
            "place_turns": 0,
            "self_bit_aligned_places": 0,
            "immediate_win_opportunities": 0,
            "immediate_wins_taken": 0,
        },
    }

    def _piece_gives_win_for_player(piece_id: int, target_player: str, board: Sequence[int | None]) -> bool:
        for cell_idx, existing in enumerate(board):
            if existing is not None:
                continue
            for line in WINNING_LINES:
                if cell_idx not in line:
                    continue
                line_pieces = [piece_id if c == cell_idx else board[c] for c in line]
                if any(p is None for p in line_pieces):
                    continue
                for bit in range(4):
                    if bit_owners.get(bit) != target_player:
                        continue
                    vals = [(int(p) >> bit) & 1 for p in line_pieces]  # type: ignore[arg-type]
                    if len(set(vals)) == 1:
                        return True
        return False

    def _max_own_bit_alignment(cell_idx: int, piece_id: int, player: str, board: Sequence[int | None]) -> int:
        best = 0
        for line in WINNING_LINES:
            if cell_idx not in line:
                continue
            others = [board[c] for c in line if c != cell_idx and board[c] is not None]
            if not others:
                continue
            for bit in range(4):
                if bit_owners.get(bit) != player:
                    continue
                p_val = (piece_id >> bit) & 1
                if all(((int(o) >> bit) & 1) == p_val for o in others):
                    best = max(best, len(others) + 1)
        return best

    for move in public_history:
        kind = move.get("kind")
        player = move.get("player")
        if player not in stats or state.is_terminal:
            break
        if kind == "select_entity":
            entity_id = move["entity_id"]
            chosen_piece = int(entity_to_piece[entity_id])
            opponent = "player_2" if player == "player_1" else "player_1"
            legal = legal_actions(state)
            candidate_pieces = [int(p) for p in legal.get("piece_ids", ())]
            safe_candidates = [
                p for p in candidate_pieces if not _piece_gives_win_for_player(p, opponent, state.board)
            ]
            if safe_candidates:
                stats[player]["select_turns"] += 1
                if chosen_piece in safe_candidates:
                    stats[player]["safe_selects"] += 1
                    if _piece_gives_win_for_player(chosen_piece, player, state.board):
                        stats[player]["trap_selects"] += 1
                else:
                    stats[player]["blunder_selects"] += 1
            state = select_piece(state, player, chosen_piece)
        elif kind == "place_entity":
            chosen_cell = int(move["cell"])
            selected_piece = int(state.selected_piece)  # type: ignore[arg-type]
            stats[player]["place_turns"] += 1
            opponent = "player_2" if player == "player_1" else "player_1"
            legal_now = legal_actions(state)
            legal_cells_now = [int(c) for c in legal_now.get("cells", ())]
            board_after_place = [
                selected_piece if idx == chosen_cell else state.board[idx] for idx in range(16)
            ]
            self_wins_now = bool(find_winning_lines(board_after_place, bit_owners=bit_owners, owner=player))
            opp_wins_now = bool(find_winning_lines(board_after_place, bit_owners=bit_owners, owner=opponent))
            if opp_wins_now and not self_wins_now:
                safe_cells = [
                    c for c in legal_cells_now
                    if not find_winning_lines(
                        [selected_piece if idx == c else state.board[idx] for idx in range(16)],
                        bit_owners=bit_owners,
                        owner=opponent,
                    )
                ]
                if safe_cells:
                    stats[player]["placement_blunders"] += 1
            winning_cells = [
                c
                for c in legal_cells_now
                if find_winning_lines(
                    [selected_piece if idx == c else state.board[idx] for idx in range(16)],
                    bit_owners=bit_owners,
                    owner=player,
                )
                and not find_winning_lines(
                    [selected_piece if idx == c else state.board[idx] for idx in range(16)],
                    bit_owners=bit_owners,
                    owner=opponent,
                )
            ]
            if winning_cells:
                stats[player]["immediate_win_opportunities"] += 1
                if chosen_cell in winning_cells:
                    stats[player]["immediate_wins_taken"] += 1
            if _max_own_bit_alignment(chosen_cell, selected_piece, player, state.board) >= 2:
                stats[player]["self_bit_aligned_places"] += 1
            state = place_piece(state, player, chosen_cell)

    summary: dict[str, Any] = {}
    for p, s in stats.items():
        sel_t = s["select_turns"]
        plc_t = s["place_turns"]
        tot_dec = sel_t + plc_t
        tot_bln = s["blunder_selects"] + s["placement_blunders"]
        win_opp = s["immediate_win_opportunities"]
        summary[p] = {
            **s,
            "strategic_trap_rate": round(s["trap_selects"] / sel_t, 4) if sel_t > 0 else "N/A",
            "blunder_avoidance_rate": round((tot_dec - tot_bln) / tot_dec, 4) if tot_dec > 0 else "N/A",
            "self_bit_alignment_rate": round(s["self_bit_aligned_places"] / plc_t, 4) if plc_t > 0 else "N/A",
            "immediate_win_conversion_rate": round(s["immediate_wins_taken"] / win_opp, 4) if win_opp > 0 else "N/A",
        }
    return summary


def _build_series_aggregate(match_reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not match_reports:
        return {"completed_games": 0}
    wins = {"player_1": 0, "player_2": 0, "draw": 0}
    by_player: dict[str, dict[str, float]] = {
        "player_1": {
            "draft_proposals": 0.0,
            "draft_accepted": 0.0,
            "select_turns": 0.0,
            "safe_selects": 0.0,
            "trap_selects": 0.0,
            "blunder_selects": 0.0,
            "placement_blunders": 0.0,
            "place_turns": 0.0,
            "self_bit_aligned_places": 0.0,
            "immediate_win_opportunities": 0.0,
            "immediate_wins_taken": 0.0,
        },
        "player_2": {
            "draft_proposals": 0.0,
            "draft_accepted": 0.0,
            "select_turns": 0.0,
            "safe_selects": 0.0,
            "trap_selects": 0.0,
            "blunder_selects": 0.0,
            "placement_blunders": 0.0,
            "place_turns": 0.0,
            "self_bit_aligned_places": 0.0,
            "immediate_win_opportunities": 0.0,
            "immediate_wins_taken": 0.0,
        },
    }
    for rep in match_reports:
        out = rep.get("outcome", {}) if isinstance(rep.get("outcome"), Mapping) else {}
        winner = out.get("winner")
        if winner in ("player_1", "player_2"):
            wins[winner] += 1
        elif out.get("outcome") == "draw":
            wins["draw"] += 1
        dm = rep.get("draft_metrics", {}) if isinstance(rep.get("draft_metrics"), Mapping) else {}
        psm = rep.get("piece_strategy_metrics", {}) if isinstance(rep.get("piece_strategy_metrics"), Mapping) else {}
        for p in ("player_1", "player_2"):
            pd = dm.get(p, {}) if isinstance(dm.get(p), Mapping) else {}
            by_player[p]["draft_proposals"] += float(pd.get("proposals", 0))
            by_player[p]["draft_accepted"] += float(pd.get("accepted", 0))
            ps = psm.get(p, {}) if isinstance(psm.get(p), Mapping) else {}
            for k in (
                "select_turns",
                "safe_selects",
                "trap_selects",
                "blunder_selects",
                "placement_blunders",
                "place_turns",
                "self_bit_aligned_places",
                "immediate_win_opportunities",
                "immediate_wins_taken",
            ):
                by_player[p][k] = by_player[p].get(k, 0.0) + float(ps.get(k, 0))

    summary_players: dict[str, Any] = {}
    for p, stats in by_player.items():
        tot_decisions = stats["select_turns"] + stats["place_turns"]
        tot_blunders = stats["blunder_selects"] + stats["placement_blunders"]
        summary_players[p] = {
            "wins": wins[p],
            "win_rate": round(wins[p] / len(match_reports), 4),
            "draft_proposals": int(stats["draft_proposals"]),
            "draft_accepted": int(stats["draft_accepted"]),
            "draft_precision": round(stats["draft_accepted"] / stats["draft_proposals"], 4) if stats["draft_proposals"] > 0 else 0.0,
            "select_turns": int(stats["select_turns"]),
            "safe_selects": int(stats["safe_selects"]),
            "trap_selects": int(stats["trap_selects"]),
            "strategic_trap_rate": round(stats["trap_selects"] / stats["select_turns"], 4) if stats["select_turns"] > 0 else "N/A",
            "blunder_selects": int(stats["blunder_selects"]),
            "placement_blunders": int(stats["placement_blunders"]),
            "blunder_avoidance_rate": round((tot_decisions - tot_blunders) / tot_decisions, 4) if tot_decisions > 0 else "N/A",
            "place_turns": int(stats["place_turns"]),
            "self_bit_aligned_places": int(stats["self_bit_aligned_places"]),
            "self_bit_alignment_rate": round(stats["self_bit_aligned_places"] / stats["place_turns"], 4) if stats["place_turns"] > 0 else 0.0,
            "immediate_win_opportunities": int(stats["immediate_win_opportunities"]),
            "immediate_wins_taken": int(stats["immediate_wins_taken"]),
            "immediate_win_conversion_rate": round(stats["immediate_wins_taken"] / stats["immediate_win_opportunities"], 4) if stats["immediate_win_opportunities"] > 0 else "N/A",
        }
    return {
        "completed_games": len(match_reports),
        "wins": wins,
        "players": summary_players,
    }


def _evaluate_instance_quality(instance_data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(instance_data, Mapping):
        return {"status": "not_provided"}
    sv = instance_data.get("strict_validation", {}) if isinstance(instance_data.get("strict_validation"), Mapping) else {}
    sigs = instance_data.get("signature_values_signature_order", [])
    feats = instance_data.get("feature_ids", [])
    unique_sigs = sorted({int(s) for s in sigs}) if isinstance(sigs, Sequence) else []
    id_count = int(sv.get("id_level_count", 0))
    struct_count = int(sv.get("structural_count", 0))
    return {
        "status": "verified",
        "candidate_id": instance_data.get("candidate_id"),
        "public_seed": instance_data.get("public_seed"),
        "id_level_count": id_count,
        "structural_count": struct_count,
        "strict_acceptance_passed": bool(id_count > 1 and struct_count > 1),
        "signature_coverage_count": len(unique_sigs),
        "complete_16_signature_coverage": unique_sigs == list(range(16)),
        "selected_feature_count": len(feats) if isinstance(feats, Sequence) else 0,
    }


def evaluate_automated(
    data: Mapping[str, Any],
    *,
    instance_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    kind, payload = _extract_payload(data)
    if kind == "kaggle_run":
        match_meta = payload.get("match", {})
        replay = payload.get("public_replay", {})
        draft_stats = _evaluate_draft(replay.get("draft_history", []))
        public_history = replay.get("public_history", [])
        select_count = sum(1 for m in public_history if m.get("kind") == "select_entity")
        place_count = sum(1 for m in public_history if m.get("kind") == "place_entity")
        return {
            "schema_version": AUTOMATED_REPORT_SCHEMA_VERSION,
            "evaluator_mode": "automated_public_replay",
            "match_id": match_meta.get("match_id") or replay.get("match_id"),
            "models": match_meta.get("harness_model_tags", {}),
            "outcome": {
                "status": payload.get("status"),
                "winner": match_meta.get("winner"),
                "termination_reason": match_meta.get("termination_reason"),
                "duration_seconds": match_meta.get("duration_seconds"),
                "total_actions": match_meta.get("action_count"),
                "board_play_moves": select_count + place_count,
                "audit_valid": match_meta.get("audit_valid"),
                "replay_valid": match_meta.get("replay_valid"),
            },
            "instance_validation_metrics": _evaluate_instance_quality(instance_data),
            "draft_metrics": draft_stats,
            "piece_strategy_metrics": {
                "status": "unavailable_in_public_replay",
                "reason": "Per-match UUID-to-signature crosswalk is withheld from public Kaggle outputs.",
            },
        }

    match_reports: list[dict[str, Any]] = []
    for raw_match in payload.get("matches", []):
        audit = raw_match.get("audit_snapshot", {})
        pub_audit = audit.get("public_audit", {})
        res_data = audit.get("restricted_evaluator_data", {})
        draft_history = pub_audit.get("draft_history") or res_data.get("draft_history") or []
        draft_stats = _evaluate_draft(draft_history)
        feature_to_bit = {str(k): int(v) for k, v in res_data.get("feature_to_bit", {}).items()}
        ownership = res_data.get("private_feature_ownership", {})
        bit_owners: dict[int, str] = {}
        for player_id, feats in ownership.items():
            for feat in feats:
                if feat in feature_to_bit:
                    bit_owners[feature_to_bit[feat]] = str(player_id)
        entity_to_piece = {str(k): int(v) for k, v in res_data.get("entity_to_piece", {}).items()}
        strategy_stats = _evaluate_piece_strategy(
            starting_player=str(pub_audit.get("starting_player", "player_1")),
            public_history=pub_audit.get("public_history", []),
            entity_to_piece=entity_to_piece,
            bit_owners=bit_owners,
        )
        match_reports.append({
            "match_id": raw_match.get("match_id"),
            "status": raw_match.get("status"),
            "outcome": pub_audit.get("result"),
            "audit_valid": raw_match.get("audit_valid"),
            "replay_valid": raw_match.get("replay_valid"),
            "instance_validation_metrics": _evaluate_instance_quality(instance_data),
            "draft_metrics": draft_stats,
            "piece_strategy_metrics": strategy_stats,
        })

    return {
        "schema_version": AUTOMATED_REPORT_SCHEMA_VERSION,
        "evaluator_mode": "automated_restricted_log",
        "instance_validation_metrics": _evaluate_instance_quality(instance_data),
        "match_count": len(match_reports),
        "series_aggregate": _build_series_aggregate(match_reports),
        "matches": match_reports,
    }


def evaluate_automated_file(path: str | Path) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("Automated evaluator input must be a JSON object.")
    return evaluate_automated(raw)



def audit_reasoning_grounding(
    decision_traces: Sequence[Mapping[str, Any]],
    blunder_steps: set[int] | None = None,
    missed_win_steps: set[int] | None = None,
) -> dict[str, Any]:
    """Deterministic claim-to-engine audit (RL-03 / RL-06 grounded without 3rd-LLM bias)."""
    blunder_steps = blunder_steps or set()
    missed_win_steps = missed_win_steps or set()
    per_player: dict[str, dict[str, Any]] = {
        "player_1": {
            "total_explanations": 0,
            "evidence_cited_count": 0,
            "blunder_blindness_count": 0,
            "missed_win_blindness_count": 0,
            "draft_repeat_claim_count": 0,
        },
        "player_2": {
            "total_explanations": 0,
            "evidence_cited_count": 0,
            "blunder_blindness_count": 0,
            "missed_win_blindness_count": 0,
            "draft_repeat_claim_count": 0,
        },
    }
    seen_draft_proposals: dict[str, set[str]] = {"player_1": set(), "player_2": set()}
    evidence_re = re.compile(
        r"(fma:|row|col|diagonal|cell\s*\d+|bit\s*[0-3]|8/8|4/4|3-in-a-row|three-in-a-row)",
        re.IGNORECASE,
    )
    safe_claim_re = re.compile(
        r"(\bsafe\b|no immediate|cannot win|doesn't complete|does not complete|prevent)",
        re.IGNORECASE,
    )

    for tr in decision_traces:
        if not isinstance(tr, Mapping):
            continue
        pl = tr.get("agent_id")
        if pl not in per_player:
            continue
        expl = tr.get("decision_explanation")
        if not isinstance(expl, str) or not expl.strip():
            continue
        turn_id = int(tr.get("turn_id") or 0)
        act = tr.get("selected_action") if isinstance(tr.get("selected_action"), Mapping) else {}
        stats = per_player[pl]
        stats["total_explanations"] += 1

        if evidence_re.search(expl):
            stats["evidence_cited_count"] += 1

        if act.get("kind") == "propose_feature":
            fid = str(act.get("feature_id") or "")
            if fid in seen_draft_proposals[pl]:
                stats["draft_repeat_claim_count"] += 1
            seen_draft_proposals[pl].add(fid)

        if turn_id in blunder_steps and safe_claim_re.search(expl):
            stats["blunder_blindness_count"] += 1
        if turn_id in missed_win_steps:
            stats["missed_win_blindness_count"] += 1

    summary: dict[str, Any] = {}
    for pl, st in per_player.items():
        tot = st["total_explanations"]
        ev_rate = round(st["evidence_cited_count"] / tot, 4) if tot else None
        halluc_events = st["blunder_blindness_count"] + st["draft_repeat_claim_count"]
        faithfulness = round(max(0.0, 1.0 - (halluc_events / tot)), 4) if tot else None
        summary[pl] = {
            **st,
            "evidence_citation_rate": ev_rate,
            "deterministic_faithfulness_rate": faithfulness,
        }
    return summary
