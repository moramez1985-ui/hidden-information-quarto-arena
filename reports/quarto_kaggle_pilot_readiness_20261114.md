# Quarto FMA Two-Model Pilot: Offline Kaggle Readiness Assessment

**Assessment date:** 2026-11-14
**Instance:** `fma_seed11_candidate_ordinal_0003_v1`
**Models:** Player 1 `google/gemini-3.8-flash`; Player 2 `anthropic/claude-sonnet-4-6@default`

## Assessment

The local source package and archive checks are consistent with the fixed pilot configuration, and the Task's preflight ordering, model mapping, and success checks are visible in source. This does **not** make the pilot ready to execute: rights remain conditionally confirmed, the required license acknowledgment has not been set, the independent review's HIGH and MEDIUM technical findings remain unresolved, and Kaggle Notebook/runtime behavior is unverified.

No Task or model was executed for this assessment. No upload, publication, dependency installation, Git mutation, or `QUARTO_FMA_LICENSE_APPROVED=1` setting occurred.

## Readiness checks

### 1. Independent-review findings

The independent review's technical findings remain **documented but unresolved**; this assessment found no intervening implementation changes that close them:

| Prior finding | Current disposition |
|---|---|
| Notebook-converted Task source can be `not_verifiable_in_notebook` while execution continues. | Unresolved; recorded in [the independent review](quarto_fma_pilot_independent_review.md#L14). |
| Staging manifest is self-consistent but not authenticated by an independent trusted digest/signature; invalid configured roots can fall through. | Unresolved; [review finding](quarto_fma_pilot_independent_review.md#L24). |
| Staged instance artifact/code discloses the 16 FMA source IDs and their signature assignment. | Unresolved; [review finding](quarto_fma_pilot_independent_review.md#L34). |
| Restricted-value scan can miss values embedded within strings. | Unresolved; [review finding](quarto_fma_pilot_independent_review.md#L44). |
| Security preflight exercises only initial-state prompts/artifacts, not later phases. | Unresolved; [review finding](quarto_fma_pilot_independent_review.md#L54). |
| Kaggle model call ignores the Runner timeout; a late final action may still complete successfully. | Unresolved; [review finding](quarto_fma_pilot_independent_review.md#L64). |

These are not treated as cleared merely because they are documented or because earlier tests passed.

### 2. Task and staged-source parity

The current offline byte comparison passed for all eight runtime files that have workspace counterparts: `phase0_foundation.py`, `quarto_engine.py`, `tournament_harness.py`, `kaggle_agent_adapter.py`, `decision_trace.py`, `fma_pilot.py`, `fma_pilot_instance.json`, and `quarto_two_model_match.py`.

The manifest sidecar is valid (`manifest.json` SHA-256: `cdbff019c1c700a7bb8e12040f4cf942471b334960886f43a1205b698455a4b7`). All 11 payload hashes and sizes and all five `domain_adapters.zip` member hashes and sizes match the manifest. The staged attribution blockquote matches the root notice and is included in the manifest. These local checks establish package consistency, not authenticity or hosted Notebook parity.

### 3. Archive mount and SHA-256 contract

The FMA archive is deliberately absent from the source package. The Task requires an existing separately mounted file at `QUARTO_FMA_ARCHIVE_PATH`; the adapter checks its SHA-256 against `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265` before reading the archive. The current local archive matches that digest. The upstream SHA-1 and conditional rights assessment are recorded in the [license audit](fma_metadata_license_audit.md#L13).

The Task uses the fixed instance JSON and does not select or resample another candidate. The loader revalidates the artifact, rebuilds the exact fixed instance and requires `accepted=True`, `id_level_count == 2`, and `structural_count == 2`.

### 4. Missing gate/archive/hash failure ordering

Static call-order inspection confirms:

1. Missing license acknowledgment fails before archive resolution or pilot loading.
2. Missing/unavailable archive fails before pilot loading.
3. Archive digest mismatch raises during `load_fma_pilot()` before the security preflight, client construction, Runner, or provider call.
4. Only after these checks and a passing security preflight does the Task construct its model clients and call `runner.run_match()`.

The existing offline Task tests assert that missing acknowledgment and missing archive do not increase fake prompt counts; the pilot-loader test checks a bad archive hash. Those tests were inspected but **not run**, because this assessment does not execute the Task. The ordering is established from source, not a hosted observation.

### 5. Synthetic/fake fallback

The hosted Task path requires the source archive, FMA archive, fixed pilot artifact, and a passing real-adapter preflight. It passes the loaded FMA adapter and instance explicitly to `run_security_audit()` and the Runner; it does not fall back to `SyntheticAdapter` or fake clients. The generic `run_security_audit()` helper has a synthetic default when called without an adapter, but the Task's call site does not use that default. Fake agents in the test suite are test fixtures only.

### 6. Model identities and registry

The source constants and assignment map match the requested pair. `_resolve_models()` requires the selected Task LLM to identify as `google/gemini-3.8-flash`, requires exactly one registry key and handle for `anthropic/claude-sonnet-4-6@default`, checks the resolved identity, and rejects duplicate handles/identities before inference.

Actual Kaggle registry availability, SDK identity metadata, and provider access are **unverified** because no hosted Task or live model call was made.

### 7. Kaggle SDK/runtime dependencies

The staged [requirements.txt](../kaggle_dataset_staging/quarto-two-model-source-v1/requirements.txt) declares `kaggle_benchmarks==0.6.2` and says the hosted Task runtime supplies it. No dependencies were installed. The installed hosted SDK/runtime version and compatibility are not verified offline. The staging manifest also says Kaggle upload metadata was not created because it requires the owner slug and license choice; no upload was prepared or attempted.

### 8. Timeout limitation

The Task documents a 900-second match wall-clock limit and explicitly says the provider call is not interruptible. The Kaggle adapter does not forward the Runner timeout to `llm.prompt()`. As documented by the independent review, a late final response can still be submitted and result in a completed match because there is no post-response deadline rejection. This remains an operational/correctness limitation, not a verified hosted timeout behavior.

### 9. Attribution and license status

`ATTRIBUTION.md` accompanies the staged package, is included in the manifest, and gives the FMA attribution, fixed four-column threshold transformation, no-MP3/no-Echonest scope, and conditional license caveats. The archive is excluded from staging.

The [license audit](fma_metadata_license_audit.md#L1) is **CONDITIONALLY CONFIRMED**, not legal approval. The rights clarification file is an unsent draft; it is not a maintainer response or commercial clearance. The Task's explicit `QUARTO_FMA_LICENSE_APPROVED=1` gate is therefore not satisfied or asserted here.

### 10. Success and incomplete-match behavior

The Task accepts a result only when the Runner reports `status == "completed"`, there is at least one action, audit and replay are valid, and the terminal result is valid. It then separately validates the projected public replay and raises on failure. Runner action-limit, agent, audit, replay, and terminal-result failures do not produce a successful Task result.

The timeout finding above is an important exception to time-limit semantics: a response arriving after the declared deadline may still be accepted if it completes the match. No hosted failure or timeout behavior is claimed as verified.

## Verification performed

- Read the requested license, attribution, rights-inquiry, independent-review, and current manifest documents.
- Read-only source/manifest verification: manifest checksum valid; 11 payload hashes/sizes valid; five adapter ZIP member hashes/sizes valid; 8/8 runtime files byte-identical to workspace counterparts; attribution notice included and its attribution text matches the root notice.
- Confirmed `fma_metadata.zip` is not bundled and the local archive hash matches the pinned SHA-256.
- `git diff --check` passed.
- No unit tests were run in this assessment; prior test reports were not treated as proof. No Task, model, or hosted runtime was invoked.
- Worktree remained on `main` at HEAD `fc7e5d355162c81c267eb3d02462539bc2283113`; no Git state was changed. Only this readiness report was created.

## Decision

The primary gate is licensing: the rights status remains conditional, the clarification request is unsent, and this assessment must not set the required acknowledgment. Independently, the HIGH source-parity finding and MEDIUM technical findings remain unresolved, and Kaggle registry/runtime behavior remains unverified. Do not treat this report as authorization to run the Task or as a claim of benchmark readiness.

BLOCKED_BY_LICENSE
