# Quarto FMA First Pilot: Independent Implementation and Security Review

**Review date:** 2026-11-14
**Scope:** Local source and current worktree only. No hosted Kaggle Task, live model, upload, or publication was run.

## Executive summary

The fixed pilot identity, strict two-count validation, runtime public-ID crosswalk boundary, archive digest check, static model assignment, no-synthetic-fallback Task path, staged-file parity, and attribution wording are supported by the code inspected. The current Task path checks the archive digest before constructing agent prompts.

The review found one **HIGH** and five **MEDIUM** findings. In particular, hosted Notebook source parity is reported as unverifiable but is not a Task gate; the privacy scan has a reproducible string-embedding false negative and only examines initial-state artifacts; and the advertised wall-clock deadline is not enforced around the Kaggle provider call. The fixed source IDs and signature assignment are also included in the staged source package, distinct from the per-match UUID crosswalk that remains restricted.

## Findings

### HIGH - The Task can proceed without verifying the executing Notebook source

**File and lines:** [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L406), [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L433), [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L668), [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L760)

**Evidence:** `_verify_task_source()` returns `status="not_verifiable_in_notebook"` with no executing-source hash when `__file__` is unavailable. `_run_quarto_two_model_match()` stores that result, imports the staged modules, and continues. The successful-match predicate checks completion, audit, replay, and terminal result, but not `task_source_integrity["status"]`.

**Impact:** In a Notebook-converted hosted Task, success does not establish that the executed Notebook corresponds to the reviewed Python Task source. This review did not inspect a hosted Task or its backing Notebook.

**Minimal remediation:** Require an independently recorded hash/attestation for the exact backing Notebook source and fail closed unless it matches the reviewed Task source. Do not treat `not_verifiable_in_notebook` as verified parity.

### MEDIUM - Snapshot checks establish internal consistency, not source authenticity

**File and lines:** [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L306), [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L326), [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L382), [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L668)

**Evidence:** `_validate_source_snapshot()` verifies the manifest against its adjacent `manifest.sha256` and payloads against digests in that same manifest. There is no independent trusted manifest digest or signature. A replacement package can be internally re-hashed and then accepted. In addition, an invalid `QUARTO_SOURCE_SNAPSHOT_ROOT` does not cause immediate failure; resolution continues to other candidates.

**Impact:** The checks detect accidental corruption and inventory drift, but do not authenticate the snapshot against a trusted release. Since the Task adds the accepted root and adapter ZIP to `sys.path`, modified Python modules from an accepted package can be imported.

**Minimal remediation:** Pin or sign the expected manifest digest outside the source snapshot, verify it before imports, and fail immediately when an explicitly configured root is invalid.

### MEDIUM - The staged package contains source track IDs and their signature assignment

**File and lines:** [fma_pilot_instance.json](../fma_pilot_instance.json#L29), [fma_pilot_instance.json](../fma_pilot_instance.json#L47), [fma_pilot.py](../fma_pilot.py#L36), [manifest.json](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json#L69)

**Evidence:** The staged `fma_pilot_instance.json` is an included payload and contains all 16 FMA track IDs in signature order and the matching signature values `0..15`. `fma_pilot.py` also hardcodes the same source ID list.

**Impact:** Readers of the source package can learn the fixed FMA sample membership and each source track's pilot signature. This is not the same as exposing the per-match public-UUID-to-source-ID crosswalk: that crosswalk is still written only to restricted evaluator data, and the Task result/prompt projection inspected here uses opaque public UUIDs. Whether the static membership itself is intended to be public is not specified.

**Minimal remediation:** If source membership and signatures are meant to remain restricted, keep them in a controlled runtime input and package only a commitment or non-revealing validation artifact. If public membership is intentional, document that exception separately from the restricted crosswalk guarantee.

### MEDIUM - Restricted values embedded in strings can evade the privacy scan

**File and lines:** [tournament_harness.py](../tournament_harness.py#L1107), [tournament_harness.py](../tournament_harness.py#L1118), [tournament_harness.py](../tournament_harness.py#L1125)

**Evidence:** `contains_token()` requires both boundaries around a restricted string and treats underscore as a word character. A local deterministic probe passed `{"label": "track_53194_hidden"}` with `"53194"` forbidden to `recursive_privacy_check()`; it returned no finding.

**Impact:** An exact FMA track ID embedded inside an otherwise permitted string or serialized identifier can evade this value-based check. The boundary rule reduces substring false positives but does not detect every copied restricted value.

**Minimal remediation:** Use field-aware checks for values that can contain restricted identifiers, with an explicit representation/encoding strategy for serialized artifacts. Preserve false-positive protection and keep diagnostics generic so they do not print the restricted value.

### MEDIUM - Security preflight checks only initial-state observations and prompts

**File and lines:** [tournament_harness.py](../tournament_harness.py#L1294), [tournament_harness.py](../tournament_harness.py#L1300), [tournament_harness.py](../tournament_harness.py#L1302), [tournament_harness.py](../tournament_harness.py#L1316), [tournament_harness.py](../tournament_harness.py#L1406)

**Evidence:** `run_security_audit()` constructs a fresh controller for each starting player and builds prompts without submitting any action. It therefore scans initial select-phase observations and audit snapshots only; it does not scan a post-selection place prompt, a post-placement select prompt, or a terminal public artifact. The current exact-signature list includes integers `0..15` (`tournament_harness.py:1371-1375`), which overlap with legitimate public placement-cell indices, so simply adding later-phase scans would also require context-aware comparisons.

**Impact:** The preflight does not exercise all public artifacts produced over a real match and cannot substantiate equivalent leak coverage for state-dependent or later-phase serialization. No concrete leak in the normal phase transition path was established by this static review.

**Minimal remediation:** Exercise representative select, place, post-placement, and terminal states through the actual projection/prompt path, with schema- and field-aware treatment of internal piece signatures versus public cell numbers.

### MEDIUM - The configured model deadline is not enforced after a response

**File and lines:** [kaggle_agent_adapter.py](../kaggle_agent_adapter.py#L28), [kaggle_agent_adapter.py](../kaggle_agent_adapter.py#L47), [tournament_harness.py](../tournament_harness.py#L629), [tournament_harness.py](../tournament_harness.py#L641), [tournament_harness.py](../tournament_harness.py#L1007), [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L760)

**Evidence:** The Runner passes the remaining time to `client.chat()`, but `_KagglePromptClient.chat()` ignores its `timeout` parameter and calls `llm.prompt()` without a timeout. `AgentAdapter.get_decision()` checks the deadline before the call but not after it. After a delayed response, the Runner may still submit the action and mark a terminal next observation completed; the Task's success predicate does not check elapsed time. The Task result itself discloses that provider calls are not interruptible.

A local fake-client probe used a deadline 0.03 seconds ahead and returned after a 0.10-second sleep. `get_decision()` accepted the action about 0.07 seconds after the deadline.

**Impact:** A blocking provider request can exceed the 900-second match limit. In particular, a late final action can be treated as a completed match rather than a timeout; hosted runtime termination behavior was not tested.

**Minimal remediation:** Use a provider/API timeout or cancellation mechanism, re-check the deadline immediately after every model response and before action submission, and reject any terminal result completed after the configured deadline.

## Confirmed controls and implementation evidence

| Area | Review result |
|---|---|
| Approved instance | `fma_seed11_candidate_ordinal_0003_v1` is bound to the exact 16 source IDs and signature permutation `0..15` in the artifact and loader. `load_fma_pilot()` recomputes the instance from the loaded domain and checks the signature map. See [fma_pilot.py](../fma_pilot.py#L134) and [fma_pilot.py](../fma_pilot.py#L179). |
| Strict two-count acceptance | The loader rejects unless the actual validation reports `accepted is True`, `id_level_count == 2`, and `structural_count == 2`. See [fma_pilot.py](../fma_pilot.py#L216). The separate generic controller check allows counts greater than one, but the fixed Task path first goes through this exact-two loader. |
| Opaque-ID crosswalk | `MatchSession` creates UUIDv4 public IDs per session and stores the source mapping in `public_entity_to_source_id` only in restricted evaluator data. Public observation and audit builders use public UUIDs. See [phase0_foundation.py](../phase0_foundation.py#L1117), [phase0_foundation.py](../phase0_foundation.py#L1255), and [phase0_foundation.py](../phase0_foundation.py#L1320). The staged artifact disclosure is separately recorded above. |
| FMA data and archive | The adapter checks SHA-256 `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265` before reading archive contents and binarizes with `value > threshold`. See [fma_adapter.py](../domain_adapters/fma_adapter.py#L20), [fma_adapter.py](../domain_adapters/fma_adapter.py#L277), and [fma_adapter.py](../domain_adapters/fma_adapter.py#L285). The adapter reads `tracks.csv` and `features.csv`, retains descriptive track metadata in memory, and marks audio files unused. |
| Task preflight and fallback | The Task requires the license acknowledgment and an explicitly mounted archive, invokes `load_fma_pilot()` and the security preflight before constructing the Runner and issuing agent prompts, and has no SyntheticAdapter fallback in this path. The default synthetic option in `run_security_audit()` is not used because the Task supplies the real adapter and instance. See [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L684) and [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L699). |
| Model identity mapping | The Task checks the selected model identity and exact unique registry entry, then assigns the selected Gemini and configured Claude handles to distinct player tags. This is code-level validation only; hosted registry identities and actual model calls were not verified. See [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L583) and [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L713). |
| Prompt and public-result boundary | `AgentAdapter.build_messages()` uses `project_agent_observations()` and serializes only the public projection plus the authorized private payload. The Task constructs its result from public replay/model metadata and does not include the restricted match log or private trace. See [tournament_harness.py](../tournament_harness.py#L572) and [quarto_two_model_match.py](../kaggle_task/quarto_two_model_match.py#L779). |
| Attribution | Root and staged notices describe the four selected columns, thresholding, no MP3/Echonest use, and the audit's **CONDITIONALLY CONFIRMED** status without claiming definitive commercial clearance. See [FMA_ATTRIBUTION.md](../FMA_ATTRIBUTION.md#L5) and [staged ATTRIBUTION.md](../kaggle_dataset_staging/quarto-two-model-source-v1/ATTRIBUTION.md#L5). |

## Validation and scope

- Worktree at review start: branch `main`, HEAD `fc7e5d355162c81c267eb3d02462539bc2283113`; dirty tracked and untracked files were present and preserved.
- Local archive SHA-256 matched the pinned value above.
- Staging check: manifest sidecar valid; all 11 payload hashes and declared sizes valid; eight source files byte-identical to their workspace counterparts; all five adapter ZIP members byte-identical; `fma_metadata.zip` absent from staging.
- `git diff --check` passed.
- The two deterministic local probes described in the findings ran without a real model or hosted Task.
- No unit-test suite was run for this review. Prior implementation reports and passing tests were treated as supporting context, not proof of correctness.
- No source/implementation file was modified. This report is the only file created for this review. No dependency installation, Git mutation, upload, publication, live model call, or hosted execution occurred.

## Remaining uncertainty

The staged source audience, confidentiality status of the fixed FMA membership, and actual Kaggle Notebook conversion/runtime behavior are not established by this local review. Neither the configured Kaggle model registry nor provider timeout/cancellation semantics were tested in a hosted environment. The FMA rights conclusion remains **CONDITIONALLY CONFIRMED**, not legal approval.
