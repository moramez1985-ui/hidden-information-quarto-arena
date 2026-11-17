import json
import sys
from pathlib import Path

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Quarto Hidden-Information Game Arena Visualizer</title>
<style>
  :root {
    --bg: #0b1120;
    --panel: #111827;
    --card: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --muted: #94a3b8;
    --p1: #38bdf8;
    --p2: #fb923c;
    --win: #10b981;
    --danger: #f43f5e;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, sans-serif; }
  .container { max-width: 1240px; margin: 16px auto; padding: 16px; }
  .header { display: flex; justify-content: space-between; align-items: center; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 18px; margin-bottom: 14px; flex-wrap: wrap; gap: 10px; }
  .header h1 { margin: 0; font-size: 1.2rem; color: var(--p1); }
  .sub { font-size: 0.82rem; color: var(--muted); margin-top: 4px; }
  .badge { padding: 6px 14px; border-radius: 999px; font-weight: 700; font-size: 0.82rem; }
  .tabs { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
  .tab-btn { background: var(--card); color: var(--text); border: 1px solid var(--border); padding: 7px 14px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.82rem; }
  .tab-btn.active { background: #0284c7; border-color: var(--p1); }
  .main-grid { display: grid; grid-template-columns: 56px 430px 1fr; gap: 16px; align-items: start; }
  @media (max-width: 980px) { .main-grid { grid-template-columns: 1fr; } }
  .eval-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 8px; display: flex; flex-direction: column; align-items: center; height: 470px; }
  .eval-label { font-size: 0.7rem; font-weight: 700; color: var(--muted); margin-bottom: 6px; }
  .eval-bar { width: 22px; flex: 1; background: var(--p2); border-radius: 6px; overflow: hidden; display: flex; flex-direction: column; border: 1px solid #475569; }
  .eval-p1 { background: var(--p1); width: 100%; transition: height 0.25s ease; }
  .eval-score { font-size: 0.72rem; font-weight: 700; margin-top: 6px; color: var(--text); }
  .board-panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px; }
  .controls { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .controls button { background: var(--card); color: var(--text); border: 1px solid var(--border); padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: 600; }
  .controls button:hover { border-color: var(--p1); }
  .controls input { flex: 1; cursor: pointer; }
  .step-banner { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 0.84rem; font-weight: 600; margin-bottom: 10px; text-align: center; }
  .board { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; background: #0f172a; padding: 10px; border-radius: 10px; border: 1px solid var(--border); }
  .cell { height: 88px; border-radius: 8px; background: var(--card); border: 2px solid var(--border); display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; transition: all 0.2s; }
  .cell.last { border-color: var(--p1); box-shadow: 0 0 10px rgba(56, 189, 248, 0.35); }
  .cell.win { border-color: var(--win); background: rgba(16, 185, 129, 0.14); box-shadow: 0 0 14px rgba(16, 185, 129, 0.45); }
  .cell-idx { position: absolute; top: 4px; left: 6px; font-size: 0.65rem; color: var(--muted); }
  .cell-id { font-size: 0.66rem; color: var(--muted); margin-top: 4px; font-family: monospace; }
  .glyph { display: grid; grid-template-columns: 1fr 1fr; gap: 3px; width: 42px; height: 42px; padding: 3px; background: #0b1120; border-radius: 8px; border: 1px solid #475569; }
  .qbit { border-radius: 3px; display: flex; align-items: center; justify-content: center; font-size: 0.58rem; font-weight: 800; }
  .qbit.p1.on { background: var(--p1); color: #082f49; }
  .qbit.p1.off { border: 1.5px solid var(--p1); color: var(--p1); opacity: 0.55; }
  .qbit.p2.on { background: var(--p2); color: #431407; }
  .qbit.p2.off { border: 1.5px solid var(--p2); color: var(--p2); opacity: 0.55; }
  .right-col { display: flex; flex-direction: column; gap: 12px; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }
  .card-title { font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 700; margin-bottom: 8px; display: flex; justify-content: space-between; }
  .legend-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .legend-item { background: var(--card); border-radius: 8px; padding: 7px 10px; font-size: 0.78rem; border-left: 4px solid var(--border); }
  .legend-item.p1 { border-left-color: var(--p1); }
  .legend-item.p2 { border-left-color: var(--p2); }
  .reasoning-box { background: var(--card); border-left: 4px solid var(--p1); border-radius: 8px; padding: 10px 12px; font-size: 0.85rem; line-height: 1.5; min-height: 64px; }
  .reasoning-box.p2 { border-left-color: var(--p2); }
  .log-list { max-height: 210px; overflow-y: auto; font-family: monospace; font-size: 0.78rem; }
  .log-row { padding: 4px 6px; border-radius: 5px; cursor: pointer; display: flex; justify-content: space-between; gap: 8px; }
  .log-row:hover { background: var(--card); }
  .log-row.active { background: #0284c7; color: #fff; }
  .tag-blunder { background: var(--danger); color: #fff; padding: 1px 6px; border-radius: 4px; font-size: 0.68rem; font-weight: 700; }
  .tag-mate { background: var(--win); color: #052e16; padding: 1px 6px; border-radius: 4px; font-size: 0.68rem; font-weight: 700; }
  .bottom-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
  @media (max-width: 980px) { .bottom-grid { grid-template-columns: 1fr; } }
  table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 600; }
  svg.spark { width: 100%; height: 64px; background: #0f172a; border-radius: 8px; border: 1px solid var(--border); }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Quarto Hidden-Information Game Arena</h1>
      <div id="match-meta" class="sub"></div>
    </div>
    <div id="outcome-badge" class="badge"></div>
  </div>

  <div id="game-tabs" class="tabs"></div>

  <div class="main-grid">
    <div class="eval-wrap" title="Deterministic Win-Threat Balance (Blue = Player 1, Orange = Player 2)">
      <div class="eval-label">EVAL</div>
      <div class="eval-bar"><div id="eval-p1-fill" class="eval-p1" style="height:50%;"></div></div>
      <div id="eval-score-text" class="eval-score">0.0</div>
    </div>

    <div class="board-panel">
      <div class="controls">
        <button onclick="stepMove(-1)">Prev</button>
        <input id="step-slider" type="range" min="0" max="0" value="0" oninput="renderStep(parseInt(this.value))">
        <button onclick="stepMove(1)">Next</button>
      </div>
      <div id="step-banner" class="step-banner"></div>
      <div id="board-grid" class="board"></div>
      <div style="margin-top:10px;font-size:0.75rem;color:var(--muted);display:flex;justify-content:space-between;">
        <span>Left Quadrants: <b style="color:var(--p1);">Player 1 Bits (0,1)</b></span>
        <span>Right Quadrants: <b style="color:var(--p2);">Player 2 Bits (2,3)</b></span>
      </div>
    </div>

    <div class="right-col">
      <div class="card">
        <div class="card-title"><span>Private Feature Ownership (4-Bit Quartet)</span><span id="win-trait-note" style="color:var(--win);"></span></div>
        <div id="legend-grid" class="legend-grid"></div>
      </div>

      <div class="card">
        <div class="card-title"><span>Agent Decision Rationale (Self-Reported)</span><span id="reasoning-actor"></span></div>
        <div id="reasoning-box" class="reasoning-box">No rationale emitted for this step.</div>
      </div>

      <div class="card">
        <div class="card-title"><span>Advantage Swing & Action Timeline</span><span id="selected-piece-badge"></span></div>
        <svg id="eval-spark" class="spark" viewBox="0 0 400 64" preserveAspectRatio="none"></svg>
        <div id="action-log" class="log-list" style="margin-top:8px;"></div>
      </div>
    </div>
  </div>

  <div class="bottom-grid">
    <div class="card">
      <div class="card-title"><span>Series Summary & Automated Evaluator</span></div>
      <div id="eval-summary"></div>
    </div>
    <div class="card">
      <div class="card-title"><span>Post-Game 3rd-LLM Semantic Judge</span></div>
      <div id="judge-summary"></div>
    </div>
  </div>
</div>

<script>
const DATA = __PAYLOAD_JSON__;
const GAMES = Array.isArray(DATA.matches) && DATA.matches.length > 0
  ? DATA.matches
  : [{ match: DATA.match || {}, public_replay: DATA.public_replay || {}, terminal_visualization: DATA.terminal_visualization || {} }];
const MODELS = DATA.model_metadata || {};
const P1_NAME = MODELS.player_1 ? MODELS.player_1.model : "player_1";
const P2_NAME = MODELS.player_2 ? MODELS.player_2.model : "player_2";

const LINES = [
  [0,1,2,3],[4,5,6,7],[8,9,10,11],[12,13,14,15],
  [0,4,8,12],[1,5,9,13],[2,6,10,14],[3,7,11,15],
  [0,5,10,15],[3,6,9,12]
];

let currentGameIdx = 0;
let states = [];
let winCellsSet = new Set();

function renderTabs() {
  const tabs = document.getElementById("game-tabs");
  tabs.innerHTML = GAMES.map((g, idx) => {
    const m = g.match || {};
    const label = `Game ${idx + 1} (${m.instance_id || 'instance'}) — ${m.winner || 'Draw'}`;
    return `<button class="tab-btn ${idx === currentGameIdx ? 'active' : ''}" onclick="loadGame(${idx})">${label}</button>`;
  }).join("");
}

function evaluateBoard(board, sigMap, bitOwners) {
  let p1Score = 0, p2Score = 0;
  let p1Win = false, p2Win = false;
  for (const line of LINES) {
    const vals = line.map(c => board[c] ? sigMap[board[c]] : null);
    const present = vals.filter(v => v !== null && v !== undefined);
    if (present.length < 2) continue;
    for (let b = 0; b < 4; b++) {
      const owner = bitOwners[b];
      const bits = present.map(v => (v >> b) & 1);
      const allSame = bits.every(x => x === bits[0]);
      if (!allSame) continue;
      if (present.length === 4) {
        if (owner === "player_1") p1Win = true;
        if (owner === "player_2") p2Win = true;
      } else if (present.length === 3) {
        if (owner === "player_1") p1Score += 3.0;
        if (owner === "player_2") p2Score += 3.0;
      } else if (present.length === 2) {
        if (owner === "player_1") p1Score += 0.5;
        if (owner === "player_2") p2Score += 0.5;
      }
    }
  }
  if (p1Win) return 10.0;
  if (p2Win) return -10.0;
  return Math.max(-9.5, Math.min(9.5, p1Score - p2Score));
}

function loadGame(idx) {
  currentGameIdx = idx;
  renderTabs();
  const g = GAMES[idx];
  const match = g.match || {};
  const replay = g.public_replay || {};
  const tv = g.terminal_visualization || {};
  const sigMap = tv.entity_signatures || {};
  const legend = tv.bit_feature_legend || [];
  const winLines = tv.winning_lines || [];
  const rlog = tv.post_game_reasoning_log || [];

  const bitOwners = ["player_1", "player_1", "player_2", "player_2"];
  legend.forEach(item => {
    if (typeof item.bit === "number" && item.owner) bitOwners[item.bit] = item.owner;
  });

  winCellsSet = new Set();
  winLines.forEach(wl => (wl.cells || []).forEach(c => winCellsSet.add(c)));
  document.getElementById("win-trait-note").textContent = winLines.length
    ? `Winning Line: [${winLines[0].cells.join(",")}] via ${winLines[0].feature_id || 'bit ' + winLines[0].bit}`
    : "";

  document.getElementById("match-meta").innerHTML =
    `<b>P1 (Blue):</b> ${P1_NAME} &nbsp;|&nbsp; <b>P2 (Orange):</b> ${P2_NAME} &nbsp;|&nbsp; <b>Instance:</b> ${match.instance_id || 'N/A'} &nbsp;|&nbsp; <b>Start:</b> ${match.starting_player || 'player_1'}`;

  const badge = document.getElementById("outcome-badge");
  badge.textContent = match.outcome ? `${match.outcome.toUpperCase()} — ${match.winner || 'DRAW'}` : "COMPLETED";
  badge.style.background = match.winner === "player_1" ? "#0369a1" : (match.winner === "player_2" ? "#c2410c" : "#334155");

  document.getElementById("legend-grid").innerHTML = legend.length
    ? legend.map(item => {
        const isP1 = item.owner === "player_1";
        return `<div class="legend-item ${isP1 ? 'p1' : 'p2'}">
          <div style="font-weight:700;color:${isP1 ? 'var(--p1)' : 'var(--p2)'};">Bit ${item.bit} (${isP1 ? 'P1' : 'P2'})</div>
          <div style="font-family:monospace;font-size:0.74rem;margin-top:2px;">${item.feature_id}</div>
        </div>`;
      }).join("")
    : `<div style="color:var(--muted);font-size:0.8rem;">Legend available in post-terminal visualization.</div>`;

  const reasonByStep = {};
  rlog.forEach(r => {
    if (typeof r.step === "number") reasonByStep[r.step] = r;
  });

  states = [{
    board: Array(16).fill(null),
    desc: "Initial Board State",
    cell: -1,
    selected: null,
    actor: null,
    rationale: "Draft and match initialized.",
    evalScore: 0.0,
    tag: null,
    sigMap,
    bitOwners
  }];

  let curBoard = Array(16).fill(null);
  let curSelected = null;
  let stepCounter = 0;

  (replay.draft_history || []).forEach((d, i) => {
    stepCounter += 1;
    const r = reasonByStep[stepCounter] || {};
    states.push({
      board: [...curBoard],
      desc: `Draft ${i + 1}: ${d.player} proposed ${d.attribute_id} (${d.accepted ? 'ACCEPTED' : 'REJECTED'})`,
      cell: -1,
      selected: null,
      actor: d.player,
      rationale: r.decision_explanation || "(No rationale emitted)",
      evalScore: 0.0,
      tag: null,
      sigMap,
      bitOwners
    });
  });

  (replay.public_history || []).forEach((act, i) => {
    stepCounter += 1;
    const r = reasonByStep[stepCounter] || {};
    const prevEval = states[states.length - 1].evalScore;
    if (act.kind === "select_entity") {
      curSelected = act.entity_id;
      const sig = sigMap[curSelected];
      const sigStr = sig !== undefined ? ` [${sig.toString(2).padStart(4, '0')}]` : "";
      states.push({
        board: [...curBoard],
        desc: `Move ${i + 1}: ${act.player} selected ${act.entity_id.slice(0, 8)}${sigStr}`,
        cell: -1,
        selected: curSelected,
        actor: act.player,
        rationale: r.decision_explanation || "(No rationale emitted)",
        evalScore: prevEval,
        tag: null,
        sigMap,
        bitOwners
      });
    } else if (act.kind === "place_entity") {
      curBoard[act.cell] = curSelected;
      const placed = curSelected;
      curSelected = null;
      const newEval = evaluateBoard(curBoard, sigMap, bitOwners);
      let tag = null;
      if (Math.abs(newEval) >= 10.0) tag = "MATE";
      else if (act.player === "player_1" && newEval - prevEval <= -3.5) tag = "BLUNDER";
      else if (act.player === "player_2" && newEval - prevEval >= 3.5) tag = "BLUNDER";
      states.push({
        board: [...curBoard],
        desc: `Move ${i + 1}: ${act.player} placed ${placed ? placed.slice(0, 8) : '?'} at cell ${act.cell}`,
        cell: act.cell,
        selected: null,
        actor: act.player,
        rationale: r.decision_explanation || "(No rationale emitted)",
        evalScore: newEval,
        tag,
        sigMap,
        bitOwners
      });
    }
  });

  drawSparkline();
  const slider = document.getElementById("step-slider");
  slider.max = states.length - 1;
  slider.value = states.length - 1;
  renderStep(states.length - 1);
}

function drawSparkline() {
  const svg = document.getElementById("eval-spark");
  if (states.length < 2) { svg.innerHTML = ""; return; }
  const pts = states.map((s, i) => {
    const x = (i / (states.length - 1)) * 400;
    const y = 32 - (s.evalScore / 10.0) * 28;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  svg.innerHTML = `<line x1="0" y1="32" x2="400" y2="32" stroke="#334155" stroke-dasharray="4 4"/>
    <polyline fill="none" stroke="#38bdf8" stroke-width="2.2" points="${pts}"/>`;
}

function stepMove(delta) {
  const slider = document.getElementById("step-slider");
  const next = Math.max(0, Math.min(states.length - 1, parseInt(slider.value) + delta));
  slider.value = next;
  renderStep(next);
}

function renderGlyph(sig, bitOwners) {
  if (sig === undefined || sig === null) {
    return `<div class="glyph"><div class="qbit p1 off">?</div><div class="qbit p2 off">?</div><div class="qbit p1 off">?</div><div class="qbit p2 off">?</div></div>`;
  }
  // Top-left: bit 0 (P1), Top-right: bit 2 (P2), Bottom-left: bit 1 (P1), Bottom-right: bit 3 (P2)
  const order = [0, 2, 1, 3];
  const cells = order.map(b => {
    const val = (sig >> b) & 1;
    const pCls = bitOwners[b] === "player_1" ? "p1" : "p2";
    return `<div class="qbit ${pCls} ${val ? 'on' : 'off'}">${val}</div>`;
  }).join("");
  return `<div class="glyph">${cells}</div>`;
}

function renderStep(idx) {
  const st = states[idx];
  const isFinal = idx === states.length - 1;
  document.getElementById("step-banner").textContent = `[${idx}/${states.length - 1}] ${st.desc}`;

  const pct = Math.max(5, Math.min(95, 50 + (st.evalScore / 10.0) * 45));
  document.getElementById("eval-p1-fill").style.height = `${pct}%`;
  document.getElementById("eval-score-text").textContent = (st.evalScore >= 0 ? "+" : "") + st.evalScore.toFixed(1);

  const rBox = document.getElementById("reasoning-box");
  rBox.textContent = st.rationale;
  rBox.className = `reasoning-box ${st.actor === 'player_2' ? 'p2' : ''}`;
  document.getElementById("reasoning-actor").textContent = st.actor ? `${st.actor}` : "";

  document.getElementById("selected-piece-badge").textContent = st.selected ? `Held: ${st.selected.slice(0,8)}` : "";

  const grid = document.getElementById("board-grid");
  grid.innerHTML = st.board.map((eid, c) => {
    const isLast = c === st.cell;
    const isWin = isFinal && winCellsSet.has(c);
    const sig = eid ? st.sigMap[eid] : null;
    return `<div class="cell ${isLast ? 'last' : ''} ${isWin ? 'win' : ''}">
      <span class="cell-idx">${c}</span>
      ${eid ? renderGlyph(sig, st.bitOwners) : '<span style="color:#475569;font-size:0.75rem;">Empty</span>'}
      <span class="cell-id">${eid ? eid.slice(0, 6) : ''}</span>
    </div>`;
  }).join("");

  document.getElementById("action-log").innerHTML = states.map((s, i) => {
    const tagHtml = s.tag === "BLUNDER" ? `<span class="tag-blunder">BLUNDER</span>`
      : (s.tag === "MATE" ? `<span class="tag-mate">WIN</span>` : "");
    return `<div class="log-row ${i === idx ? 'active' : ''}" onclick="document.getElementById('step-slider').value=${i};renderStep(${i})">
      <span>${s.desc}</span><span>${tagHtml}</span>
    </div>`;
  }).join("");
}

function renderBottomPanels() {
  const ev = DATA.evaluator || {};
  const series = DATA.series || {};
  document.getElementById("eval-summary").innerHTML = `
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Completed Games</td><td>${series.completed_games_count || GAMES.length} / ${series.target_games || GAMES.length}</td></tr>
      <tr><td>Evaluator Status</td><td>${ev.status || 'completed'}</td></tr>
      <tr><td>Total Matches Evaluated</td><td>${ev.match_count || GAMES.length}</td></tr>
      <tr><td>Privacy Boundary</td><td>${ev.privacy_boundary || 'verified'}</td></tr>
    </table>`;

  const sj = ev.semantic_judge || {};
  if (sj.status === "completed") {
    document.getElementById("judge-summary").innerHTML = `
      <table>
        <tr><th>Judge Model</th><td>${sj.judge_model || 'N/A'}</td></tr>
        <tr><td>Logical Faithfulness</td><td>${sj.logical_faithfulness_rate ?? 'N/A'}</td></tr>
        <tr><td>Self-Consistency</td><td>${sj.self_consistency_score ?? 'N/A'}</td></tr>
        <tr><td>Summary</td><td>${sj.summary || JSON.stringify(sj)}</td></tr>
      </table>`;
  } else {
    document.getElementById("judge-summary").innerHTML = `<div style="color:var(--muted);font-size:0.82rem;">Status: <b>${sj.status || 'unavailable'}</b> — ${sj.reason || ''}</div>`;
  }
}

renderBottomPanels();
loadGame(0);
</script>
</body>
</html>"""


def render_visualizer_from_run_json(run_json_path: str | Path, out_html_path: str | Path = "quarto_match_visualizer.html") -> Path:
    payload = json.loads(Path(run_json_path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], dict):
        payload = payload["result"]
    html = HTML_TEMPLATE.replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=False))
    out_path = Path(out_html_path)
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_visualizer.py <path_to_run.json> [output.html]")
        raise SystemExit(1)
    out = render_visualizer_from_run_json(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "quarto_match_visualizer.html")
    print(f"Visualizer written to {out}")
