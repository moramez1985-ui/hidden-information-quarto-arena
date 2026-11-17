import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import types
import zipfile

sys.dont_write_bytecode = True

import kaggle_benchmarks as kbench

EXPECTED_PLAIN_FILES = {
    "ATTRIBUTION.md",
    "quarto_two_model_match.py",
    "requirements.txt",
    "kaggle_agent_adapter.py",
    "tournament_harness.py",
    "phase0_foundation.py",
    "quarto_engine.py",
    "decision_trace.py",
    "fma_pilot.py",
    "fma_pilot_instance.json",
}


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


def _prepare_and_load_quarto_module():
    sys.dont_write_bytecode = True
    manifest_candidates = list(Path("/kaggle/input").rglob("manifest.json"))
    if not manifest_candidates:
        raise FileNotFoundError("manifest.json not found under /kaggle/input")
    mounted_root = manifest_candidates[0].parent

    fma_candidates = list(Path("/kaggle/input").rglob("fma_metadata.zip*"))
    if not fma_candidates:
        raise FileNotFoundError("fma_metadata.zip* not found under /kaggle/input")
    fma_archive = fma_candidates[0]

    work_root = Path("/tmp/quarto-two-model-source-v1")
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    for name in EXPECTED_PLAIN_FILES:
        src = mounted_root / name
        if not src.is_file():
            raise FileNotFoundError(f"Missing {name} in {mounted_root}")
        shutil.copy2(src, work_root / name)

    for arena_src in sorted(mounted_root.glob("fma_*arena*.json")):
        shutil.copy2(arena_src, work_root / arena_src.name)

    manifest = json.loads((mounted_root / "manifest.json").read_text(encoding="utf-8"))
    zip_path = work_root / "domain_adapters.zip"

    if (mounted_root / "domain_adapters.zip").is_file():
        shutil.copy2(mounted_root / "domain_adapters.zip", zip_path)
    elif (mounted_root / "domain_adapters.zip.bin").is_file():
        shutil.copy2(mounted_root / "domain_adapters.zip.bin", zip_path)
    else:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for member in manifest["archive_members"]:
                rel_posix = member["path"]
                src_candidates = list((mounted_root / "domain_adapters").rglob(Path(rel_posix).name))
                if not src_candidates:
                    raise FileNotFoundError(f"Missing adapter {rel_posix} in {mounted_root}")
                data = src_candidates[0].read_bytes()
                info = zipfile.ZipInfo(filename=rel_posix, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o644 << 16
                zf.writestr(info, data)

        actual_zip_bytes = zip_path.read_bytes()
        actual_zip_sha = hashlib.sha256(actual_zip_bytes).hexdigest()
        for entry in manifest["included_files"]:
            if entry["path"] == "domain_adapters.zip":
                entry["sha256"] = actual_zip_sha
                entry["size_bytes"] = len(actual_zip_bytes)

    eval_zip_path = work_root / "evaluator.zip"
    if (mounted_root / "evaluator.zip").is_file():
        shutil.copy2(mounted_root / "evaluator.zip", eval_zip_path)
    elif (mounted_root / "evaluator.zip.bin").is_file():
        shutil.copy2(mounted_root / "evaluator.zip.bin", eval_zip_path)
    else:
        with zipfile.ZipFile(eval_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for member in manifest.get("evaluator_members", []):
                rel_posix = member["path"]
                src_candidates = list((mounted_root / "evaluator").rglob(Path(rel_posix).name))
                if not src_candidates:
                    raise FileNotFoundError(f"Missing evaluator module {rel_posix} in {mounted_root}")
                data = src_candidates[0].read_bytes()
                info = zipfile.ZipInfo(filename=rel_posix, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o644 << 16
                zf.writestr(info, data)
        actual_eval_bytes = eval_zip_path.read_bytes()
        actual_eval_sha = hashlib.sha256(actual_eval_bytes).hexdigest()
        for entry in manifest["included_files"]:
            if entry["path"] == "evaluator.zip":
                entry["sha256"] = actual_eval_sha
                entry["size_bytes"] = len(actual_eval_bytes)

    new_manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    (work_root / "manifest.json").write_bytes(new_manifest_bytes)
    (work_root / "manifest.sha256").write_text(
        f"{hashlib.sha256(new_manifest_bytes).hexdigest()}  manifest.json\n",
        encoding="utf-8",
    )

    os.environ["QUARTO_FMA_LICENSE_APPROVED"] = "1"
    os.environ["QUARTO_SOURCE_SNAPSHOT_ROOT"] = str(work_root)
    os.environ["QUARTO_FMA_ARCHIVE_PATH"] = str(fma_archive)

    if str(work_root) not in sys.path:
        sys.path.insert(0, str(work_root))
    if str(zip_path) not in sys.path:
        sys.path.insert(0, str(zip_path))
    if str(eval_zip_path) not in sys.path:
        sys.path.insert(0, str(eval_zip_path))

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

    task_module.kbench = real_kbench
    return task_module


def _save_visualizer(result_payload: dict) -> None:
    if not isinstance(result_payload, dict):
        return
    html_tpl = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>Quarto Hidden-Information Game Arena Visualizer</title>\n<style>\n  :root {\n    --bg: #0b1120;\n    --panel: #111827;\n    --card: #1e293b;\n    --border: #334155;\n    --text: #f8fafc;\n    --muted: #94a3b8;\n    --p1: #38bdf8;\n    --p2: #fb923c;\n    --win: #10b981;\n    --danger: #f43f5e;\n  }\n  * { box-sizing: border-box; }\n  body { margin: 0; background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, sans-serif; }\n  .container { max-width: 1240px; margin: 16px auto; padding: 16px; }\n  .header { display: flex; justify-content: space-between; align-items: center; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 18px; margin-bottom: 14px; flex-wrap: wrap; gap: 10px; }\n  .header h1 { margin: 0; font-size: 1.2rem; color: var(--p1); }\n  .sub { font-size: 0.82rem; color: var(--muted); margin-top: 4px; }\n  .badge { padding: 6px 14px; border-radius: 999px; font-weight: 700; font-size: 0.82rem; }\n  .tabs { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }\n  .tab-btn { background: var(--card); color: var(--text); border: 1px solid var(--border); padding: 7px 14px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.82rem; }\n  .tab-btn.active { background: #0284c7; border-color: var(--p1); }\n  .main-grid { display: grid; grid-template-columns: 56px 430px 1fr; gap: 16px; align-items: start; }\n  @media (max-width: 980px) { .main-grid { grid-template-columns: 1fr; } }\n  .eval-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 8px; display: flex; flex-direction: column; align-items: center; height: 470px; }\n  .eval-label { font-size: 0.7rem; font-weight: 700; color: var(--muted); margin-bottom: 6px; }\n  .eval-bar { width: 22px; flex: 1; background: var(--p2); border-radius: 6px; overflow: hidden; display: flex; flex-direction: column; border: 1px solid #475569; }\n  .eval-p1 { background: var(--p1); width: 100%; transition: height 0.25s ease; }\n  .eval-score { font-size: 0.72rem; font-weight: 700; margin-top: 6px; color: var(--text); }\n  .board-panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px; }\n  .controls { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }\n  .controls button { background: var(--card); color: var(--text); border: 1px solid var(--border); padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: 600; }\n  .controls button:hover { border-color: var(--p1); }\n  .controls input { flex: 1; cursor: pointer; }\n  .step-banner { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 0.84rem; font-weight: 600; margin-bottom: 10px; text-align: center; }\n  .board { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; background: #0f172a; padding: 10px; border-radius: 10px; border: 1px solid var(--border); }\n  .cell { height: 88px; border-radius: 8px; background: var(--card); border: 2px solid var(--border); display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; transition: all 0.2s; }\n  .cell.last { border-color: var(--p1); box-shadow: 0 0 10px rgba(56, 189, 248, 0.35); }\n  .cell.win { border-color: var(--win); background: rgba(16, 185, 129, 0.14); box-shadow: 0 0 14px rgba(16, 185, 129, 0.45); }\n  .cell-idx { position: absolute; top: 4px; left: 6px; font-size: 0.65rem; color: var(--muted); }\n  .cell-id { font-size: 0.66rem; color: var(--muted); margin-top: 4px; font-family: monospace; }\n  .glyph { display: grid; grid-template-columns: 1fr 1fr; gap: 3px; width: 42px; height: 42px; padding: 3px; background: #0b1120; border-radius: 8px; border: 1px solid #475569; }\n  .qbit { border-radius: 3px; display: flex; align-items: center; justify-content: center; font-size: 0.58rem; font-weight: 800; }\n  .qbit.p1.on { background: var(--p1); color: #082f49; }\n  .qbit.p1.off { border: 1.5px solid var(--p1); color: var(--p1); opacity: 0.55; }\n  .qbit.p2.on { background: var(--p2); color: #431407; }\n  .qbit.p2.off { border: 1.5px solid var(--p2); color: var(--p2); opacity: 0.55; }\n  .right-col { display: flex; flex-direction: column; gap: 12px; }\n  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }\n  .card-title { font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 700; margin-bottom: 8px; display: flex; justify-content: space-between; }\n  .legend-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }\n  .legend-item { background: var(--card); border-radius: 8px; padding: 7px 10px; font-size: 0.78rem; border-left: 4px solid var(--border); }\n  .legend-item.p1 { border-left-color: var(--p1); }\n  .legend-item.p2 { border-left-color: var(--p2); }\n  .reasoning-box { background: var(--card); border-left: 4px solid var(--p1); border-radius: 8px; padding: 10px 12px; font-size: 0.85rem; line-height: 1.5; min-height: 64px; }\n  .reasoning-box.p2 { border-left-color: var(--p2); }\n  .log-list { max-height: 210px; overflow-y: auto; font-family: monospace; font-size: 0.78rem; }\n  .log-row { padding: 4px 6px; border-radius: 5px; cursor: pointer; display: flex; justify-content: space-between; gap: 8px; }\n  .log-row:hover { background: var(--card); }\n  .log-row.active { background: #0284c7; color: #fff; }\n  .tag-blunder { background: var(--danger); color: #fff; padding: 1px 6px; border-radius: 4px; font-size: 0.68rem; font-weight: 700; }\n  .tag-mate { background: var(--win); color: #052e16; padding: 1px 6px; border-radius: 4px; font-size: 0.68rem; font-weight: 700; }\n  .bottom-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }\n  @media (max-width: 980px) { .bottom-grid { grid-template-columns: 1fr; } }\n  table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }\n  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }\n  th { color: var(--muted); font-weight: 600; }\n  svg.spark { width: 100%; height: 64px; background: #0f172a; border-radius: 8px; border: 1px solid var(--border); }\n</style>\n</head>\n<body>\n<div class="container">\n  <div class="header">\n    <div>\n      <h1>Quarto Hidden-Information Game Arena</h1>\n      <div id="match-meta" class="sub"></div>\n    </div>\n    <div id="outcome-badge" class="badge"></div>\n  </div>\n\n  <div id="game-tabs" class="tabs"></div>\n\n  <div class="main-grid">\n    <div class="eval-wrap" title="Deterministic Win-Threat Balance (Blue = Player 1, Orange = Player 2)">\n      <div class="eval-label">EVAL</div>\n      <div class="eval-bar"><div id="eval-p1-fill" class="eval-p1" style="height:50%;"></div></div>\n      <div id="eval-score-text" class="eval-score">0.0</div>\n    </div>\n\n    <div class="board-panel">\n      <div class="controls">\n        <button onclick="stepMove(-1)">Prev</button>\n        <input id="step-slider" type="range" min="0" max="0" value="0" oninput="renderStep(parseInt(this.value))">\n        <button onclick="stepMove(1)">Next</button>\n      </div>\n      <div id="step-banner" class="step-banner"></div>\n      <div id="board-grid" class="board"></div>\n      <div style="margin-top:10px;font-size:0.75rem;color:var(--muted);display:flex;justify-content:space-between;">\n        <span>Left Quadrants: <b style="color:var(--p1);">Player 1 Bits (0,1)</b></span>\n        <span>Right Quadrants: <b style="color:var(--p2);">Player 2 Bits (2,3)</b></span>\n      </div>\n    </div>\n\n    <div class="right-col">\n      <div class="card">\n        <div class="card-title"><span>Private Feature Ownership (4-Bit Quartet)</span><span id="win-trait-note" style="color:var(--win);"></span></div>\n        <div id="legend-grid" class="legend-grid"></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span>Agent Decision Rationale (Self-Reported)</span><span id="reasoning-actor"></span></div>\n        <div id="reasoning-box" class="reasoning-box">No rationale emitted for this step.</div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span>Advantage Swing & Action Timeline</span><span id="selected-piece-badge"></span></div>\n        <svg id="eval-spark" class="spark" viewBox="0 0 400 64" preserveAspectRatio="none"></svg>\n        <div id="action-log" class="log-list" style="margin-top:8px;"></div>\n      </div>\n    </div>\n  </div>\n\n  <div class="bottom-grid">\n    <div class="card">\n      <div class="card-title"><span>Series Summary & Automated Evaluator</span></div>\n      <div id="eval-summary"></div>\n    </div>\n    <div class="card">\n      <div class="card-title"><span>Post-Game 3rd-LLM Semantic Judge</span></div>\n      <div id="judge-summary"></div>\n    </div>\n  </div>\n</div>\n\n<script>\nconst DATA = __PAYLOAD_JSON__;\nconst GAMES = Array.isArray(DATA.matches) && DATA.matches.length > 0\n  ? DATA.matches\n  : [{ match: DATA.match || {}, public_replay: DATA.public_replay || {}, terminal_visualization: DATA.terminal_visualization || {} }];\nconst MODELS = DATA.model_metadata || {};\nconst P1_NAME = MODELS.player_1 ? MODELS.player_1.model : "player_1";\nconst P2_NAME = MODELS.player_2 ? MODELS.player_2.model : "player_2";\n\nconst LINES = [\n  [0,1,2,3],[4,5,6,7],[8,9,10,11],[12,13,14,15],\n  [0,4,8,12],[1,5,9,13],[2,6,10,14],[3,7,11,15],\n  [0,5,10,15],[3,6,9,12]\n];\n\nlet currentGameIdx = 0;\nlet states = [];\nlet winCellsSet = new Set();\n\nfunction renderTabs() {\n  const tabs = document.getElementById("game-tabs");\n  tabs.innerHTML = GAMES.map((g, idx) => {\n    const m = g.match || {};\n    const label = `Game ${idx + 1} (${m.instance_id || \'instance\'}) — ${m.winner || \'Draw\'}`;\n    return `<button class="tab-btn ${idx === currentGameIdx ? \'active\' : \'\'}" onclick="loadGame(${idx})">${label}</button>`;\n  }).join("");\n}\n\nfunction evaluateBoard(board, sigMap, bitOwners) {\n  let p1Score = 0, p2Score = 0;\n  let p1Win = false, p2Win = false;\n  for (const line of LINES) {\n    const vals = line.map(c => board[c] ? sigMap[board[c]] : null);\n    const present = vals.filter(v => v !== null && v !== undefined);\n    if (present.length < 2) continue;\n    for (let b = 0; b < 4; b++) {\n      const owner = bitOwners[b];\n      const bits = present.map(v => (v >> b) & 1);\n      const allSame = bits.every(x => x === bits[0]);\n      if (!allSame) continue;\n      if (present.length === 4) {\n        if (owner === "player_1") p1Win = true;\n        if (owner === "player_2") p2Win = true;\n      } else if (present.length === 3) {\n        if (owner === "player_1") p1Score += 3.0;\n        if (owner === "player_2") p2Score += 3.0;\n      } else if (present.length === 2) {\n        if (owner === "player_1") p1Score += 0.5;\n        if (owner === "player_2") p2Score += 0.5;\n      }\n    }\n  }\n  if (p1Win) return 10.0;\n  if (p2Win) return -10.0;\n  return Math.max(-9.5, Math.min(9.5, p1Score - p2Score));\n}\n\nfunction loadGame(idx) {\n  currentGameIdx = idx;\n  renderTabs();\n  const g = GAMES[idx];\n  const match = g.match || {};\n  const replay = g.public_replay || {};\n  const tv = g.terminal_visualization || {};\n  const sigMap = tv.entity_signatures || {};\n  const legend = tv.bit_feature_legend || [];\n  const winLines = tv.winning_lines || [];\n  const rlog = tv.post_game_reasoning_log || [];\n\n  const bitOwners = ["player_1", "player_1", "player_2", "player_2"];\n  legend.forEach(item => {\n    if (typeof item.bit === "number" && item.owner) bitOwners[item.bit] = item.owner;\n  });\n\n  winCellsSet = new Set();\n  winLines.forEach(wl => (wl.cells || []).forEach(c => winCellsSet.add(c)));\n  document.getElementById("win-trait-note").textContent = winLines.length\n    ? `Winning Line: [${winLines[0].cells.join(",")}] via ${winLines[0].feature_id || \'bit \' + winLines[0].bit}`\n    : "";\n\n  document.getElementById("match-meta").innerHTML =\n    `<b>P1 (Blue):</b> ${P1_NAME} &nbsp;|&nbsp; <b>P2 (Orange):</b> ${P2_NAME} &nbsp;|&nbsp; <b>Instance:</b> ${match.instance_id || \'N/A\'} &nbsp;|&nbsp; <b>Start:</b> ${match.starting_player || \'player_1\'}`;\n\n  const badge = document.getElementById("outcome-badge");\n  badge.textContent = match.outcome ? `${match.outcome.toUpperCase()} — ${match.winner || \'DRAW\'}` : "COMPLETED";\n  badge.style.background = match.winner === "player_1" ? "#0369a1" : (match.winner === "player_2" ? "#c2410c" : "#334155");\n\n  document.getElementById("legend-grid").innerHTML = legend.length\n    ? legend.map(item => {\n        const isP1 = item.owner === "player_1";\n        return `<div class="legend-item ${isP1 ? \'p1\' : \'p2\'}">\n          <div style="font-weight:700;color:${isP1 ? \'var(--p1)\' : \'var(--p2)\'};">Bit ${item.bit} (${isP1 ? \'P1\' : \'P2\'})</div>\n          <div style="font-family:monospace;font-size:0.74rem;margin-top:2px;">${item.feature_id}</div>\n        </div>`;\n      }).join("")\n    : `<div style="color:var(--muted);font-size:0.8rem;">Legend available in post-terminal visualization.</div>`;\n\n  const reasonByStep = {};\n  rlog.forEach(r => {\n    if (typeof r.step === "number") reasonByStep[r.step] = r;\n  });\n\n  states = [{\n    board: Array(16).fill(null),\n    desc: "Initial Board State",\n    cell: -1,\n    selected: null,\n    actor: null,\n    rationale: "Draft and match initialized.",\n    evalScore: 0.0,\n    tag: null,\n    sigMap,\n    bitOwners\n  }];\n\n  let curBoard = Array(16).fill(null);\n  let curSelected = null;\n  let stepCounter = 0;\n\n  (replay.draft_history || []).forEach((d, i) => {\n    stepCounter += 1;\n    const r = reasonByStep[stepCounter] || {};\n    states.push({\n      board: [...curBoard],\n      desc: `Draft ${i + 1}: ${d.player} proposed ${d.attribute_id} (${d.accepted ? \'ACCEPTED\' : \'REJECTED\'})`,\n      cell: -1,\n      selected: null,\n      actor: d.player,\n      rationale: r.decision_explanation || "(No rationale emitted)",\n      evalScore: 0.0,\n      tag: null,\n      sigMap,\n      bitOwners\n    });\n  });\n\n  (replay.public_history || []).forEach((act, i) => {\n    stepCounter += 1;\n    const r = reasonByStep[stepCounter] || {};\n    const prevEval = states[states.length - 1].evalScore;\n    if (act.kind === "select_entity") {\n      curSelected = act.entity_id;\n      const sig = sigMap[curSelected];\n      const sigStr = sig !== undefined ? ` [${sig.toString(2).padStart(4, \'0\')}]` : "";\n      states.push({\n        board: [...curBoard],\n        desc: `Move ${i + 1}: ${act.player} selected ${act.entity_id.slice(0, 8)}${sigStr}`,\n        cell: -1,\n        selected: curSelected,\n        actor: act.player,\n        rationale: r.decision_explanation || "(No rationale emitted)",\n        evalScore: prevEval,\n        tag: null,\n        sigMap,\n        bitOwners\n      });\n    } else if (act.kind === "place_entity") {\n      curBoard[act.cell] = curSelected;\n      const placed = curSelected;\n      curSelected = null;\n      const newEval = evaluateBoard(curBoard, sigMap, bitOwners);\n      let tag = null;\n      if (Math.abs(newEval) >= 10.0) tag = "MATE";\n      else if (act.player === "player_1" && newEval - prevEval <= -3.5) tag = "BLUNDER";\n      else if (act.player === "player_2" && newEval - prevEval >= 3.5) tag = "BLUNDER";\n      states.push({\n        board: [...curBoard],\n        desc: `Move ${i + 1}: ${act.player} placed ${placed ? placed.slice(0, 8) : \'?\'} at cell ${act.cell}`,\n        cell: act.cell,\n        selected: null,\n        actor: act.player,\n        rationale: r.decision_explanation || "(No rationale emitted)",\n        evalScore: newEval,\n        tag,\n        sigMap,\n        bitOwners\n      });\n    }\n  });\n\n  drawSparkline();\n  const slider = document.getElementById("step-slider");\n  slider.max = states.length - 1;\n  slider.value = states.length - 1;\n  renderStep(states.length - 1);\n}\n\nfunction drawSparkline() {\n  const svg = document.getElementById("eval-spark");\n  if (states.length < 2) { svg.innerHTML = ""; return; }\n  const pts = states.map((s, i) => {\n    const x = (i / (states.length - 1)) * 400;\n    const y = 32 - (s.evalScore / 10.0) * 28;\n    return `${x.toFixed(1)},${y.toFixed(1)}`;\n  }).join(" ");\n  svg.innerHTML = `<line x1="0" y1="32" x2="400" y2="32" stroke="#334155" stroke-dasharray="4 4"/>\n    <polyline fill="none" stroke="#38bdf8" stroke-width="2.2" points="${pts}"/>`;\n}\n\nfunction stepMove(delta) {\n  const slider = document.getElementById("step-slider");\n  const next = Math.max(0, Math.min(states.length - 1, parseInt(slider.value) + delta));\n  slider.value = next;\n  renderStep(next);\n}\n\nfunction renderGlyph(sig, bitOwners) {\n  if (sig === undefined || sig === null) {\n    return `<div class="glyph"><div class="qbit p1 off">?</div><div class="qbit p2 off">?</div><div class="qbit p1 off">?</div><div class="qbit p2 off">?</div></div>`;\n  }\n  // Top-left: bit 0 (P1), Top-right: bit 2 (P2), Bottom-left: bit 1 (P1), Bottom-right: bit 3 (P2)\n  const order = [0, 2, 1, 3];\n  const cells = order.map(b => {\n    const val = (sig >> b) & 1;\n    const pCls = bitOwners[b] === "player_1" ? "p1" : "p2";\n    return `<div class="qbit ${pCls} ${val ? \'on\' : \'off\'}">${val}</div>`;\n  }).join("");\n  return `<div class="glyph">${cells}</div>`;\n}\n\nfunction renderStep(idx) {\n  const st = states[idx];\n  const isFinal = idx === states.length - 1;\n  document.getElementById("step-banner").textContent = `[${idx}/${states.length - 1}] ${st.desc}`;\n\n  const pct = Math.max(5, Math.min(95, 50 + (st.evalScore / 10.0) * 45));\n  document.getElementById("eval-p1-fill").style.height = `${pct}%`;\n  document.getElementById("eval-score-text").textContent = (st.evalScore >= 0 ? "+" : "") + st.evalScore.toFixed(1);\n\n  const rBox = document.getElementById("reasoning-box");\n  rBox.textContent = st.rationale;\n  rBox.className = `reasoning-box ${st.actor === \'player_2\' ? \'p2\' : \'\'}`;\n  document.getElementById("reasoning-actor").textContent = st.actor ? `${st.actor}` : "";\n\n  document.getElementById("selected-piece-badge").textContent = st.selected ? `Held: ${st.selected.slice(0,8)}` : "";\n\n  const grid = document.getElementById("board-grid");\n  grid.innerHTML = st.board.map((eid, c) => {\n    const isLast = c === st.cell;\n    const isWin = isFinal && winCellsSet.has(c);\n    const sig = eid ? st.sigMap[eid] : null;\n    return `<div class="cell ${isLast ? \'last\' : \'\'} ${isWin ? \'win\' : \'\'}">\n      <span class="cell-idx">${c}</span>\n      ${eid ? renderGlyph(sig, st.bitOwners) : \'<span style="color:#475569;font-size:0.75rem;">Empty</span>\'}\n      <span class="cell-id">${eid ? eid.slice(0, 6) : \'\'}</span>\n    </div>`;\n  }).join("");\n\n  document.getElementById("action-log").innerHTML = states.map((s, i) => {\n    const tagHtml = s.tag === "BLUNDER" ? `<span class="tag-blunder">BLUNDER</span>`\n      : (s.tag === "MATE" ? `<span class="tag-mate">WIN</span>` : "");\n    return `<div class="log-row ${i === idx ? \'active\' : \'\'}" onclick="document.getElementById(\'step-slider\').value=${i};renderStep(${i})">\n      <span>${s.desc}</span><span>${tagHtml}</span>\n    </div>`;\n  }).join("");\n}\n\nfunction renderBottomPanels() {\n  const ev = DATA.evaluator || {};\n  const series = DATA.series || {};\n  document.getElementById("eval-summary").innerHTML = `\n    <table>\n      <tr><th>Metric</th><th>Value</th></tr>\n      <tr><td>Completed Games</td><td>${series.completed_games_count || GAMES.length} / ${series.target_games || GAMES.length}</td></tr>\n      <tr><td>Evaluator Status</td><td>${ev.status || \'completed\'}</td></tr>\n      <tr><td>Total Matches Evaluated</td><td>${ev.match_count || GAMES.length}</td></tr>\n      <tr><td>Privacy Boundary</td><td>${ev.privacy_boundary || \'verified\'}</td></tr>\n    </table>`;\n\n  const sj = ev.semantic_judge || {};\n  if (sj.status === "completed") {\n    document.getElementById("judge-summary").innerHTML = `\n      <table>\n        <tr><th>Judge Model</th><td>${sj.judge_model || \'N/A\'}</td></tr>\n        <tr><td>Logical Faithfulness</td><td>${sj.logical_faithfulness_rate ?? \'N/A\'}</td></tr>\n        <tr><td>Self-Consistency</td><td>${sj.self_consistency_score ?? \'N/A\'}</td></tr>\n        <tr><td>Summary</td><td>${sj.summary || JSON.stringify(sj)}</td></tr>\n      </table>`;\n  } else {\n    document.getElementById("judge-summary").innerHTML = `<div style="color:var(--muted);font-size:0.82rem;">Status: <b>${sj.status || \'unavailable\'}</b> — ${sj.reason || \'\'}</div>`;\n  }\n}\n\nrenderBottomPanels();\nloadGame(0);\n</script>\n</body>\n</html>'
    html_code = html_tpl.replace("__PAYLOAD_JSON__", json.dumps(result_payload, ensure_ascii=False))
    Path("/kaggle/working/quarto_match_visualizer.html").write_text(html_code, encoding="utf-8")
    Path("/kaggle/working/quarto_match_result.json").write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
