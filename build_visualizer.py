from __future__ import annotations

import json
from pathlib import Path
import sys


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Quarto Hidden-Information Benchmark — Classic Board &amp; Evaluator Report</title>
  <style>
    :root {
      --bg: #f3f0e9;
      --panel: #fbf9f5;
      --border: #d8d0c1;
      --text: #23201b;
      --muted: #6c6458;
      --accent: #3f7652;
      --accent-warm: #bb6b37;
      --win-bg: #d9f2e1;
      --win-border: #2e6b43;
      --cell-bg: #efe9dd;
      --cell-hover: #e5dec9;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 24px;
      font-family: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .container { max-width: 1280px; margin: 0 auto; }
    header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 20px;
    }
    h1 { margin: 0; font-size: 1.5rem; }
    .subtitle { color: var(--muted); font-size: 0.9rem; margin-top: 4px; }
    .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    select, button {
      font: inherit;
      padding: 7px 11px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--panel);
      color: var(--text);
      cursor: pointer;
    }
    button:hover:not(:disabled) { background: var(--cell-hover); }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
    button.live-on { background: #b83b2b; color: #fff; border-color: #b83b2b; }
    .grid-layout {
      display: grid;
      grid-template-columns: 440px 1fr;
      gap: 20px;
      align-items: start;
    }
    @media (max-width: 980px) { .grid-layout { grid-template-columns: 1fr; } }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 20px;
    }
    .card h2 { margin: 0 0 12px; font-size: 1.05rem; }
    .board-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      background: #ded6c6;
      padding: 12px;
      border-radius: 12px;
    }
    .board-cell {
      aspect-ratio: 1;
      background: var(--cell-bg);
      border: 2px solid #cfc5b2;
      border-radius: 10px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      position: relative;
      padding: 4px;
      transition: transform 0.15s ease;
    }
    .board-cell.is-last { border-color: var(--accent-warm); box-shadow: 0 0 0 2px rgba(187,107,55,0.3); }
    .board-cell.is-win {
      background: var(--win-bg);
      border-color: var(--win-border);
      border-width: 3px;
      box-shadow: 0 0 12px rgba(63, 118, 82, 0.35);
    }
    .cell-idx {
      position: absolute;
      top: 4px;
      left: 6px;
      font-size: 0.7rem;
      color: var(--muted);
      font-family: monospace;
    }
    .bits-tag {
      position: absolute;
      top: 4px;
      right: 6px;
      font-size: 0.65rem;
      color: var(--muted);
      font-family: monospace;
    }
    .uuid-tag {
      font-family: monospace;
      font-size: 0.68rem;
      color: var(--muted);
      margin-top: 2px;
    }
    .status-banner {
      padding: 10px 12px;
      border-radius: 8px;
      background: #efe9dd;
      margin-bottom: 12px;
      font-size: 0.92rem;
      line-height: 1.45;
    }
    .status-banner.win { background: var(--win-bg); border: 1px solid var(--win-border); font-weight: 600; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }
    th, td {
      padding: 7px 9px;
      border-bottom: 1px solid var(--border);
      text-align: left;
    }
    th { background: #f0ebe0; font-weight: 600; }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .badge.ok { background: #dff2e5; color: #265938; }
    .badge.no { background: #f8e2df; color: #8c2d23; }
    .tray {
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      gap: 6px;
      margin-top: 12px;
    }
    .tray-item {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 4px;
      text-align: center;
      background: #fff;
    }
    .tray-item.used { opacity: 0.25; }
    .tray-item.selected { border-color: var(--accent-warm); background: #fdf3ec; }
    .draft-list { max-height: 190px; overflow-y: auto; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Quarto Hidden-Information Benchmark</h1>
        <div class="subtitle" id="header-meta"></div>
      </div>
      <div class="controls">
        <label for="game-select">Game:</label>
        <select id="game-select"></select>
        <button id="btn-first" type="button">|&lt;</button>
        <button id="btn-prev" type="button">&lt; Prev</button>
        <span id="step-label" style="font-family: monospace; min-width: 90px; text-align: center;">Step 0 / 0</span>
        <button id="btn-next" class="primary" type="button">Next &gt;</button>
        <button id="btn-last" type="button">&gt;|</button>
        <button id="btn-autoplay" type="button">Auto-Play</button>
        <button id="btn-live" type="button" style="display:none;">Live Poll: OFF</button>
      </div>
    </header>

    <div id="series-warning" class="status-banner" style="display:none; background:#fbf0d9; border:1px solid #d4a64a;"></div>

    <div class="card">
      <h2>Series Aggregate Evaluator Report (Seat-Counterbalanced)</h2>
      <div id="series-eval-container"></div>
      <div id="semantic-judge-container" style="margin-top:14px;"></div>
    </div>

    <div class="grid-layout">
      <div>
        <div class="card">
          <h2>Classic 4&times;4 Quarto Board</h2>
          <div id="turn-banner" class="status-banner"></div>
          <div id="board-grid" class="board-grid"></div>
          <div style="margin-top:10px; font-size:0.8rem; color:var(--muted);">
            Bit 0: Tall/Short | Bit 1: Terracotta/Forest | Bit 2: Round/Square | Bit 3: Hollow/Solid
          </div>
          <div id="tray" class="tray"></div>
        </div>
      </div>

      <div>
        <div class="card">
          <h2>Classic Trait &harr; Drafted FMA Feature Mapping</h2>
          <div id="legend-container"></div>
        </div>

        <div class="card">
          <h2>Current Game Evaluator Metrics</h2>
          <div id="match-eval-container"></div>
        </div>

        <div class="card">
          <h2>Phase 1 — Attribute Draft History</h2>
          <div class="draft-list">
            <table>
              <thead>
                <tr><th>#</th><th>Player</th><th>Proposed FMA Feature</th><th>Status</th></tr>
              </thead>
              <tbody id="draft-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let BENCHMARK_PAYLOAD = __PAYLOAD_JSON__;
    const LIVE_ENDPOINT = __LIVE_ENDPOINT__;

    let currentGameIdx = 0;
    let currentStep = 0;
    let autoPlayTimer = null;
    let livePollTimer = null;

    function getGames() {
      return Array.isArray(BENCHMARK_PAYLOAD.matches) && BENCHMARK_PAYLOAD.matches.length
        ? BENCHMARK_PAYLOAD.matches
        : [{
            match: BENCHMARK_PAYLOAD.match || {},
            public_replay: BENCHMARK_PAYLOAD.public_replay || {},
            terminal_visualization: BENCHMARK_PAYLOAD.terminal_visualization || {},
          }];
    }

    function createClassicPieceSvg(sig, size) {
      const ns = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(ns, "svg");
      const tall = Boolean(sig & 1);
      const light = Boolean(sig & 2);
      const cylinder = Boolean(sig & 4);
      const hollow = Boolean(sig & 8);
      const topY = tall ? 28 : 42;
      const colors = light
        ? { body: "#bb6b37", top: "#d89263", shade: "#98532f" }
        : { body: "#3f7652", top: "#75a17e", shade: "#315e41" };

      svg.setAttribute("viewBox", "0 0 64 64");
      svg.setAttribute("width", String(size));
      svg.setAttribute("height", String(size));

      const add = (tag, attrs) => {
        const el = document.createElementNS(ns, tag);
        for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
        svg.appendChild(el);
      };

      if (cylinder) {
        add("ellipse", { cx: 32, cy: 55, rx: 22, ry: 8, fill: colors.shade });
        add("path", { d: `M10 ${topY} V55 H54 V${topY} Z`, fill: colors.body });
        add("ellipse", { cx: 32, cy: topY, rx: 22, ry: 8, fill: colors.top, stroke: colors.shade, "stroke-width": 1.5 });
      } else {
        add("path", { d: `M10 ${topY} L32 ${topY + 10} V58 L10 48 Z`, fill: colors.shade, stroke: colors.shade, "stroke-linejoin": "round" });
        add("path", { d: `M32 ${topY + 10} L54 ${topY} V48 L32 58 Z`, fill: colors.body, stroke: colors.shade, "stroke-linejoin": "round" });
        add("path", { d: `M10 ${topY} L32 ${topY - 10} L54 ${topY} L32 ${topY + 10} Z`, fill: colors.top, stroke: colors.shade, "stroke-linejoin": "round", "stroke-width": 1.5 });
      }
      if (hollow) {
        add("ellipse", { cx: 32, cy: topY, rx: cylinder ? 9 : 7, ry: 4, fill: "#fbf9f5", stroke: colors.shade, "stroke-width": 1.2 });
      }
      return svg;
    }

    function renderHeaderAndSeries() {
      const games = getGames();
      const evaluator = BENCHMARK_PAYLOAD.evaluator || {};
      const models = BENCHMARK_PAYLOAD.model_metadata || {};
      const p1Model = models.player_1?.model || "player_1";
      const p2Model = models.player_2?.model || "player_2";

      document.getElementById("header-meta").textContent =
        `Player 1: ${p1Model} vs Player 2: ${p2Model} | Instance: ${games[0]?.match?.instance_id || "unknown"}`;

      const seriesInfo = BENCHMARK_PAYLOAD.series || {};
      const warnEl = document.getElementById("series-warning");
      if (Array.isArray(seriesInfo.skipped_or_failed_games) && seriesInfo.skipped_or_failed_games.length) {
        warnEl.style.display = "block";
        const details = seriesInfo.skipped_or_failed_games
          .map(g => `Game ${g.game_index} (starter: ${g.starting_player}) -> ${g.status}: ${g.reason}`)
          .join(" | ");
        warnEl.textContent = `Series Notice (${seriesInfo.completed_games_count}/${seriesInfo.target_games} games completed): ${details}`;
      } else {
        warnEl.style.display = "none";
      }

      const gameSelect = document.getElementById("game-select");
      const prevVal = gameSelect.value;
      gameSelect.innerHTML = "";
      games.forEach((g, idx) => {
        const opt = document.createElement("option");
        const m = g.match || {};
        opt.value = String(idx);
        opt.textContent = `Game ${m.game_index || idx + 1} (Starter: ${m.starting_player || g.public_replay?.starting_player || "player_1"} | Winner: ${m.winner || "in_progress"})`;
        gameSelect.appendChild(opt);
      });
      if (prevVal && Number(prevVal) < games.length) {
        gameSelect.value = prevVal;
      }

      const container = document.getElementById("series-eval-container");
      const agg = evaluator.series_aggregate;
      if (!agg || !agg.players) {
        container.innerHTML = "<p>Single-game or in-progress run (series aggregate will appear upon match completion).</p>";
        return;
      }
      const p1 = agg.players.player_1 || {};
      const p2 = agg.players.player_2 || {};
      container.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Player 1 (${p1Model})</th>
              <th>Player 2 (${p2Model})</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Completed Games / Wins</td><td>${p1.wins ?? 0} / ${agg.completed_games} (${((p1.win_rate ?? 0)*100).toFixed(1)}%)</td><td>${p2.wins ?? 0} / ${agg.completed_games} (${((p2.win_rate ?? 0)*100).toFixed(1)}%)</td></tr>
            <tr><td>Draft Precision (Accepted / Proposals)</td><td>${p1.draft_accepted}/${p1.draft_proposals} (${((p1.draft_precision ?? 0)*100).toFixed(1)}%)</td><td>${p2.draft_accepted}/${p2.draft_proposals} (${((p2.draft_precision ?? 0)*100).toFixed(1)}%)</td></tr>
            <tr><td>Blunder Avoidance Rate (Safe Selects)</td><td>${p1.safe_selects}/${p1.select_turns} (${((p1.blunder_avoidance_rate ?? 0)*100).toFixed(1)}%)</td><td>${p2.safe_selects}/${p2.select_turns} (${((p2.blunder_avoidance_rate ?? 0)*100).toFixed(1)}%)</td></tr>
            <tr><td>Self-Bit Alignment Rate</td><td>${p1.self_bit_aligned_places}/${p1.place_turns} (${((p1.self_bit_alignment_rate ?? 0)*100).toFixed(1)}%)</td><td>${p2.self_bit_aligned_places}/${p2.place_turns} (${((p2.self_bit_alignment_rate ?? 0)*100).toFixed(1)}%)</td></tr>
            <tr><td>Immediate Win Conversion</td><td>${p1.immediate_wins_taken}/${p1.immediate_win_opportunities} (${((p1.immediate_win_conversion_rate ?? 0)*100).toFixed(1)}%)</td><td>${p2.immediate_wins_taken}/${p2.immediate_win_opportunities} (${((p2.immediate_win_conversion_rate ?? 0)*100).toFixed(1)}%)</td></tr>
          </tbody>
        </table>
      `;
      const sjContainer = document.getElementById("semantic-judge-container");
      const sj = evaluator.semantic_judge || {};
      if (sj.status === "completed" && sj.scores) {
        const s1 = sj.scores.player_1 || {};
        const s2 = sj.scores.player_2 || {};
        sjContainer.innerHTML = `
          <h3 style="margin:8px 0;font-size:0.96rem;">3rd-Model Semantic Reasoning Audit (Judge: ${sj.judge_model})</h3>
          <table>
            <thead><tr><th>Semantic Reasoning Metric</th><th>Player 1 (${p1Model})</th><th>Player 2 (${p2Model})</th></tr></thead>
            <tbody>
              <tr><td>Logical Faithfulness (RL-01)</td><td>${((s1.logical_faithfulness_rate ?? 0)*100).toFixed(1)}%</td><td>${((s2.logical_faithfulness_rate ?? 0)*100).toFixed(1)}%</td></tr>
              <tr><td>Trap &amp; Opponent Awareness</td><td>${((s1.trap_awareness_rate ?? 0)*100).toFixed(1)}%</td><td>${((s2.trap_awareness_rate ?? 0)*100).toFixed(1)}%</td></tr>
              <tr><td>Self-Consistency (RL-06)</td><td>${((s1.self_consistency_score ?? 0)*100).toFixed(1)}%</td><td>${((s2.self_consistency_score ?? 0)*100).toFixed(1)}%</td></tr>
              <tr><td>Auditor Finding</td><td>${s1.key_finding || "-"}</td><td>${s2.key_finding || "-"}</td></tr>
            </tbody>
          </table>
        `;
      } else if (sj.status) {
        sjContainer.innerHTML = `<p style="color:var(--muted);font-size:0.84rem;">Semantic Judge: ${sj.status} (${sj.reason || ""})</p>`;
      }
    }

    function buildEntitySignatures(replay, termViz) {
      const explicitSigs = termViz?.entity_signatures || {};
      const seen = [];
      for (const act of (replay.public_history || [])) {
        if (act.kind === "select_entity" && !seen.includes(act.entity_id)) {
          seen.push(act.entity_id);
        }
      }
      for (const cellUuid of (replay.board || [])) {
        if (cellUuid && !seen.includes(cellUuid)) {
          seen.push(cellUuid);
        }
      }
      const sigMap = {};
      const hasTruth = Object.keys(explicitSigs).length > 0;
      seen.forEach((uuid, i) => {
        sigMap[uuid] = (uuid in explicitSigs) ? Number(explicitSigs[uuid]) : (i % 16);
      });
      return { seen, sigMap, hasTruth };
    }

    function renderGame() {
      const games = getGames();
      const gameObj = games[currentGameIdx] || games[0];
      const matchMeta = gameObj.match || {};
      const replay = gameObj.public_replay || {};
      const termViz = gameObj.terminal_visualization || {};
      const history = replay.public_history || [];
      const evalMatches = Array.isArray(BENCHMARK_PAYLOAD.evaluator?.matches) ? BENCHMARK_PAYLOAD.evaluator.matches : [];
      const evalMatch = evalMatches[currentGameIdx] || {};
      const { seen, sigMap, hasTruth } = buildEntitySignatures(replay, termViz);

      if (currentStep > history.length) currentStep = history.length;

      document.getElementById("step-label").textContent = `Step ${currentStep} / ${history.length}`;
      document.getElementById("btn-first").disabled = currentStep === 0;
      document.getElementById("btn-prev").disabled = currentStep === 0;
      document.getElementById("btn-next").disabled = currentStep >= history.length;
      document.getElementById("btn-last").disabled = currentStep >= history.length;

      const boardState = Array(16).fill(null);
      let heldEntity = null;
      let lastCell = null;
      const usedSet = new Set();

      for (let i = 0; i < currentStep; i++) {
        const act = history[i];
        if (act.kind === "select_entity") {
          heldEntity = act.entity_id;
        } else if (act.kind === "place_entity") {
          boardState[Number(act.cell)] = heldEntity;
          usedSet.add(heldEntity);
          lastCell = Number(act.cell);
          heldEntity = null;
        }
      }

      const winningLines = Array.isArray(termViz.winning_lines) ? termViz.winning_lines : [];
      const isFinalStep = currentStep === history.length && history.length > 0;
      const winCells = new Set(isFinalStep ? winningLines.flatMap(l => l.cells || []) : []);

      const banner = document.getElementById("turn-banner");
      banner.className = "status-banner";
      if (currentStep === 0) {
        banner.textContent = `Start of game — ${replay.starting_player || "player_1"} selects the first piece.`;
      } else if (isFinalStep && replay.result) {
        banner.classList.add("win");
        const winDesc = winningLines.length
          ? " | Winning Line: " + winningLines.map(w => `${w.line_name} [${w.cells.join(",")}] sharing ${w.classic_trait} (${w.feature_id || ""}, owner: ${w.owner || ""})`).join("; ")
          : (hasTruth ? "" : " (Run new version to attach exact post-terminal bit signatures & winning line coordinates)");
        banner.textContent = replay.result.outcome === "win"
          ? `Game Over: ${replay.result.winner} wins by ${replay.result.reason}!${winDesc}`
          : `Game Over: Draw (${replay.result.reason}).`;
      } else {
        const lastAct = history[currentStep - 1];
        const reasoningList = Array.isArray(termViz.post_game_reasoning_log) ? termViz.post_game_reasoning_log : [];
        const gameplayReasons = reasoningList.filter(r => r.action && (r.action.kind === "select_entity" || r.action.kind === "place_entity"));
        const stepReason = gameplayReasons[currentStep - 1]?.decision_explanation;
        const baseMsg = lastAct.kind === "select_entity"
          ? `Step ${currentStep}: ${lastAct.player} selected piece ${lastAct.entity_id.slice(0, 8)}...`
          : `Step ${currentStep}: ${lastAct.player} placed piece at cell ${Number(lastAct.cell)} (Row ${Math.floor(Number(lastAct.cell)/4)+1}, Col ${(Number(lastAct.cell)%4)+1}).`;
        banner.textContent = stepReason ? `${baseMsg} | Rationale: "${stepReason}"` : baseMsg;
      }

      const boardGrid = document.getElementById("board-grid");
      boardGrid.innerHTML = "";
      for (let c = 0; c < 16; c++) {
        const cellDiv = document.createElement("div");
        cellDiv.className = "board-cell"
          + (c === lastCell ? " is-last" : "")
          + (winCells.has(c) ? " is-win" : "");
        const idxSpan = document.createElement("span");
        idxSpan.className = "cell-idx";
        idxSpan.textContent = String(c);
        cellDiv.appendChild(idxSpan);

        const uuid = boardState[c];
        if (uuid) {
          const sig = sigMap[uuid] ?? 0;
          const bitsSpan = document.createElement("span");
          bitsSpan.className = "bits-tag";
          bitsSpan.textContent = hasTruth ? sig.toString(2).padStart(4, "0") : "sim";
          cellDiv.appendChild(bitsSpan);

          cellDiv.appendChild(createClassicPieceSvg(sig, 46));
          const tag = document.createElement("div");
          tag.className = "uuid-tag";
          tag.textContent = uuid.slice(0, 6);
          cellDiv.appendChild(tag);
        }
        boardGrid.appendChild(cellDiv);
      }

      const tray = document.getElementById("tray");
      tray.innerHTML = "";
      seen.forEach((uuid) => {
        const sig = sigMap[uuid] ?? 0;
        const item = document.createElement("div");
        item.className = "tray-item" + (usedSet.has(uuid) ? " used" : "") + (uuid === heldEntity ? " selected" : "");
        item.appendChild(createClassicPieceSvg(sig, 26));
        const lbl = document.createElement("div");
        lbl.className = "uuid-tag";
        lbl.textContent = hasTruth ? sig.toString(2).padStart(4, "0") : uuid.slice(0, 4);
        item.appendChild(lbl);
        tray.appendChild(item);
      });

      // Legend Table
      const legendContainer = document.getElementById("legend-container");
      const legend = Array.isArray(termViz.bit_feature_legend) ? termViz.bit_feature_legend : [];
      if (legend.length) {
        legendContainer.innerHTML = `
          <table>
            <thead><tr><th>Classic Trait</th><th>Visual Rule</th><th>Drafted FMA Feature</th><th>Owner</th></tr></thead>
            <tbody>
              ${legend.map(l => `<tr><td>${l.classic_trait}</td><td>${l.visual_rule}</td><td style="font-family:monospace;">${l.feature_id || "-"}</td><td>${l.owner || "-"}</td></tr>`).join("")}
            </tbody>
          </table>
        `;
      } else {
        legendContainer.innerHTML = "<p style='color:var(--muted);font-size:0.85rem;'>Post-terminal trait mapping will appear for new runs.</p>";
      }

      // Match Evaluator Table
      const matchEvalContainer = document.getElementById("match-eval-container");
      const dm = evalMatch.draft_metrics || {};
      const psm = evalMatch.piece_strategy_metrics || {};
      const p1d = dm.player_1 || {};
      const p2d = dm.player_2 || {};
      const p1s = psm.player_1 || {};
      const p2s = psm.player_2 || {};
      matchEvalContainer.innerHTML = `
        <table>
          <thead>
            <tr><th>Game ${matchMeta.game_index || currentGameIdx + 1} Metric</th><th>Player 1</th><th>Player 2</th></tr>
          </thead>
          <tbody>
            <tr><td>Owned Drafted Features</td><td>${(p1d.owned_features || []).join(", ") || "-"}</td><td>${(p2d.owned_features || []).join(", ") || "-"}</td></tr>
            <tr><td>Draft Precision</td><td>${p1d.accepted ?? 0}/${p1d.proposals ?? 0} (${((p1d.draft_precision ?? 0)*100).toFixed(1)}%)</td><td>${p2d.accepted ?? 0}/${p2d.proposals ?? 0} (${((p2d.draft_precision ?? 0)*100).toFixed(1)}%)</td></tr>
            <tr><td>Blunder Avoidance Rate</td><td>${p1s.safe_selects ?? 0}/${p1s.select_turns ?? 0} (${((p1s.blunder_avoidance_rate ?? 0)*100).toFixed(1)}%)</td><td>${p2s.safe_selects ?? 0}/${p2s.select_turns ?? 0} (${((p2s.blunder_avoidance_rate ?? 0)*100).toFixed(1)}%)</td></tr>
            <tr><td>Self-Bit Alignment Rate</td><td>${p1s.self_bit_aligned_places ?? 0}/${p1s.place_turns ?? 0} (${((p1s.self_bit_alignment_rate ?? 0)*100).toFixed(1)}%)</td><td>${p2s.self_bit_aligned_places ?? 0}/${p2s.place_turns ?? 0} (${((p2s.self_bit_alignment_rate ?? 0)*100).toFixed(1)}%)</td></tr>
            <tr><td>Immediate Win Conversion</td><td>${p1s.immediate_wins_taken ?? 0}/${p1s.immediate_win_opportunities ?? 0} (${((p1s.immediate_win_conversion_rate ?? 0)*100).toFixed(1)}%)</td><td>${p2s.immediate_wins_taken ?? 0}/${p2s.immediate_win_opportunities ?? 0} (${((p2s.immediate_win_conversion_rate ?? 0)*100).toFixed(1)}%)</td></tr>
          </tbody>
        </table>
      `;

      // Draft table
      const tbody = document.getElementById("draft-tbody");
      tbody.innerHTML = "";
      (replay.draft_history || []).forEach((d, idx) => {
        const tr = document.createElement("tr");
        const ok = d.accepted === true;
        tr.innerHTML = `
          <td>${idx + 1}</td>
          <td>${d.player}</td>
          <td style="font-family:monospace;">${d.attribute_id}</td>
          <td><span class="badge ${ok ? "ok" : "no"}">${ok ? "Accepted" : "Rejected"}</span></td>
        `;
        tbody.appendChild(tr);
      });
    }

    document.getElementById("game-select").addEventListener("change", (e) => {
      currentGameIdx = Number(e.target.value);
      const games = getGames();
      currentStep = (games[currentGameIdx]?.public_replay?.public_history || []).length;
      renderGame();
    });
    document.getElementById("btn-first").addEventListener("click", () => { currentStep = 0; renderGame(); });
    document.getElementById("btn-prev").addEventListener("click", () => { if (currentStep > 0) { currentStep--; renderGame(); } });
    document.getElementById("btn-next").addEventListener("click", () => {
      const max = (getGames()[currentGameIdx]?.public_replay?.public_history || []).length;
      if (currentStep < max) { currentStep++; renderGame(); }
    });
    document.getElementById("btn-last").addEventListener("click", () => {
      currentStep = (getGames()[currentGameIdx]?.public_replay?.public_history || []).length;
      renderGame();
    });

    const autoBtn = document.getElementById("btn-autoplay");
    autoBtn.addEventListener("click", () => {
      if (autoPlayTimer) {
        clearInterval(autoPlayTimer);
        autoPlayTimer = null;
        autoBtn.textContent = "Auto-Play";
        return;
      }
      const max = (getGames()[currentGameIdx]?.public_replay?.public_history || []).length;
      if (currentStep >= max) currentStep = 0;
      autoBtn.textContent = "Stop Auto-Play";
      autoPlayTimer = setInterval(() => {
        const m = (getGames()[currentGameIdx]?.public_replay?.public_history || []).length;
        if (currentStep < m) {
          currentStep++;
          renderGame();
        } else {
          clearInterval(autoPlayTimer);
          autoPlayTimer = null;
          autoBtn.textContent = "Auto-Play";
        }
      }, 850);
    });

    const liveBtn = document.getElementById("btn-live");
    if (LIVE_ENDPOINT) {
      liveBtn.style.display = "inline-block";
      const toggleLive = () => {
        if (livePollTimer) {
          clearInterval(livePollTimer);
          livePollTimer = null;
          liveBtn.textContent = "Live Poll: OFF";
          liveBtn.classList.remove("live-on");
          return;
        }
        liveBtn.textContent = "Live Poll: ON";
        liveBtn.classList.add("live-on");
        livePollTimer = setInterval(async () => {
          try {
            const resp = await fetch(LIVE_ENDPOINT, { cache: "no-store" });
            if (resp.ok) {
              BENCHMARK_PAYLOAD = await resp.json();
              const games = getGames();
              currentGameIdx = games.length - 1;
              currentStep = (games[currentGameIdx]?.public_replay?.public_history || []).length;
              renderHeaderAndSeries();
              renderGame();
            }
          } catch (_) {}
        }, 1500);
      };
      liveBtn.addEventListener("click", toggleLive);
      toggleLive();
    }

    renderHeaderAndSeries();
    currentStep = (getGames()[0]?.public_replay?.public_history || []).length;
    renderGame();
  </script>
</body>
</html>
"""


def render_visualizer_html(payload: dict, live_endpoint: str | None = None) -> str:
    return (
        HTML_TEMPLATE
        .replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=False))
        .replace("__LIVE_ENDPOINT__", json.dumps(live_endpoint))
    )


def render_visualizer_from_run_json(run_json_path: Path, output_html_path: Path) -> None:
    raw = json.loads(run_json_path.read_text(encoding="utf-8"))
    payload = raw
    if isinstance(raw, dict) and isinstance(raw.get("results"), list):
        for item in raw["results"]:
            if isinstance(item, dict) and isinstance(item.get("dictResult"), dict):
                payload = item["dictResult"]
                break
    output_html_path.write_text(render_visualizer_html(payload), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: python build_visualizer.py <input.run.json> <output.html>")
    render_visualizer_from_run_json(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"Visualizer generated: {sys.argv[2]}")
