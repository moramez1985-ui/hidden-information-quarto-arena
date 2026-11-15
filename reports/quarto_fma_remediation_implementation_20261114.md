# Quarto FMA Pilot — Minimal Technical Remediation

**Date:** 2026-11-14
**Scope:** Local code and offline tests only. No hosted Kaggle Task, live model, upload, or publication was run.

## Outcome

| Finding | Classification | Result |
|---|---|---|
| 1. Notebook-converted Task source integrity | `PARTIALLY_MITIGATED` | Unverifiable execution now fails before preflight or prompts. The actual Kaggle-executed Notebook still has no independent local attestation. |
| 2. Snapshot authenticity and configured root | `BLOCKED_EXTERNALLY` | Invalid explicit roots fail closed and are covered by regression tests. Snapshot authenticity remains unproven without an independently delivered trust anchor. |
| 3. Static source-ID visibility | `UNCHANGED_PENDING_OWNER_DECISION` | The approved static membership and signature assignment remain in the staged package, as required. The owner must decide whether they are public or restricted. |
| 4. Restricted values embedded in strings | `FIXED_LOCALLY` | Recursive, representation- and field-aware scanning now catches embedded IDs, including raw serialized prompt text, while preserving valid public cell positions. |
| 5. Security preflight phase coverage | `FIXED_LOCALLY` | The real approved FMA pilot preflight exercises all five required phases through observation, projection, validation, prompt, and terminal replay paths. |
| 6. Late provider responses | `PARTIALLY_MITIGATED` | Late responses/actions are rejected locally. A blocking provider call may still overrun the deadline because no supported cancellation mechanism was verified. |

## Finding-by-finding results

### 1. Notebook-converted Task source integrity — `PARTIALLY_MITIGATED`

`_verify_task_source()` continues to compare the packaged Python source and the executing `.py` source with the staged manifest. If `__file__` does not identify a matching `.py` source file, it now raises instead of returning `not_verifiable_in_notebook`; the Task therefore fails before preflight or prompts. The final success predicate also requires `task_source_integrity["status"] == "verified"` ([Task source](../kaggle_task/quarto_two_model_match.py#L413), [success predicate](../kaggle_task/quarto_two_model_match.py#L757)).

The local positive path is exercised by the fake Task test with an executing `.py` file. The negative Notebook-style test removes `__file__` and confirms failure with zero additional fake prompts ([Task tests](../tests/test_quarto_two_model_task.py#L273)). This closes the unsafe local fallthrough, but does **not** attest the exact Notebook code Kaggle may execute after conversion. No such hosted source identity or external attestation was available or tested. Do not treat packaged Python hash verification as proof of executed Notebook parity.

### 2. Snapshot authenticity and configured root — `BLOCKED_EXTERNALLY`

The snapshot payload, inventory, and adjacent `manifest.sha256` checks remain intact ([snapshot validation](../kaggle_task/quarto_two_model_match.py#L313), [root resolution](../kaggle_task/quarto_two_model_match.py#L389)). A non-empty invalid `QUARTO_SOURCE_SNAPSHOT_ROOT` aborts through validation rather than falling through; a new regression test covers this behavior, and the existing unset-root test still verifies the documented default ([Task tests](../tests/test_quarto_two_model_task.py#L286)).

These checks establish consistency/corruption detection only. The sidecar is stored with the package and is not an independent trust anchor. No trusted external digest, signing key, release attestation, or delivery channel was invented or found. Authenticity remains externally blocked until a trust anchor bound to the reviewed Task source is independently supplied and verified.

### 3. Static source-ID visibility — `UNCHANGED_PENDING_OWNER_DECISION`

The staged package still includes [fma_pilot_instance.json](../fma_pilot_instance.json#L29), which contains the approved 16 source track IDs in `entity_ids_signature_order` and their assignment to signatures `0..15` in `signature_values_signature_order` ([signature list](../fma_pilot_instance.json#L47)). [fma_pilot.py](../fma_pilot.py#L36) also retains the fixed approved source-ID list. These files and their content were not changed or relocated.

This static membership disclosure is distinct from the per-match UUID crosswalk. The crosswalk remains in restricted evaluator data and is not added to public observations or the Task result ([Phase 0 crosswalk construction](../phase0_foundation.py#L1321)). Whether the fixed membership and ID-to-signature assignment are intended to be public is still an owner decision. If restricted, the project needs a genuinely access-controlled runtime input and verified access controls; moving the same data to another package file would not provide confidentiality.

### 4. Restricted values embedded in strings — `FIXED_LOCALLY`

`recursive_privacy_check()` now recognizes underscore-delimited restricted identifiers such as `track_53194_hidden`, traverses nested mappings/sequences, and uses field-aware handling for exact signature values. It exempts valid integer cell positions `0..15` only in public history and legal-cell paths, and permits the public replay schema version; it does not globally exempt those integers in signature-bearing fields. `_prompt_privacy_findings()` scans the actual serialized message content for restricted string identifiers and also validates/scans the decoded prompt payload. Findings remain generic (`forbidden_value`, `forbidden_structure`, etc.) and do not echo the restricted value ([scanner](../tournament_harness.py#L1120), [serialized prompt scan](../tournament_harness.py#L1301)).

Focused tests cover underscore-embedded IDs, nested values, duplicate-key serialized prompt leakage, public audit leakage, generic diagnostics, legitimate public cells, ordinary UUIDs, and signature-bearing fields ([privacy tests](../tests/test_tournament_harness.py#L415), [cell/signature tests](../tests/test_tournament_harness.py#L621)).

### 5. Security preflight phase coverage — `FIXED_LOCALLY`

`run_security_audit()` now runs deterministic traces over the supplied adapter and fixed instance. For each nonterminal state it obtains the observation through `Phase0Controller`, runs the existing public/private projection and validation, builds messages through `AgentAdapter.build_messages()`, and scans the observations, public audit, private payload, and serialized prompt. It covers initial select, post-selection place, post-placement select, win terminal, and draw terminal. Terminal states do not generate prompts or fabricated legal actions.

The Task passes its actual public replay projection plus validator into the audit, rather than a parallel Task-specific approximation ([audit phase coverage](../tournament_harness.py#L1342), [Task replay projector](../kaggle_task/quarto_two_model_match.py#L306), [Task preflight call](../kaggle_task/quarto_two_model_match.py#L703)). The fixed traces use win signatures `[0, 2, 4, 6]` at cells `[0, 1, 2, 3]` and the specified 16-piece draw order. The existing engine reports the draw as terminal with a full board and no winning line; the audit records this invariant without changing [quarto_engine.py](../quarto_engine.py).

The actual FMA-adapter test verifies all five phases, that projection occurs in select/place/terminal states, and that prompts are built only for nonterminal select/place states ([FMA pilot test](../tests/test_fma_pilot.py#L95)). A Task-level test verifies that the Task's validated public replay projector is supplied and accepts both terminal outcomes ([Task tests](../tests/test_quarto_two_model_task.py#L304), [terminal replay test](../tests/test_quarto_two_model_task.py#L330)).

### 6. Late provider responses — `PARTIALLY_MITIGATED`

`AgentAdapter.get_decision()` rechecks the deadline immediately after a provider response returns and rejects a late response. `TournamentRunner.run_match()` checks again immediately before submitting the action; a late action cannot be accepted or produce `status == "completed"` ([post-response check](../tournament_harness.py#L645), [pre-submit check](../tournament_harness.py#L947)). Fake-client tests cover a response returned late, expiration between decision receipt and submission, and existing in-budget acceptance ([adapter test](../tests/test_kaggle_agent_adapter.py#L126), [Runner test](../tests/test_tournament_harness.py#L673)).

This is late-response rejection, **not hard interruption or cancellation**. The selected Kaggle SDK/backend timeout behavior was not demonstrably available locally, and no provider-specific timeout argument was added. The Task result and staging manifest now state that late responses are rejected but a blocking `llm.prompt()` call may overrun the 900-second wall-clock deadline until it returns ([Task timeout disclosure](../kaggle_task/quarto_two_model_match.py#L788), [staging manifest](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json#L721)).

## Preserved invariants and boundaries

- The approved instance remains `fma_seed11_candidate_ordinal_0003_v1`, with the same 16 source IDs, four features, thresholds, and signature assignment. The loader's strict acceptance rule remains `accepted is True`, `id_level_count == 2`, and `structural_count == 2`.
- Gemini remains Player 1 and Claude remains Player 2. Registry availability is unverified.
- Quarto Core and `quarto_engine.py` were not changed. The existing dirty `starting_player` and replay changes were preserved.
- Public observation, prompt, and Task result schemas were not expanded. Internal security-check details and the existing timeout limitation text were updated; the Task result retains its existing timeout fields.
- The FMA archive hash pin remains unchanged, and `fma_metadata.zip` remains excluded from the staging payload.
- The license gate was not approved or changed. The Task tests use only a local fake SDK/model fixture that temporarily sets the acknowledgment within the test process; no persistent environment setting was made.

## Files changed

- [tournament_harness.py](../tournament_harness.py)
- [kaggle_task/quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py)
- [tests/test_tournament_harness.py](../tests/test_tournament_harness.py)
- [tests/test_fma_pilot.py](../tests/test_fma_pilot.py)
- [tests/test_kaggle_agent_adapter.py](../tests/test_kaggle_agent_adapter.py)
- [tests/test_quarto_two_model_task.py](../tests/test_quarto_two_model_task.py)
- [kaggle_dataset_staging/quarto-two-model-source-v1/tournament_harness.py](../kaggle_dataset_staging/quarto-two-model-source-v1/tournament_harness.py)
- [kaggle_dataset_staging/quarto-two-model-source-v1/quarto_two_model_match.py](../kaggle_dataset_staging/quarto-two-model-source-v1/quarto_two_model_match.py)
- [kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json)
- [kaggle_dataset_staging/quarto-two-model-source-v1/manifest.sha256](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.sha256)
- This report.

No changes were made to `phase0_foundation.py`, `quarto_engine.py`, `fma_pilot.py`, or `fma_pilot_instance.json`.

## Validation

All commands below were local and offline:

| Command | Result |
|---|---|
| `python -B -m unittest discover -s tests -p "test_tournament_harness.py"` | 33 passed |
| `python -B -m unittest discover -s tests -p "test_fma_pilot.py"` | 5 passed |
| `python -B -m unittest discover -s tests -p "test_kaggle_agent_adapter.py"` | 20 passed |
| `python -B -m unittest discover -s tests -p "test_quarto_two_model_task.py" -v` | 14 passed |
| Staging integrity check | Manifest JSON and sidecar valid; all 11 payload hashes/sizes and all 5 adapter archive-member hashes verified; Task and harness copies byte-identical to workspace sources; FMA metadata archive absent. |
| `git diff --check` | Passed |

The Task test suite uses fake Kaggle/model handles; passing it does not verify Kaggle-hosted Notebook conversion, registry availability, hosted access controls, or provider cancellation. No dependencies were installed, no model was called, no hosted Task was run, no upload/publication occurred, and no Git mutation was made. Existing dirty worktree changes were preserved.

## Remaining blockers and decisions

1. **Executed Notebook identity:** independent evidence binding the exact Notebook Kaggle runs to reviewed source is still required.
2. **Snapshot authenticity:** provide a trusted digest/signature outside the snapshot and bind it to reviewed Task source; the adjacent sidecar is not sufficient.
3. **Static pilot membership:** the project owner must decide whether fixed source membership and signatures are public or require verified access control.
4. **Hard deadline:** verify a real timeout/cancellation mechanism for the exact hosted provider handles if a strict wall-clock bound is required.
5. **Rights clearance and model availability:** this remediation does not change the conditional FMA rights position or verify hosted model registry availability.
