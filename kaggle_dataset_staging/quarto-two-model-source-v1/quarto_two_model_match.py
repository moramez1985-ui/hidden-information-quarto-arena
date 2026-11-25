import hashlib
import json
import math
import os
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
import sys
import time
from typing import Any
from uuid import UUID
import zipfile

import kaggle_benchmarks as kbench


SOURCE_ROOT_ENV = "QUARTO_SOURCE_SNAPSHOT_ROOT"
FMA_ARCHIVE_ENV = "QUARTO_FMA_ARCHIVE_PATH"
FMA_LICENSE_ACK_ENV = "QUARTO_FMA_LICENSE_APPROVED"
DEFAULT_SOURCE_ROOT = Path("/kaggle/input/quarto-two-model-source-v1")
PLAYER_1_MODEL = "google/gemini-3.8-flash"
PLAYER_2_REGISTRY_KEY = "anthropic/claude-sonnet-4-6@default"
PLAYER_2_MODEL = "anthropic/claude-sonnet-4-6@default"
PUBLIC_REPLAY_SCHEMA_VERSION = 2
SERIES_TARGET_GAMES = max(1, int(os.environ.get("QUARTO_SERIES_GAMES", "4")))
SERIES_STARTING_PLAYERS = tuple("player_1" if i % 2 == 0 else "player_2" for i in range(SERIES_TARGET_GAMES))

_PUBLIC_AUDIT_FIELDS = frozenset({
    "match_id",
    "mode",
    "starting_player",
    "phase",
    "current_player",
    "selected_entity",
    "board",
    "draft_history",
    "public_history",
    "result",
    "legal_actions",
})
_PUBLIC_REPLAY_FIELDS = frozenset({
    "match_id",
    "replay_schema_version",
    "mode",
    "starting_player",
    "board",
    "draft_history",
    "public_history",
    "result",
})
EXPECTED_SNAPSHOT_FILES = {
    "ATTRIBUTION.md",
    "quarto_two_model_match.py",
    "requirements.txt",
    "kaggle_agent_adapter.py",
    "tournament_harness.py",
    "phase0_foundation.py",
    "quarto_engine.py",
    "decision_trace.py",
    "domain_adapters.zip",
    "evaluator.zip",
    "fma_pilot.py",
    "fma_pilot_instance.json",
}
EXPECTED_EVALUATOR_MEMBERS = {
    "evaluator/__init__.py",
    "evaluator/__main__.py",
    "evaluator/adapters.py",
    "evaluator/annotations.py",
    "evaluator/automated.py",
    "evaluator/metrics.py",
    "evaluator/report.py",
    "evaluator/semantic_judge.py",
}

EXPECTED_DOMAIN_ADAPTERS = {
    "domain_adapters/__init__.py",
    "domain_adapters/instance_builder.py",
    "domain_adapters/dataset_adapter.py",
    "domain_adapters/fma_adapter.py",
    "domain_adapters/qm9_adapter.py",
}


def _is_opaque_entity_id(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 32:
        return False
    try:
        parsed = UUID(hex=value)
    except ValueError:
        return False
    return parsed.version == 4 and parsed.hex == value


def _is_match_id(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("match:"):
        return False
    try:
        parsed = UUID(value[len("match:"):])
    except ValueError:
        return False
    return parsed.version == 4


def _is_valid_attribute_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 128


def _project_draft_history(raw_draft_history: object) -> list[dict[str, Any]]:
    if not isinstance(raw_draft_history, (list, tuple)):
        raise ValueError("Public audit draft_history must be a sequence.")
    projected: list[dict[str, Any]] = []
    for entry in raw_draft_history:
        if not isinstance(entry, Mapping):
            raise ValueError("Public draft_history entries must be objects.")
        if set(entry) != {"kind", "player", "attribute_id", "accepted"}:
            raise ValueError("Public draft_history entry has missing or unexpected fields.")
        if (
            entry.get("kind") != "propose_attribute"
            or entry.get("player") not in ("player_1", "player_2")
            or not _is_valid_attribute_id(entry.get("attribute_id"))
            or type(entry.get("accepted")) is not bool
        ):
            raise ValueError("Public draft_history entry contains invalid values.")
        projected.append({
            "kind": "propose_attribute",
            "player": entry["player"],
            "attribute_id": entry["attribute_id"],
            "accepted": entry["accepted"],
        })
    return projected


def _extract_post_terminal_visualization(
    restricted_log: Mapping[str, Any],
    public_audit: Mapping[str, Any] | None,
) -> dict[str, Any]:
    entity_signatures: dict[str, int] = {}
    bit_feature_legend: list[dict[str, Any]] = []
    winning_lines: list[dict[str, Any]] = []

    audit_snap = restricted_log.get("audit_snapshot")
    restricted_eval = (
        audit_snap.get("restricted_evaluator_data")
        if isinstance(audit_snap, Mapping)
        else getattr(audit_snap, "restricted_evaluator_data", None)
    )
    if isinstance(restricted_eval, Mapping):
        entity_to_piece = restricted_eval.get("entity_to_piece")
        if isinstance(entity_to_piece, Mapping):
            for eid, piece_id in entity_to_piece.items():
                entity_signatures[str(eid)] = int(piece_id)

        feature_to_bit = restricted_eval.get("feature_to_bit")
        ownership = restricted_eval.get("private_feature_ownership")
        owner_by_feat: dict[str, str] = {}
        if isinstance(ownership, Mapping):
            for pl, feats in ownership.items():
                if isinstance(feats, (list, tuple)):
                    for f in feats:
                        owner_by_feat[str(f)] = str(pl)

        if isinstance(feature_to_bit, Mapping):
            classic_traits = [
                ("Bit 0 (Height)", "Tall (1) vs Short (0)"),
                ("Bit 1 (Color)", "Light/Terracotta (1) vs Dark/Forest (0)"),
                ("Bit 2 (Shape)", "Round/Cylinder (1) vs Square/Cube (0)"),
                ("Bit 3 (Top)", "Hollow (1) vs Solid (0)"),
            ]
            bit_to_feat = {int(b): str(f) for f, b in feature_to_bit.items()}
            for bit_idx in range(4):
                feat_id = bit_to_feat.get(bit_idx)
                trait_name, trait_desc = classic_traits[bit_idx]
                bit_feature_legend.append({
                    "bit": bit_idx,
                    "classic_trait": trait_name,
                    "visual_rule": trait_desc,
                    "feature_id": feat_id,
                    "owner": owner_by_feat.get(feat_id) if feat_id else None,
                })

    board = public_audit.get("board") if isinstance(public_audit, Mapping) else None
    if isinstance(board, (list, tuple)) and len(board) == 16 and len(entity_signatures) == 16:
        lines = [
            ("Row 1", [0, 1, 2, 3]),
            ("Row 2", [4, 5, 6, 7]),
            ("Row 3", [8, 9, 10, 11]),
            ("Row 4", [12, 13, 14, 15]),
            ("Col 1", [0, 4, 8, 12]),
            ("Col 2", [1, 5, 9, 13]),
            ("Col 3", [2, 6, 10, 14]),
            ("Col 4", [3, 7, 11, 15]),
            ("Main Diagonal", [0, 5, 10, 15]),
            ("Anti Diagonal", [3, 6, 9, 12]),
        ]
        legend_by_bit = {entry["bit"]: entry for entry in bit_feature_legend}
        for line_name, cells in lines:
            sigs = [entity_signatures.get(str(board[c])) for c in cells if board[c] is not None]
            if len(sigs) == 4 and all(s is not None for s in sigs):
                for bit_idx in range(4):
                    bits = [(int(s) >> bit_idx) & 1 for s in sigs]
                    if len(set(bits)) == 1:
                        leg = legend_by_bit.get(bit_idx, {})
                        winning_lines.append({
                            "line_name": line_name,
                            "cells": cells,
                            "bit": bit_idx,
                            "bit_value": bits[0],
                            "classic_trait": leg.get("classic_trait", f"Bit {bit_idx}"),
                            "feature_id": leg.get("feature_id"),
                            "owner": leg.get("owner"),
                        })

    # Extract post-terminal self-reported decision explanations from decision_traces (primary) or events (fallback)
    reasoning_log: list[dict[str, Any]] = []
    traces = restricted_log.get("decision_traces")
    if isinstance(traces, (list, tuple)) and traces:
        for tr in traces:
            if not isinstance(tr, Mapping):
                continue
            reasoning_log.append({
                "step": tr.get("turn_id"),
                "player": tr.get("agent_id"),
                "action": dict(tr.get("selected_action", {})) if isinstance(tr.get("selected_action"), Mapping) else {},
                "decision_explanation": tr.get("decision_explanation"),
                "candidate_hypotheses": list(tr.get("candidate_hypotheses") or ()),
                "declared_confidence": tr.get("declared_confidence"),
            })
    else:
        events = restricted_log.get("events")
        if isinstance(events, (list, tuple)):
            step_num = 0
            for ev in events:
                if not isinstance(ev, Mapping) or ev.get("validation") != "passed":
                    continue
                step_num += 1
                parsed = ev.get("parsed_action") if isinstance(ev.get("parsed_action"), Mapping) else {}
                expl = None
                if isinstance(ev.get("response_content"), str):
                    try:
                        raw_obj = json.loads(ev["response_content"])
                        if isinstance(raw_obj, Mapping):
                            expl = raw_obj.get("decision_explanation")
                    except Exception:
                        pass
                reasoning_log.append({
                    "step": step_num,
                    "player": ev.get("requester"),
                    "action": dict(parsed),
                    "decision_explanation": expl if isinstance(expl, str) else None,
                })

    return {
        "entity_signatures": entity_signatures,
        "bit_feature_legend": bit_feature_legend,
        "winning_lines": winning_lines,
        "post_game_reasoning_log": reasoning_log,
    }


def _run_deterministic_reasoning_audit(
    restricted_logs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Deterministic claim-to-engine grounding & hidden-trait discovery audit (no 3rd-LLM bias)."""
    import re

    per_player: dict[str, dict[str, Any]] = {
        "player_1": {
            "total_explanations": 0,
            "evidence_cited_count": 0,
            "draft_repeat_claim_count": 0,
            "blunder_blindness_count": 0,
            "phantom_claim_count": 0,
            "opponent_traits_total": 0,
            "opponent_traits_discovered": 0,
        },
        "player_2": {
            "total_explanations": 0,
            "evidence_cited_count": 0,
            "draft_repeat_claim_count": 0,
            "blunder_blindness_count": 0,
            "phantom_claim_count": 0,
            "opponent_traits_total": 0,
            "opponent_traits_discovered": 0,
        },
    }
    evidence_re = re.compile(
        r"(fma:|row|col|diagonal|cell\s*\d+|bit\s*[0-3]|8/8|4/4|3-in-a-row|three-in-a-row)",
        re.IGNORECASE,
    )
    safe_claim_re = re.compile(
        r"(\bsafe\b|no immediate|cannot win|doesn't complete|does not complete|prevent)",
        re.IGNORECASE,
    )
    win_claim_re = re.compile(
        r"(quarto|winning line|completes? my|four-in-a-row|4-in-a-row)",
        re.IGNORECASE,
    )
    feat_token_re = re.compile(r"fma:[a-z0-9_]+:[a-z0-9_]+:\d+", re.IGNORECASE)

    for rlog in restricted_logs:
        if not isinstance(rlog, Mapping):
            continue
        traces = rlog.get("decision_traces")
        if not isinstance(traces, Sequence):
            continue

        red = rlog.get("restricted_evaluator_data") if isinstance(rlog.get("restricted_evaluator_data"), Mapping) else {}
        owners_map = red.get("feature_ownership") if isinstance(red.get("feature_ownership"), Mapping) else {}
        true_owned: dict[str, set[str]] = {"player_1": set(), "player_2": set()}
        for fid, owner in owners_map.items():
            if owner in true_owned:
                true_owned[owner].add(str(fid))

        if not true_owned["player_1"] and not true_owned["player_2"]:
            for tr in traces:
                if not isinstance(tr, Mapping):
                    continue
                priv = ((tr.get("observation_snapshot") or {}).get("private") or {})
                ag = tr.get("agent_id")
                if ag in true_owned and isinstance(priv.get("owned_features"), Sequence):
                    for f in priv["owned_features"]:
                        true_owned[ag].add(str(f))

        mentioned_by_player: dict[str, set[str]] = {"player_1": set(), "player_2": set()}
        seen_drafts: dict[str, set[str]] = {"player_1": set(), "player_2": set()}

        for tr in traces:
            if not isinstance(tr, Mapping):
                continue
            pl = tr.get("agent_id")
            if pl not in per_player:
                continue
            expl = tr.get("decision_explanation")
            hyps = tr.get("candidate_hypotheses") if isinstance(tr.get("candidate_hypotheses"), Sequence) else []
            combined_text = " ".join([str(expl or "")] + [str(h) for h in hyps])
            for m_feat in feat_token_re.findall(combined_text):
                mentioned_by_player[pl].add(m_feat)

            if not isinstance(expl, str) or not expl.strip():
                continue
            stats = per_player[pl]
            stats["total_explanations"] += 1
            if evidence_re.search(expl):
                stats["evidence_cited_count"] += 1

            act = tr.get("selected_action") if isinstance(tr.get("selected_action"), Mapping) else {}
            kind = str(act.get("kind") or "")
            if kind == "propose_feature":
                fid = str(act.get("feature_id") or "")
                if fid in seen_drafts[pl]:
                    stats["draft_repeat_claim_count"] += 1
                seen_drafts[pl].add(fid)
            elif kind == "select_entity":
                fb = tr.get("received_feedback") if isinstance(tr.get("received_feedback"), Mapping) else {}
                post_obs = fb.get("post_action_public_observation") if isinstance(fb.get("post_action_public_observation"), Mapping) else {}
                if post_obs.get("phase") == "terminal" and safe_claim_re.search(expl):
                    stats["blunder_blindness_count"] += 1
            elif kind == "place_entity":
                fb = tr.get("received_feedback") if isinstance(tr.get("received_feedback"), Mapping) else {}
                post_obs = fb.get("post_action_public_observation") if isinstance(fb.get("post_action_public_observation"), Mapping) else {}
                res = post_obs.get("result") if isinstance(post_obs.get("result"), Mapping) else {}
                if win_claim_re.search(expl) and res.get("winner") != pl:
                    stats["phantom_claim_count"] += 1
                if safe_claim_re.search(expl) and res.get("winner") and res.get("winner") != pl:
                    stats["blunder_blindness_count"] += 1

        for pl, opp in (("player_1", "player_2"), ("player_2", "player_1")):
            opp_feats = true_owned[opp]
            if opp_feats:
                per_player[pl]["opponent_traits_total"] += len(opp_feats)
                discovered = len(opp_feats.intersection(mentioned_by_player[pl]))
                per_player[pl]["opponent_traits_discovered"] += discovered

    scores: dict[str, Any] = {}
    for pl, st in per_player.items():
        tot = st["total_explanations"]
        ev_rate = round(st["evidence_cited_count"] / tot, 4) if tot else 0.0
        errors = st["draft_repeat_claim_count"] + st["blunder_blindness_count"] + st["phantom_claim_count"]
        faithfulness = round(max(0.0, 1.0 - (errors / tot)), 4) if tot else 0.0
        opp_tot = st["opponent_traits_total"]
        hi_disc = round(st["opponent_traits_discovered"] / opp_tot, 4) if opp_tot else 0.0
        scores[pl] = {
            **st,
            "evidence_citation_rate": ev_rate,
            "deterministic_faithfulness_rate": faithfulness,
            "hidden_trait_discovery_rate": hi_disc,
        }
    return {
        "status": "completed",
        "method": "deterministic_claim_to_engine_grounding_v2",
        "trust_boundary": "ground_truth_engine_verified_no_llm_judge_bias",
        "scores": scores,
    }


def _attach_arena_composite_scores(
    auto_eval: dict[str, Any],
    grounding_audit: dict[str, Any],
) -> dict[str, Any]:
    """Attach unified 0-100 Arena Composite Index combining gameplay, deduction, and grounding."""
    agg_players = (auto_eval.get("series_aggregate") or {}).get("players") or {}
    audit_scores = grounding_audit.get("scores") or {}
    for pl in ("player_1", "player_2"):
        p_stats = agg_players.get(pl)
        a_stats = audit_scores.get(pl) or {}
        if not isinstance(p_stats, dict):
            continue
        wr = float(p_stats.get("win_rate") or 0.0)
        ba = float(p_stats.get("blunder_avoidance_rate") or 0.0)
        dp = float(p_stats.get("draft_precision") or 0.0)
        hi = float(a_stats.get("hidden_trait_discovery_rate") or 0.0)
        sf = float(a_stats.get("deterministic_faithfulness_rate") or 0.0)
        composite = round(100.0 * (0.40 * wr + 0.20 * ba + 0.15 * dp + 0.15 * hi + 0.10 * sf), 2)
        p_stats["hidden_trait_discovery_rate"] = hi
        p_stats["arena_composite_index"] = composite
    return {
        **auto_eval,
        "reasoning_grounding_audit": grounding_audit,
    }


def _run_automated_evaluator(
    restricted_logs: list[Mapping[str, Any]] | Mapping[str, Any],
    instance_path: Path,
) -> dict[str, Any]:
    from evaluator.automated import evaluate_automated

    raw_instance = json.loads(instance_path.read_text(encoding="utf-8"))
    payload: Mapping[str, Any] = (
        {"matches": restricted_logs}
        if isinstance(restricted_logs, list)
        else restricted_logs
    )
    report = evaluate_automated(payload, instance_data=raw_instance)
    report["status"] = "completed"
    report["privacy_boundary"] = "aggregated_metrics_only_no_restricted_crosswalk"
    return report


def _project_public_replay(public_audit: object) -> dict[str, Any]:
    required_audit_fields = _PUBLIC_AUDIT_FIELDS - {"draft_history"}
    if (
        not isinstance(public_audit, Mapping)
        or not required_audit_fields.issubset(set(public_audit))
        or not set(public_audit).issubset(_PUBLIC_AUDIT_FIELDS)
    ):
        raise ValueError("Public audit has missing or unexpected fields.")
    if not _is_match_id(public_audit.get("match_id")):
        raise ValueError("Public audit has an invalid match identifier.")
    if public_audit.get("mode") not in ("classic", "self_selection"):
        raise ValueError("Public audit has an invalid mode.")
    if public_audit.get("starting_player") not in ("player_1", "player_2"):
        raise ValueError("Public audit has an invalid starting player.")
    if public_audit.get("current_player") not in ("player_1", "player_2"):
        raise ValueError("Public audit has an invalid current player.")
    phase = public_audit.get("phase")
    if phase not in ("draft", "select", "place", "terminal"):
        raise ValueError("Public audit has an invalid phase.")

    board = public_audit.get("board")
    if not isinstance(board, (list, tuple)) or len(board) != 16:
        raise ValueError("Public audit board must contain exactly 16 cells.")
    board_entities = [entity_id for entity_id in board if entity_id is not None]
    if any(not _is_opaque_entity_id(entity_id) for entity_id in board_entities):
        raise ValueError("Public audit board contains an invalid entity identifier.")
    if len(set(board_entities)) != len(board_entities):
        raise ValueError("Public audit board contains duplicate entities.")

    draft_history = _project_draft_history(public_audit.get("draft_history", ()))

    history = public_audit.get("public_history")
    if not isinstance(history, (list, tuple)):
        raise ValueError("Public audit history must be a sequence.")
    public_history: list[dict[str, Any]] = []
    for action in history:
        if not isinstance(action, Mapping):
            raise ValueError("Public history entries must be objects.")
        kind = action.get("kind")
        if kind == "select_entity":
            if set(action) != {"kind", "player", "entity_id"}:
                raise ValueError("Public selection history has missing or unexpected fields.")
            if action.get("player") not in ("player_1", "player_2") or not _is_opaque_entity_id(
                action.get("entity_id")
            ):
                raise ValueError("Public selection history contains invalid values.")
            public_history.append({
                "kind": "select_entity",
                "player": action["player"],
                "entity_id": action["entity_id"],
            })
        elif kind == "place_entity":
            if set(action) != {"kind", "player", "cell"}:
                raise ValueError("Public placement history has missing or unexpected fields.")
            if (
                action.get("player") not in ("player_1", "player_2")
                or type(action.get("cell")) is not int
                or not 0 <= action["cell"] < 16
            ):
                raise ValueError("Public placement history contains invalid values.")
            public_history.append({
                "kind": "place_entity",
                "player": action["player"],
                "cell": action["cell"],
            })
        else:
            raise ValueError("Public history contains an unknown action kind.")

    result = public_audit.get("result")
    if result is not None and (
        not isinstance(result, Mapping)
        or set(result) != {"mode", "outcome", "winner", "reason"}
        or not _is_valid_terminal_result(result)
        or result["mode"] != public_audit["mode"]
    ):
        raise ValueError("Public audit has an invalid terminal result.")
    if (phase == "terminal") != (result is not None):
        raise ValueError("Public audit phase and result disagree.")

    selected_entity = public_audit.get("selected_entity")
    if selected_entity is not None and not _is_opaque_entity_id(selected_entity):
        raise ValueError("Public audit has an invalid selected entity.")
    if (phase == "place") != (selected_entity is not None):
        raise ValueError("Public audit phase and selected entity disagree.")

    legal_actions = public_audit.get("legal_actions")
    if not isinstance(legal_actions, Mapping):
        raise ValueError("Public audit has invalid legal-action metadata.")
    if phase == "draft":
        if (
            set(legal_actions) != {"kind", "attribute_ids"}
            or legal_actions.get("kind") != "propose_attribute"
        ):
            raise ValueError("Public draft actions have missing or unexpected fields.")
        attribute_ids = legal_actions.get("attribute_ids")
        if (
            not isinstance(attribute_ids, (list, tuple))
            or not attribute_ids
            or any(not _is_valid_attribute_id(attr_id) for attr_id in attribute_ids)
            or len(attribute_ids) != len(set(attribute_ids))
        ):
            raise ValueError("Public draft actions contain invalid attribute identifiers.")
    elif phase == "select":
        if set(legal_actions) != {"kind", "entity_ids"} or legal_actions.get("kind") != "select_entity":
            raise ValueError("Public select actions have missing or unexpected fields.")
        entity_ids = legal_actions.get("entity_ids")
        if (
            not isinstance(entity_ids, (list, tuple))
            or not entity_ids
            or any(not _is_opaque_entity_id(entity_id) for entity_id in entity_ids)
            or len(entity_ids) != len(set(entity_ids))
        ):
            raise ValueError("Public select actions contain invalid entity identifiers.")
    elif phase == "place":
        if set(legal_actions) != {"kind", "cells"} or legal_actions.get("kind") != "place_entity":
            raise ValueError("Public place actions have missing or unexpected fields.")
        cells = legal_actions.get("cells")
        if (
            not isinstance(cells, (list, tuple))
            or not cells
            or any(type(cell) is not int or not 0 <= cell < 16 for cell in cells)
            or len(cells) != len(set(cells))
        ):
            raise ValueError("Public place actions contain invalid cells.")
    elif set(legal_actions) != {"kind"} or legal_actions.get("kind") != "terminal":
        raise ValueError("Terminal public audit has invalid legal-action metadata.")

    return {
        "match_id": public_audit["match_id"],
        "replay_schema_version": PUBLIC_REPLAY_SCHEMA_VERSION,
        "mode": public_audit["mode"],
        "starting_player": public_audit["starting_player"],
        "board": list(board),
        "draft_history": draft_history,
        "public_history": public_history,
        "result": None if result is None else {
            "mode": result["mode"],
            "outcome": result["outcome"],
            "winner": result["winner"],
            "reason": result["reason"],
        },
    }


def _validate_public_replay(public_replay: object) -> bool:
    if not isinstance(public_replay, Mapping) or set(public_replay) != _PUBLIC_REPLAY_FIELDS:
        return False
    if type(public_replay.get("replay_schema_version")) is not int:
        return False
    if public_replay["replay_schema_version"] != PUBLIC_REPLAY_SCHEMA_VERSION:
        return False
    mode = public_replay.get("mode")
    if mode not in ("classic", "self_selection"):
        return False
    if public_replay.get("starting_player") not in ("player_1", "player_2"):
        return False
    if not _is_match_id(public_replay.get("match_id")):
        return False

    board = public_replay.get("board")
    draft_history = public_replay.get("draft_history")
    history = public_replay.get("public_history")
    result = public_replay.get("result")
    if not isinstance(board, (list, tuple)) or len(board) != 16:
        return False
    if not isinstance(draft_history, (list, tuple)):
        return False
    if not isinstance(history, (list, tuple)):
        return False
    if (
        result is None
        or not _is_valid_terminal_result(result)
        or result["mode"] != mode
    ):
        return False
    board_entities = [entity_id for entity_id in board if entity_id is not None]
    if any(not _is_opaque_entity_id(entity_id) for entity_id in board_entities):
        return False
    if len(board_entities) != len(set(board_entities)):
        return False

    accepted_counts = {"player_1": 0, "player_2": 0}
    accepted_attributes: set[str] = set()
    for entry in draft_history:
        if not isinstance(entry, Mapping):
            return False
        if set(entry) != {"kind", "player", "attribute_id", "accepted"}:
            return False
        player = entry.get("player")
        attribute_id = entry.get("attribute_id")
        accepted = entry.get("accepted")
        if (
            entry.get("kind") != "propose_attribute"
            or player not in ("player_1", "player_2")
            or not _is_valid_attribute_id(attribute_id)
            or type(accepted) is not bool
        ):
            return False
        if accepted_counts[player] >= 2:
            return False
        if accepted:
            if attribute_id in accepted_attributes:
                return False
            accepted_attributes.add(attribute_id)
            accepted_counts[player] += 1

    if draft_history and (accepted_counts["player_1"] != 2 or accepted_counts["player_2"] != 2):
        return False

    reconstructed_board: list[str | None] = [None] * 16
    active_player = public_replay["starting_player"]
    selected_entity: str | None = None
    expected_placer: str | None = None
    used_entities: set[str] = set()
    for action in history:
        if not isinstance(action, Mapping):
            return False
        if action.get("kind") == "select_entity":
            if set(action) != {"kind", "player", "entity_id"}:
                return False
            entity_id = action.get("entity_id")
            player = action.get("player")
            if (
                selected_entity is not None
                or player != active_player
                or not _is_opaque_entity_id(entity_id)
                or entity_id in used_entities
            ):
                return False
            selected_entity = entity_id
            expected_placer = (
                "player_2" if player == "player_1" else "player_1"
            ) if mode == "classic" else player
        elif action.get("kind") == "place_entity":
            if set(action) != {"kind", "player", "cell"}:
                return False
            cell = action.get("cell")
            player = action.get("player")
            if (
                selected_entity is None
                or player != expected_placer
                or type(cell) is not int
                or not 0 <= cell < 16
                or reconstructed_board[cell] is not None
            ):
                return False
            reconstructed_board[cell] = selected_entity
            used_entities.add(selected_entity)
            selected_entity = None
            expected_placer = None
            active_player = (
                player
                if mode == "classic"
                else ("player_2" if player == "player_1" else "player_1")
            )
        else:
            return False

    if selected_entity is not None or not history:
        return False
    if history[-1].get("kind") != "place_entity":
        return False
    if result["outcome"] == "win" and result["winner"] not in ("player_1", "player_2"):
        return False
    if (
        result["outcome"] == "draw"
        and result["reason"] == "board_full"
        and any(entity_id is None for entity_id in reconstructed_board)
    ):
        return False
    return reconstructed_board == list(board)


def _project_and_validate_public_replay(public_audit: object) -> dict[str, Any]:
    projection = _project_public_replay(public_audit)
    if not _validate_public_replay(projection):
        raise RuntimeError("Security preflight produced an invalid public replay projection.")
    return projection


def _validate_source_snapshot(root: Path) -> bool:
    manifest_path = root / "manifest.json"
    checksum_path = root / "manifest.sha256"
    try:
        manifest_bytes = manifest_path.read_bytes()
        checksum_parts = checksum_path.read_text(encoding="utf-8").split()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read the Quarto source snapshot manifest: {error}") from error
    if (
        len(checksum_parts) != 2
        or checksum_parts[1] != "manifest.json"
        or checksum_parts[0] != hashlib.sha256(manifest_bytes).hexdigest()
    ):
        raise RuntimeError("Quarto source snapshot manifest checksum is invalid.")
    if not isinstance(manifest, dict) or manifest.get("snapshot_id") != "quarto-two-model-source-v1":
        raise RuntimeError("Unexpected Quarto source snapshot identifier.")
    entries = manifest.get("included_files")
    if not isinstance(entries, list):
        raise RuntimeError("Quarto source snapshot manifest has no file inventory.")
    listed_files = {
        entry.get("path")
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    if listed_files != EXPECTED_SNAPSHOT_FILES or len(entries) != len(listed_files):
        raise RuntimeError("Quarto source snapshot manifest has an unexpected file inventory.")

    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name not in ("manifest.json", "manifest.sha256")
    }
    non_arena_files = {f for f in actual_files if not (f.startswith("fma_") and f.endswith(".json") and "arena" in f)}
    if non_arena_files != EXPECTED_SNAPSHOT_FILES:
        raise RuntimeError("Quarto source snapshot contains missing or unexpected files.")
    for entry in entries:
        relative_path = Path(entry["path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError("Quarto source snapshot manifest contains an unsafe path.")
        file_path = (root / relative_path).resolve()
        try:
            file_path.relative_to(root.resolve())
        except ValueError as error:
            raise RuntimeError("Quarto source snapshot file escapes its root.") from error
        if hashlib.sha256(file_path.read_bytes()).hexdigest() != entry.get("sha256"):
            raise RuntimeError(
                f"Quarto source snapshot hash mismatch for {entry['path']!r}."
            )
    archive_members = manifest.get("archive_members")
    if not isinstance(archive_members, list):
        raise RuntimeError("Quarto source snapshot manifest has no archive-member inventory.")
    member_by_path = {
        entry.get("path"): entry
        for entry in archive_members
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    if set(member_by_path) != EXPECTED_DOMAIN_ADAPTERS or len(archive_members) != len(member_by_path):
        raise RuntimeError("Quarto source snapshot archive inventory is unexpected.")
    try:
        with zipfile.ZipFile(root / "domain_adapters.zip") as archive:
            if set(archive.namelist()) != EXPECTED_DOMAIN_ADAPTERS:
                raise RuntimeError("Quarto source archive contains missing or unexpected files.")
            for path, entry in member_by_path.items():
                data = archive.read(path)
                if (
                    len(data) != entry.get("size_bytes")
                    or hashlib.sha256(data).hexdigest() != entry.get("sha256")
                ):
                    raise RuntimeError(
                        f"Quarto source archive hash mismatch for {path!r}."
                    )
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise RuntimeError(f"Could not verify the Quarto source archive: {error}") from error
    return True


def _resolve_source_root() -> Path:
    configured_root = os.environ.get(SOURCE_ROOT_ENV)
    if configured_root:
        candidate = Path(configured_root).resolve()
        if _validate_source_snapshot(candidate):
            return candidate
    candidates = [DEFAULT_SOURCE_ROOT]
    candidates.append(
        Path.cwd() / "kaggle_dataset_staging" / "quarto-two-model-source-v1"
    )
    task_file = globals().get("__file__")
    if isinstance(task_file, str):
        candidates.append(Path(task_file).resolve().parent)
    for candidate in candidates:
        if all((candidate / filename).is_file() for filename in EXPECTED_SNAPSHOT_FILES):
            if _validate_source_snapshot(candidate):
                return candidate.resolve()
    raise RuntimeError(
        "Quarto source snapshot is unavailable or invalid. Attach the "
        "'quarto-two-model-source-v1' dataset or set "
        f"{SOURCE_ROOT_ENV} to its mounted root."
    )


def _verify_task_source(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    task_entry = next(
        entry
        for entry in manifest["included_files"]
        if entry["path"] == "quarto_two_model_match.py"
    )
    expected_hash = task_entry["sha256"]
    snapshot_source_hash = hashlib.sha256(
        (root / "quarto_two_model_match.py").read_bytes()
    ).hexdigest()
    if snapshot_source_hash != expected_hash:
        raise RuntimeError("Packaged Task source does not match the source snapshot manifest.")

    task_file = globals().get("__file__")
    if isinstance(task_file, str):
        source_path = Path(task_file)
        if source_path.suffix == ".py" and source_path.is_file():
            executing_source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if executing_source_hash != expected_hash:
                raise RuntimeError("Executing Task source does not match the packaged snapshot.")
            return {
                "status": "verified",
                "executing_source_sha256": executing_source_hash,
                "snapshot_source_sha256": snapshot_source_hash,
            }

    raise RuntimeError(
        "Executing Task source identity is unverifiable; Notebook execution "
        "requires an independently verified source identity."
    )


def _is_valid_terminal_result(value: object, expected_mode: str = "classic") -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "mode",
        "outcome",
        "winner",
        "reason",
    }:
        return False
    if value["mode"] != expected_mode:
        return False
    if value["outcome"] == "win":
        return value["winner"] in ("player_1", "player_2") and value["reason"] == "quarto"
    if value["outcome"] == "draw":
        return value["winner"] is None and value["reason"] in ("board_full", "simultaneous_quarto")
    return False


def _model_identity(llm: Any, label: str) -> str:
    model = getattr(llm, "model", None)
    name = getattr(llm, "name", None)
    if not isinstance(model, str) or not model:
        raise RuntimeError(f"{label} Kaggle LLM does not expose a model identity.")
    if name is not None and name != model:
        raise RuntimeError(
            f"{label} Kaggle LLM identity fields disagree: model={model!r}, name={name!r}."
        )
    return model


def _model_version(llm: Any) -> str | None:
    version = getattr(llm, "model_version", None)
    return version if isinstance(version, str) and version else None


_FAILURE_LOG_PREFIX = "QUARTO_TASK_FAILURE:"
_FAILURE_SUMMARIES = {
    "model_resolution": "Task model selection or registry validation failed.",
    "task_setup": "Task runtime, source snapshot, or match setup failed.",
    "instance_validation": "The approved real FMA instance or security preflight failed.",
    "match_execution": "The match runner raised an exception.",
    "match_validation": (
        "The match did not satisfy completion, draft, audit, replay, or terminal-result checks."
    ),
    "public_replay_validation": "The public replay projection or validation failed.",
    "result_construction": "The successful Task result could not be assembled.",
}
_SAFE_MATCH_STATUSES = frozenset({
    "agent_failure",
    "completed",
    "validation_failure",
})


def _emit_failure_diagnostic(
    error: Exception,
    failure_context: Mapping[str, Any],
) -> None:
    stage = failure_context.get("stage")
    if stage not in _FAILURE_SUMMARIES:
        stage = "task_setup"

    exception_class = type(error).__name__
    if not exception_class.isidentifier():
        exception_class = "Exception"
    diagnostic: dict[str, Any] = {
        "status": "failed",
        "passed": False,
        "failure_stage": stage,
        "exception_class": exception_class,
        "error_summary": _FAILURE_SUMMARIES[stage],
    }

    started_at = failure_context.get("started_at")
    if isinstance(started_at, (int, float)) and not isinstance(started_at, bool):
        elapsed_seconds = time.monotonic() - started_at
        if math.isfinite(elapsed_seconds) and elapsed_seconds >= 0:
            diagnostic["elapsed_seconds"] = round(elapsed_seconds, 3)

    match_result = failure_context.get("match_result")
    if match_result is not None:
        match_id = getattr(match_result, "match_id", None)
        if _is_match_id(match_id):
            diagnostic["match_id"] = match_id

        match_status = getattr(match_result, "status", None)
        if match_status in _SAFE_MATCH_STATUSES:
            diagnostic["match_status"] = match_status

        match_elapsed = getattr(match_result, "elapsed_seconds", None)
        if (
            isinstance(match_elapsed, (int, float))
            and not isinstance(match_elapsed, bool)
            and math.isfinite(match_elapsed)
            and match_elapsed >= 0
        ):
            diagnostic["match_elapsed_seconds"] = round(match_elapsed, 3)

        action_count = getattr(match_result, "action_count", None)
        if type(action_count) is int and action_count >= 0:
            diagnostic["action_count"] = action_count

        for field in ("audit_valid", "replay_valid"):
            value = getattr(match_result, field, None)
            if type(value) is bool:
                diagnostic[field] = value

    print(
        _FAILURE_LOG_PREFIX
        + json.dumps(diagnostic, sort_keys=True, separators=(",", ":"))
    )


class _IsolatedChatLLM:
    def __init__(self, llm: Any, *, player: str) -> None:
        self._llm = llm
        self._player = player
        self._kbench = kbench
        self.model = getattr(llm, "model")
        name = getattr(llm, "name", None)
        if isinstance(name, str):
            self.name = name
        version = _model_version(llm)
        if version is not None:
            self.model_version = version

    def prompt(self, prompt: str) -> str:
        last_exc: Exception | None = None
        for attempt, delay in enumerate((0.0, 2.0, 5.0, 10.0), start=1):
            if delay > 0:
                time.sleep(delay)
            try:
                with self._kbench.chats.new(
                    name=f"quarto-{self._player}-a{attempt}",
                    orphan=True,
                ):
                    return self._llm.prompt(prompt)
            except Exception as exc:
                last_exc = exc
        assert last_exc is not None
        raise last_exc


def _resolve_models(selected_llm: Any) -> tuple[Any, Any, dict[str, Any]]:
    selected_identity = _model_identity(selected_llm, "Selected Task model")

    registry = getattr(kbench, "llms", None)
    if not isinstance(registry, dict) or not registry:
        raise RuntimeError("Kaggle Benchmarks did not expose the kbench.llms registry.")

    target_opponent = os.environ.get("QUARTO_OPPONENT_MODEL", PLAYER_2_REGISTRY_KEY).strip()
    opponent_llm = registry.get(target_opponent)
    registry_key = target_opponent

    if opponent_llm is None:
        for key, candidate in registry.items():
            if getattr(candidate, "model", None) == target_opponent:
                registry_key, opponent_llm = key, candidate
                break

    if opponent_llm is None or getattr(opponent_llm, "model", None) == selected_identity:
        for key, candidate in registry.items():
            cand_id = getattr(candidate, "model", None)
            if isinstance(cand_id, str) and cand_id and cand_id != selected_identity and candidate is not selected_llm:
                registry_key, opponent_llm = key, candidate
                break

    if opponent_llm is None:
        raise RuntimeError(
            f"No distinct opponent model available in kbench.llms for {target_opponent!r}."
        )

    opponent_identity = _model_identity(opponent_llm, "Registry model")
    if selected_llm is opponent_llm or selected_identity == opponent_identity:
        raise RuntimeError("The two player model handles must have distinct identities.")

    return selected_llm, opponent_llm, {
        "player_1": {
            "registry_key": "selected Task llm",
            "model": selected_identity,
            "model_version": _model_version(selected_llm),
        },
        "player_2": {
            "registry_key": registry_key,
            "model": opponent_identity,
            "model_version": _model_version(opponent_llm),
        },
    }

class _IsolatedChatLLM:
    def __init__(self, llm: Any, *, player: str) -> None:
        self._llm = llm
        self._player = player
        self._kbench = kbench
        self.model = getattr(llm, "model")
        name = getattr(llm, "name", None)
        if isinstance(name, str):
            self.name = name
        version = _model_version(llm)
        if version is not None:
            self.model_version = version

    def prompt(self, prompt: str) -> str:
        last_exc: Exception | None = None
        for attempt, delay in enumerate((0.0, 2.0, 5.0, 10.0), start=1):
            if delay > 0:
                time.sleep(delay)
            try:
                with self._kbench.chats.new(
                    name=f"quarto-{self._player}-a{attempt}",
                    orphan=True,
                ):
                    return self._llm.prompt(prompt)
            except Exception as exc:
                last_exc = exc
        assert last_exc is not None
        raise last_exc

@kbench.task(name="Hidden information - Quarto Arena")
def run_quarto_two_model_match(llm) -> dict:
    failure_context: dict[str, Any] = {
        "stage": "model_resolution",
        "started_at": time.monotonic(),
    }
    try:
        return _run_quarto_two_model_match(llm, failure_context)
    except Exception as error:
        _emit_failure_diagnostic(error, failure_context)
        raise


def _render_live_step_panel(
    game_index: int,
    total_games: int,
    step_info: dict[str, Any],
    elapsed_sec: float,
    models_meta: dict[str, Any],
) -> None:
    actor = step_info.get("actor", "?")
    action = step_info.get("action") or {}
    kind = action.get("kind", "?")
    phase = step_info.get("phase", "?")
    turn_idx = step_info.get("turn_index", 0)
    board = step_info.get("board") or [None] * 16
    placed_count = sum(1 for c in board if c is not None)
    sel_ent = step_info.get("selected_entity")

    detail_txt = ""
    if kind == "propose_feature":
        detail_txt = f"feature={action.get('feature_id')}"
    elif kind == "select_entity":
        detail_txt = f"entity={str(action.get('entity_id'))[:8]}..."
    elif kind == "place_entity":
        cell = action.get("cell")
        r, c = (divmod(int(cell), 4) if isinstance(cell, int) else (0, 0))
        detail_txt = f"cell={cell} (R{r+1}C{c+1})"

    print(
        f"[LIVE Game {game_index}/{total_games} | Turn {turn_idx:02d} | {phase.upper()}] "
        f"{actor} -> {kind} ({detail_txt}) | Board: {placed_count}/16 | {elapsed_sec:.1f}s",
        flush=True,
    )

    try:
        Path("live_match_state.json").write_text(
            json.dumps(
                {
                    "game_index": game_index,
                    "total_games": total_games,
                    "elapsed_seconds": round(elapsed_sec, 2),
                    "models": models_meta,
                    **step_info,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    try:
        from IPython.display import HTML, clear_output, display
        p1_name = (models_meta.get("player_1") or {}).get("model", "player_1")
        p2_name = (models_meta.get("player_2") or {}).get("model", "player_2")
        cells_html = []
        for idx in range(16):
            val = board[idx] if idx < len(board) else None
            r, c = divmod(idx, 4)
            if val:
                bg = "#1f6feb" if idx == action.get("cell") else "#21262d"
                cells_html.append(
                    f'<div style="background:{bg};border:1px solid #388bfd;border-radius:8px;'
                    f'padding:10px;text-align:center;color:#f0f6fc;font-family:monospace;">'
                    f'<div style="font-size:10px;color:#8b949e;">R{r+1}C{c+1} (#{idx})</div>'
                    f'<div style="font-size:13px;font-weight:700;margin-top:4px;">{str(val)[:8]}</div></div>'
                )
            else:
                cells_html.append(
                    f'<div style="background:#0d1117;border:1px dashed #30363d;border-radius:8px;'
                    f'padding:10px;text-align:center;color:#484f58;font-family:monospace;">'
                    f'<div style="font-size:10px;">R{r+1}C{c+1} (#{idx})</div>'
                    f'<div style="font-size:12px;margin-top:4px;">empty</div></div>'
                )
        html_panel = f"""
        <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;padding:16px;color:#c9d1d9;font-family:system-ui,sans-serif;max-width:680px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <strong style="color:#58a6ff;font-size:15px;">Quarto Arena LIVE — Game {game_index}/{total_games}</strong>
            <span style="background:#238636;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;">Turn {turn_idx} • {phase.upper()} • {elapsed_sec:.1f}s</span>
          </div>
          <div style="font-size:12px;color:#8b949e;margin-bottom:10px;">
            P1: <code style="color:#79c0ff;">{p1_name}</code> vs P2: <code style="color:#d2a8ff;">{p2_name}</code><br/>
            Last move: <strong>{actor}</strong> → <code>{kind}</code> ({detail_txt}) | Selected: <code>{str(sel_ent)[:8] if sel_ent else 'None'}</code>
          </div>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">
            {''.join(cells_html)}
          </div>
        </div>
        """
        clear_output(wait=True)
        display(HTML(html_panel))
    except Exception:
        pass


def _run_quarto_two_model_match(
    llm: Any,
    failure_context: dict[str, Any],
    *,
    game_mode: str = "classic",
) -> dict[str, Any]:
    if game_mode not in ("classic", "self_selection"):
        raise ValueError(f"Unsupported Quarto game_mode: {game_mode!r}")
    sys.dont_write_bytecode = True
    selected_llm, opponent_llm, model_metadata = _resolve_models(llm)
    failure_context["stage"] = "task_setup"
    chats = getattr(kbench, "chats", None)
    if not callable(getattr(chats, "new", None)):
        raise RuntimeError("Kaggle SDK does not expose isolated chat contexts.")

    source_root = _resolve_source_root()
    task_source_integrity = _verify_task_source(source_root)
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    adapter_archive = str(source_root / "domain_adapters.zip")
    if adapter_archive not in sys.path:
        sys.path.insert(0, adapter_archive)
    evaluator_archive = str(source_root / "evaluator.zip")
    if evaluator_archive not in sys.path:
        sys.path.insert(0, evaluator_archive)

    from kaggle_agent_adapter import KaggleAgentAdapter
    from fma_pilot import load_fma_pilot
    from tournament_harness import TournamentRunner, run_security_audit

    if not (source_root / "domain_adapters.zip").exists():
        raise RuntimeError(
            "No verified real-instance source is available for Kaggle benchmark execution; "
            "the Task refuses to fall back to SyntheticAdapter or other smoke fixtures."
        )
    if os.environ.get(FMA_LICENSE_ACK_ENV) != "1":
        raise RuntimeError(
            "The FMA source license must be explicitly approved before Task execution."
        )
    archive_value = os.environ.get(FMA_ARCHIVE_ENV)
    if not archive_value:
        raise RuntimeError(
            f"A mounted FMA metadata archive is required through {FMA_ARCHIVE_ENV}; "
            "the archive is intentionally not bundled."
        )
    archive_path = Path(archive_value).resolve()
    if not archive_path.is_file():
        raise RuntimeError("The configured FMA metadata archive is unavailable.")

    failure_context["stage"] = "instance_validation"
    candidate_files = sorted(source_root.glob("fma_*arena*.json")) or sorted(source_root.glob("fma_*candidate*.json"))
    if not candidate_files:
        candidate_files = [source_root / "fma_pilot_instance.json"]
    rng = random.SystemRandom()
    if len(candidate_files) >= SERIES_TARGET_GAMES:
        chosen_files = rng.sample(candidate_files, k=SERIES_TARGET_GAMES)
    else:
        chosen_files = [rng.choice(candidate_files) for _ in range(SERIES_TARGET_GAMES)]
    series_pilots = [
        load_fma_pilot(archive_path, instance_path=cf)
        for cf in chosen_files
    ]
    pilot = series_pilots[0]
    security_preflight = run_security_audit(
        adapter=pilot.adapter,
        instance=pilot.instance,
        restricted_source_ids=pilot.restricted_source_ids,
        public_replay_projector=_project_and_validate_public_replay,
        enable_draft=True,
    )
    if security_preflight.get("status") != "passed":
        failed_checks = [
            check.get("check")
            for check in security_preflight.get("checks", [])
            if isinstance(check, Mapping) and check.get("passed") is not True
        ]
        raise RuntimeError(
            "The real-instance security preflight failed: "
            + ", ".join(str(check) for check in failed_checks)
        )

    swap_seats = os.environ.get("QUARTO_SWAP_SEATS", "").strip().lower() in {"1", "true", "yes"}
    p1_tag = model_metadata["player_1"]["model"]
    p2_tag = model_metadata["player_2"]["model"]
    assignments = (
        {
            "player_1": p2_tag,
            "player_2": p1_tag,
        }
        if swap_seats
        else {
            "player_1": p1_tag,
            "player_2": p2_tag,
        }
    )
    clients = {
        p1_tag: KaggleAgentAdapter(
            _IsolatedChatLLM(selected_llm, player="player_1")
        ).client,
        p2_tag: KaggleAgentAdapter(
            _IsolatedChatLLM(opponent_llm, player="player_2")
        ).client,
    }
    series_started_at = time.monotonic()
    series_budget_seconds = 3600.0
    min_remaining_for_next_game = 360.0
    completed_games: list[dict[str, Any]] = []
    completed_restricted_logs: list[Mapping[str, Any]] = []
    skipped_or_failed_games: list[dict[str, Any]] = []

    for game_index, starting_player in enumerate(SERIES_STARTING_PLAYERS, start=1):
        elapsed_series = time.monotonic() - series_started_at
        remaining_series = series_budget_seconds - elapsed_series
        if game_index > 1 and remaining_series < min_remaining_for_next_game:
            skipped_or_failed_games.append({
                "game_index": game_index,
                "starting_player": starting_player,
                "status": "skipped_time_budget",
                "reason": (
                    f"Insufficient remaining series budget ({round(remaining_series, 1)}s < "
                    f"{int(min_remaining_for_next_game)}s) before starting game {game_index}."
                ),
            })
            continue

        game_timeout = min(1700.0, max(120.0, remaining_series - 30.0))
        runner = TournamentRunner(
            clients,
            model_tags=(p1_tag, p2_tag),
            max_correction_attempts=0,
            wall_clock_timeout=game_timeout,
        )
        failure_context["stage"] = f"match_execution_game_{game_index}"
        try:
            active_pilot = series_pilots[(game_index - 1) % len(series_pilots)]
            _g_start = time.monotonic()
            result = runner.run_match(
                active_pilot.adapter,
                active_pilot.instance,
                assignments,
                mode=game_mode,
            starting_player=starting_player,
                restricted_source_ids=active_pilot.restricted_source_ids,
                enable_draft=True,
                on_step=lambda st, gi=game_index: _render_live_step_panel(
                    gi, SERIES_TARGET_GAMES, st, time.monotonic() - _g_start, model_metadata
                ),
            )
            failure_context["match_result"] = result
            failure_context["stage"] = "match_validation" if game_index == 1 else f"match_validation_game_{game_index}"

            restricted_log = result.restricted_log
            audit_snapshot = restricted_log.get("audit_snapshot")
            public_audit = (
                audit_snapshot.get("public_audit")
                if isinstance(audit_snapshot, Mapping)
                else getattr(audit_snapshot, "public_audit", None)
                if audit_snapshot is not None
                else restricted_log.get("public_audit")
            )
            terminal_result = (
                public_audit.get("result")
                if isinstance(public_audit, Mapping)
                else None
            )
            draft_history = (
                public_audit.get("draft_history")
                if isinstance(public_audit, Mapping)
                else None
            )
            accepted_draft_count = (
                sum(
                    1
                    for item in draft_history
                    if isinstance(item, Mapping) and item.get("accepted") is True
                )
                if isinstance(draft_history, (list, tuple))
                else 0
            )
            match_passed = (
                task_source_integrity.get("status") == "verified"
                and result.status == "completed"
                and result.action_count > 0
                and accepted_draft_count == 4
                and result.audit_valid
                and result.replay_valid
                and _is_valid_terminal_result(terminal_result, expected_mode=game_mode)
            )
            if not match_passed:
                detail = result.failure or "match_validation_failed"
                raise RuntimeError(
                    f"Game {game_index} validation failed ({detail})."
                )

            failure_context["stage"] = f"public_replay_validation_game_{game_index}"
            public_replay = _project_public_replay(public_audit)
            public_replay_valid = _validate_public_replay(public_replay)
            if not public_replay_valid:
                raise RuntimeError(f"Game {game_index} public replay validation failed.")

            match_summary = {
                "game_index": game_index,
                "starting_player": starting_player,
                "match_id": result.match_id,
                "instance_id": active_pilot.instance.instance_id,
                "mode": game_mode,
                "draft_enabled": True,
                "draft_proposal_count": len(draft_history) if isinstance(draft_history, list) else 0,
                "harness_model_tags": result.assignments,
                "outcome": result.outcome,
                "winner": result.winner,
                "termination_reason": (
                    terminal_result.get("reason")
                    if isinstance(terminal_result, dict)
                    else result.failure
                ),
                "action_count": result.action_count,
                "duration_seconds": round(result.elapsed_seconds, 3),
                "audit_valid": result.audit_valid,
                "replay_valid": result.replay_valid,
                "public_replay_valid": public_replay_valid,
                "failure": result.failure,
            }
            terminal_visualization = _extract_post_terminal_visualization(
                restricted_log,
                public_audit,
            )
            completed_games.append({
                "match": match_summary,
                "public_replay": public_replay,
                "terminal_visualization": terminal_visualization,
            })
            completed_restricted_logs.append(restricted_log)
        except Exception as game_err:
            err_reason = getattr(failure_context.get("match_result"), "failure", None) or type(game_err).__name__
            skipped_or_failed_games.append({
                "game_index": game_index,
                "starting_player": starting_player,
                "status": "failed",
                "reason": str(err_reason),
            })
            if not completed_games and game_index == 1:
                raise

    if not completed_games:
        raise RuntimeError("No games completed in the 3-game series.")

    primary_game = completed_games[0]
    failure_context["stage"] = "result_construction"
    return {
        "status": "passed",
        "passed": True,
        "source_snapshot": str(source_root),
        "task_source_integrity": task_source_integrity,
        "security_preflight": {
            "status": security_preflight["status"],
            "check_count": len(security_preflight["checks"]),
        },
        "timeout": {
            "match_wall_clock_seconds": 1700.0,
            "series_budget_seconds": series_budget_seconds,
            "provider_call_interruptible": False,
            "limitation": (
                "Responses returned after the local deadline are rejected before "
                "action submission. The Kaggle adapter's timeout is not forwarded "
                "to llm.prompt(), so a blocking provider call may overrun the "
                "deadline until it returns."
            ),
        },
        "model_metadata": model_metadata,
        "series": {
            "target_games": SERIES_TARGET_GAMES,
            "completed_games_count": len(completed_games),
            "incomplete_games_count": len(skipped_or_failed_games),
            "starting_player_schedule": list(SERIES_STARTING_PLAYERS),
            "skipped_or_failed_games": skipped_or_failed_games,
        },
        "match": primary_game["match"],
        "public_replay": primary_game["public_replay"],
        "matches": completed_games,
        "private_trace_storage": {
            "status": "not_emitted",
            "reason": (
                "Kaggle Task result and Notebook outputs have no verified "
                "field-level privacy boundary; secure storage requires a "
                "separate access-controlled design."
            ),
        },
        "evaluator": _attach_arena_composite_scores(
            _run_automated_evaluator(
                completed_restricted_logs,
                source_root / "fma_pilot_instance.json",
            ),
            _run_deterministic_reasoning_audit(
                completed_restricted_logs,
            ),
        ),
    }


_task_run = run_quarto_two_model_match.run(llm=kbench.llm)