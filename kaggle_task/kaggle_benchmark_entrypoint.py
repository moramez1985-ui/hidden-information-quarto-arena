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
    payload_json = json.dumps(result_payload, ensure_ascii=False)
    html_code = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Quarto Match Visualizer</title></head>
<body style="margin:0;background:#0f172a;color:#f8fafc;font-family:system-ui,sans-serif;">
<div id="quarto-viz" style="padding:20px;max-width:960px;margin:20px auto;border:1px solid #334155;border-radius:12px;">
  <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #334155;padding-bottom:12px;margin-bottom:16px;">
    <div><h2 style="margin:0;color:#38bdf8;">Quarto Hidden-Info Match Visualizer</h2><div id="match-meta" style="font-size:0.85rem;color:#94a3b8;margin-top:4px;"></div></div>
    <div id="outcome-badge" style="padding:6px 12px;border-radius:999px;font-weight:600;font-size:0.85rem;"></div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
    <div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
        <button onclick="stepMove(-1)" style="background:#1e293b;color:#fff;border:1px solid #475569;padding:6px 12px;border-radius:6px;cursor:pointer;">Prev</button>
        <input id="step-slider" type="range" min="0" max="0" value="0" oninput="renderStep(parseInt(this.value))" style="flex:1;cursor:pointer;">
        <button onclick="stepMove(1)" style="background:#1e293b;color:#fff;border:1px solid #475569;padding:6px 12px;border-radius:6px;cursor:pointer;">Next</button>
      </div>
      <div id="step-label" style="text-align:center;font-size:0.9rem;color:#cbd5e1;margin-bottom:10px;font-weight:600;"></div>
      <div id="board-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;background:#1e293b;padding:12px;border-radius:10px;"></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:12px;">
      <div style="background:#1e293b;padding:12px;border-radius:8px;border:1px solid #334155;">
        <div style="font-size:0.8rem;color:#94a3b8;text-transform:uppercase;margin-bottom:6px;">Players & Integrity</div>
        <div id="players-info" style="font-size:0.85rem;line-height:1.6;"></div>
      </div>
      <div style="background:#1e293b;padding:12px;border-radius:8px;border:1px solid #334155;flex:1;max-height:300px;overflow-y:auto;">
        <div style="font-size:0.8rem;color:#94a3b8;text-transform:uppercase;margin-bottom:6px;">Timeline (Draft + Game)</div>
        <div id="action-log" style="font-size:0.82rem;font-family:monospace;line-height:1.5;"></div>
      </div>
    </div>
  </div>
</div>
<script>
const DATA = {payload_json};
const replay = DATA.public_replay || {{}};
const draft = replay.draft_history || [];
const history = replay.public_history || [];
const match = DATA.match || {{}};
const models = DATA.model_metadata || {{}};
const states = [{{ board: Array(16).fill(null), desc: "Initial State", cell: -1 }}];
let curBoard = Array(16).fill(null);
let curSelected = null;
draft.forEach((d, idx) => {{
  states.push({{
    board: [...curBoard],
    desc: `Draft ${{idx+1}}: ${{d.player}} proposed ${{d.attribute_id}} (${{d.accepted ? 'ACCEPTED' : 'REJECTED'}})`,
    cell: -1
  }});
}});
history.forEach((act, idx) => {{
  if (act.kind === "select_entity") {{
    curSelected = act.entity_id;
    states.push({{ board: [...curBoard], desc: `Move ${{idx+1}}: ${{act.player}} selected ${{act.entity_id.slice(0,8)}}`, cell: -1 }});
  }} else if (act.kind === "place_entity") {{
    curBoard[act.cell] = curSelected;
    const placed = curSelected;
    curSelected = null;
    states.push({{ board: [...curBoard], desc: `Move ${{idx+1}}: ${{act.player}} placed ${{placed ? placed.slice(0,8) : '?'}} at cell ${{act.cell}}`, cell: act.cell }});
  }}
}});
document.getElementById("match-meta").textContent = `Match: ${{match.match_id || 'N/A'}} | Actions: ${{match.action_count || 0}} | Duration: ${{match.duration_seconds || 0}}s`;
const badge = document.getElementById("outcome-badge");
badge.textContent = match.outcome ? `${{match.outcome.toUpperCase()}} (${{match.winner || 'None'}})` : "FAILED";
badge.style.background = match.outcome === "win" ? "#065f46" : "#7f1d1d";
const p1 = models.player_1 ? models.player_1.model : "player_1";
const p2 = models.player_2 ? models.player_2.model : "player_2";
document.getElementById("players-info").innerHTML = `<div><b>Player 1:</b> ${{p1}}</div><div><b>Player 2:</b> ${{p2}}</div><div>Audit: <b>${{match.audit_valid}}</b> | Replay: <b>${{match.replay_valid}}</b></div>`;
const slider = document.getElementById("step-slider");
slider.max = states.length - 1;
slider.value = states.length - 1;
function stepMove(d) {{ slider.value = Math.max(0, Math.min(states.length - 1, parseInt(slider.value) + d)); renderStep(parseInt(slider.value)); }}
function renderStep(idx) {{
  const st = states[idx];
  document.getElementById("step-label").textContent = `[${{idx}}/${{states.length - 1}}] ${{st.desc}}`;
  const grid = document.getElementById("board-grid");
  grid.innerHTML = "";
  st.board.forEach((v, c) => {{
    const div = document.createElement("div");
    const isLast = c === st.cell;
    div.style.cssText = `height:64px;border-radius:8px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:0.75rem;background:${{v ? (isLast ? '#0284c7' : '#334155') : '#0f172a'}};border:2px solid ${{isLast ? '#38bdf8' : '#475569'}};color:${{v ? '#f8fafc' : '#64748b'}};`;
    div.innerHTML = `<span style="font-size:0.65rem;opacity:0.7;">Cell ${{c}}</span><strong style="margin-top:4px;">${{v ? v.slice(0, 8) : 'Empty'}}</strong>`;
    grid.appendChild(div);
  }});
  document.getElementById("action-log").innerHTML = states.map((s, i) => `<div style="padding:2px 4px;border-radius:4px;background:${{i === idx ? '#0284c7' : 'transparent'}};cursor:pointer;" onclick="slider.value=${{i}};renderStep(${{i}})">${{s.desc}}</div>`).join("");
}}
renderStep(states.length - 1);
</script></body></html>"""
    Path("/kaggle/working/quarto_match_visualizer.html").write_text(html_code, encoding="utf-8")
    Path("/kaggle/working/quarto_match_result.json").write_text(json.dumps(result_payload, indent=2), encoding="utf-8")


@kbench.task(name="Quarto Two-Model Match")
def run_quarto_two_model_match(llm) -> dict:
    failure_context = {
        "stage": "task_setup",
        "started_at": time.monotonic(),
    }
    task_module = _prepare_and_load_quarto_module()
    try:
        res = task_module._run_quarto_two_model_match(llm, failure_context)
        _save_visualizer(res)
        return res
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