# Quarto FMA Pilot — Minimal Remediation Plan

**Date:** 2026-11-14

**Scope:** Planning only; no implementation changes.

## Assessment basis

The six findings were compared with the current worktree and the latest readiness assessment. The worktree remains on `main` at `fc7e5d355162c81c267eb3d02462539bc2283113`. It was already dirty: `phase0_foundation.py` and `quarto_engine.py` have tracked changes, while the pilot, Task, harness, adapter, staging package, and several tests are untracked. I inspected the relevant tracked diffs and current untracked source; untracked files have no committed-base diff to compare. The plan does not overwrite or reinterpret those changes.

The current engine diff adds `starting_player` to game state and replay handling. The current Phase 0 diff adds strict observation projection and restricted source-ID audit data. Neither needs a change for these findings. The plan preserves those behaviors and does not modify `quarto_engine.py`.

Two local probes were run without a model or Task: an underscore-embedded FMA ID was missed by the privacy scanner, and a fake client returning after a short deadline had its action accepted. No Kaggle Task, live model, hosted runtime, or package installation was used. The pinned Kaggle SDK package is not installed locally. Its versioned public source was inspected: `LLMChat.prompt` has provider-specific `extra_api_params`, but no universal timeout/cancellation argument; backend handling differs. The actual types and capabilities of the hosted model handles remain unverified. Connected Qodo search found no indexed repository matching `quarto`, and the applicable rules searches returned no rules; this plan therefore relies on local source and the two supplied project reports, not remote history.

## Findings and proposed corrections

### 1. HIGH — Notebook-converted Task source integrity

**Reproduction status: Reproduced locally; actual hosted Notebook parity remains unverified.**

`_verify_task_source()` compares the packaged `.py` file with the snapshot manifest when `__file__` identifies a Python file. Otherwise it returns `not_verifiable_in_notebook` ([Task source](../kaggle_task/quarto_two_model_match.py#L406)). `_run_quarto_two_model_match()` records that status and proceeds ([Task source](../kaggle_task/quarto_two_model_match.py#L668)); the success predicate checks the match, audit, replay, and terminal result, but not source-integrity status ([Task source](../kaggle_task/quarto_two_model_match.py#L760)). The existing unit test explicitly exercises the no-`__file__` case and expects `not_verifiable_in_notebook` ([Task tests](../tests/test_quarto_two_model_task.py#L259)).

**Smallest safe correction:** Require a positive, independently verifiable attestation for the exact Notebook code that Kaggle executes, and make absence, mismatch, or an unverifiable status fail before imports, prompts, or match execution. Do not equate a verified packaged `.py` file with a verified converted Notebook. Keep the existing `.py` hash comparison for non-Notebook execution.

**Files/functions:** `kaggle_task/quarto_two_model_match.py` — `_verify_task_source()` and `_run_quarto_two_model_match()`; the synchronized staged Task copy and its manifest; `tests/test_quarto_two_model_task.py`.

**Regression tests:** Positive: matching reviewed Python and independently attested Notebook hashes pass. Negative: missing attestation, mismatching Notebook hash, and `not_verifiable_in_notebook` fail before any fake prompt or import-dependent match path. Retain the existing `.py` mismatch rejection and no-fallback assertions.

**Resolution boundary:** The local code can enforce a supplied attestation and fail closed. It cannot independently attest the Notebook Kaggle actually executes unless Kaggle exposes that executed source/hash or the release process supplies a verifiable binding. If neither mechanism exists, the Task must remain blocked or use an execution mode where the reviewed script itself is verifiable; local source hashing alone cannot close this finding.

### 2. MEDIUM — Snapshot authenticity and configured-root handling

**Reproduction status: Partly reproduced.** The authenticity gap remains. The reported configured-root fallthrough is **not reproducible in the current code**.

`_validate_source_snapshot()` compares `manifest.json` to its adjacent `manifest.sha256`, then checks payloads against that manifest ([Task source](../kaggle_task/quarto_two_model_match.py#L306)). There is no digest or signature anchored outside the snapshot. Someone able to replace the package can recompute both the manifest and sidecar, so these checks detect accidental corruption and inconsistency, not authenticity against a trusted release.

For a non-empty `QUARTO_SOURCE_SNAPSHOT_ROOT`, `_resolve_source_root()` calls `_validate_source_snapshot()` directly and does not catch its errors ([Task source](../kaggle_task/quarto_two_model_match.py#L382)). That validator returns `True` on success and raises on invalid or unreadable input; it has no `False` path. Thus an invalid explicit root currently aborts rather than falling through to defaults. Preserve this fail-closed behavior and add a regression test for it; no root-resolution code change is indicated by this finding.

**Smallest safe correction:** Verify the manifest against a digest or signature supplied by a trusted source outside the snapshot, before adding the snapshot or adapter archive to `sys.path` or importing modules. Keep existing sidecar, inventory, and payload checks as corruption/drift checks. Do not treat a digest stored only alongside the manifest as an independent trust anchor.

**Files/functions:** `kaggle_task/quarto_two_model_match.py` — `_validate_source_snapshot()` and `_resolve_source_root()`; staged release metadata/manifest; `tests/test_quarto_two_model_task.py`.

**Regression tests:** Positive: the approved snapshot with its trusted anchor and payload hashes passes. Negative: a mutated manifest with a recomputed adjacent sidecar, and rehashed modified payloads, fail the independent anchor check before import. Also assert that an explicitly configured invalid root raises immediately and does not select a default candidate; assert that an unset root can still resolve the documented default.

**Resolution boundary:** Corruption checks are local. Authenticity requires a trusted digest/signing key or release attestation delivered independently of the snapshot and itself bound to verified Task code. No such external trust source is established by the current local package, so full authenticity is not achieved by changing the sidecar alone.

### 3. MEDIUM — Static source IDs and signature assignment in the staged package

**Reproduction status: Reproduced.**

The staged manifest lists `fma_pilot_instance.json` as a payload ([manifest](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json#L52), [entry](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json#L74)). That JSON contains the 16 IDs in signature order and signature values `0..15` ([instance artifact](../fma_pilot_instance.json#L29), [signature list](../fma_pilot_instance.json#L47)). `fma_pilot.py` duplicates the approved IDs in `_EXPECTED_SOURCE_IDS` and validates the artifact against them ([pilot loader](../fma_pilot.py#L36), [artifact validation](../fma_pilot.py#L92)). This reveals fixed sample membership and each ID's signature to anyone who can read the staged package. It does **not** show that the per-match public-UUID/source-ID crosswalk is emitted publicly: Phase 0 stores that mapping in restricted evaluator data ([Phase 0 audit view](../phase0_foundation.py#L1255)); public observations continue to use per-match opaque UUIDs ([public projection source](../phase0_foundation.py#L1153)).

**Smallest safe correction:** First classify whether fixed membership and ID-to-signature assignment are intended to be public. If restricted, remove both the JSON literals and `_EXPECTED_SOURCE_IDS` from the distributable package and load the unchanged approved definition from an access-controlled runtime input. Update the loader, Task input path, staged inventory, and checksums without reselection or reconstruction of a different candidate. Keep the generated public UUID crosswalk restricted. If membership is intentionally public, make that exception explicit in the package visibility/access documentation; no ID-removal code change is warranted.

**Public-versus-restricted consequence:** Public membership allows package readers to identify the 16 source tracks and infer their pilot signature mapping, which may aid reconstruction or targeted analysis; it does not reveal the independently generated per-match UUID crosswalk. Restricted membership requires the IDs and assignment to stay out of any package visible to unauthorized readers. The package's actual audience/access controls are not proven by this worktree, so the confidentiality policy must not be inferred from the word “staging.”

**Files/functions:** If restricted: `fma_pilot.py` — constants, `_read_instance_artifact()`, `load_fma_pilot()`; `fma_pilot_instance.json`; `kaggle_task/quarto_two_model_match.py` — runtime input resolution; staging manifest/build files; `tests/test_fma_pilot.py` and Task tests.

**Regression tests:** Negative: scan every staged payload and adapter archive member for the approved source-ID literals and ID/signature pairs when membership is classified restricted; verify no public result, prompt, or public audit adds the crosswalk. Positive: load the same fixed instance from the controlled input and assert the unchanged instance ID, all 16 IDs, four feature definitions and thresholds, exact signature map, and strict `accepted=True`, `id_level_count == 2`, `structural_count == 2`.

**Resolution boundary:** Package changes are local; whether a runtime input is actually restricted depends on the selected Kaggle dataset/secret access controls and intended audience. Without verified access controls, moving the JSON to another staged file does not establish confidentiality.

### 4. MEDIUM — Restricted values embedded in strings

**Reproduction status: Reproduced.**

`recursive_privacy_check()` uses `contains_token()` and treats underscores as word characters in both boundary checks ([scanner](../tournament_harness.py#L1107), [token boundaries](../tournament_harness.py#L1118)). The local probe `{"label": "track_53194_hidden"}` with `"53194"` forbidden returned no finding. A direct scan also showed that banning exact integers `0..15` flags a legitimate public history cell index (`cell: 0`); the current audit passes those signature integers into `forbidden_exact_values` ([signature setup and checks](../tournament_harness.py#L1371), [public scan call](../tournament_harness.py#L1406)).

**Smallest safe correction:** Make restricted-value matching representation- and path-aware. For restricted FMA IDs in strings, treat the ID as an identifier token even when surrounded by underscores; inspect parsed prompt JSON and public artifacts recursively, and inspect raw serialized output only with the same explicit token policy. Keep diagnostics generic. For low-entropy piece signatures, distinguish piece-signature-bearing fields from legitimate public cell positions; do not globally ban integers `0..15` in public history or legal-cell fields.

**Files/functions:** `tournament_harness.py` — `recursive_privacy_check()`, `_prompt_privacy_findings()`, and `run_security_audit()`; `tests/test_tournament_harness.py` and `tests/test_fma_pilot.py`.

**Regression tests:** Negative: source ID embedded as `track_<id>_hidden`; restricted values in nested dictionary/list values, public audit, and the actual serialized prompt path. Positive: ordinary UUIDs/metadata and all legitimate public cell values `0..15` in history and legal actions pass. Also assert failure diagnostics never include the restricted value.

**Invariants:** Keep strict public schema validation and allowlisted projections. Do not weaken field validation or treat all substring coincidences as leaks. Keep public cell numbers intact and keep the source-ID crosswalk out of public artifacts.

**Resolution boundary:** Fully addressable locally, subject to focused tests against actual projection and serialization outputs.

### 5. MEDIUM — Security preflight covers only initial state

**Reproduction status: Reproduced as a coverage gap.**

`run_security_audit()` creates fresh controllers for each starting player and builds initial observations and prompts without submitting an action ([audit setup](../tournament_harness.py#L1267), [first prompt](../tournament_harness.py#L1302), [second prompt](../tournament_harness.py#L1316)). Its public-observation and public-audit scans therefore see the initial select phase, not later phase or terminal artifacts ([public scans](../tournament_harness.py#L1406)). The existing actual-FMA test exercises that preflight and full matches, but does not show that the preflight scans later-phase prompts/artifacts ([pilot test](../tests/test_fma_pilot.py#L92)).

**Smallest safe correction:** Extend the audit with a small deterministic state walk using the supplied adapter and approved instance. At every nonterminal state, obtain the active player's observations through `Phase0Controller`, run the existing validators/projection, and build the actual `AgentAdapter` messages with a no-op client. Scan the public observation, projected audit, and serialized prompt. At terminal states, scan the public observation/audit and replay projection; do not fabricate an agent prompt for a state where no action is legal. Keep this in the harness/pilot boundary, not the Quarto engine.

Use the approved signature mapping to create deterministic traces: a win by placing signatures `[0, 2, 4, 6]` in cells `0..3`; a full-board draw can use piece-by-cell order `[12, 0, 11, 5, 13, 10, 2, 1, 8, 14, 7, 6, 3, 15, 4, 9]`, which the current engine reports has no winning line. These are test traces over the fixed instance, not new candidates or mappings.

**Files/functions:** `tournament_harness.py` — `run_security_audit()` and a narrowly scoped state-artifact helper if needed; likely tests in `tests/test_fma_pilot.py` or `tests/test_tournament_harness.py`. Do not change `quarto_engine.py` or the public observation/result schema.

**Regression tests:** Assert coverage of initial select, post-selection place, post-placement select, win-terminal, and draw-terminal states. For each nonterminal phase, assert prompt creation passed through `AgentAdapter.build_messages()` and `project_agent_observations()` with the active requester. For both terminal outcomes, assert public observation, audit, and replay projections are scanned. Include legitimate public cell indices `0..15` as non-leaks (finding 4).

**Invariants:** Use the real FMA adapter and exact approved instance in the Task preflight; keep synthetic defaults test-only. Preserve legal actions, active-player authorization, UUID projection, exact-two acceptance, and the engine's existing state transitions.

**Resolution boundary:** Fully testable locally with deterministic no-op/fake clients; no hosted capability is required for this coverage correction.

### 6. MEDIUM — Late provider response accepted after deadline

**Reproduction status: Reproduced locally with a fake blocking client.** A client slept 0.08 seconds against a deadline 0.02 seconds away; `AgentAdapter.get_decision()` returned an accepted action after the deadline.

**Current path:** The Kaggle wrapper's protocol exposes only `prompt(prompt: str)` and `_KagglePromptClient.chat()` calls `self.llm.prompt(prompt)` without forwarding its `timeout` ([adapter protocol and call](../kaggle_agent_adapter.py#L11), [prompt call](../kaggle_agent_adapter.py#L49)). `AgentAdapter.get_decision()` checks remaining time before the call but not after it ([decision path](../tournament_harness.py#L614), [pre-call check](../tournament_harness.py#L630), [provider call](../tournament_harness.py#L641)); `TournamentRunner.run_match()` checks at the top of the action loop, then submits the returned action without a fresh deadline check ([runner](../tournament_harness.py#L879), [loop check](../tournament_harness.py#L921), [action submission](../tournament_harness.py#L938)).

The manifest pins `kaggle_benchmarks==0.6.2` but says it is supplied by the hosted runtime ([manifest SDK entry](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json#L689), [requirements](../kaggle_dataset_staging/quarto-two-model-source-v1/requirements.txt)). The SDK source at the manifest's cited commit exposes `LLMChat.prompt(..., extra_api_params=...)`, not a universal timeout/cancel parameter ([SDK `llms.py`](https://github.com/Kaggle/kaggle-benchmarks/blob/5ffefc57696e26b172fc3626392731ebecbb1195/src/kaggle_benchmarks/actors/llms.py)). The OpenAI backend passes extra kwargs to its API call ([`proxy_openai.py`](https://github.com/Kaggle/kaggle-benchmarks/blob/5ffefc57696e26b172fc3626392731ebecbb1195/src/kaggle_benchmarks/actors/proxy_openai.py)); the Google GenAI backend converts them into a `GenerateContentConfig` before calling `generate_content` ([`proxy_genai.py`](https://github.com/Kaggle/kaggle-benchmarks/blob/5ffefc57696e26b172fc3626392731ebecbb1195/src/kaggle_benchmarks/actors/proxy_genai.py)). This indicates a possible backend-specific timeout route, not a verified timeout or cancellation for either actual hosted model handle.

**Smallest safe correction:** Always reject a response if the deadline has expired when it returns, and recheck immediately before the Runner submits its action. This locally prevents a late response from completing the match. Separately, forward the remaining budget through a provider-specific timeout only after verifying the exact selected handle/backend supports it. A post-response check does **not** interrupt a blocking call; without an actual SDK/backend timeout or cancellation mechanism, the process can still overrun the deadline while waiting.

**Files/functions:** `kaggle_agent_adapter.py` — `KaggleLLM` and `_KagglePromptClient.chat()`; `kaggle_task/quarto_two_model_match.py` — `_IsolatedChatLLM.prompt()`; `tournament_harness.py` — `AgentAdapter.get_decision()` and `TournamentRunner.run_match()`; `tests/test_kaggle_agent_adapter.py` and `tests/test_tournament_harness.py`.

**Regression tests:** Negative: a fake response delayed past deadline is rejected and cannot be submitted or produce `status == "completed"`; deadline expiration between response and action submission is rejected; provider timeout/cancellation, if supported by the actual backend, is invoked with the remaining budget and aborts the request. Positive: a valid response returned before the deadline is accepted. Test with deterministic fakes; do not call either model.

**Resolution boundary:** Late-action acceptance can be fixed and tested locally. Hard interruption depends on the exact Kaggle SDK/backend implementation and hosted handle. The SDK package is absent locally and the hosted runtime/model classes were not inspected, so do not claim a hard wall-clock guarantee until timeout/cancellation is demonstrated against the actual hosted backend.

## Test matrix

| Finding | Required negative test | Required positive/invariant test | Hosted dependency |
|---|---|---|---|
| 1. Notebook source | Missing, unverifiable, or mismatching executed-Notebook attestation fails before prompts. | Matching independent attestation and existing `.py` hash verification pass. | **Yes:** executed Notebook identity/attestation must be available. |
| 2. Snapshot trust | Rehashed manifest/sidecar/payload rejected by an external trust anchor; invalid explicit root aborts without fallback. | Trusted approved snapshot passes; unset-root default resolution remains supported. | **Yes for authenticity:** independent digest/signature delivery and Task-source binding. Root behavior is local. |
| 3. Static membership | Restricted IDs and assignments absent from every public staged payload and public artifact. | Controlled runtime input reconstructs the exact approved instance and strict two-count result. | **Yes if restricted:** access-control boundary for the runtime input must be verified. |
| 4. String privacy | Embedded, nested, serialized, audit, and prompt leaks detected without echoing values. | UUIDs, ordinary metadata, and public cell indices `0..15` pass. | No. |
| 5. Phase coverage | Leaks in place/select and terminal outputs fail the preflight. | Actual projection/prompt paths cover all listed phases using the fixed instance; terminal artifacts are validated without a prompt. | No. |
| 6. Deadline | Late response and pre-submit deadline race cannot produce an accepted action/completed result. | In-budget response passes; supported provider timeout receives remaining budget. | **Yes for hard interruption:** exact hosted backend capability. |

## Preserved invariants and trade-offs

- Keep `fma_seed11_candidate_ordinal_0003_v1`, all 16 approved source IDs, the four feature definitions, thresholds, and signature mapping exactly unchanged. Do not resample or rebuild a candidate.
- Preserve the strict acceptance requirement that both counts equal two on the fixed pilot; do not weaken the existing validation.
- Keep Quarto Core dataset-independent and leave original engine behavior—including the already dirty `starting_player`/replay changes—unchanged. Keep FMA-specific configuration and loading at the adapter/pilot boundary.
- Preserve the Gemini and Claude model identities and player assignment. No synthetic adapter or fake client enters the production Task path.
- Keep public UUID projection and the source-to-public-ID crosswalk restricted. Finding 3 concerns static source-ID/signature disclosure, a distinct boundary.
- Preserve public observation and result shapes. The scanner should become more context-aware, not broaden bans in a way that rejects valid cell positions or public identifiers.
- Timeout enforcement trades a late-but-valid response for a failed/incomplete match once the deadline expires. If the provider cannot be interrupted, the result must still fail closed after return, while the runtime overrun limitation remains explicit.

## Execution and change boundary

This is a plan only. No implementation files were modified; only this report is being created. No Git mutation or dependency installation, Kaggle Task, hosted runtime, live model call, upload, or publication occurred. Before claiming full resolution for findings 1–2, a restricted-membership correction for finding 3, or hard interruption for finding 6, obtain the external source-attestation, release trust-anchor, membership-access, and provider-timeout decisions identified above. The late-response rejection in finding 6 and findings 4–5 can be implemented and tested locally.
