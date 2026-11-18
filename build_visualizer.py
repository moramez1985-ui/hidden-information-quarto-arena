from __future__ import annotations

import json
import sys
from pathlib import Path


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Quarto Hidden-Information Arena — Game Replay</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root {
    --shell-bg: #121316;
    --panel-dark: #191b20;
    --panel-card: #22252c;
    --panel-border: #2f333d;
    --text-light: #f3f4f6;
    --text-muted: #9ca3af;

    --paper-bg: #f3efe6;
    --paper-grain: #e5dec9;
    --ink: #23211e;
    --ink-soft: #5c574e;
    --pencil: #8c8578;

    --p1: #1d4ed8;
    --p1-soft: rgba(29, 78, 216, 0.14);
    --p2: #c2410c;
    --p2-soft: rgba(194, 65, 12, 0.14);
    --win: #15803d;
    --win-soft: rgba(21, 128, 61, 0.16);
    --danger: #dc2626;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--shell-bg);
    color: var(--text-light);
    font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  }

  .app-wrap {
    max-width: 1440px;
    margin: 0 auto;
    padding: 16px;
  }

  /* Top Match Switcher Bar */
  .top-header {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    background: var(--panel-dark);
    border: 1px solid var(--panel-border);
    border-radius: 10px;
    margin-bottom: 14px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .brand-title {
    font-weight: 700;
    font-size: 1.02rem;
    letter-spacing: -0.01em;
  }
  .brand-sub {
    font-size: 0.78rem;
    color: var(--text-muted);
  }
  .game-tabs {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .tab-btn {
    background: var(--panel-card);
    color: var(--text-muted);
    border: 1px solid var(--panel-border);
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .tab-btn:hover { color: var(--text-light); border-color: #4b5563; }
  .tab-btn.active {
    background: #f3f4f6;
    color: #111827;
    border-color: #f3f4f6;
  }

  /* Main Split Arena Layout (Kaggle Game Arena Style) */
  .arena-layout {
    display: grid;
    grid-template-columns: 1fr 410px;
    gap: 14px;
    align-items: stretch;
  }
  @media (max-width: 1100px) {
    .arena-layout { grid-template-columns: 1fr; }
  }

  /* Left: Matte Tactile Paper Canvas */
  .paper-canvas {
    background-color: var(--paper-bg);
    background-image:
      radial-gradient(rgba(120, 110, 90, 0.14) 1px, transparent 0),
      radial-gradient(rgba(160, 148, 125, 0.1) 1px, transparent 0);
    background-size: 22px 22px;
    background-position: 0 0, 11px 11px;
    color: var(--ink);
    border-radius: 12px;
    border: 1px solid #3a3d46;
    padding: 20px 24px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    position: relative;
    min-height: 620px;
    box-shadow: inset 0 0 60px rgba(180, 168, 142, 0.25);
  }

  .paper-top-strip {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }
  .versus-pill {
    font-family: "Caveat", cursive;
    font-size: 1.45rem;
    font-weight: 700;
    color: var(--ink);
  }
  .outcome-pill {
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.76rem;
    font-weight: 700;
    border: 1.5px solid currentColor;
  }

  .paper-center {
    display: grid;
    grid-template-columns: 46px minmax(300px, 430px) 220px;
    gap: 20px;
    align-items: center;
    justify-content: center;
    margin: auto 0;
  }
  @media (max-width: 860px) {
    .paper-center { grid-template-columns: 1fr; }
  }

  /* Vertical Eval Bar (Positive UP, Negative DOWN) */
  .eval-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 416px;
  }
  .eval-num {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--ink);
    margin-bottom: 6px;
  }
  .eval-track {
    width: 18px;
    flex: 1;
    background: var(--p2);
    border: 1.5px solid var(--ink);
    border-radius: 4px;
    overflow: hidden;
    display: flex;
    flex-direction: column-reverse;
    position: relative;
  }
  .eval-zero {
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    height: 1.5px;
    background: var(--paper-bg);
    z-index: 2;
  }
  .eval-fill-p1 {
    width: 100%;
    height: 50%;
    background: var(--p1);
    transition: height 0.28s cubic-bezier(0.22, 1, 0.36, 1);
  }
  .eval-end-labels {
    display: flex;
    flex-direction: column;
    align-items: center;
    font-size: 0.65rem;
    font-weight: 700;
    margin-top: 4px;
    line-height: 1.2;
  }

  /* Pencil-Drawn 4x4 Grid */
  .board-frame {
    position: relative;
    padding: 14px;
    background: rgba(255, 253, 248, 0.65);
    border: 2px solid var(--ink);
    border-radius: 6px;
    box-shadow: 4px 4px 0px rgba(35, 33, 30, 0.12);
  }
  .col-coords {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    text-align: center;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.7rem;
    color: var(--ink-soft);
    margin-bottom: 6px;
  }
  .board-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }
  .cell {
    aspect-ratio: 1;
    border: 1.5px dashed var(--pencil);
    border-radius: 5px;
    background: rgba(255, 255, 255, 0.45);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    position: relative;
    transition: all 0.18s ease;
  }
  .cell-num {
    position: absolute;
    top: 3px;
    left: 5px;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.62rem;
    color: var(--pencil);
  }
  .cell.last {
    border: 2px solid var(--ink);
    background: #ffffff;
    box-shadow: 2px 2px 0 rgba(35, 33, 30, 0.15);
  }
  .cell.projected-p1 {
    border: 2px dashed var(--p1);
    background: var(--p1-soft);
  }
  .cell.projected-p2 {
    border: 2px dashed var(--p2);
    background: var(--p2-soft);
  }
  .cell.win {
    border: 2.5px solid var(--win);
    background: var(--win-soft);
  }

  /* Hand-crafted 4-Bit Piece Token */
  .token {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 3px;
    width: 46px;
    height: 46px;
    padding: 3px;
    border: 1.5px solid var(--ink);
    border-radius: 6px;
    background: #fffdf9;
  }
  .bit-box {
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.68rem;
    font-weight: 700;
    border-radius: 2px;
  }
  .bit-box.p1-on { background: var(--p1); color: #fff; }
  .bit-box.p1-off { border: 1px dashed var(--p1); color: var(--p1); }
  .bit-box.p2-on { background: var(--p2); color: #fff; }
  .bit-box.p2-off { border: 1px dashed var(--p2); color: var(--p2); }
  .token-code {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.62rem;
    color: var(--ink-soft);
    margin-top: 3px;
  }

  /* Handwritten Margin Notes (Like Kaggle Go/Chess Annotations) */
  .margin-notes {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 416px;
  }
  .hand-note {
    font-family: "Caveat", cursive;
    font-size: 1.24rem;
    line-height: 1.22;
    color: var(--ink);
    transform: rotate(-1deg);
    height: 96px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .hand-note .sub-note {
    font-size: 1.05rem;
    color: var(--ink-soft);
    display: block;
    margin-top: 3px;
  }
  .held-card {
    border: 1.5px dashed var(--ink);
    border-radius: 8px;
    padding: 10px;
    background: rgba(255, 255, 255, 0.55);
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .held-title {
    font-family: "Caveat", cursive;
    font-size: 1.15rem;
    font-weight: 700;
    margin-bottom: 6px;
  }
  .trait-key {
    font-size: 0.72rem;
    border-top: 1px dashed var(--pencil);
    padding-top: 8px;
    line-height: 1.45;
  }

  .corner-staff-wrap {
    margin-top: 8px;
    padding-top: 6px;
    background: transparent;
  }
  .paper-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
    color: var(--ink-soft);
    border-top: 1px dashed var(--pencil);
    padding-top: 8px;
    margin-top: 12px;
  }

  /* Right: Dark Sleek Kaggle Game Log Panel */
  .log-panel {
    background: var(--panel-dark);
    border: 1px solid var(--panel-border);
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    height: 620px;
    overflow: hidden;
  }
  .log-header {
    padding: 14px 16px;
    border-bottom: 1px solid var(--panel-border);
  }
  .log-title-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }
  .log-title-row h2 {
    margin: 0;
    font-size: 0.96rem;
    font-weight: 700;
  }
  .transport-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
  }
  .t-btns {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .t-btn {
    background: var(--panel-card);
    color: var(--text-light);
    border: 1px solid var(--panel-border);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
  }
  .t-btn:hover { background: #2d313a; }
  .step-counter {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.82rem;
    color: var(--text-muted);
  }
  .scrubber-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
  }
  .scrubber-row input[type=range] {
    flex: 1;
    accent-color: #f3f4f6;
    cursor: pointer;
  }
  .speed-select {
    background: var(--panel-card);
    color: var(--text-light);
    border: 1px solid var(--panel-border);
    border-radius: 6px;
    padding: 3px 6px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  .filter-row {
    display: flex;
    gap: 8px;
  }
  .pill-toggle {
    flex: 1;
    background: var(--panel-card);
    color: var(--text-light);
    border: 1px solid var(--panel-border);
    border-radius: 999px;
    padding: 5px 10px;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
  }
  .pill-toggle:hover { border-color: #6b7280; }

  .log-stream {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .log-card {
    background: var(--panel-card);
    border: 1px solid var(--panel-border);
    border-radius: 8px;
    padding: 10px 12px;
    cursor: pointer;
    transition: border-color 0.15s ease;
  }
  .log-card:hover { border-color: #4b5563; }
  .log-card.active {
    border-color: #f3f4f6;
    background: #282c35;
  }
  .log-card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.8rem;
    font-weight: 700;
    margin-bottom: 4px;
  }
  .log-card-desc {
    font-size: 0.8rem;
    color: #d1d5db;
  }
  .thinking-toggle {
    margin-top: 7px;
    font-size: 0.74rem;
    color: var(--text-muted);
    display: inline-flex;
    align-items: center;
    gap: 4px;
    user-select: none;
  }
  .thinking-body {
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid var(--panel-border);
    font-size: 0.77rem;
    line-height: 1.45;
    color: #cbd5e1;
    display: none;
  }
  .log-card.expanded .thinking-body { display: block; }

  .tag {
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 0.66rem;
    font-weight: 700;
  }
  .tag-blunder { background: rgba(220, 38, 38, 0.2); color: #fca5a5; border: 1px solid #ef4444; }
  .tag-win { background: rgba(21, 128, 61, 0.25); color: #86efac; border: 1px solid #22c55e; }
  .tag-miss { background: rgba(217, 119, 6, 0.2); color: #fcd34d; border: 1px solid #f59e0b; }

  /* Collapsible Draft & Benchmark Summary Drawer Below */
  .bottom-metrics {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 14px;
    margin-top: 14px;
  }
  @media (max-width: 1000px) { .bottom-metrics { grid-template-columns: 1fr; } }
  .dark-card {
    background: var(--panel-dark);
    border: 1px solid var(--panel-border);
    border-radius: 10px;
    padding: 14px;
  }
  .dark-card h3 {
    margin: 0 0 10px 0;
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
  }
  table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
  th, td { padding: 6px 8px; border-bottom: 1px solid var(--panel-border); text-align: left; }
  th { color: var(--text-muted); }
  .draft-scroll { max-height: 170px; overflow-y: auto; font-size: 0.76rem; }
</style>
</head>
<body>
<div class="app-wrap">
  <div class="top-header">
    <div class="brand">
      <div>
        <div class="brand-title">Quarto Hidden-Information Arena</div>
        <div class="brand-sub" id="match-meta">Loading match telemetry...</div>
      </div>
    </div>
    <div class="game-tabs" id="game-tabs"></div>
  </div>

  <div class="arena-layout">
    <!-- Left: Tactile Paper Board -->
    <div class="paper-canvas">
      <div class="paper-top-strip">
        <div class="versus-pill" id="versus-title">Player 1 vs. Player 2</div>
        <div class="outcome-pill" id="outcome-badge">COMPLETED</div>
      </div>

      <div class="paper-center">
        <!-- Exact Eval Bar (+ Up for P1, - Down for P2) -->
        <div class="eval-col" title="Positive (+) moves up for Player 1 | Negative (-) moves down for Player 2">
          <div class="eval-num" id="eval-score">0.0</div>
          <div class="eval-track">
            <div class="eval-zero"></div>
            <div class="eval-fill-p1" id="eval-p1-fill"></div>
          </div>
          <div class="eval-end-labels">
            <span style="color:var(--p1);">+P1</span>
            <span style="color:var(--p2);">-P2</span>
          </div>
        </div>

        <!-- 4x4 Pencil Grid -->
        <div class="board-frame">
          <div class="col-coords"><span>C0</span><span>C1</span><span>C2</span><span>C3</span></div>
          <div class="board-grid" id="board-grid"></div>
        </div>

        <!-- Handwritten Side Annotations & Active Piece -->
        <div class="margin-notes">
          <div class="hand-note" id="hand-annotation">
            Board play begins!
            <span class="sub-note" id="hand-subnote">Draft phase completed off-board.</span>
          </div>

          <div class="held-card">
            <div class="held-title">Piece in Hand</div>
            <div id="held-piece-box" style="min-height:66px;display:flex;flex-direction:column;align-items:center;justify-content:center;">
              <span style="font-size:0.75rem;color:var(--ink-soft);">None</span>
            </div>
          </div>

          <div class="trait-key" id="trait-legend-compact"></div>
          <div class="corner-staff-wrap" title="Minimal Advantage Staff (Click any note to jump)">
            <svg id="music-staff" width="100%" height="54" viewBox="0 0 220 54" style="display:block;background:transparent;cursor:pointer;"></svg>
          </div>
        </div>
      </div>

      <div class="paper-footer">
        <span>Left quadrants: <b style="color:var(--p1);">Player 1 Bits</b> &nbsp;|&nbsp; Right quadrants: <b style="color:var(--p2);">Player 2 Bits</b></span>
        <span id="win-trait-note" style="font-weight:700;color:var(--win);"></span>
      </div>
    </div>

    <!-- Right: Kaggle Game Arena Style Log & Thinking Stream -->
    <div class="log-panel">
      <div class="log-header">
        <div class="log-title-row">
          <h2>Game Log</h2>
          <span class="step-counter" id="step-counter">0 / 0</span>
        </div>
        <div class="transport-bar">
          <div class="t-btns">
            <button class="t-btn" onclick="stepTo(0)" title="Reset">&#8634;</button>
            <button class="t-btn" onclick="stepBy(-1)" title="Previous">|&lt;</button>
            <button class="t-btn" id="play-btn" onclick="togglePlay()">&#9654;</button>
            <button class="t-btn" onclick="stepBy(1)" title="Next">&gt;|</button>
          </div>
          <select class="speed-select" id="speed-select" onchange="updatePlaySpeed()">
            <option value="1400">0.5X</option>
            <option value="850" selected>1X</option>
            <option value="400">2X</option>
          </select>
        </div>
        <div class="scrubber-row">
          <input type="range" id="step-slider" min="0" max="0" value="0" oninput="stepTo(parseInt(this.value, 10))" />
        </div>
        <div class="filter-row">
          <button class="pill-toggle" id="expand-all-btn" onclick="toggleExpandAll()">&#8597; Expand All Thinking</button>
        </div>
      </div>

      <div class="log-stream" id="log-stream"></div>
    </div>
  </div>

  <!-- Bottom Metrics & Collapsible Draft Log -->
  <div class="bottom-metrics">
    <div class="dark-card">
      <h3>Pre-Game Draft Log (Hidden Feature Discovery)</h3>
      <div class="draft-scroll" id="draft-log-box"></div>
    </div>
    <div class="dark-card">
      <h3>Series Aggregate Performance</h3>
      <div id="series-summary"></div>
    </div>
    <div class="dark-card">
      <h3>Deterministic Claim-to-Engine Audit</h3>
      <div id="judge-summary"></div>
    </div>
  </div>
</div>

<script>
const PAYLOAD = __PAYLOAD_JSON__;
const GAMES = PAYLOAD.matches || [];
const MODEL_META = PAYLOAD.model_metadata || {};
const P1_NAME = (MODEL_META.player_1 && MODEL_META.player_1.model) || "Player 1";
const P2_NAME = (MODEL_META.player_2 && MODEL_META.player_2.model) || "Player 2";

const LINES = [
  [0,1,2,3], [4,5,6,7], [8,9,10,11], [12,13,14,15],
  [0,4,8,12], [1,5,9,13], [2,6,10,14], [3,7,11,15],
  [0,5,10,15], [3,6,9,12]
];

let currentGameIdx = 0;
let states = [];
let currentStep = 0;
let playTimer = null;
let expandAll = false;
let winCellsSet = new Set();

function renderToken(sig, bitOwners) {
  if (sig === null || sig === undefined) return "";
  const s = Math.round(sig);
  const b0 = (s >> 0) & 1;
  const b1 = (s >> 1) & 1;
  const b2 = (s >> 2) & 1;
  const b3 = (s >> 3) & 1;
  const cls = (bIdx, val) => {
    const isP1 = bitOwners[bIdx] === "player_1";
    return isP1 ? (val ? "p1-on" : "p1-off") : (val ? "p2-on" : "p2-off");
  };
  return `<div class="token">
    <div class="bit-box ${cls(0, b0)}">${b0}</div>
    <div class="bit-box ${cls(2, b2)}">${b2}</div>
    <div class="bit-box ${cls(1, b1)}">${b1}</div>
    <div class="bit-box ${cls(3, b3)}">${b3}</div>
  </div>`;
}

function staticBoardScore(board, sigMap, bitOwners, poolSigs) {
  let p1Score = 0, p2Score = 0;
  let p1Win = false, p2Win = false;
  let winningLineFound = null;
  const projectedP1 = new Set();
  const projectedP2 = new Set();

  for (const line of LINES) {
    const vals = line.map(c => board[c] ? Math.round(Number(sigMap[board[c]])) : null);
    const present = vals.filter(v => v !== null && v !== undefined);
    if (present.length < 2) continue;
    for (let b = 0; b < 4; b++) {
      const owner = bitOwners[b];
      const bits = present.map(v => (v >> b) & 1);
      if (!bits.every(x => x === bits[0])) continue;
      const targetBit = bits[0];
      if (present.length === 4) {
        if (owner === "player_1") p1Win = true;
        if (owner === "player_2") p2Win = true;
        if (!winningLineFound) winningLineFound = { cells: line, bit: b, owner };
      } else if (present.length === 3) {
        const hasLiveCompleter = poolSigs.some(s => ((s >> b) & 1) === targetBit);
        if (hasLiveCompleter) {
          if (owner === "player_1") {
            p1Score += 3.5;
            line.forEach(c => projectedP1.add(c));
          } else {
            p2Score += 3.5;
            line.forEach(c => projectedP2.add(c));
          }
        }
      } else if (present.length === 2) {
        const completers = poolSigs.filter(s => ((s >> b) & 1) === targetBit).length;
        if (completers >= 2) {
          if (owner === "player_1") p1Score += 0.6;
          if (owner === "player_2") p2Score += 0.6;
        }
      }
    }
  }

  let score = Math.max(-9.0, Math.min(9.0, p1Score - p2Score));
  if (p1Win) score = 10.0;
  if (p2Win) score = -10.0;
  return { score, p1Win, p2Win, winningLineFound, projectedP1, projectedP2 };
}

function evaluateBoard(board, sigMap, bitOwners, holderPlayer, heldPiece, remainingPool) {
  const allSigs = Object.values(sigMap).map(v => Math.round(Number(v)));
  const poolAfterHeld = Array.isArray(remainingPool)
    ? remainingPool.filter(eid => eid !== heldPiece).map(eid => sigMap[eid]).filter(v => v !== undefined && v !== null).map(v => Math.round(Number(v)))
    : allSigs;

  const base = staticBoardScore(board, sigMap, bitOwners, poolAfterHeld);
  if (base.p1Win || base.p2Win || !heldPiece || !holderPlayer || sigMap[heldPiece] === undefined) {
    return {
      score: base.score,
      winningLineFound: base.winningLineFound,
      projectedP1: base.projectedP1,
      projectedP2: base.projectedP2,
      heldMateFor: null
    };
  }

  // True 1-Ply Minimax: simulate holderPlayer placing heldPiece into EVERY empty square
  // and pick the optimal square for holderPlayer (maximizing for P1, minimizing for P2)!
  const emptyCells = [];
  for (let c = 0; c < 16; c++) {
    if (!board[c]) emptyCells.push(c);
  }
  if (emptyCells.length === 0) {
    return { score: base.score, winningLineFound: null, projectedP1: base.projectedP1, projectedP2: base.projectedP2, heldMateFor: null };
  }

  let bestEval = null;
  const allProjectedP1 = new Set(base.projectedP1);
  const allProjectedP2 = new Set(base.projectedP2);

  for (const c of emptyCells) {
    const simBoard = [...board];
    simBoard[c] = heldPiece;
    const simRes = staticBoardScore(simBoard, sigMap, bitOwners, poolAfterHeld);
    if (simRes.p1Win) simRes.winningLineFound.cells.forEach(idx => allProjectedP1.add(idx));
    if (simRes.p2Win) simRes.winningLineFound.cells.forEach(idx => allProjectedP2.add(idx));

    if (bestEval === null) {
      bestEval = simRes;
    } else if (holderPlayer === "player_1" && simRes.score > bestEval.score) {
      bestEval = simRes;
    } else if (holderPlayer === "player_2" && simRes.score < bestEval.score) {
      bestEval = simRes;
    }
  }

  let finalScore = bestEval.score;
  let heldMateFor = null;
  if (bestEval.p1Win) {
    finalScore = 9.8;
    heldMateFor = "player_1";
  } else if (bestEval.p2Win) {
    finalScore = -9.8;
    heldMateFor = "player_2";
  }

  return {
    score: finalScore,
    winningLineFound: null,
    projectedP1: allProjectedP1,
    projectedP2: allProjectedP2,
    heldMateFor
  };
}

function renderMusicStaff() {
  const svg = document.getElementById("music-staff");
  if (!svg) return;
  const w = 220, h = 54;
  // 5 ultra-subtle pencil staff lines directly on paper (middle line = 27 is 0.0 equilibrium)
  const staffYs = [11, 19, 27, 35, 43];
  let out = "";

  staffYs.forEach((y, idx) => {
    const isCenter = idx === 2;
    out += `<line x1="18" y1="${y}" x2="${w - 4}" y2="${y}" stroke="rgba(92, 87, 78, ${isCenter ? '0.42' : '0.24'})" stroke-width="${isCenter ? '0.9' : '0.65'}" ${isCenter ? 'stroke-dasharray="2.5,2.5"' : ''} />`;
  });

  // Faint pencil treble clef on the far left
  out += `<text x="2" y="38" font-size="31" fill="rgba(92, 87, 78, 0.45)" font-family="serif">&#119070;</text>`;

  if (states.length === 0) {
    svg.innerHTML = out;
    return;
  }

  const leftPad = 24, rightPad = w - 8;
  const usableW = Math.max(1, rightPad - leftPad);
  const denom = Math.max(1, states.length - 1);

  states.forEach((s, i) => {
    const x = leftPad + (i / denom) * usableW;
    const y = 27 - (s.evalScore / 10) * 18;
    const isP1 = s.evalScore > 0.05;
    const isP2 = s.evalScore < -0.05;
    const isNeutral = !isP1 && !isP2;
    const isCur = i === currentStep;

    if (isCur) {
      out += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6" fill="none" stroke="rgba(35, 33, 30, 0.55)" stroke-width="0.9" />`;
    }

    if (isNeutral) {
      // Quarter rest glyph (𝄽) centered on the middle equilibrium line for neutral/balanced moves
      out += `<g onclick="stepTo(${i})" style="cursor:pointer;">
        <title>Step ${i}: ${s.title} (0.0 Neutral)</title>
        <text x="${x.toFixed(1)}" y="33" text-anchor="middle" font-size="17" fill="rgba(82, 78, 70, 0.65)" font-family="serif">&#119099;</text>
      </g>`;
    } else {
      const matteColor = isP1
        ? "rgba(59, 98, 168, 0.72)"
        : "rgba(176, 92, 52, 0.72)";
      const stemY2 = isP2 ? y + 10 : y - 10;
      const stemX = isP2 ? x - 2.6 : x + 2.6;
      out += `<line x1="${stemX.toFixed(1)}" y1="${y.toFixed(1)}" x2="${stemX.toFixed(1)}" y2="${stemY2.toFixed(1)}" stroke="${matteColor}" stroke-width="0.95" />`;
      out += `<g onclick="stepTo(${i})" style="cursor:pointer;">
        <title>Step ${i}: ${s.title} (${s.evalScore > 0 ? '+' : ''}${s.evalScore.toFixed(1)})</title>
        <ellipse cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" rx="3.1" ry="2.2" transform="rotate(-18 ${x.toFixed(1)} ${y.toFixed(1)})" fill="${matteColor}" />
      </g>`;
    }
  });

  svg.innerHTML = out;
}

function loadGame(idx) {
  if (playTimer) togglePlay();
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
  const bitToFeat = {};
  legend.forEach(item => {
    const b = Math.round(item.bit);
    if (!Number.isNaN(b) && b >= 0 && b < 4) {
      if (item.owner) bitOwners[b] = item.owner;
      if (item.feature_id) bitToFeat[b] = item.feature_id;
    }
  });

  winCellsSet = new Set();
  winLines.forEach(wl => (wl.cells || []).forEach(c => winCellsSet.add(Math.round(c))));

  document.getElementById("match-meta").innerHTML =
    `Instance: <b>${match.instance_id || 'N/A'}</b> &nbsp;|&nbsp; Starter: <b>${match.starting_player || 'player_1'}</b> &nbsp;|&nbsp; Duration: <b>${match.duration_seconds || 0}s</b>`;
  document.getElementById("versus-title").innerHTML =
    `<span style="color:var(--p1);">${P1_NAME}</span> vs. <span style="color:var(--p2);">${P2_NAME}</span>`;

  document.getElementById("trait-legend-compact").innerHTML = legend.map(item => {
    const isP1 = item.owner === "player_1";
    return `<div style="margin-bottom:3px;">
      <b style="color:${isP1 ? 'var(--p1)' : 'var(--p2)'};">Bit ${Math.round(item.bit)} (${isP1 ? 'P1' : 'P2'}):</b>
      <span style="font-family:monospace;font-size:0.68rem;">${item.feature_id}</span>
    </div>`;
  }).join("");

  const reasonByStep = {};
  rlog.forEach(r => {
    const s = Math.round(r.step);
    if (!Number.isNaN(s)) reasonByStep[s] = r;
  });

  // Render Draft Log separately in the bottom drawer so the board replay starts immediately at Move 1!
  const draftHist = replay.draft_history || [];
  let stepCounter = 0;
  document.getElementById("draft-log-box").innerHTML = draftHist.length
    ? draftHist.map((d, i) => {
        stepCounter += 1;
        const r = reasonByStep[stepCounter] || {};
        const acc = d.accepted ? `<span style="color:#4ade80;font-weight:700;">ACCEPTED</span>` : `<span style="color:#9ca3af;">REJECTED</span>`;
        return `<div style="padding:5px 0;border-bottom:1px solid var(--panel-border);">
          <div><b>#${i + 1} ${d.player}</b> &rarr; <code>${d.attribute_id}</code> (${acc})</div>
          <div style="color:var(--text-muted);font-size:0.72rem;margin-top:2px;">${r.decision_explanation || ''}</div>
        </div>`;
      }).join("")
    : `<div style="color:var(--text-muted);">No draft actions recorded.</div>`;

  const allEntityIds = Object.keys(sigMap);
  let remainingPool = [...allEntityIds];

  states = [{
    board: Array(16).fill(null),
    actorLabel: "System",
    title: "Match Start — Empty 4x4 Board",
    handNote: `${match.starting_player || 'player_1'} goes first`,
    handSub: `${draftHist.length} draft proposals resolved off-board.`,
    cell: -1,
    selected: null,
    rationale: "Both players drafted 2 secret binary features. Board play starts now.",
    evalScore: 0.0,
    tag: null,
    projectedP1: new Set(),
    projectedP2: new Set(),
    sigMap,
    bitOwners
  }];

  let curBoard = Array(16).fill(null);
  let curSelected = null;
  let actualWinner = match.winner || null;
  let actualWinNote = winLines.length
    ? `Winning Line: [${winLines[0].cells.map(c => Math.round(c)).join(",")}] via ${winLines[0].feature_id || 'bit ' + Math.round(winLines[0].bit)}`
    : "";

  const pubHist = replay.public_history || [];
  for (let i = 0; i < pubHist.length; i++) {
    const act = pubHist[i];
    stepCounter += 1;
    const r = reasonByStep[stepCounter] || {};
    const prevState = states[states.length - 1];
    const prevEval = prevState.evalScore;
    const modelLabel = act.player === "player_1" ? P1_NAME : P2_NAME;

    if (act.kind === "select_entity") {
      curSelected = act.entity_id;
      const receiver = act.player === "player_1" ? "player_2" : "player_1";
      const safePieces = remainingPool.filter(eid =>
        evaluateBoard(curBoard, sigMap, bitOwners, receiver, eid, remainingPool).heldMateFor !== receiver
      );
      const evObj = evaluateBoard(curBoard, sigMap, bitOwners, receiver, curSelected, remainingPool);
      let tag = null;
      if (evObj.heldMateFor === receiver && safePieces.length > 0) {
        tag = "BLUNDER";
      }
      states.push({
        board: [...curBoard],
        actorLabel: `${modelLabel} (${act.player})`,
        title: `Selects piece ${act.entity_id.slice(0, 8)} for ${receiver}`,
        handNote: `${act.player} hands piece ${act.entity_id.slice(0, 6)} to ${receiver}`,
        handSub: tag === "BLUNDER" ? `Blunder! Gives ${receiver} an immediate winning piece.` : `Awaiting placement on the 4x4 grid.`,
        cell: -1,
        selected: curSelected,
        rationale: r.decision_explanation || "(No thinking trace emitted)",
        evalScore: evObj.score,
        tag,
        projectedP1: evObj.projectedP1,
        projectedP2: evObj.projectedP2,
        sigMap,
        bitOwners
      });
    } else if (act.kind === "place_entity") {
      const targetCell = Math.round(act.cell);
      const hadMate = (act.player === "player_1" && prevEval >= 9.7) || (act.player === "player_2" && prevEval <= -9.7);
      curBoard[targetCell] = curSelected;
      const placed = curSelected;
      remainingPool = remainingPool.filter(eid => eid !== placed);
      curSelected = null;

      const evObj = evaluateBoard(curBoard, sigMap, bitOwners, null, null, remainingPool);
      const newEval = evObj.score;
      let tag = null;
      if (evObj.winningLineFound) {
        tag = "WIN";
        actualWinner = evObj.winningLineFound.owner;
        winCellsSet = new Set(evObj.winningLineFound.cells);
        const fName = bitToFeat[evObj.winningLineFound.bit] || `Bit ${evObj.winningLineFound.bit}`;
        actualWinNote = `Winning Line: [${evObj.winningLineFound.cells.join(",")}] via ${fName} (${actualWinner})`;
      } else if (hadMate) {
        tag = "MISSED WIN";
      }

      states.push({
        board: [...curBoard],
        actorLabel: `${modelLabel} (${act.player})`,
        title: `Places ${placed ? placed.slice(0, 8) : '?'} on Cell ${targetCell}`,
        handNote: evObj.winningLineFound ? `QUARTO! ${actualWinner} wins!` : `${act.player} places on Cell ${targetCell}`,
        handSub: evObj.winningLineFound ? actualWinNote : (tag === "MISSED WIN" ? "Missed an immediate winning line!" : "Board updated."),
        cell: targetCell,
        selected: null,
        rationale: r.decision_explanation || "(No thinking trace emitted)",
        evalScore: newEval,
        tag,
        projectedP1: evObj.projectedP1,
        projectedP2: evObj.projectedP2,
        sigMap,
        bitOwners
      });

      if (evObj.winningLineFound) {
        break;
      }
    }
  }

  document.getElementById("win-trait-note").textContent = actualWinNote;
  const badge = document.getElementById("outcome-badge");
  badge.textContent = actualWinner ? `WINNER: ${actualWinner.toUpperCase()}` : (match.outcome ? `${match.outcome.toUpperCase()}` : "COMPLETED");
  badge.style.color = actualWinner === "player_1" ? "var(--p1)" : (actualWinner === "player_2" ? "var(--p2)" : "var(--ink)");
  badge.style.background = actualWinner === "player_1" ? "var(--p1-soft)" : (actualWinner === "player_2" ? "var(--p2-soft)" : "transparent");

  const slider = document.getElementById("step-slider");
  slider.max = states.length - 1;
  slider.value = states.length - 1;
  renderStep(states.length - 1);
}

function renderStep(idx) {
  currentStep = Math.max(0, Math.min(states.length - 1, idx));
  document.getElementById("step-slider").value = currentStep;
  document.getElementById("step-counter").textContent = `${currentStep}/${states.length - 1}`;
  const st = states[currentStep];
  const isFinal = currentStep === states.length - 1;

  document.getElementById("hand-annotation").innerHTML = `${st.handNote}<span class="sub-note">${st.handSub}</span>`;

  const sc = st.evalScore;
  document.getElementById("eval-score").textContent = (sc > 0 ? "+" : "") + sc.toFixed(1);
  const p1Pct = Math.round(((sc + 10) / 20) * 100);
  document.getElementById("eval-p1-fill").style.height = `${p1Pct}%`;

  const heldBox = document.getElementById("held-piece-box");
  if (st.selected) {
    const hSig = st.sigMap[st.selected];
    heldBox.innerHTML = `${renderToken(hSig, st.bitOwners)}<div class="token-code">${st.selected.slice(0, 8)}</div>`;
  } else {
    heldBox.innerHTML = `<span style="font-size:0.75rem;color:var(--ink-soft);">None</span>`;
  }

  renderMusicStaff();
  const grid = document.getElementById("board-grid");
  grid.innerHTML = st.board.map((eid, c) => {
    const isLast = st.cell === c;
    const isWin = isFinal && winCellsSet.has(c);
    const isProjP1 = !isWin && st.projectedP1 && st.projectedP1.has(c);
    const isProjP2 = !isWin && !isProjP1 && st.projectedP2 && st.projectedP2.has(c);
    const sig = eid ? st.sigMap[eid] : null;
    return `<div class="cell ${isLast ? 'last' : ''} ${isProjP1 ? 'projected-p1' : ''} ${isProjP2 ? 'projected-p2' : ''} ${isWin ? 'win' : ''}">
      <span class="cell-num">${c}</span>
      ${eid ? renderToken(sig, st.bitOwners) + `<span class="token-code">${eid.slice(0, 6)}</span>` : ``}
    </div>`;
  }).join("");

  const streamEl = document.getElementById("log-stream");
  streamEl.innerHTML = states.map((s, i) => {
    const tagHtml = s.tag === "BLUNDER"
      ? `<span class="tag tag-blunder">BLUNDER</span>`
      : (s.tag === "WIN"
          ? `<span class="tag tag-win">WIN</span>`
          : (s.tag === "MISSED WIN" ? `<span class="tag tag-miss">MISSED WIN</span>` : ""));
    const isExp = expandAll || i === currentStep;
    return `<div class="log-card ${i === currentStep ? 'active' : ''} ${isExp ? 'expanded' : ''}" onclick="stepTo(${i})">
      <div class="log-card-top">
        <span>${s.actorLabel} ${tagHtml}</span>
        <span style="color:var(--text-muted);font-family:monospace;">${i}</span>
      </div>
      <div class="log-card-desc">${s.title}</div>
      <div class="thinking-toggle">&#9662; Show thinking</div>
      <div class="thinking-body">${s.rationale}</div>
    </div>`;
  }).join("");

  const activeCard = streamEl.querySelector(".log-card.active");
  if (activeCard) activeCard.scrollIntoView({ block: "nearest" });
}

function toggleExpandAll() {
  expandAll = !expandAll;
  document.getElementById("expand-all-btn").textContent = expandAll ? "Collapse All Thinking" : "Expand All Thinking";
  renderStep(currentStep);
}

function stepTo(i) { renderStep(i); }
function stepBy(d) { renderStep(currentStep + d); }

function updatePlaySpeed() {
  if (playTimer) {
    togglePlay();
    togglePlay();
  }
}

function togglePlay() {
  const btn = document.getElementById("play-btn");
  if (playTimer) {
    clearInterval(playTimer);
    playTimer = null;
    btn.innerHTML = "&#9654;";
  } else {
    if (currentStep >= states.length - 1) renderStep(0);
    btn.innerHTML = "&#10074;&#10074;";
    const delay = parseInt(document.getElementById("speed-select").value, 10) || 850;
    playTimer = setInterval(() => {
      if (currentStep >= states.length - 1) { togglePlay(); return; }
      stepBy(1);
    }, delay);
  }
}

function renderTabs() {
  document.getElementById("game-tabs").innerHTML = GAMES.map((g, i) => {
    const m = g.match || {};
    return `<button class="tab-btn ${i === currentGameIdx ? 'active' : ''}" onclick="loadGame(${i})">
      Game ${i + 1} (${m.winner || 'Draw'})
    </button>`;
  }).join("");
}

function renderBottomPanels() {
  const ev = PAYLOAD.evaluator || {};
  const agg = (ev.series_aggregate && ev.series_aggregate.players) || {};
  const p1 = agg.player_1 || {};
  const p2 = agg.player_2 || {};
  document.getElementById("series-summary").innerHTML = `
    <table>
      <tr><th>Metric</th><th>Player 1</th><th>Player 2</th></tr>
      <tr><td>Wins</td><td>${p1.wins ?? 0}</td><td>${p2.wins ?? 0}</td></tr>
      <tr><td>Draft Precision</td><td>${p1.draft_precision ?? 'N/A'}</td><td>${p2.draft_precision ?? 'N/A'}</td></tr>
      <tr><td>Blunder Avoidance</td><td>${p1.blunder_avoidance_rate ?? 'N/A'}</td><td>${p2.blunder_avoidance_rate ?? 'N/A'}</td></tr>
      <tr><td>Self-Bit Alignment</td><td>${p1.self_bit_alignment_rate ?? 'N/A'}</td><td>${p2.self_bit_alignment_rate ?? 'N/A'}</td></tr>
      <tr><td>Win Conversion</td><td>${p1.immediate_win_conversion_rate ?? 'N/A'}</td><td>${p2.immediate_win_conversion_rate ?? 'N/A'}</td></tr>
    </table>`;

  const rga = ev.reasoning_grounding_audit || ev.semantic_judge || {};
  if (rga.status === "completed" && rga.scores) {
    const sc = rga.scores || {};
    const j1 = sc.player_1 || {};
    const j2 = sc.player_2 || {};
    document.getElementById("judge-summary").innerHTML = `
      <table>
        <tr><th>Deterministic Audit</th><th>Player 1</th><th>Player 2</th></tr>
        <tr><td>Faithfulness (RL-01)</td><td>${j1.deterministic_faithfulness_rate ?? j1.logical_faithfulness_rate ?? 'N/A'}</td><td>${j2.deterministic_faithfulness_rate ?? j2.logical_faithfulness_rate ?? 'N/A'}</td></tr>
        <tr><td>Evidence Citation (RL-03)</td><td>${j1.evidence_citation_rate ?? 'N/A'}</td><td>${j2.evidence_citation_rate ?? 'N/A'}</td></tr>
        <tr><td>Draft Repeats (RL-06)</td><td>${j1.draft_repeat_claim_count ?? 0}</td><td>${j2.draft_repeat_claim_count ?? 0}</td></tr>
      </table>`;
  } else {
    document.getElementById("judge-summary").innerHTML = `<div style="color:var(--text-muted);font-size:0.8rem;">Status: <b>${rga.status || 'unavailable'}</b></div>`;
  }
}

renderBottomPanels();
if (GAMES.length > 0) loadGame(0);
</script>
</body>
</html>
"""


def build_visualizer(run_json_path: str | Path, out_html_path: str | Path) -> Path:
    raw = json.loads(Path(run_json_path).read_text(encoding="utf-8"))
    payload = raw
    if isinstance(raw, dict) and isinstance(raw.get("results"), list):
        for item in raw["results"]:
            if isinstance(item, dict) and isinstance(item.get("dictResult"), dict):
                payload = item["dictResult"]
                break
    html = HTML_TEMPLATE.replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=False))
    out_path = Path(out_html_path)
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python build_visualizer.py <run.json> <out.html>")
        sys.exit(1)
    out = build_visualizer(sys.argv[1], sys.argv[2])
    print(f"Visualizer written to {out}")
