# Quarto History and Readiness Reconciliation

**As of:** 2026-11-14  
**Repository:** `D:\CODES\quarto`  
**Purpose:** Reconcile the current worktree, retained FMA evidence, local pilot, Kaggle integration, privacy/replay hardening, staging, and remaining blockers. This is a read-only audit; no tests, Tasks, sampling, model calls, uploads, or dependency changes were made for it.

## Executive conclusion

There is evidence of **one completed local two-model Quarto game**, but it was a historical **QM9** pilot using `qwen3.5:4b` and `gemma4:31b-cloud`; a second match failed after six actions. This is not an FMA benchmark, a Kaggle Task run, or evidence that the Task's currently configured Gemini/Claude models were called. The saved pilot also lacks a valid starting-player value and uses a pre-hardening audit shape, so its stored `audit_valid`/`replay_valid` flags are not proof that the same snapshots pass the current validator.

FMA progress is substantial but remains inventory/feasibility evidence: 6,120 retained candidate specifications, 1,150 accepted by the strict two-count rule, and one independently inspected candidate. No candidate has a stable persisted `InstanceSpec` identity or has been passed to `TournamentRunner.run_match()`.

The current root and staged Kaggle Tasks fail closed before inference. Their match code is unreachable and has no call to `runner.run_match()`. The stage's hashes are internally valid, but key staged sources do not match the current workspace, including Phase 0 replay/private-access hardening and the Phase 2 privacy audit. The manifest's claim of an 8-action synthetic fake-model Task run describes an earlier Task revision, not the Task source it currently hashes.

**Readiness:** not ready for a real FMA-backed or Kaggle two-model benchmark. A historic local QM9 match did complete, but it does not satisfy that target.

## 1. Repository state and evidence hierarchy

### Git/worktree state

- Branch: `main`
- HEAD: `fc7e5d355162c81c267eb3d02462539bc2283113` (`feat(fma): add validated real-data instance adapter`, 2026-11-09)
- No Git remote is configured.
- No staged changes or deletions.
- Six tracked files are modified: `README.md`, `phase0_foundation.py`, `quarto_engine.py`, `tests/test_phase0_foundation.py`, `tests/test_qm9_instance_validation_integration.py`, and `tests/test_quarto_engine.py`.
- `git diff --stat`: 6 files, 1,017 insertions, 105 deletions.
- 106 untracked files were present before creating this report; the final count is 107 including this report. `git status --short --branch` reports these top-level entries (directories are collapsed by Git):

```text
## main
 M README.md
 M phase0_foundation.py
 M quarto_engine.py
 M tests/test_phase0_foundation.py
 M tests/test_qm9_instance_validation_integration.py
 M tests/test_quarto_engine.py
?? .github/
?? .vscode/
?? artifacts/
?? data/
?? decision_trace.py
?? deepseek_placement_test.jsonl
?? deepseek_rule_test.jsonl
?? deepseek_selection_test.jsonl
?? docs/
?? evaluator/
?? experiments/
?? hidden_quarto_benchmark.py
?? kaggle_agent_adapter.py
?? kaggle_dataset_staging/
?? kaggle_task/
?? notebooks/
?? out.txt
?? reports/
?? security_review_evidence.txt
?? tests/fixtures/
?? tests/test_decision_trace.py
?? tests/test_evaluator.py
?? tests/test_hidden_quarto_benchmark.py
?? tests/test_kaggle_adapter_metadata.py
?? tests/test_kaggle_agent_adapter.py
?? tests/test_phase1_qm9_adapter.py
?? tests/test_quarto_two_model_task.py
?? tests/test_tournament_harness.py
?? tournament_harness.py
```

The untracked [FMA inventory report](./fma_instance_inventory_audit_20261114.md) predates this reconciliation and was not changed. Its SHA-256 before this report was `8c3bf798b2b5a6c537b75731f1cea362cccfcd03bc0c50abe183886f6474e109`.

### History qualification

The current `main` ancestry is short: HEAD plus the local UI and initial-import commits. Historical checkpoint commits cited in [the dataset-isolation recovery report](./quarto_dataset_isolation_recovery_20261112.md) are present as Git objects, but the generic-factory checkpoint `e7e8b1c` has no merge base with current HEAD and is not an ancestor. Treat that chronology as recovered checkpoint evidence, not as a linear `main` history. Earlier Qodo repository discovery found no accessible Quarto repository; this report therefore uses local Git objects, current files, and retained reports/logs.

### What changed after earlier readiness reports

| Area | Current evidence | State |
|---|---|---|
| Generic adapters and FMA | Generic factory/build/validation code and the FMA adapter are in the current HEAD; FMA is available but not automatically selected. | Present; no FMA match. |
| QM9 retirement | `make_qm9_instance()` now raises, and `run_pilot()` refuses to fall back to QM9 or synthetic data. | Fallback disabled, but the pilot raises only after model connectivity calls and leaves unreachable code after the raise. |
| Phase 1 | Current workspace Phase 0 enforces active-player private access and exact replay-state fields; focused tests are present. | Implemented in the dirty worktree, not in the staged Phase 0 copy. |
| Phase 2 | Current workspace harness compares restricted values and structures against actual public observations, public audit, and prompts. | Implemented in the untracked workspace harness; not in the staged harness. |
| Kaggle Task | Root and staged Task both fail closed without a real validated instance. | Safer than the earlier synthetic Task path, but no real match can run. |
| Staging | Manifest/payload hashes are internally consistent. | Source parity with the workspace is incomplete; evidence text is stale. |

The Nov. 12 [recovery report](./quarto_dataset_isolation_recovery_20261112.md) describes the earlier root Task as actively running `SyntheticAdapter`. The later [remediation report](./quarto_dataset_isolation_remediation_20261112.md) records the switch to fail-closed behavior. Current source confirms that later state. This is a chronological change, not a reason to treat the earlier synthetic Task as current.

## 2. Actual model and match evidence

| Evidence class | Result | What it establishes—and what it does not |
|---|---|---|
| Local provider connectivity | The saved Nov. 8 [public pilot report](../experiments/pilot_tournament/public_report.json) records successful smoke responses from `qwen3.5:4b` and `gemma4:31b-cloud`. | Actual local-harness provider calls; not Kaggle inference. |
| Local Quarto game | One 8-action match completed with a win for player 1; all eight logged action events received responses and passed controller validation. The recorded model mapping was Qwen/Gemma. | Evidence of one actual two-model QM9 game. It is not FMA, and the historical audit flags predate current replay validation. |
| Second local game | A second match completed six valid actions, then an Ollama request timed out; it ended as `agent_failure`, with audit/replay marked false. | A failed attempt, not a second completed benchmark game. |
| Seat/start balance | The two saved matches reverse model-to-player assignments, but both public and restricted records contain `starting_player: null`; their serialized engine-state snapshots omit `starting_player`. | The saved evidence cannot establish that both starting-player assignments were exercised. |
| Current Kaggle models | The root Task configures `google/gemini-3.8-flash` and `anthropic/claude-sonnet-4-6@default` ([Task](../kaggle_task/quarto_two_model_match.py#L18)). | Configuration and fake-object identity checks only; no provider call or hosted Task run is recorded. |
| Offline Kaggle adapter tests | The adapter and Task tests use fake LLM/SDK objects and synthetic fixtures. | Plumbing/schema behavior only, never real inference or a real benchmark. |

The saved local match uses instance ID `qm9_pilot_hf_ring_db_0001`. The first game's historical JSON reports `audit_valid=true` and `replay_valid=true`, but its serialized audit state lacks `starting_player`; current `AuditSnapshot.validate_replay()` requires the exact engine-state schema, including that field ([Phase 0](../phase0_foundation.py#L624), [schema](../phase0_foundation.py#L48)). Do not present the old flags as current-validator replays. The restricted match log contains private prompt content and should remain restricted; no prompt text is reproduced here.

The model-selection record also changed over time. The Nov. 10 [model feasibility report](./kaggle_model_discovery_feasibility_20261110.md) proposes Gemma 3/Qwen 3 as provisional catalog candidates and says no final pair or inference was established. The later Task source selects Gemini/Claude. The Nov. 10 [Kaggle capability report](./kaggle_discovery/kaggle_cli_capability_report_20261110.md) lists corresponding Model Proxy names, but explicitly does not establish a successful inference request. The source change is confirmed; live registry availability is untested.

## 3. FMA state and dataset independence

The retained FMA inventory reports two disjoint 25,000-track samples, 3,060 quartets scanned in each, 6,120 distinct candidate specifications total, 541 accepted in seed 11, and 609 accepted in the seed-23 holdout. Acceptance is conjunctive: `id_level_count > 1 AND structural_count > 1`. Candidate rows are not standalone reusable `InstanceSpec` artifacts; they do not carry a stable `instance_id` or `public_seed`.

The [accepted-instance inspection](./diagnostics/fma_first_accepted_instance_inspection.md) independently reproduced one recorded candidate against the local archive and validator. That candidate has not been selected for a match or reconstructed in this audit. No FMA candidate has been passed to `TournamentRunner.run_match()`. The local archive hash in the inventory (`d9527a…bf265`) matches the adapter's pinned SHA-256; it is not included in Kaggle staging.

Current code supports dataset-independent instance validation: adapters declare `requires_instance_validation`, and Phase 0 enforces both counts for those adapters ([controller](../phase0_foundation.py#L1326), [generic builder](../domain_adapters/instance_builder.py#L532)). No active domain-name predicate selects QM9; however, `InstanceValidationError` still says “QM9 instance” in its generic error message ([Phase 0](../phase0_foundation.py#L578)). That is a stale diagnostic, not a QM9-specific acceptance rule. `make_qm9_instance()` raises instead of returning a default instance ([harness](../tournament_harness.py#L1074)); no automatic QM9 fallback is active.

FMA remains optional: neither the generic factory nor `TournamentRunner.run_match()` silently chooses FMA. The generic `run_match()` accepts an explicit adapter and instance, while `run_pilot()` currently supplies neither and raises. `SyntheticAdapter` is used by tests and the local security preflight, not by the current root/staged Kaggle Task. The package initializer eagerly imports both concrete adapters when importing `domain_adapters`; those adapters use the standard library, so this is unnecessary code coupling rather than an identified missing third-party dependency. The FMA metadata archive's exact license remains unresolved in the inventory report, relevant before packaging or hosted use.

## 4. Privacy, public identifiers, and replay

### Workspace implementation

- `validate_public_observation()` enforces exact top-level and nested schemas, UUID-shaped public entity identifiers, board/available-entity partitioning, legal-action consistency, and typed public history ([Phase 0](../phase0_foundation.py#L143)).
- `project_public_observation()` validates before allowlisted projection; `project_agent_observations()` additionally binds the private requester to `current_player`, checks that the embedded public observation matches, and projects only the expected private payload ([Phase 0](../phase0_foundation.py#L322), [agent projection](../phase0_foundation.py#L329)).
- `MatchSession.private_observation()` and `Phase0Controller.private_observation()` reject inactive-player requests ([session](../phase0_foundation.py#L1154), [controller](../phase0_foundation.py#L1363)). The normal runner asks for the current player; the Kaggle adapter serializes the projected observation only.
- Each match creates UUIDv4 public IDs, sorts that public order, and reuses the mapping in public observations, actions, history, and public audit ([UUID generation](../phase0_foundation.py#L1082), [mapping](../phase0_foundation.py#L1094)). Source entity IDs and internal piece IDs are not sent as public entity IDs. The restricted audit view contains both public-ID-to-piece and piece-to-public-ID mappings, plus feature ownership and engine replay/state ([audit construction](../phase0_foundation.py#L1220)).
- Replay-only validation now requires the exact engine-state field set and compares the replayed state, including explicit `result=None`, to the snapshot. Full audit validation independently checks exact public/restricted allowlists and their agreement with replay ([replay](../phase0_foundation.py#L624), [full validator](../phase0_foundation.py#L669)). Tests cover missing `starting_player`, missing `result`, unexpected fields, wrong types, inconsistent states, both modes, both starting players, and terminal win/draw cases ([tests](../tests/test_phase0_foundation.py#L324), [matrix](../tests/test_phase0_foundation.py#L369)).

**Provenance limit:** the session retains a source-ID-to-public-UUID mapping, but `get_read_only_audit_view()` serializes only the public-UUID/piece mappings, not the source-ID/public-UUID crosswalk. Evaluators can recover the internal piece mapping, but cannot fully map a saved public UUID back to an FMA source track from that snapshot alone. This is a restricted provenance gap, not a public leak.

### Phase 2 security audit

The current workspace `run_security_audit()` derives restricted strings and structures from the actual instance and restricted audit view, then checks the actual public observation, public audit, private observations, and generated Agent messages. Its recursive checker scans nested mappings/lists and string values, compares exact copied structures, and uses token boundaries to avoid flagging incidental substrings in public UUIDs. Missing restricted inputs fail the audit. Focused tests cover a sentinel in an allowed field, nested dictionary/list, public audit, and prompt, plus legitimate public identifiers/cells ([harness](../tournament_harness.py#L1081), [audit](../tournament_harness.py#L1222), [tests](../tests/test_tournament_harness.py#L406)).

The Phase 2 boundary is present in the workspace but **not** in the staged harness. The staged checker does not derive restricted values/structures for public observations or public audit and retains the older checker. The Kaggle Task also does not call `run_security_audit()`; if its fail-closed guard is later replaced, the Task needs an explicit preflight in addition to the per-call schema validation. The current code has no demonstrated leak; these are staging/integration gaps.

## 5. Kaggle Task and staging

### Task execution path

The current root Task resolves and checks the selected Task LLM and exact `kbench.llms` opponent identity, then checks source files and imports the adapter/runner ([model resolution](../kaggle_task/quarto_two_model_match.py#L577)). It unconditionally raises that a validated real dataset adapter instance is required ([fail-closed guard](../kaggle_task/quarto_two_model_match.py#L674)). The staged Task has the same fail-closed behavior. Neither current Task uses `SyntheticAdapter`.

Everything after the guard is unreachable. The post-guard code constructs clients and a `TournamentRunner`, but contains no `runner.run_match()` call; later it references `result` and `instance` without assignments ([root Task](../kaggle_task/quarto_two_model_match.py#L686)). Removing the raise alone would not create a working match. The Task currently cannot run a genuine two-model match.

There is also a future result-labeling defect in that unreachable block: it maps Gemini/Claude clients under existing `MODEL_TAGS` values for OpenCode DeepSeek and Gemma, then would publish those old tags as `harness_model_tags` ([harness tags](../tournament_harness.py#L39), [Task output](../kaggle_task/quarto_two_model_match.py#L756)). Exact `model_metadata` is separately recorded, but the harness assignment labels would still be misleading. The Task explicitly records that `llm.prompt()` is not interruptible through the Runner timeout ([Task](../kaggle_task/quarto_two_model_match.py#L743)).

### Staging integrity and parity

The stage manifest checksum is valid (`c14e9107…bf4bf2`); all 8 payload hashes, all 5 `domain_adapters.zip` member hashes, and the sidecar checksum match. The five adapter ZIP members also match the current workspace files. `requirements.txt` contains only `kaggle-benchmarks==0.6.2`; the project source and bundled adapters use the standard library plus that hosted SDK, so no additional third-party dependency omission was found.

Internal hash validity is not current-source parity:

| File | Workspace SHA-256 | Staged SHA-256 |
|---|---|---|
| Task | `fee22413127c3885bb8ab418bc10b8def6312753067ffdbc9c1eba640ff8e896` | `67951954334b96cb579831f21a8d97ba6f759467a049f2b3bb273bf235a9da4b` |
| `phase0_foundation.py` | `f1b74fc34c9ad979ca6523d91d52e2765746265a544a7275053057d2a70aed4c` | `2bf58d9fcdc4c0d1532e47c14decf1bd704cc822d7d8f87750ea97c4944e7279` |
| `tournament_harness.py` | `1870c5dd86786bf5b6f07e1f5f95bcbd36d82a205450165ff402d683357d050d` | `dda903c9ae7863d34c61a05deb3d92df8a2112cc54f0473bcbbad7264b310b16` |

The staged Phase 0 still permits inactive-player reads through `Phase0Controller.private_observation()` and retains the replay-only `starting_player` default (`state_snapshot.get("starting_player", "player_1")`); its full audit validator is stricter. The staged harness lacks current value-aware public/audit checks. Thus it does not carry the full workspace Phase 1/2 guarantees. The current root Task also fails its own packaged-source hash check if executed as a Python file against this stage; Notebook conversion may lack `__file__`, in which case exact executing-source verification is unavailable.

The staged manifest's validation section says a fake-model Task completed an 8-action synthetic match and lists prior test counts ([manifest](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json#L749)). The staged Task currently raises before any prompt or match, so that entry is historical evidence for an earlier source revision, not validation of the payload currently hashed. The manifest also excludes local data, including `data/fma_metadata.zip`; no real FMA instance source is packaged.

## 6. Test evidence

No tests or Task executions were run for this audit.

| Evidence | Command/result | Qualification |
|---|---|---|
| Retained `out.txt` (timestamp 2026-11-08) | `python -B -m unittest discover -s tests -v`; 54 tests in 4.991s, 50 passed, 4 errors, no skips reported. All four errors were in `test_phase1_qm9_adapter`, caused by `NameError: name 'feature_id' is not defined` in the then-current `QM9Adapter._validate_registry_rows`. | The output does not preserve the process exit code. This is an old run and not evidence of a current full-suite result; current source at the corresponding code has since changed. |
| Nov. 12 remediation report | Lists `python -m unittest tests.test_phase0_foundation tests.test_tournament_harness` and two selected Task tests as passing. | No exact counts, exit codes, runtimes, or raw output were retained. It does not establish that the current full Task test module passes. |
| Stage manifest | Claims prior offline fake-model counts: 7 Task, 13 Kaggle adapter, 2 metadata, and 16 runner tests; claims an 8-action synthetic Task smoke passed. | Historical fake-only evidence; inconsistent with the currently hashed fail-closed Task. |
| Prior Phase 1/2 session summary | Reports 25 Phase 0, 28 harness, and 19 Kaggle adapter tests passed. | No exact commands or retained run output in the repository; not independently verifiable here. |

Static inspection finds 10 Task test methods today. At least `test_failed_match_fails_the_task_run()` expects the fail-closed Task to issue a fake prompt, and `test_public_result_contains_no_private_decision_traces()` expects `_task_run.result` to be a successful match result ([Task tests](../tests/test_quarto_two_model_task.py#L306), [success-result test](../tests/test_quarto_two_model_task.py#L385)). Current Task code raises before those outcomes; these tests are inconsistent with the current guard and need reconciliation. This is a source-level contradiction, not a test result from this audit.

## 7. Ranked blockers and minimal implementation sequence

### Blockers

1. **BLOCKER — no FMA-backed match path (confirmed).** No stable accepted FMA instance is selected/persisted, and neither current `run_pilot()` nor the Kaggle Task supplies an adapter/instance to the runner.
2. **BLOCKER — Kaggle Task cannot execute a match (confirmed).** Both root and staged Task raise before inference; the remaining code is unreachable and lacks a match invocation and initialized `result`/`instance`.
3. **HIGH — deployable stage is stale (confirmed).** Its Phase 0 misses active-player and replay-only fixes; its harness misses Phase 2 checks; its source hashes differ from the workspace. Its manifest evidence is also stale relative to its fail-closed Task.
4. **HIGH — model attribution would be wrong (confirmed in unreachable code).** The current Gemini/Claude handles are assigned under old DeepSeek/Gemma harness tags. Live model identity/registry availability is not verified.
5. **HIGH — old pilot audit flags are not current-schema proof (confirmed).** Both saved snapshots omit `starting_player`; starting-player balance cannot be established.
6. **MEDIUM — Task tests and guard disagree (confirmed statically).** Two current tests require a successful/failing match prompt although the Task now fails closed before any prompt.
7. **MEDIUM — FMA evaluator provenance is incomplete (confirmed).** Restricted audit has public-ID/piece mappings but not the source-ID/public-ID crosswalk.
8. **MEDIUM — external inference privacy and timeout remain unverified.** Future prompts intentionally contain the active player's feature IDs; hosted provider retention is not established, and the adapter does not forward the Runner timeout to `llm.prompt()`.
9. **LOW — generic validation diagnostic is stale (confirmed).** `InstanceValidationError` still names QM9 despite capability-based validation.

### Minimum sequence before a real two-model test

1. Select an accepted FMA candidate explicitly and persist a reproducible `InstanceSpec` identity plus archive/sample/feature-pool/threshold provenance. Do not treat the inspected candidate as selected without a separate decision.
2. Wire an explicit adapter and validated instance into a runnable local match path. Run both starting-player assignments with fixed model identities; validate audit and replay using the current workspace validators. Resolve the restricted source-to-public mapping requirement if source-level evaluator traceability is needed.
3. Make the Kaggle Task construct/load that same explicit validated real instance and actually invoke the runner. Remove or restructure unreachable code only as part of this implementation; fix the player-to-model tags and reconcile the Task tests with the intended fail-closed/success path.
4. Copy the reviewed current Phase 0, harness, Task, and dependency closure into staging; refresh manifest/checksum together; verify byte/hash parity. Replace historical fake-smoke claims with evidence tied to the exact staged source.
5. Run bounded focused local tests for the FMA instance/controller, privacy/replay, and runner path; then run fake-model Task integration and verify the full public/restricted boundaries. Only after those pass should a separate, authorized hosted model smoke be considered.

## Scope and preservation statement

This audit did not edit source, tests, staging, manifests, archives, prior reports, or data. No test, model inference, Kaggle Task, upload, dependency installation, Git staging, commit, reset, checkout, clean, rebase, or branch switch occurred. The only intended file creation is this report; all pre-existing dirty worktree content was preserved.
