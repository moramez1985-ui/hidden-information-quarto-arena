import sys
sys.dont_write_bytecode = True

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import types
import zipfile

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

try:
    import kaggle_benchmarks as kbench
except ModuleNotFoundError:
    from contextlib import nullcontext
    import re as _re
    import types as _types

    class _LocalLegalAgent:
        def __init__(self, model_id: str):
            self.model = model_id
            self.name = model_id
            self._call_count = 0

        def _extract_entity_feature_matrix(self, pub: dict) -> tuple[list[str], dict[str, list[int]]]:
            entities = pub.get("public_entities") or []
            if not isinstance(entities, list) or not entities:
                return [], {}
            ent_ids: list[str] = []
            feat_vals: dict[str, list[int]] = {}
            for idx, ent in enumerate(entities):
                if not isinstance(ent, dict):
                    continue
                eid = str(ent.get("entity_id") or ent.get("id") or idx)
                ent_ids.append(eid)
                fdict = None
                for key in ("features", "binary_features", "attributes", "properties"):
                    if isinstance(ent.get(key), dict):
                        fdict = ent[key]
                        break
                if fdict is None:
                    fdict = {k: v for k, v in ent.items() if isinstance(v, (bool, int, float))}
                for fk, fv in fdict.items():
                    feat_vals.setdefault(str(fk), []).append(1 if bool(fv) else 0)
            # Keep only features present for all entities
            n = len(ent_ids)
            valid_matrix = {k: v for k, v in feat_vals.items() if len(v) == n}
            return ent_ids, valid_matrix

        def _collect_state_sets(self, pub: dict, priv: dict) -> tuple[set[str], list[str]]:
            rejected_or_tried: set[str] = set()
            accepted_order: list[str] = []

            for item in pub.get("draft_history") or ():
                if isinstance(item, dict):
                    fid = item.get("feature_id") or item.get("attribute_id")
                    if fid:
                        sfid = str(fid)
                        if item.get("accepted") is True and sfid not in accepted_order:
                            accepted_order.append(sfid)
                        else:
                            rejected_or_tried.add(sfid)

            for container in (pub, priv):
                if not isinstance(container, dict):
                    continue
                for fid in container.get("rejected_features") or ():
                    rejected_or_tried.add(str(fid))
                for fid in container.get("owned_features") or container.get("accepted_features") or ():
                    sfid = str(fid)
                    if sfid not in accepted_order:
                        accepted_order.append(sfid)

            return rejected_or_tried, accepted_order

        def _pick_draft_feature(self, pub: dict, priv: dict, legal: dict) -> str:
            from itertools import combinations

            candidates = [str(f) for f in (legal.get("feature_ids") or [])]
            if not candidates:
                raise RuntimeError("No feature_ids available in legal_actions.")

            self._call_count += 1
            blocked, owned = self._collect_state_sets(pub, priv)
            allowed = [f for f in candidates if f not in blocked and f not in owned]
            pool = allowed if allowed else [f for f in candidates if f not in owned] or candidates

            ent_ids, matrix = self._extract_entity_feature_matrix(pub)
            n_ents = len(ent_ids)

            if n_ents > 0 and matrix:
                avail_feats = [f for f in candidates if f in matrix and f not in blocked]
                needed = max(0, 4 - len(owned))
                valid_next_features: set[str] = set()

                if needed > 0 and len(avail_feats) >= needed:
                    for comb in combinations(avail_feats, needed):
                        quartet = owned + list(comb)
                        if len(set(quartet)) != len(quartet):
                            continue
                        sigs = {
                            tuple(matrix[col][i] for col in quartet)
                            for i in range(n_ents)
                        }
                        if len(sigs) == n_ents:
                            valid_next_features.update(comb)

                if valid_next_features:
                    preferred = [f for f in pool if f in valid_next_features]
                    if preferred:
                        return preferred[0]
                    return sorted(valid_next_features)[0]

                # Score by unique signatures achieved when adding candidate to `owned`
                def _sig_score(fid: str) -> tuple[int, int, str]:
                    if fid not in matrix:
                        return (0, 0, fid)
                    trial = owned + [fid]
                    uniq = len({tuple(matrix[c][i] for c in trial if c in matrix) for i in range(n_ents)})
                    ones = sum(matrix[fid])
                    return (-uniq, abs(ones - (n_ents // 2)), fid)

                return min(pool, key=_sig_score)

            return pool[(self._call_count - 1) % len(pool)]

        def prompt(self, prompt_text: str) -> str:
            obs_str = prompt_text.split("Observation JSON:\n", 1)[1]
            obs = json.loads(obs_str)
            pub = obs.get("public_observation") or {}
            priv = obs.get("private_observation") or obs.get("requester_private_observation") or {}
            if not priv and isinstance(pub.get("private"), dict):
                priv = pub["private"]
            legal = pub.get("legal_actions") or {}
            kind = legal.get("kind")

            if kind == "propose_feature":
                fid = self._pick_draft_feature(pub, priv, legal)
                return json.dumps({
                    "action": {"kind": "propose_feature", "feature_id": fid},
                    "decision_explanation": f"Selecting separating draft feature {fid}.",
                })
            if kind == "select_entity":
                eids = list(legal.get("entity_ids") or [])
                eid = eids[(self._call_count - 1) % len(eids)]
                return json.dumps({
                    "action": {"kind": "select_entity", "entity_id": eid},
                    "decision_explanation": f"Selecting candidate entity {str(eid)[:8]}.",
                })
            if kind == "place_entity":
                cells = list(legal.get("cells") or [])
                cell = cells[0]
                return json.dumps({
                    "action": {"kind": "place_entity", "cell": cell},
                    "decision_explanation": f"Placing entity onto cell {cell}.",
                })
            raise ValueError(f"Unsupported legal action: {kind}")

    class _LocalTaskWrapper:
        def __init__(self, fn):
            self.fn = fn
        def run(self, llm):
            res = self.fn(llm)
            return _types.SimpleNamespace(passed=True, result=res)

    _p1 = _LocalLegalAgent("google/gemini-3.8-flash")
    _p2 = _LocalLegalAgent("anthropic/claude-sonnet-4-6@default")
    kbench = _types.SimpleNamespace(
        task=lambda **kw: (lambda fn: _LocalTaskWrapper(fn)),
        llm=_p1,
        llms={"anthropic/claude-sonnet-4-6@default": _p2},
        chats=_types.SimpleNamespace(new=lambda **kw: nullcontext()),
    )


def _extract_clean_json_object(raw_text: str) -> str:
    if not isinstance(raw_text, str):
        return raw_text
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1].strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    return text


def _reconstruct_or_copy_zip(
    mounted_root: Path,
    work_root: Path,
    manifest: dict,
    zip_filename: str,
    extracted_dir_name: str,
    members_key: str,
) -> Path:
    zip_path = work_root / zip_filename
    if (mounted_root / zip_filename).is_file():
        shutil.copy2(mounted_root / zip_filename, zip_path)
    elif (mounted_root / f"{zip_filename}.bin").is_file():
        shutil.copy2(mounted_root / f"{zip_filename}.bin", zip_path)
    else:
        src_dir = mounted_root / extracted_dir_name
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for member in manifest.get(members_key, []):
                rel_posix = member["path"]
                src_candidates = list(src_dir.rglob(Path(rel_posix).name))
                if not src_candidates:
                    raise FileNotFoundError(f"Missing {rel_posix} under {src_dir}")
                data = src_candidates[0].read_bytes()
                info = zipfile.ZipInfo(filename=rel_posix, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o644 << 16
                zf.writestr(info, data)

        actual_bytes = zip_path.read_bytes()
        actual_sha = hashlib.sha256(actual_bytes).hexdigest()
        for entry in manifest["included_files"]:
            if entry["path"] == zip_filename:
                entry["sha256"] = actual_sha
                entry["size_bytes"] = len(actual_bytes)
    return zip_path


def _prepare_and_load_quarto_module(input_root: Path = Path("/kaggle/input")):
    sys.dont_write_bytecode = True
    manifest_candidates = list(input_root.rglob("manifest.json"))
    if not manifest_candidates:
        raise FileNotFoundError(f"manifest.json not found under {input_root}")
    mounted_root = manifest_candidates[0].parent

    fma_candidates = list(input_root.rglob("fma_metadata.zip*"))
    if not fma_candidates:
        raise FileNotFoundError(f"fma_metadata.zip* not found under {input_root}")
    fma_archive = fma_candidates[0]

    work_root = Path(tempfile.gettempdir()) / "quarto-two-model-source-v1"
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    manifest = json.loads((mounted_root / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["included_files"]:
        rel_name = entry["path"]
        if rel_name in ("domain_adapters.zip", "evaluator.zip"):
            continue
        src = mounted_root / rel_name
        if not src.is_file():
            raise FileNotFoundError(f"Missing {rel_name} in {mounted_root}")
        shutil.copy2(src, work_root / rel_name)

    for arena_src in sorted(mounted_root.glob("fma_*arena*.json")):
        shutil.copy2(arena_src, work_root / arena_src.name)

    adapters_zip = _reconstruct_or_copy_zip(
        mounted_root, work_root, manifest, "domain_adapters.zip", "domain_adapters", "archive_members"
    )
    evaluator_zip = _reconstruct_or_copy_zip(
        mounted_root, work_root, manifest, "evaluator.zip", "evaluator", "evaluator_members"
    )

    new_manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    (work_root / "manifest.json").write_bytes(new_manifest_bytes)
    (work_root / "manifest.sha256").write_text(
        f"{hashlib.sha256(new_manifest_bytes).hexdigest()}  manifest.json\n",
        encoding="utf-8",
    )

    os.environ["QUARTO_FMA_LICENSE_APPROVED"] = "1"
    os.environ["QUARTO_SOURCE_SNAPSHOT_ROOT"] = str(work_root)
    os.environ["QUARTO_FMA_ARCHIVE_PATH"] = str(fma_archive)

    for p in (str(evaluator_zip), str(adapters_zip), str(work_root)):
        if p not in sys.path:
            sys.path.insert(0, p)

    import kaggle_agent_adapter

    orig_chat = kaggle_agent_adapter._KagglePromptClient.chat

    def _patched_chat(self, messages, *, timeout=None):
        res = orig_chat(self, messages, timeout=timeout)
        cleaned = _extract_clean_json_object(res.content)
        if cleaned != res.content:
            res = type(res)(
                content=cleaned,
                raw_response=res.raw_response,
                duration_seconds=res.duration_seconds,
                session_id=res.session_id,
                input_tokens=res.input_tokens,
                output_tokens=res.output_tokens,
            )
        return res

    kaggle_agent_adapter._KagglePromptClient.chat = _patched_chat

    real_kbench = kbench
    sys.modules["kaggle_benchmarks"] = types.SimpleNamespace(
        task=lambda **kw: (lambda fn: types.SimpleNamespace(run=lambda **rkw: None)),
        llm=getattr(real_kbench, "llm", None),
        llms=getattr(real_kbench, "llms", None),
        chats=getattr(real_kbench, "chats", None),
    )
    try:
        task_file = work_root / "quarto_two_model_match.py"
        spec = importlib.util.spec_from_file_location("quarto_two_model_match", task_file)
        task_module = importlib.util.module_from_spec(spec)
        sys.modules["quarto_two_model_match"] = task_module
        spec.loader.exec_module(task_module)
    finally:
        sys.modules["kaggle_benchmarks"] = real_kbench

    for pyc_dir in work_root.rglob("__pycache__"):
        shutil.rmtree(pyc_dir, ignore_errors=True)

    task_module.kbench = real_kbench
    return task_module


HTML_TEMPLATE = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8" />\n<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n<title>Quarto Hidden-Information Arena — Game Replay</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">\n<style>\n  :root {\n    --shell-bg: #141518;\n    --panel-dark: #1b1d22;\n    --panel-card: #23262d;\n    --panel-border: #31353f;\n    --text-light: #eceef2;\n    --text-muted: #9aa0ac;\n\n    --paper-bg: #f4f1ea;\n    --ink: #2b2926;\n    --ink-soft: #666158;\n    --pencil: #9e978b;\n\n    --p1: #3b6998;\n    --p1-soft: rgba(59, 105, 152, 0.10);\n    --p2: #b8653b;\n    --p2-soft: rgba(184, 101, 59, 0.10);\n    --win: #3f7856;\n    --win-soft: rgba(63, 120, 86, 0.11);\n    --warn: #9a6b26;\n    --danger: #a84444;\n  }\n\n  * { box-sizing: border-box; }\n  html { scroll-behavior: smooth; }\n  body {\n    margin: 0;\n    background: var(--shell-bg);\n    color: var(--text-light);\n    font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;\n  }\n\n  /* Single Clean Tooltip (No Navy Duplicate Box) */\n  [data-tip] {\n    position: relative;\n    cursor: help;\n    border-bottom: 1px dotted rgba(156, 163, 175, 0.55);\n  }\n  [data-tip]:hover::after {\n    content: attr(data-tip);\n    position: absolute;\n    left: 0;\n    bottom: calc(100% + 6px);\n    z-index: 60;\n    width: max-content;\n    max-width: 280px;\n    padding: 7px 10px;\n    border-radius: 7px;\n    background: #16181d;\n    color: #f3f4f6;\n    border: 1px solid #3f4451;\n    font-family: "Inter", sans-serif;\n    font-size: 0.73rem;\n    font-weight: 500;\n    line-height: 1.42;\n    text-transform: none;\n    letter-spacing: normal;\n    white-space: normal;\n    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.42);\n    pointer-events: none;\n  }\n\n  /* Full-Viewport First Screen */\n  .viewport-stage {\n    max-width: 1460px;\n    margin: 0 auto;\n    padding: 10px 14px 8px 14px;\n    min-height: 100vh;\n    display: flex;\n    flex-direction: column;\n    justify-content: space-between;\n  }\n\n  .top-header {\n    display: flex;\n    flex-wrap: wrap;\n    justify-content: space-between;\n    align-items: center;\n    gap: 10px;\n    padding: 8px 14px;\n    background: var(--panel-dark);\n    border: 1px solid var(--panel-border);\n    border-radius: 10px;\n    margin-bottom: 10px;\n  }\n  .brand-title { font-weight: 700; font-size: 0.98rem; letter-spacing: -0.01em; }\n  .brand-sub { font-size: 0.74rem; color: var(--text-muted); margin-top: 1px; }\n  .game-tabs { display: flex; gap: 6px; flex-wrap: wrap; }\n  .tab-btn {\n    background: var(--panel-card);\n    color: var(--text-muted);\n    border: 1px solid var(--panel-border);\n    padding: 5px 11px;\n    border-radius: 6px;\n    font-size: 0.76rem;\n    font-weight: 600;\n    cursor: pointer;\n    transition: all 0.15s ease;\n  }\n  .tab-btn:hover { color: var(--text-light); border-color: #4b5563; }\n  .tab-btn.active { background: #eceef2; color: #141518; border-color: #eceef2; }\n\n  .arena-layout {\n    flex: 1;\n    display: grid;\n    grid-template-columns: minmax(0, 1fr) 390px;\n    gap: 12px;\n    align-items: stretch;\n    min-height: 0;\n  }\n  @media (max-width: 1120px) {\n    .arena-layout { grid-template-columns: minmax(0, 1fr); }\n  }\n\n  /* Left: Tactile Paper Canvas */\n  .paper-canvas {\n    background-color: var(--paper-bg);\n    background-image:\n      radial-gradient(rgba(120, 110, 90, 0.13) 1px, transparent 0),\n      radial-gradient(rgba(160, 148, 125, 0.09) 1px, transparent 0);\n    background-size: 22px 22px;\n    background-position: 0 0, 11px 11px;\n    color: var(--ink);\n    border-radius: 12px;\n    border: 1px solid #3a3d46;\n    padding: 14px 18px 10px 18px;\n    display: flex;\n    flex-direction: column;\n    justify-content: space-between;\n    box-shadow: inset 0 0 50px rgba(180, 168, 142, 0.22);\n    min-width: 0;\n  }\n\n  .paper-top-strip {\n    display: flex;\n    flex-wrap: wrap;\n    justify-content: space-between;\n    align-items: center;\n    gap: 10px;\n    margin-bottom: 6px;\n  }\n  .versus-pill {\n    font-family: "Caveat", cursive;\n    font-size: 1.42rem;\n    font-weight: 700;\n    color: var(--ink);\n  }\n  .outcome-pill {\n    padding: 3px 11px;\n    border-radius: 999px;\n    font-size: 0.72rem;\n    font-weight: 700;\n    border: 1.5px solid currentColor;\n  }\n\n  .paper-center {\n    display: grid;\n    grid-template-columns: 48px minmax(240px, 410px) minmax(215px, 265px);\n    gap: 16px;\n    align-items: center;\n    justify-content: center;\n    margin: auto 0;\n    width: 100%;\n  }\n  @media (max-width: 820px) {\n    .paper-center { grid-template-columns: 44px minmax(0, 1fr); gap: 12px; }\n    .margin-notes { grid-column: 1 / -1; flex-direction: row; flex-wrap: wrap; }\n    .margin-notes > * { flex: 1 1 200px; }\n  }\n  @media (max-width: 480px) {\n    .paper-center { grid-template-columns: minmax(0, 1fr); }\n    .eval-col { flex-direction: row; height: auto; width: 100%; gap: 8px; }\n    .eval-track { height: 14px; width: 100%; }\n    .eval-zero { top: 0; bottom: 0; left: 50%; width: 1.5px; height: 100%; transform: translateX(-50%); }\n    .eval-fill-p2 { top: 0; bottom: 0; left: 0; right: auto; height: 100% !important; transition: width 0.26s ease; }\n    .eval-fill-p1 { top: 0; bottom: 0; right: 0; left: auto; height: 100% !important; transition: width 0.26s ease; }\n  }\n\n  /* Two-Segment Eval Bar: Claude (Terracotta) on Top, Gemini (Blue) on Bottom */\n  .eval-col {\n    display: flex;\n    flex-direction: column;\n    align-items: center;\n    height: clamp(280px, 46vh, 400px);\n  }\n  .eval-num {\n    font-family: "JetBrains Mono", monospace;\n    font-size: 0.76rem;\n    font-weight: 700;\n    color: var(--ink);\n    margin-bottom: 3px;\n  }\n  .eval-cap-top, .eval-cap-bot {\n    font-size: 0.64rem;\n    font-weight: 700;\n    line-height: 1.2;\n    text-align: center;\n    margin: 2px 0;\n  }\n  .eval-track {\n    width: 18px;\n    flex: 1;\n    background: var(--paper-bg);\n    border: 1.5px solid var(--ink);\n    border-radius: 4px;\n    overflow: hidden;\n    position: relative;\n  }\n  .eval-zero {\n    position: absolute;\n    top: 50%;\n    left: 0;\n    right: 0;\n    height: 1.5px;\n    background: var(--paper-bg);\n    transform: translateY(-50%);\n    z-index: 4;\n    opacity: 0.95;\n  }\n  .eval-fill-p2 {\n    position: absolute;\n    top: 0;\n    left: 0;\n    right: 0;\n    height: 50%;\n    background: var(--p2);\n    transition: height 0.26s cubic-bezier(0.22, 1, 0.36, 1);\n    z-index: 2;\n  }\n  .eval-fill-p1 {\n    position: absolute;\n    bottom: 0;\n    left: 0;\n    right: 0;\n    height: 50%;\n    background: var(--p1);\n    transition: height 0.26s cubic-bezier(0.22, 1, 0.36, 1);\n    z-index: 2;\n  }\n\n  /* 4x4 Pencil Grid */\n  .board-frame {\n    width: 100%;\n    max-width: 410px;\n    margin: 0 auto;\n    padding: clamp(8px, 1.8vw, 12px);\n    background: rgba(255, 253, 249, 0.72);\n    border: 2px solid var(--ink);\n    border-radius: 6px;\n    box-shadow: 3px 3px 0px rgba(43, 41, 38, 0.10);\n  }\n  .col-coords {\n    display: grid;\n    grid-template-columns: repeat(4, minmax(0, 1fr));\n    text-align: center;\n    font-family: "JetBrains Mono", monospace;\n    font-size: 0.68rem;\n    font-weight: 600;\n    color: var(--ink-soft);\n    margin-bottom: 5px;\n  }\n  .board-grid {\n    display: grid;\n    grid-template-columns: repeat(4, minmax(0, 1fr));\n    gap: clamp(4px, 1vw, 7px);\n  }\n  .cell {\n    aspect-ratio: 1 / 1;\n    min-width: 0;\n    border: 1.5px dashed var(--pencil);\n    border-radius: 5px;\n    background: rgba(255, 255, 255, 0.52);\n    display: flex;\n    flex-direction: column;\n    align-items: center;\n    justify-content: center;\n    position: relative;\n    padding: 2px;\n    transition: all 0.18s ease;\n  }\n  .cell-num {\n    position: absolute;\n    top: 2px;\n    left: 4px;\n    font-family: "JetBrains Mono", monospace;\n    font-size: 0.6rem;\n    font-weight: 600;\n    color: var(--pencil);\n  }\n  .cell.last {\n    border: 2px solid var(--ink);\n    background: #ffffff;\n    box-shadow: 2px 2px 0 rgba(43, 41, 38, 0.12);\n  }\n  .cell.projected-p1 { border: 2px dashed var(--p1); background: var(--p1-soft); }\n  .cell.projected-p2 { border: 2px dashed var(--p2); background: var(--p2-soft); }\n  .cell.win { border: 2px solid var(--win); background: var(--win-soft); }\n\n  /* 4-Bit Piece Token: Left = P1 bits, Right = P2 bits */\n  .token {\n    display: grid;\n    grid-template-columns: 1fr 1fr;\n    gap: 2px;\n    width: clamp(32px, 6vw, 42px);\n    height: clamp(32px, 6vw, 42px);\n    padding: 2px;\n    border: 1.5px solid var(--ink);\n    border-radius: 5px;\n    background: #fffdf9;\n  }\n  .bit-box {\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    font-family: "JetBrains Mono", monospace;\n    font-size: 0.62rem;\n    font-weight: 700;\n    border-radius: 2px;\n  }\n  .bit-box.p1-on { background: var(--p1); color: #fff; }\n  .bit-box.p1-off { border: 1px dashed var(--p1); color: var(--p1); }\n  .bit-box.p2-on { background: var(--p2); color: #fff; }\n  .bit-box.p2-off { border: 1px dashed var(--p2); color: var(--p2); }\n  .token-code {\n    font-family: "JetBrains Mono", monospace;\n    font-size: 0.56rem;\n    color: var(--ink-soft);\n    margin-top: 2px;\n  }\n\n  /* Decluttered Tactical Move Interpreter */\n  .margin-notes {\n    display: flex;\n    flex-direction: column;\n    gap: 10px;\n    min-width: 0;\n  }\n  .tactical-card {\n    background: rgba(255, 253, 249, 0.45);\n    border: 1px solid var(--pencil);\n    border-radius: 8px;\n    padding: 9px 11px;\n  }\n  .tactical-header {\n    display: flex;\n    justify-content: space-between;\n    align-items: center;\n    font-size: 0.66rem;\n    font-weight: 700;\n    text-transform: uppercase;\n    letter-spacing: 0.05em;\n    color: var(--ink-soft);\n    margin-bottom: 4px;\n    border-bottom: 1px dashed var(--pencil);\n    padding-bottom: 3px;\n  }\n  .tactical-headline {\n    font-family: "Caveat", cursive;\n    font-size: 1.2rem;\n    font-weight: 700;\n    line-height: 1.18;\n    color: var(--ink);\n  }\n  .tactical-detail {\n    font-size: 0.73rem;\n    line-height: 1.38;\n    color: var(--ink-soft);\n    margin-top: 3px;\n  }\n  .tactical-risk {\n    margin-top: 6px;\n    padding-top: 5px;\n    border-top: 1px dashed var(--pencil);\n    font-size: 0.7rem;\n    font-weight: 500;\n    color: var(--ink-soft);\n    background: transparent;\n  }\n\n  .held-card {\n    border: 1.5px dashed var(--ink);\n    border-radius: 8px;\n    padding: 7px;\n    background: rgba(255, 255, 255, 0.55);\n    display: flex;\n    flex-direction: column;\n    align-items: center;\n  }\n  .held-title {\n    font-family: "Caveat", cursive;\n    font-size: 1.06rem;\n    font-weight: 700;\n    margin-bottom: 3px;\n  }\n  .trait-key {\n    font-size: 0.68rem;\n    border-top: 1px dashed var(--pencil);\n    padding-top: 6px;\n    line-height: 1.38;\n  }\n\n  /* Minimal Footer */\n  .paper-footer {\n    display: flex;\n    justify-content: space-between;\n    align-items: center;\n    gap: 8px;\n    font-size: 0.71rem;\n    color: var(--ink-soft);\n    border-top: 1px dashed var(--pencil);\n    padding-top: 6px;\n    margin-top: 6px;\n  }\n\n  /* Right: Dark Sleek Game Log Panel */\n  .log-panel {\n    background: var(--panel-dark);\n    border: 1px solid var(--panel-border);\n    border-radius: 12px;\n    display: flex;\n    flex-direction: column;\n    height: calc(100vh - 106px);\n    min-height: 500px;\n    overflow: hidden;\n  }\n  @media (max-width: 1120px) {\n    .log-panel { height: 460px; }\n  }\n  .log-header {\n    padding: 10px 12px;\n    border-bottom: 1px solid var(--panel-border);\n  }\n  .log-title-row {\n    display: flex;\n    justify-content: space-between;\n    align-items: center;\n    margin-bottom: 8px;\n  }\n  .log-title-row h2 { margin: 0; font-size: 0.9rem; font-weight: 700; }\n  .transport-bar {\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    gap: 6px;\n    margin-bottom: 6px;\n  }\n  .t-btns { display: flex; align-items: center; gap: 4px; }\n  .t-btn {\n    background: var(--panel-card);\n    color: var(--text-light);\n    border: 1px solid var(--panel-border);\n    border-radius: 6px;\n    padding: 4px 9px;\n    font-size: 0.78rem;\n    font-weight: 600;\n    cursor: pointer;\n  }\n  .t-btn:hover { background: #2d313a; }\n  .step-counter { font-family: "JetBrains Mono", monospace; font-size: 0.78rem; color: var(--text-muted); }\n  .scrubber-row { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }\n  .scrubber-row input[type=range] { flex: 1; accent-color: #eceef2; cursor: pointer; }\n  .speed-select {\n    background: var(--panel-card);\n    color: var(--text-light);\n    border: 1px solid var(--panel-border);\n    border-radius: 6px;\n    padding: 3px 6px;\n    font-size: 0.72rem;\n    font-weight: 600;\n  }\n  .filter-row { display: flex; gap: 6px; }\n  .pill-toggle {\n    flex: 1;\n    background: var(--panel-card);\n    color: var(--text-light);\n    border: 1px solid var(--panel-border);\n    border-radius: 999px;\n    padding: 4px 8px;\n    font-size: 0.71rem;\n    font-weight: 600;\n    cursor: pointer;\n    text-align: center;\n  }\n  .pill-toggle:hover { border-color: #6b7280; }\n  .pill-toggle.active-filter { background: #374151; border-color: #9ca3af; }\n\n  .log-stream {\n    flex: 1;\n    overflow-y: auto;\n    padding: 8px 10px;\n    display: flex;\n    flex-direction: column;\n    gap: 7px;\n  }\n  .log-card {\n    background: var(--panel-card);\n    border: 1px solid var(--panel-border);\n    border-radius: 8px;\n    padding: 8px 10px;\n    cursor: pointer;\n    transition: border-color 0.15s ease;\n  }\n  .log-card:hover { border-color: #4b5563; }\n  .log-card.active { border-color: #eceef2; background: #282c35; }\n  .log-card-top {\n    display: flex;\n    justify-content: space-between;\n    align-items: center;\n    gap: 6px;\n    font-size: 0.76rem;\n    font-weight: 700;\n    margin-bottom: 3px;\n  }\n  .log-card-desc { font-size: 0.76rem; color: #d1d5db; }\n  .thinking-toggle {\n    margin-top: 5px;\n    font-size: 0.71rem;\n    color: var(--text-muted);\n    display: inline-flex;\n    align-items: center;\n    gap: 4px;\n    padding: 2px 4px;\n    border-radius: 4px;\n    user-select: none;\n  }\n  .thinking-toggle:hover { color: var(--text-light); background: rgba(255,255,255,0.06); }\n  .thinking-body {\n    margin-top: 5px;\n    padding-top: 5px;\n    border-top: 1px solid var(--panel-border);\n    font-size: 0.74rem;\n    line-height: 1.44;\n    color: #cbd5e1;\n    display: none;\n  }\n  .log-card.expanded .thinking-body { display: block; }\n\n  /* Log List Tags */\n  .tag {\n    padding: 1px 5px;\n    border-radius: 4px;\n    font-size: 0.62rem;\n    font-weight: 700;\n    letter-spacing: 0.02em;\n    display: inline-block;\n    vertical-align: middle;\n  }\n  .tag-blunder { background: rgba(168, 68, 68, 0.22); color: #fca5a5; border: 1px solid #dc2626; }\n  .tag-warning { background: rgba(154, 107, 38, 0.22); color: #fcd34d; border: 1px solid #d97706; }\n  .tag-win { background: rgba(63, 120, 86, 0.26); color: #86efac; border: 1px solid #22c55e; }\n  .tag-draw { background: rgba(148, 163, 184, 0.18); color: #cbd5e1; border: 1px solid #64748b; }\n\n  /* Subtle Downward Scroll Cue at Bottom of First Viewport */\n  .scroll-cue {\n    display: flex;\n    justify-content: center;\n    align-items: center;\n    padding-top: 6px;\n  }\n  .scroll-cue a {\n    display: inline-flex;\n    align-items: center;\n    gap: 6px;\n    color: var(--text-muted);\n    text-decoration: none;\n    font-size: 0.73rem;\n    font-weight: 600;\n    padding: 3px 12px;\n    border-radius: 999px;\n    background: rgba(35, 38, 45, 0.75);\n    border: 1px solid var(--panel-border);\n    transition: all 0.15s ease;\n  }\n  .scroll-cue a:hover { color: var(--text-light); border-color: #6b7280; transform: translateY(1px); }\n\n  /* Below-the-Fold Benchmark & Draft Section */\n  .benchmark-section {\n    max-width: 1460px;\n    margin: 0 auto;\n    padding: 12px 14px 28px 14px;\n  }\n  .bottom-metrics {\n    display: grid;\n    grid-template-columns: repeat(3, minmax(0, 1fr));\n    gap: 14px;\n  }\n  @media (max-width: 1020px) { .bottom-metrics { grid-template-columns: minmax(0, 1fr); } }\n  .dark-card {\n    background: var(--panel-dark);\n    border: 1px solid var(--panel-border);\n    border-radius: 10px;\n    padding: 14px;\n    min-width: 0;\n  }\n  .dark-card h3 {\n    margin: 0 0 10px 0;\n    font-size: 0.78rem;\n    text-transform: uppercase;\n    letter-spacing: 0.05em;\n    color: var(--text-muted);\n    display: inline-block;\n  }\n  table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }\n  th, td { padding: 6px 8px; border-bottom: 1px solid var(--panel-border); text-align: left; }\n  th { color: var(--text-muted); }\n  .draft-scroll { max-height: 210px; overflow-y: auto; font-size: 0.76rem; }\n\n  /* 4 Overview & Dataset Evolution Cards Below Metrics */\n  .project-overview-grid {\n    display: grid;\n    grid-template-columns: repeat(4, minmax(0, 1fr));\n    gap: 14px;\n    margin-top: 14px;\n  }\n  @media (max-width: 1120px) { .project-overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }\n  @media (max-width: 680px) { .project-overview-grid { grid-template-columns: minmax(0, 1fr); } }\n  .overview-card {\n    background: var(--panel-dark);\n    border: 1px solid var(--panel-border);\n    border-radius: 10px;\n    padding: 15px 17px;\n    display: flex;\n    flex-direction: column;\n    justify-content: space-between;\n  }\n  .overview-badge {\n    display: inline-block;\n    font-family: "JetBrains Mono", monospace;\n    font-size: 0.65rem;\n    font-weight: 700;\n    padding: 2px 8px;\n    border-radius: 999px;\n    margin-bottom: 8px;\n    width: fit-content;\n  }\n  .badge-arch { background: rgba(59, 105, 152, 0.22); color: #93c5fd; border: 1px solid rgba(59, 105, 152, 0.5); }\n  .badge-past { background: rgba(156, 163, 175, 0.14); color: #d1d5db; border: 1px solid rgba(156, 163, 175, 0.35); }\n  .badge-active { background: rgba(63, 120, 86, 0.24); color: #86efac; border: 1px solid rgba(63, 120, 86, 0.5); }\n  .overview-card h4 {\n    margin: 0 0 6px 0;\n    font-size: 0.88rem;\n    font-weight: 700;\n    color: var(--text-light);\n  }\n  .overview-card p {\n    margin: 0 0 10px 0;\n    font-size: 0.77rem;\n    line-height: 1.52;\n    color: #cbd5e1;\n  }\n  .overview-card code {\n    background: rgba(255, 255, 255, 0.08);\n    padding: 1px 4px;\n    border-radius: 3px;\n    font-size: 0.72rem;\n  }\n  .overview-meta {\n    font-family: "JetBrains Mono", monospace;\n    font-size: 0.67rem;\n    color: var(--text-muted);\n    border-top: 1px solid var(--panel-border);\n    padding-top: 8px;\n  }\n</style>\n</head>\n<body>\n\n<div class="viewport-stage">\n  <div class="top-header">\n    <div class="brand">\n      <div class="brand-title">Quarto Hidden-Information Arena</div>\n      <div class="brand-sub" id="match-meta">Loading match telemetry...</div>\n    </div>\n    <div class="game-tabs" id="game-tabs"></div>\n  </div>\n\n  <div class="arena-layout">\n    <!-- Left: Tactile Paper Board -->\n    <div class="paper-canvas">\n      <div class="paper-top-strip">\n        <div class="versus-pill" id="versus-title">Model 1 vs. Model 2</div>\n        <div class="outcome-pill" id="outcome-badge">COMPLETED</div>\n      </div>\n\n      <div class="paper-center">\n        <!-- Two-Segment Eval Bar: Claude (Terracotta) on Top, Gemini (Blue) on Bottom -->\n        <div class="eval-col" id="eval-col-tip" data-tip="Live 1-ply tactical balance. Terracotta expands down from top for Claude; Blue expands up from bottom for Gemini.">\n          <div class="eval-num" id="eval-score">0.0</div>\n          <div class="eval-cap-top" id="eval-top-lbl" style="color:var(--p2);">Claude</div>\n          <div class="eval-track">\n            <div class="eval-zero"></div>\n            <div class="eval-fill-p2" id="eval-p2-fill"></div>\n            <div class="eval-fill-p1" id="eval-p1-fill"></div>\n          </div>\n          <div class="eval-cap-bot" id="eval-bot-lbl" style="color:var(--p1);">Gemini</div>\n        </div>\n\n        <!-- 4x4 Pencil Grid (1-indexed C1..C4 and Cells 1..16) -->\n        <div class="board-frame">\n          <div class="col-coords"><span>C1</span><span>C2</span><span>C3</span><span>C4</span></div>\n          <div class="board-grid" id="board-grid"></div>\n        </div>\n\n        <!-- Tactical Move Interpreter & Active Piece -->\n        <div class="margin-notes">\n          <div class="tactical-card">\n            <div class="tactical-header">\n              <span>Tactical Move Interpreter</span>\n              <span id="tactical-badge"></span>\n            </div>\n            <div class="tactical-headline" id="hand-annotation">Board play begins!</div>\n            <div class="tactical-detail" id="hand-subnote">Draft phase completed off-board.</div>\n            <div class="tactical-risk" id="tactical-risk">No immediate line threats on the board yet.</div>\n          </div>\n\n          <div class="held-card">\n            <div class="held-title">Piece in Hand</div>\n            <div id="held-piece-box" style="min-height:58px;display:flex;flex-direction:column;align-items:center;justify-content:center;">\n              <span style="font-size:0.74rem;color:var(--ink-soft);">None</span>\n            </div>\n          </div>\n\n          <div class="trait-key" id="trait-legend-compact"></div>\n          <div class="corner-staff-wrap" data-tip="Advantage timeline across moves. Click any note dot to jump directly to that move.">\n            <svg id="music-staff" width="100%" height="46" viewBox="0 0 220 46" style="display:block;background:transparent;cursor:pointer;"></svg>\n          </div>\n        </div>\n      </div>\n\n      <div class="paper-footer">\n        <span id="footer-quad-hint">Left bits: Blue &nbsp;|&nbsp; Right bits: Terracotta</span>\n        <span id="win-trait-note" style="font-weight:700;color:var(--win);"></span>\n      </div>\n    </div>\n\n    <!-- Right: Game Log & Thinking Stream -->\n    <div class="log-panel">\n      <div class="log-header">\n        <div class="log-title-row">\n          <h2>Game Log <span style="font-size:0.68rem;font-weight:500;color:var(--text-muted);">(Use &larr; / &rarr; keys)</span></h2>\n          <span class="step-counter" id="step-counter">0 / 0</span>\n        </div>\n        <div class="transport-bar">\n          <div class="t-btns">\n            <button class="t-btn" onclick="stepTo(0)" title="Reset to Move 0">&#8634;</button>\n            <button class="t-btn" onclick="stepBy(-1)" title="Previous Move (Left Arrow)">|&lt;</button>\n            <button class="t-btn" id="play-btn" onclick="togglePlay()" title="Play / Pause (Space)">&#9654;</button>\n            <button class="t-btn" onclick="stepBy(1)" title="Next Move (Right Arrow)">&gt;|</button>\n          </div>\n          <select class="speed-select" id="speed-select" onchange="updatePlaySpeed()" title="Playback speed">\n            <option value="1400">0.5X</option>\n            <option value="850" selected>1X</option>\n            <option value="400">2X</option>\n          </select>\n        </div>\n        <div class="scrubber-row">\n          <input type="range" id="step-slider" min="0" max="0" value="0" oninput="stepTo(parseInt(this.value, 10))" />\n        </div>\n        <div class="filter-row">\n          <button class="pill-toggle" id="expand-all-btn" onclick="toggleExpandAll()">&#8597; Expand All Thinking</button>\n          <button class="pill-toggle" id="key-only-btn" onclick="toggleKeyOnly()">&#9733; Key Moments</button>\n        </div>\n      </div>\n\n      <div class="log-stream" id="log-stream"></div>\n    </div>\n  </div>\n\n  <div class="scroll-cue">\n    <a href="#benchmark-details">&#8595; Scroll for Draft Log, Series Metrics &amp; Benchmark Overview</a>\n  </div>\n</div>\n\n<!-- Below-the-Fold Benchmark Details & Dataset Evolution Cards -->\n<div class="benchmark-section" id="benchmark-details">\n  <div class="bottom-metrics">\n    <div class="dark-card">\n      <h3 data-tip="Pre-board negotiation phase where models propose real FMA audio descriptors to form a mathematically valid 4-bit quartet (16 unique piece signatures). Each model privately owns 2 accepted features as its secret win conditions.">\n        Pre-Game Draft Log (Hidden Feature Discovery)\n      </h3>\n      <div class="draft-scroll" id="draft-log-box"></div>\n    </div>\n    <div class="dark-card">\n      <h3 data-tip="Aggregated tactical and strategic performance metrics computed deterministically by the ground-truth game engine across all games in this series.">\n        Series Aggregate Performance\n      </h3>\n      <div id="series-summary"></div>\n    </div>\n    <div class="dark-card">\n      <h3 data-tip="Zero-LLM-judge deterministic audit verifying each model\'s self-reported decision_explanation against exact engine board state, threat geometry, and prior draft history.">\n        Deterministic Claim-to-Engine Audit\n      </h3>\n      <div id="judge-summary"></div>\n    </div>\n  </div>\n\n  <!-- 4 Summary Cards: Benchmark Architecture & Dataset Evolution -->\n  <div class="project-overview-grid">\n    <div class="overview-card" id="arch-overview-card">\n      <div>\n        <span class="overview-badge badge-arch"><span id="arch-badge">BENCHMARK ARCHITECTURE</span></span>\n        <h4><span id="arch-title">Quarto Hidden-Information Arena</span></h4>\n        <p><span id="arch-desc">\n          A 4&times;4 asymmetric-information game benchmark where two LLMs draft <b>2 secret binary features</b> each from an 18-feature pool, then play Classic Quarto over opaque entity UUIDs without seeing the opponent\'s owned traits or bit permutation.\n        </span></p>\n      </div>\n      <div class="overview-meta"><span id="arch-meta">Deterministic Engine &bull; 1-Ply Eval &bull; Grounding Audit (RL-01)</span></div>\n    </div>\n\n    <div class="overview-card">\n      <div>\n        <span class="overview-badge badge-past">STAGE 1 &bull; PROTOTYPE (BLOCKED)</span>\n        <h4>PubChem Chemical Sample</h4>\n        <p>\n          Initial local prototype over 40 binary molecular attributes using deterministic seed <code>1729</code>. Exhaustive search across 91,390 quartets yielded <b>0 valid 16-entity instances</b> with complete 4-bit coverage, motivating strict combinatorial screening.\n        </p>\n      </div>\n      <div class="overview-meta">40 Attributes &bull; Seed 1729 &bull; 0 / 91,390 Valid Quartets</div>\n    </div>\n\n    <div class="overview-card">\n      <div>\n        <span class="overview-badge badge-past">STAGE 2 &bull; PILOT (ARCHIVED)</span>\n        <h4>QM9 Quantum Chemistry</h4>\n        <p>\n          First viable real-data domain across <b>133,884 sanitized molecules</b> (SMARTS structural graphs). Global screening confirmed 203 feasible quartets and validated end-to-end two-model matches before retiring QM9 for a broader perceptual domain.\n        </p>\n      </div>\n      <div class="overview-meta">133,884 Molecules &bull; 203 Feasible Quartets &bull; Retired Pilot</div>\n    </div>\n\n    <div class="overview-card">\n      <div>\n        <span class="overview-badge badge-active">STAGE 3 &bull; PRODUCTION (ACTIVE)</span>\n        <h4>FMA (Free Music Archive)</h4>\n        <p>\n          Active benchmark pool from <b>106,574 audio tracks</b> using <b>18 frozen descriptors</b> selected out of <b>518 raw librosa columns</b>. Out of <b>1,150 strictly validated candidates</b> across seed-11 &amp; seed-23 scans (<code>id_level &gt; 1</code> &amp; <code>structural &gt; 1</code>), <b>24 curated instances</b> are currently deployed in the arena pool.\n        </p>\n      </div>\n      <div class="overview-meta">18 / 518 Columns &bull; 24 / 1,150 Valid Instances Deployed</div>\n    </div>\n  </div>\n</div>\n\n<script>\nconst PAYLOAD = __PAYLOAD_JSON__;\nconst GAMES = PAYLOAD.matches || [];\nconst MODEL_META = PAYLOAD.model_metadata || {};\n\nfunction shortModelName(raw, fallback) {\n  if (!raw || typeof raw !== "string") return fallback;\n  let s = raw.split("/").pop().split("@")[0];\n  return s\n    .split("-")\n    .map(w => (w.length <= 3 && !/^\\d/.test(w)) ? w.toUpperCase() : (w.charAt(0).toUpperCase() + w.slice(1)))\n    .join(" ");\n}\n\nconst P1_RAW = (MODEL_META.player_1 && MODEL_META.player_1.model) || "Model 1";\nconst P2_RAW = (MODEL_META.player_2 && MODEL_META.player_2.model) || "Model 2";\nconst P1_NAME = shortModelName(P1_RAW, "Gemini");\nconst P2_NAME = shortModelName(P2_RAW, "Claude");\nconst P1_MINI = P1_NAME.split(" ")[0];\nconst P2_MINI = P2_NAME.split(" ")[0];\n\nfunction actorName(role) {\n  if (role === "player_1") return P1_NAME;\n  if (role === "player_2") return P2_NAME;\n  return role || "System";\n}\n\nconst LINES = [\n  { name: "Row 1", cells: [0,1,2,3] },\n  { name: "Row 2", cells: [4,5,6,7] },\n  { name: "Row 3", cells: [8,9,10,11] },\n  { name: "Row 4", cells: [12,13,14,15] },\n  { name: "Col 1", cells: [0,4,8,12] },\n  { name: "Col 2", cells: [1,5,9,13] },\n  { name: "Col 3", cells: [2,6,10,14] },\n  { name: "Col 4", cells: [3,7,11,15] },\n  { name: "Main Diag", cells: [0,5,10,15] },\n  { name: "Anti Diag", cells: [3,6,9,12] }\n];\n\nlet currentGameIdx = 0;\nlet states = [];\nlet currentStep = 0;\nlet playTimer = null;\nlet expandAll = false;\nlet keyOnly = false;\nlet manualExpanded = new Set();\nlet winCellsSet = new Set();\n\nfunction fmtCell(c) { return Number(c) + 1; }\nfunction fmtLine(cells) { return "[" + cells.map(c => Number(c) + 1).join(", ") + "]"; }\n\nfunction renderToken(sig, bitOwners) {\n  if (sig === null || sig === undefined) return "";\n  const s = Math.round(Number(sig));\n  const p1Bits = [];\n  const p2Bits = [];\n  for (let b = 0; b < 4; b++) {\n    if (bitOwners[b] === "player_1") p1Bits.push(b);\n    else p2Bits.push(b);\n  }\n  while (p1Bits.length < 2) p1Bits.push(0);\n  while (p2Bits.length < 2) p2Bits.push(2);\n\n  const tl = (s >> p1Bits[0]) & 1;\n  const bl = (s >> p1Bits[1]) & 1;\n  const tr = (s >> p2Bits[0]) & 1;\n  const br = (s >> p2Bits[1]) & 1;\n\n  return `<div class="token">\n    <div class="bit-box ${tl ? \'p1-on\' : \'p1-off\'}">${tl}</div>\n    <div class="bit-box ${tr ? \'p2-on\' : \'p2-off\'}">${tr}</div>\n    <div class="bit-box ${bl ? \'p1-on\' : \'p1-off\'}">${bl}</div>\n    <div class="bit-box ${br ? \'p2-on\' : \'p2-off\'}">${br}</div>\n  </div>`;\n}\n\nfunction findImmediateLineCompletion(board, sigMap, bitOwners, pieceId) {\n  if (!pieceId || sigMap[pieceId] === undefined) return [];\n  const pSig = Math.round(Number(sigMap[pieceId]));\n  const matches = [];\n  for (const lObj of LINES) {\n    const line = lObj.cells;\n    const empties = line.filter(c => !board[c]);\n    if (empties.length !== 1) continue;\n    const present = line.filter(c => board[c]).map(c => Math.round(Number(sigMap[board[c]])));\n    present.push(pSig);\n    for (let b = 0; b < 4; b++) {\n      const bits = present.map(v => (v >> b) & 1);\n      if (bits.every(x => x === bits[0])) {\n        matches.push({ lineName: lObj.name, line, emptyCell: empties[0], bit: b, owner: bitOwners[b] });\n      }\n    }\n  }\n  return matches;\n}\n\nfunction staticBoardEval(board, sigMap, bitOwners, poolSigs) {\n  let p1Score = 0, p2Score = 0;\n  let p1Win = false, p2Win = false;\n  const winningLinesFound = [];\n  const projectedP1 = new Set();\n  const projectedP2 = new Set();\n  const p1Threats = [];\n  const p2Threats = [];\n\n  for (const lObj of LINES) {\n    const line = lObj.cells;\n    const vals = line.map(c => board[c] ? Math.round(Number(sigMap[board[c]])) : null);\n    const present = vals.filter(v => v !== null && v !== undefined);\n    if (present.length < 2) continue;\n    const emptyCells = line.filter(c => !board[c]);\n    for (let b = 0; b < 4; b++) {\n      const owner = bitOwners[b];\n      const bits = present.map(v => (v >> b) & 1);\n      if (!bits.every(x => x === bits[0])) continue;\n      const targetBit = bits[0];\n      if (present.length === 4) {\n        if (owner === "player_1") p1Win = true;\n        if (owner === "player_2") p2Win = true;\n        winningLinesFound.push({ lineName: lObj.name, cells: line, bit: b, owner, bitVal: targetBit });\n      } else if (present.length === 3) {\n        const liveCount = poolSigs.filter(s => ((s >> b) & 1) === targetBit).length;\n        if (liveCount > 0) {\n          const threatInfo = { lineName: lObj.name, cells: line, targetCell: emptyCells[0], bit: b, targetBit, liveCount };\n          if (owner === "player_1") {\n            p1Score += 3.8;\n            line.forEach(c => projectedP1.add(c));\n            p1Threats.push(threatInfo);\n          } else {\n            p2Score += 3.8;\n            line.forEach(c => projectedP2.add(c));\n            p2Threats.push(threatInfo);\n          }\n        }\n      } else if (present.length === 2) {\n        const completers = poolSigs.filter(s => ((s >> b) & 1) === targetBit).length;\n        if (completers >= 2) {\n          if (owner === "player_1") p1Score += 0.55;\n          if (owner === "player_2") p2Score += 0.55;\n        }\n      }\n    }\n  }\n\n  let score = Math.max(-8.8, Math.min(8.8, p1Score - p2Score));\n  if (p1Win && p2Win) score = 0.0;\n  else if (p1Win) score = 10.0;\n  else if (p2Win) score = -10.0;\n\n  return {\n    score,\n    p1Win,\n    p2Win,\n    winningLinesFound,\n    projectedP1,\n    projectedP2,\n    p1Threats,\n    p2Threats\n  };\n}\n\nfunction evaluateBoard(board, sigMap, bitOwners, receiverPlacer, heldPiece, remainingPool) {\n  const allSigs = Object.values(sigMap).map(v => Math.round(Number(v)));\n  const poolWithoutHeld = Array.isArray(remainingPool)\n    ? remainingPool\n        .filter(eid => eid !== heldPiece)\n        .map(eid => sigMap[eid])\n        .filter(v => v !== undefined && v !== null)\n        .map(v => Math.round(Number(v)))\n    : allSigs;\n\n  const base = staticBoardEval(board, sigMap, bitOwners, poolWithoutHeld);\n  if (base.p1Win || base.p2Win || !heldPiece || !receiverPlacer || sigMap[heldPiece] === undefined) {\n    return { ...base, heldMateFor: null, heldCompletions: [] };\n  }\n\n  const heldCompletions = findImmediateLineCompletion(board, sigMap, bitOwners, heldPiece);\n  const projectedP1 = new Set(base.projectedP1);\n  const projectedP2 = new Set(base.projectedP2);\n  heldCompletions.forEach(m => m.line.forEach(c => {\n    if (m.owner === "player_1") projectedP1.add(c);\n    else projectedP2.add(c);\n  }));\n\n  let bestScore = receiverPlacer === "player_1" ? -Infinity : Infinity;\n  let heldMateFor = null;\n  let hasWinningMove = false;\n  let allMovesLose = true;\n\n  for (let c = 0; c < 16; c++) {\n    if (board[c]) continue;\n    const simBoard = [...board];\n    simBoard[c] = heldPiece;\n    const sim = staticBoardEval(simBoard, sigMap, bitOwners, poolWithoutHeld);\n    const selfWon = receiverPlacer === "player_1" ? sim.p1Win : sim.p2Win;\n    const oppWon = receiverPlacer === "player_1" ? sim.p2Win : sim.p1Win;\n\n    let cellScore = sim.score;\n    if (selfWon && !oppWon) {\n      hasWinningMove = true;\n      allMovesLose = false;\n      cellScore = receiverPlacer === "player_1" ? 9.8 : -9.8;\n    } else if (oppWon && !selfWon) {\n      cellScore = receiverPlacer === "player_1" ? -9.5 : 9.5;\n    } else {\n      allMovesLose = false;\n    }\n\n    if (receiverPlacer === "player_1") {\n      if (cellScore > bestScore) bestScore = cellScore;\n    } else {\n      if (cellScore < bestScore) bestScore = cellScore;\n    }\n  }\n\n  if (hasWinningMove) {\n    heldMateFor = receiverPlacer;\n  } else if (allMovesLose) {\n    heldMateFor = receiverPlacer === "player_1" ? "player_2" : "player_1";\n  }\n\n  if (!Number.isFinite(bestScore)) bestScore = base.score;\n\n  return {\n    score: bestScore,\n    p1Win: base.p1Win,\n    p2Win: base.p2Win,\n    winningLinesFound: base.winningLinesFound,\n    projectedP1,\n    projectedP2,\n    heldMateFor,\n    heldCompletions,\n    p1Threats: base.p1Threats,\n    p2Threats: base.p2Threats\n  };\n}\n\nfunction loadGame(idx) {\n  if (playTimer) togglePlay();\n  currentGameIdx = idx;\n  manualExpanded = new Set();\n  renderTabs();\n  const g = GAMES[idx];\n  const match = g.match || {};\n  const replay = g.public_replay || {};\n  const tv = g.terminal_visualization || {};\n  const sigMap = tv.entity_signatures || {};\n  const legend = tv.bit_feature_legend || [];\n  const winLines = tv.winning_lines || [];\n  const rlog = tv.post_game_reasoning_log || [];\n\n  const bitOwners = ["player_1", "player_1", "player_2", "player_2"];\n  const bitToFeat = {};\n  legend.forEach(item => {\n    const b = Math.round(Number(item.bit));\n    const bIdx = (b >= 1 && b <= 4 && !legend.some(x => Math.round(x.bit) === 0)) ? b - 1 : b;\n    if (!Number.isNaN(bIdx) && bIdx >= 0 && bIdx < 4) {\n      if (item.owner) bitOwners[bIdx] = item.owner;\n      if (item.feature_id) bitToFeat[bIdx] = item.feature_id;\n    }\n  });\n\n  winCellsSet = new Set();\n  winLines.forEach(wl => (wl.cells || []).forEach(c => winCellsSet.add(Math.round(Number(c)))));\n\n  document.getElementById("match-meta").innerHTML =\n    `Instance: <b>${match.instance_id || \'N/A\'}</b> &nbsp;|&nbsp; Starter: <b>${actorName(match.starting_player || \'player_1\')}</b> &nbsp;|&nbsp; Duration: <b>${match.duration_seconds || 0}s</b>`;\n  document.getElementById("versus-title").innerHTML =\n    `<span style="color:var(--p1);">${P1_NAME}</span> vs. <span style="color:var(--p2);">${P2_NAME}</span>`;\n  document.getElementById("eval-top-lbl").textContent = `${P2_MINI}`;\n  document.getElementById("eval-bot-lbl").textContent = `${P1_MINI}`;\n  document.getElementById("footer-quad-hint").innerHTML =\n    `Left bits: <b style="color:var(--p1);">${P1_MINI}</b> &nbsp;|&nbsp; Right bits: <b style="color:var(--p2);">${P2_MINI}</b>`;\n\n  document.getElementById("trait-legend-compact").innerHTML = legend.map(item => {\n    const isP1 = item.owner === "player_1";\n    const ownerShort = isP1 ? P1_MINI : P2_MINI;\n    const bitNum = Math.round(Number(item.bit)) + (legend.some(x => Math.round(x.bit) === 0) ? 1 : 0);\n    return `<div style="margin-bottom:2px;" data-tip="Bit ${bitNum} (${item.feature_id}) belongs privately to ${actorName(item.owner)}. Aligning 4 pieces with matching Bit ${bitNum} wins for ${actorName(item.owner)}.">\n      <b style="color:${isP1 ? \'var(--p1)\' : \'var(--p2)\'};">Bit ${bitNum} (${ownerShort}):</b>\n      <span style="font-family:monospace;font-size:0.65rem;">${item.feature_id}</span>\n    </div>`;\n  }).join("");\n\n  const reasonByStep = {};\n  rlog.forEach(r => {\n    const s = Math.round(Number(r.step));\n    if (!Number.isNaN(s)) reasonByStep[s] = r;\n  });\n\n  const draftHist = replay.draft_history || [];\n  let stepCounter = 0;\n  document.getElementById("draft-log-box").innerHTML = draftHist.length\n    ? draftHist.map((d, i) => {\n        stepCounter += 1;\n        const r = reasonByStep[stepCounter] || {};\n        const acc = d.accepted\n          ? `<span style="color:#4ade80;font-weight:700;">ACCEPTED</span>`\n          : `<span style="color:#9ca3af;">REJECTED</span>`;\n        return `<div style="padding:5px 0;border-bottom:1px solid var(--panel-border);">\n          <div><b>#${i + 1} ${actorName(d.player)}</b> &rarr; <code>${d.attribute_id}</code> (${acc})</div>\n          <div style="color:var(--text-muted);font-size:0.72rem;margin-top:2px;">${r.decision_explanation || \'\'}</div>\n        </div>`;\n      }).join("")\n    : `<div style="color:var(--text-muted);">No draft actions recorded.</div>`;\n\n  const allEntityIds = Object.keys(sigMap);\n  let remainingPool = [...allEntityIds];\n  const starterLabel = actorName(match.starting_player || "player_1");\n\n  states = [{\n    board: Array(16).fill(null),\n    actorLabel: "System",\n    title: "Match Start — Empty 4x4 Board",\n    handNote: `${starterLabel} opens the match`,\n    handSub: `${draftHist.length} draft proposals resolved off-board. Both models hold 2 secret binary win conditions.`,\n    riskText: "Board is empty (Cells 1–16 available). Watch for 3-in-a-row trait alignments.",\n    cell: -1,\n    selected: null,\n    rationale: "Both models drafted 2 secret binary features. Board play starts now.",\n    evalScore: 0.0,\n    tag: null,\n    projectedP1: new Set(),\n    projectedP2: new Set(),\n    sigMap,\n    bitOwners\n  }];\n\n  let curBoard = Array(16).fill(null);\n  let curSelected = null;\n  let actualWinner = match.winner || null;\n  let actualOutcome = match.outcome || null;\n  let actualWinNote = winLines.length\n    ? winLines.map(wl => `Line ${fmtLine(wl.cells)} via ${wl.feature_id || \'Bit \' + (Math.round(Number(wl.bit)) + 1)} (${actorName(wl.owner)})`).join(" & ")\n    : "";\n\n  const pubHist = replay.public_history || [];\n  for (let i = 0; i < pubHist.length; i++) {\n    const act = pubHist[i];\n    stepCounter += 1;\n    const r = reasonByStep[stepCounter] || {};\n    const prevState = states[states.length - 1];\n    const prevEval = prevState.evalScore;\n    const modelLabel = actorName(act.player);\n\n    if (act.kind === "select_entity") {\n      curSelected = act.entity_id;\n      const receiver = act.player === "player_1" ? "player_2" : "player_1";\n      const receiverLabel = actorName(receiver);\n      const safePieces = remainingPool.filter(eid =>\n        findImmediateLineCompletion(curBoard, sigMap, bitOwners, eid).every(m => m.owner !== receiver)\n      );\n      const evObj = evaluateBoard(curBoard, sigMap, bitOwners, receiver, curSelected, remainingPool);\n      const receiverWinsWithPiece = evObj.heldCompletions.filter(m => m.owner === receiver);\n      const selectorTrapsWithPiece = evObj.heldCompletions.filter(m => m.owner === act.player);\n\n      let tag = null;\n      let headline = `${modelLabel} passes piece ${act.entity_id.slice(0, 6)} to ${receiverLabel}`;\n      let detail = `${remainingPool.length} pieces remain in pool. ${receiverLabel} must place it on an open cell.`;\n      let riskText = "Safe handoff: does not immediately complete a 3-in-a-row threat for the receiver.";\n\n      if (receiverWinsWithPiece.length > 0 && selectorTrapsWithPiece.length === 0) {\n        const m = receiverWinsWithPiece[0];\n        const fName = bitToFeat[m.bit] || `Bit ${m.bit + 1}`;\n        if (safePieces.length > 0) {\n          tag = "BLUNDER";\n          headline = `Critical Handoff Blunder by ${modelLabel}!`;\n          detail = `Handed ${act.entity_id.slice(0, 6)} to ${receiverLabel} while ${safePieces.length} safe piece(s) were available.`;\n          riskText = `DANGER: ${receiverLabel} can place on Cell ${fmtCell(m.emptyCell)} (${m.lineName}) to complete ${fName} and win!`;\n        } else {\n          tag = "WARNING";\n          headline = `Forced Losing Handoff (Zugzwang)`;\n          detail = `Every remaining piece completes an immediate winning line for ${receiverLabel}.`;\n          riskText = `WARNING: No safe piece existed. ${receiverLabel} wins at Cell ${fmtCell(m.emptyCell)} (${m.lineName}).`;\n        }\n      } else if (selectorTrapsWithPiece.length > 0) {\n        const m = selectorTrapsWithPiece[0];\n        const emptyCount = curBoard.filter(x => !x).length;\n        const trapCells = [...new Set(selectorTrapsWithPiece.map(x => fmtCell(x.emptyCell)))];\n        if (trapCells.length >= emptyCount) {\n          tag = "WARNING";\n          headline = `Forced Trap Set by ${modelLabel}!`;\n          detail = `Every open cell completes ${modelLabel}\'s line with piece ${act.entity_id.slice(0, 6)}.`;\n          riskText = `TRAP: ${receiverLabel} is forced to complete ${modelLabel}\'s ${m.lineName} on Cell ${trapCells.join(", ")}.`;\n        } else {\n          tag = "WARNING";\n          headline = `Poison Square Warning for ${receiverLabel}`;\n          detail = `Piece ${act.entity_id.slice(0, 6)} matches ${modelLabel}\'s secret trait on ${m.lineName}.`;\n          riskText = `WARNING: ${receiverLabel} must avoid Cell ${trapCells.join(", ")} or ${modelLabel} wins immediately!`;\n        }\n      } else {\n        const oppThreats = receiver === "player_1" ? evObj.p1Threats : evObj.p2Threats;\n        if (oppThreats.length > 0) {\n          const t = oppThreats[0];\n          riskText = `Watch: ${receiverLabel} threatens ${t.lineName} at Cell ${fmtCell(t.targetCell)} (${t.liveCount} completers left).`;\n        }\n      }\n\n      states.push({\n        board: [...curBoard],\n        actorLabel: modelLabel,\n        title: `Selects piece ${act.entity_id.slice(0, 8)} for ${receiverLabel}`,\n        handNote: headline,\n        handSub: detail,\n        riskText,\n        cell: -1,\n        selected: curSelected,\n        rationale: r.decision_explanation || "(No thinking trace emitted)",\n        evalScore: evObj.score,\n        tag,\n        projectedP1: evObj.projectedP1,\n        projectedP2: evObj.projectedP2,\n        sigMap,\n        bitOwners\n      });\n    } else if (act.kind === "place_entity") {\n      const targetCell = Math.round(Number(act.cell));\n      const opponent = act.player === "player_1" ? "player_2" : "player_1";\n      const oppLabel = actorName(opponent);\n      const hadMate = (act.player === "player_1" && prevEval >= 9.7) || (act.player === "player_2" && prevEval <= -9.7);\n\n      curBoard[targetCell] = curSelected;\n      const placed = curSelected;\n      remainingPool = remainingPool.filter(eid => eid !== placed);\n      curSelected = null;\n\n      const evObj = evaluateBoard(curBoard, sigMap, bitOwners, null, null, remainingPool);\n      const newEval = evObj.score;\n      const selfWinLines = evObj.winningLinesFound.filter(w => w.owner === act.player);\n      const oppWinLines = evObj.winningLinesFound.filter(w => w.owner === opponent);\n\n      let tag = null;\n      let headline = `${modelLabel} places on Cell ${fmtCell(targetCell)}`;\n      let detail = `Piece ${placed ? placed.slice(0, 6) : \'?\'} locked onto Cell ${fmtCell(targetCell)}.`;\n      let riskText = "Balanced position: no immediate 4-in-a-row line triggered.";\n\n      if (selfWinLines.length > 0 && oppWinLines.length > 0) {\n        tag = "DRAW";\n        actualWinner = null;\n        actualOutcome = "draw";\n        winCellsSet = new Set([...selfWinLines[0].cells, ...oppWinLines[0].cells]);\n        actualWinNote = `Simultaneous Quarto Draw! ${modelLabel} (${selfWinLines[0].lineName}) & ${oppLabel} (${oppWinLines[0].lineName})`;\n        headline = `Simultaneous Double Quarto (Draw)!`;\n        detail = `Cell ${fmtCell(targetCell)} completed winning traits for BOTH models on the exact same move.`;\n        riskText = actualWinNote;\n      } else if (selfWinLines.length > 0) {\n        const w = selfWinLines[0];\n        const fName = bitToFeat[w.bit] || `Bit ${w.bit + 1}`;\n        tag = "WIN";\n        actualWinner = act.player;\n        actualOutcome = "win";\n        winCellsSet = new Set(w.cells);\n        actualWinNote = `${w.lineName} ${fmtLine(w.cells)} via ${fName} (${modelLabel})`;\n        headline = `QUARTO! ${modelLabel} Wins!`;\n        detail = `Completed 4-in-a-row on ${w.lineName} ${fmtLine(w.cells)} using ${fName}.`;\n        riskText = `VICTORY: ${modelLabel} aligned Bit ${w.bit + 1} = ${w.bitVal} across ${w.lineName}.`;\n      } else if (oppWinLines.length > 0) {\n        const w = oppWinLines[0];\n        const fName = bitToFeat[w.bit] || `Bit ${w.bit + 1}`;\n        tag = "BLUNDER";\n        actualWinner = opponent;\n        actualOutcome = "win";\n        winCellsSet = new Set(w.cells);\n        actualWinNote = `${w.lineName} ${fmtLine(w.cells)} via ${fName} (${oppLabel})`;\n        headline = `Self-Destruct Placement Blunder!`;\n        detail = `${modelLabel} placed on Cell ${fmtCell(targetCell)} and completed ${oppLabel}\'s secret line (${w.lineName}).`;\n        riskText = `BLUNDER: Handed victory directly to ${oppLabel} via ${fName} on ${w.lineName}!`;\n      } else if (hadMate) {\n        tag = "WARNING";\n        headline = `Missed Immediate Win Opportunity!`;\n        detail = `${modelLabel} held a winning piece but placed on Cell ${fmtCell(targetCell)} instead.`;\n        riskText = `WARNING: ${modelLabel} missed a forced Quarto on this turn!`;\n      } else {\n        const oppThreats = opponent === "player_1" ? evObj.p1Threats : evObj.p2Threats;\n        const selfThreats = act.player === "player_1" ? evObj.p1Threats : evObj.p2Threats;\n        if (oppThreats.length > 0) {\n          const t = oppThreats[0];\n          tag = "WARNING";\n          headline = `Opponent 3-in-a-Row Threat Active`;\n          detail = `Placed on Cell ${fmtCell(targetCell)}, leaving ${oppLabel} one piece away on ${t.lineName}.`;\n          riskText = `WARNING: ${oppLabel} threatens ${t.lineName} at Cell ${fmtCell(t.targetCell)} (${t.liveCount} matching pieces left).`;\n        } else if (selfThreats.length > 0) {\n          const t = selfThreats[0];\n          headline = `Threat Created on ${t.lineName}`;\n          detail = `${modelLabel} aligned 3 matching pieces on ${t.lineName} ${fmtLine(t.cells)}.`;\n          riskText = `Pressure: ${modelLabel} threatens Cell ${fmtCell(t.targetCell)} if ${oppLabel} passes a matching piece.`;\n        }\n      }\n\n      states.push({\n        board: [...curBoard],\n        actorLabel: modelLabel,\n        title: `Places ${placed ? placed.slice(0, 8) : \'?\'} on Cell ${fmtCell(targetCell)}` + (selfWinLines.length || oppWinLines.length ? ` -> TERMINAL` : ""),\n        handNote: headline,\n        handSub: detail,\n        riskText,\n        cell: targetCell,\n        selected: null,\n        rationale: r.decision_explanation || "(No thinking trace emitted)",\n        evalScore: newEval,\n        tag,\n        projectedP1: evObj.projectedP1,\n        projectedP2: evObj.projectedP2,\n        sigMap,\n        bitOwners\n      });\n\n      if (selfWinLines.length > 0 || oppWinLines.length > 0) {\n        break;\n      }\n    }\n  }\n\n  document.getElementById("win-trait-note").textContent = actualWinNote;\n  const badge = document.getElementById("outcome-badge");\n  if (actualOutcome === "draw") {\n    badge.textContent = "DRAW (SIMULTANEOUS QUARTO)";\n    badge.style.color = "var(--ink)";\n    badge.style.background = "rgba(43, 41, 38, 0.08)";\n  } else {\n    badge.textContent = actualWinner ? `WINNER: ${actorName(actualWinner).toUpperCase()}` : "COMPLETED";\n    badge.style.color = actualWinner === "player_1" ? "var(--p1)" : (actualWinner === "player_2" ? "var(--p2)" : "var(--ink)");\n    badge.style.background = actualWinner === "player_1" ? "var(--p1-soft)" : (actualWinner === "player_2" ? "var(--p2-soft)" : "transparent");\n  }\n\n  const slider = document.getElementById("step-slider");\n  slider.max = states.length - 1;\n  slider.value = states.length - 1;\n  renderStep(states.length - 1);\n}\n\nfunction renderMusicStaff() {\n  const svg = document.getElementById("music-staff");\n  if (!svg || states.length === 0) return;\n  const w = 220, topY = 9, gap = 7;\n  const midY = topY + gap * 2;\n  let staffLines = "";\n  for (let i = 0; i < 5; i++) {\n    const y = topY + i * gap;\n    staffLines += `<line x1="6" y1="${y}" x2="${w - 6}" y2="${y}" stroke="#9e978b" stroke-width="0.9" opacity="0.65" />`;\n  }\n  const n = states.length;\n  const pts = states.map((s, i) => {\n    const x = n === 1 ? w / 2 : 12 + (i / (n - 1)) * (w - 24);\n    const y = midY - (s.evalScore / 10) * (gap * 2);\n    return { x, y, i, s };\n  });\n  const poly = pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");\n  const dots = pts.map(p => {\n    const isCur = p.i === currentStep;\n    const fill = p.s.evalScore > 0.2 ? "#3b6998" : (p.s.evalScore < -0.2 ? "#b8653b" : "#2b2926");\n    const r = isCur ? 4.2 : 2.3;\n    return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r}" fill="${fill}" stroke="${isCur ? \'#f4f1ea\' : \'none\'}" stroke-width="1.2" onclick="stepTo(${p.i})" />`;\n  }).join("");\n  svg.innerHTML = `${staffLines}<polyline fill="none" stroke="#2b2926" stroke-width="1.2" opacity="0.7" points="${poly}" />${dots}`;\n}\n\nfunction toggleCardThinking(e, idx) {\n  e.stopPropagation();\n  if (manualExpanded.has(idx)) manualExpanded.delete(idx);\n  else manualExpanded.add(idx);\n  renderStep(currentStep);\n}\n\nfunction renderStep(idx) {\n  currentStep = Math.max(0, Math.min(states.length - 1, idx));\n  document.getElementById("step-slider").value = currentStep;\n  document.getElementById("step-counter").textContent = `${currentStep}/${states.length - 1}`;\n  const st = states[currentStep];\n  const isFinal = currentStep === states.length - 1;\n\n  document.getElementById("hand-annotation").textContent = st.handNote;\n  document.getElementById("hand-subnote").textContent = st.handSub;\n  document.getElementById("tactical-risk").textContent = st.riskText;\n\n  const tBadge = document.getElementById("tactical-badge");\n  if (st.tag === "BLUNDER") tBadge.innerHTML = `<span style="font-weight:700;color:var(--danger);">BLUNDER</span>`;\n  else if (st.tag === "WARNING") tBadge.innerHTML = `<span style="font-weight:700;color:var(--warn);">WARNING</span>`;\n  else if (st.tag === "DRAW") tBadge.innerHTML = `<span style="font-weight:700;color:var(--ink-soft);">DRAW</span>`;\n  else if (st.tag === "WIN") tBadge.innerHTML = `<span style="font-weight:700;color:var(--win);">WIN</span>`;\n  else tBadge.innerHTML = "";\n\n  const sc = st.evalScore;\n  const scoreEl = document.getElementById("eval-score");\n  scoreEl.textContent = (sc > 0 ? "+" : "") + sc.toFixed(1);\n  scoreEl.style.color = sc > 0.05 ? "var(--p1)" : (sc < -0.05 ? "var(--p2)" : "var(--ink)");\n  const p1Pct = Math.max(0, Math.min(100, 50 + (sc / 10) * 50));\n  const p2Pct = 100 - p1Pct;\n  const p1El = document.getElementById("eval-p1-fill");\n  const p2El = document.getElementById("eval-p2-fill");\n  const isMobile = window.innerWidth <= 480;\n  if (isMobile) {\n    p2El.style.width = `${p2Pct.toFixed(1)}%`;\n    p2El.style.height = "100%";\n    p1El.style.width = `${p1Pct.toFixed(1)}%`;\n    p1El.style.height = "100%";\n  } else {\n    p2El.style.width = "100%";\n    p2El.style.height = `${p2Pct.toFixed(1)}%`;\n    p1El.style.width = "100%";\n    p1El.style.height = `${p1Pct.toFixed(1)}%`;\n  }\n\n  const heldBox = document.getElementById("held-piece-box");\n  if (st.selected) {\n    const hSig = st.sigMap[st.selected];\n    heldBox.innerHTML = `${renderToken(hSig, st.bitOwners)}<div class="token-code">${st.selected.slice(0, 8)}</div>`;\n  } else {\n    heldBox.innerHTML = `<span style="font-size:0.74rem;color:var(--ink-soft);">None</span>`;\n  }\n\n  renderMusicStaff();\n  const grid = document.getElementById("board-grid");\n  grid.innerHTML = st.board.map((eid, c) => {\n    const isLast = st.cell === c;\n    const isWin = isFinal && winCellsSet.has(c);\n    const isProjP1 = !isWin && st.projectedP1 && st.projectedP1.has(c);\n    const isProjP2 = !isWin && !isProjP1 && st.projectedP2 && st.projectedP2.has(c);\n    const sig = eid ? st.sigMap[eid] : null;\n    return `<div class="cell ${isLast ? \'last\' : \'\'} ${isProjP1 ? \'projected-p1\' : \'\'} ${isProjP2 ? \'projected-p2\' : \'\'} ${isWin ? \'win\' : \'\'}">\n      <span class="cell-num">${c + 1}</span>\n      ${eid ? renderToken(sig, st.bitOwners) + `<span class="token-code">${eid.slice(0, 6)}</span>` : ``}\n    </div>`;\n  }).join("");\n\n  const streamEl = document.getElementById("log-stream");\n  const visibleItems = states.map((s, i) => ({ s, i })).filter(({ s, i }) => !keyOnly || s.tag !== null || i === 0 || i === currentStep);\n  streamEl.innerHTML = visibleItems.map(({ s, i }) => {\n    const tagHtml = s.tag === "BLUNDER"\n      ? `<span class="tag tag-blunder">BLUNDER</span>`\n      : (s.tag === "WARNING"\n          ? `<span class="tag tag-warning">WARNING</span>`\n          : (s.tag === "DRAW"\n              ? `<span class="tag tag-draw">DRAW</span>`\n              : (s.tag === "WIN" ? `<span class="tag tag-win">WIN</span>` : "")));\n    const isExp = expandAll || i === currentStep || manualExpanded.has(i);\n    const toggleLbl = isExp ? "&#9652; Hide thinking" : "&#9662; Show thinking";\n    return `<div class="log-card ${i === currentStep ? \'active\' : \'\'} ${isExp ? \'expanded\' : \'\'}" onclick="stepTo(${i})">\n      <div class="log-card-top">\n        <span>${s.actorLabel} ${tagHtml}</span>\n        <span style="color:var(--text-muted);font-family:monospace;">#${i}</span>\n      </div>\n      <div class="log-card-desc">${s.title}</div>\n      <div class="thinking-toggle" onclick="toggleCardThinking(event, ${i})">${toggleLbl}</div>\n      <div class="thinking-body">${s.rationale}</div>\n    </div>`;\n  }).join("");\n\n  const activeCard = streamEl.querySelector(".log-card.active");\n  if (activeCard) activeCard.scrollIntoView({ block: "nearest" });\n}\n\nfunction toggleExpandAll() {\n  expandAll = !expandAll;\n  if (!expandAll) manualExpanded.clear();\n  document.getElementById("expand-all-btn").textContent = expandAll ? "Collapse All Thinking" : "Expand All Thinking";\n  renderStep(currentStep);\n}\n\nfunction toggleKeyOnly() {\n  keyOnly = !keyOnly;\n  const btn = document.getElementById("key-only-btn");\n  btn.classList.toggle("active-filter", keyOnly);\n  renderStep(currentStep);\n}\n\nfunction stepTo(i) { renderStep(i); }\nfunction stepBy(d) { renderStep(currentStep + d); }\n\nfunction updatePlaySpeed() {\n  if (playTimer) {\n    togglePlay();\n    togglePlay();\n  }\n}\n\nfunction togglePlay() {\n  const btn = document.getElementById("play-btn");\n  if (playTimer) {\n    clearInterval(playTimer);\n    playTimer = null;\n    btn.innerHTML = "&#9654;";\n  } else {\n    if (currentStep >= states.length - 1) renderStep(0);\n    btn.innerHTML = "&#10074;&#10074;";\n    const delay = parseInt(document.getElementById("speed-select").value, 10) || 850;\n    playTimer = setInterval(() => {\n      if (currentStep >= states.length - 1) { togglePlay(); return; }\n      stepBy(1);\n    }, delay);\n  }\n}\n\ndocument.addEventListener("keydown", (e) => {\n  if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA")) return;\n  if (e.key === "ArrowLeft") { e.preventDefault(); stepBy(-1); }\n  else if (e.key === "ArrowRight") { e.preventDefault(); stepBy(1); }\n  else if (e.key === " ") { e.preventDefault(); togglePlay(); }\n});\n\nfunction renderTabs() {\n  document.getElementById("game-tabs").innerHTML = GAMES.map((g, i) => {\n    const m = g.match || {};\n    const outcomeLabel = m.outcome === "draw" ? "Draw" : (m.winner ? actorName(m.winner) : "Draw");\n    return `<button class="tab-btn ${i === currentGameIdx ? \'active\' : \'\'}" onclick="loadGame(${i})">\n      Game ${i + 1} (${outcomeLabel})\n    </button>`;\n  }).join("");\n}\n\nfunction renderBottomPanels() {\n  const ev = PAYLOAD.evaluator || {};\n  const agg = (ev.series_aggregate && ev.series_aggregate.players) || {};\n  const p1 = agg.player_1 || {};\n  const p2 = agg.player_2 || {};\n  document.getElementById("series-summary").innerHTML = `\n    <table>\n      <tr>\n        <th>Metric</th>\n        <th>${P1_NAME}</th>\n        <th>${P2_NAME}</th>\n      </tr>\n      <tr style="background:rgba(255,255,255,0.04);">\n        <td><span data-tip="Weighted 0-100 Arena Composite Index: 40% Win Rate + 20% Blunder Avoidance + 15% Draft Precision + 15% Hidden Trait Discovery + 10% Strict Grounding."><b>Arena Index (0–100)</b></span></td>\n        <td><b>${p1.arena_composite_index ?? \'N/A\'}</b></td>\n        <td><b>${p2.arena_composite_index ?? \'N/A\'}</b></td>\n      </tr>\n      <tr>\n        <td><span data-tip="Total games won by completing a 4-in-a-row line on one of the model\'s 2 privately owned features.">Wins</span></td>\n        <td>${p1.wins ?? 0}</td>\n        <td>${p2.wins ?? 0}</td>\n      </tr>\n      <tr>\n        <td><span data-tip="Accepted draft proposals divided by total draft proposals. Measures how efficiently the model solves the 16-track orthogonal bit-partition constraint.">Draft Precision</span></td>\n        <td>${p1.draft_precision ?? \'N/A\'}</td>\n        <td>${p2.draft_precision ?? \'N/A\'}</td>\n      </tr>\n      <tr>\n        <td><span data-tip="Fraction of turns where the model avoided handing an immediate winning piece to the opponent or placing into an opponent\'s winning square when a safe alternative existed.">Blunder Avoidance</span></td>\n        <td>${p1.blunder_avoidance_rate ?? \'N/A\'}</td>\n        <td>${p2.blunder_avoidance_rate ?? \'N/A\'}</td>\n      </tr>\n      <tr>\n        <td><span data-tip="Fraction of select turns where the model passed a safe piece that simultaneously created an immediate winning threat on its own trait (poison-square trap pressure).">Strategic Trap Rate</span></td>\n        <td>${p1.strategic_trap_rate ?? \'N/A\'}</td>\n        <td>${p2.strategic_trap_rate ?? \'N/A\'}</td>\n      </tr>\n      <tr>\n        <td><span data-tip="Fraction of turns where the model held a piece capable of winning immediately on its own trait and successfully placed it on the winning cell.">Win Conversion</span></td>\n        <td>${p1.immediate_win_conversion_rate ?? \'N/A\'}</td>\n        <td>${p2.immediate_win_conversion_rate ?? \'N/A\'}</td>\n      </tr>\n    </table>`;\n\n  const rga = ev.reasoning_grounding_audit || ev.semantic_judge || {};\n  if (rga.status === "completed" && rga.scores) {\n    const sc = rga.scores || {};\n    const j1 = sc.player_1 || {};\n    const j2 = sc.player_2 || {};\n    document.getElementById("judge-summary").innerHTML = `\n      <table>\n        <tr>\n          <th>Deterministic Audit</th>\n          <th>${P1_NAME}</th>\n          <th>${P2_NAME}</th>\n        </tr>\n        <tr>\n          <td><span data-tip="HI-04 Hidden Trait Discovery Rate: Fraction of the opponent\'s 2 secret win-condition features explicitly deduced and identified in candidate hypotheses or explanations.">Opponent Trait Discovery (HI-04)</span></td>\n          <td>${j1.hidden_trait_discovery_rate ?? \'N/A\'}</td>\n          <td>${j2.hidden_trait_discovery_rate ?? \'N/A\'}</td>\n        </tr>\n        <tr>\n          <td><span data-tip="Strict RL-01v2 Faithfulness Rate: Percentage of move explanations free from draft repeats, blunder blindness, and phantom win claims.">Strict Faithfulness (RL-01v2)</span></td>\n          <td>${j1.deterministic_faithfulness_rate ?? j1.logical_faithfulness_rate ?? \'N/A\'}</td>\n          <td>${j2.deterministic_faithfulness_rate ?? j2.logical_faithfulness_rate ?? \'N/A\'}</td>\n        </tr>\n        <tr>\n          <td><span data-tip="RL-03 Evidence Citation Rate: Fraction of move explanations that explicitly reference concrete verifiable identifiers (feature descriptors or cell coordinates).">Evidence Citation (RL-03)</span></td>\n          <td>${j1.evidence_citation_rate ?? \'N/A\'}</td>\n          <td>${j2.evidence_citation_rate ?? \'N/A\'}</td>\n        </tr>\n        <tr>\n          <td><span data-tip="Combined count of Draft Repeats (RL-06), Blunder Blindness, and Phantom Win Claims detected by deterministic engine verification.">Audit Violations</span></td>\n          <td>${(j1.draft_repeat_claim_count ?? 0) + (j1.blunder_blindness_count ?? 0) + (j1.phantom_claim_count ?? 0)}</td>\n          <td>${(j2.draft_repeat_claim_count ?? 0) + (j2.blunder_blindness_count ?? 0) + (j2.phantom_claim_count ?? 0)}</td>\n        </tr>\n      </table>`;\n  } else {\n    document.getElementById("judge-summary").innerHTML = `<div style="color:var(--text-muted);font-size:0.8rem;">Status: <b>${rga.status || \'unavailable\'}</b></div>`;\n  }\n}\n\nfunction updateArchitectureCard() {\n  const mode = (PAYLOAD && PAYLOAD.mode) || ((GAMES[0] && GAMES[0].match && GAMES[0].match.mode) || "classic");\n  if (mode === "self_selection") {\n    const badge = document.getElementById("arch-badge");\n    const title = document.getElementById("arch-title");\n    const desc = document.getElementById("arch-desc");\n    const meta = document.getElementById("arch-meta");\n    if (badge) badge.textContent = "BENCHMARK ARCHITECTURE • SELF-SELECTION";\n    if (title) title.textContent = "Quarto Self-Selection Arena";\n    if (desc) {\n      desc.innerHTML = "A 4×4 asymmetric-information variant where two LLMs draft <b>2 secret binary features</b> each from an 18-feature pool, then <b>select and place pieces for themselves</b> on the same turn over opaque entity UUIDs without seeing the opponent\'s owned traits or bit permutation.";\n    }\n    if (meta) meta.textContent = "Self-Selection Mode • Lookahead Eval • Grounding Audit (RL-01)";\n  }\n}\n\nupdateArchitectureCard();\nrenderBottomPanels();\nif (GAMES.length > 0) loadGame(0);\n</script>\n</body>\n</html>\n'

def _save_visualizer(result_payload: dict) -> None:
    if not isinstance(result_payload, dict):
        return
    html_code = HTML_TEMPLATE.replace("__PAYLOAD_JSON__", json.dumps(result_payload, ensure_ascii=False))
    Path("quarto_match_visualizer.html").write_text(html_code, encoding="utf-8")
    Path("quarto_arena_results.json").write_text(
        json.dumps(result_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save compact CSV leaderboard summary for persistent Kaggle Output
    agg_players = ((result_payload.get("evaluator") or {}).get("series_aggregate") or {}).get("players") or {}
    meta = result_payload.get("model_metadata") or {}
    csv_lines = [
        "seat,model,arena_composite_index,wins,win_rate,blunder_avoidance_rate,strategic_trap_rate,draft_precision,hidden_trait_discovery_rate"
    ]
    for seat in ("player_1", "player_2"):
        p = agg_players.get(seat) or {}
        m_name = (meta.get(seat) or {}).get("model", seat)
        csv_lines.append(
            f"{seat},{m_name},{p.get('arena_composite_index','')},{p.get('wins','')},"
            f"{p.get('win_rate','')},{p.get('blunder_avoidance_rate','')},"
            f"{p.get('strategic_trap_rate','')},{p.get('draft_precision','')},"
            f"{p.get('hidden_trait_discovery_rate','')}"
        )
    Path("quarto_arena_leaderboard.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    # Render interactive visualizer inline inside Kaggle Notebook cell output
    try:
        import base64
        from IPython.display import HTML, display
        b64 = base64.b64encode(html_code.encode("utf-8")).decode("ascii")
        iframe = (
            f'<iframe src="data:text/html;base64,{b64}" '
            f'style="width:100%;height:980px;border:1px solid #30363d;border-radius:10px;" '
            f'sandbox="allow-scripts"></iframe>'
        )
        display(HTML(iframe))
    except Exception:
        pass

def _extract_primary_arena_score(result_payload: dict) -> float:
    if not isinstance(result_payload, dict):
        return 0.0
    ev = result_payload.get("evaluator") or {}
    agg = (ev.get("series_aggregate") or {}).get("players") or {}
    p1 = agg.get("player_1") or {}
    score = p1.get("arena_composite_index")
    try:
        return round(float(score) / 100.0, 4) if score is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


@kbench.task(name="Hidden information - Quarto Arena")
def run_quarto_two_model_match(llm) -> float:
    failure_context = {
        "stage": "task_setup",
        "started_at": time.monotonic(),
    }
    task_module = _prepare_and_load_quarto_module()
    try:
        res = task_module._run_quarto_two_model_match(llm, failure_context)
        _save_visualizer(res)
        series_info = res.get("series") or {}
        completed = float(series_info.get("completed_games_count") or 0.0)
        if hasattr(kbench, "assertions") and hasattr(kbench.assertions, "assert_true"):
            kbench.assertions.assert_true(
                completed >= 1.0,
                expectation="At least one complete game must finish in the alternating-start series.",
            )
        return _extract_primary_arena_score(res)
    except Exception as error:
        mr = failure_context.get("match_result")
        if mr is not None:
            print("DEBUG_FAILURE_REASON:", getattr(mr, "failure", None))
            rlog = getattr(mr, "restricted_log", {}) or {}
            events = rlog.get("events", [])
            if events:
                print("DEBUG_LAST_EVENT:", json.dumps(events[-1], default=str)[:1000])
        task_module._emit_failure_diagnostic(error, failure_context)
        raise


_task_run = run_quarto_two_model_match.run(llm=kbench.llm)
