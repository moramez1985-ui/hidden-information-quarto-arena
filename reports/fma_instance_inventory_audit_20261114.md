# FMA Instance Inventory and Benchmark Readiness Audit

**Audit date:** 2026-11-14

**Repository:** `D:\CODES\quarto`
**Branch / HEAD:** `main` / `fc7e5d355162c81c267eb3d02462539bc2283113`

## Executive conclusion

FMA remains the selected source for this inventory; this report does not revisit the dataset choice. The local [fma_metadata.zip](../data/fma_metadata.zip) matches the adapter's pinned SHA-256. Two saved, disjoint 25,000-track samples contain **6,120 distinct candidate instance specifications**, of which **1,150** satisfy the strict acceptance rule and **4,970** do not. Each recorded candidate has 16 source track IDs, one per signature from 0 through 15, and one selected quartet from the same frozen pool of 18 features.

Those are retained candidate records, not 6,120 standalone `InstanceSpec` files: the records have no stable `instance_id`, and only one candidate received a separate, independently reproduced inspection. The number of all FMA instances ever generated cannot be established beyond the saved artifacts.

**No current real two-model path uses any of these FMA candidates.** The workspace pilot runner stops after its connectivity preflight because no adapter and instance are configured. The Kaggle Task also raises before creating or running a match. Its staging manifest is internally valid, but the staged Task, Phase 0 controller, and tournament harness do not match their current workspace versions; the FMA metadata archive is excluded from staging.

## 1. Dataset source, identity, and use

| Item | Evidence |
|---|---|
| Local source | [data/fma_metadata.zip](../data/fma_metadata.zip), 358,412,441 bytes |
| Current SHA-256 | `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265`; matches [FMA_PILOT_ARCHIVE_SHA256](../domain_adapters/fma_adapter.py#L20) and both experiment reports |
| Adapter identity | Dataset ID `fma`; adapter version `fma-metadata-seed11-frozen-features-v1`; recorded source version only `fma_metadata.zip` |
| Upstream identification | The archive README identifies the FMA project and links to `github.com/mdeff/fma` and the FMA paper. No upstream release tag, exact metadata release, or metadata-dataset license is recorded. The README says each MP3 is licensed by its artist; that statement does not establish a license for this metadata archive. |
| Source content used | `fma_metadata/tracks.csv` for numeric track IDs and descriptive metadata; `fma_metadata/features.csv` for the 18 frozen numeric feature columns. No audio files are used. |
| Source population | Both reports record 106,574 numeric track IDs, with a matching unique-ID set in tracks and features. The metadata archive is not an FMA audio subset such as a small/medium/large audio download. |

The adapter checks the whole archive hash before loading. It sorts numeric track IDs, samples without replacement using `random.Random(seed)`, and sorts the chosen IDs. Its default is 25,000 tracks with seed 11; the seed-23 configuration removes the seed-11 sample before drawing the holdout. The report hashes for the sorted memberships are:

- Seed 11: `d0e1496b677d2f5c7aa7bb2870ba4eb388cdfea2298b3dd3893a1d0942724610`
- Disjoint seed-23 holdout: `05a78b176c2eb2c703a63207506cc58468e32f9bdf1ac43835e82471a5de31a5`

The holdout report records zero sample overlap and no missing or non-finite values in the 450,000 selected source values it checked. The adapter rejects malformed, missing, or non-finite selected values rather than imputing them. `tracks.csv` descriptive fields (album title, artist name, track title, top genre, and genres) are retained as metadata, not used as gameplay features. The adapter explicitly records `audio_files_used=False` and `descriptive_metadata_used_as_features=False`.

The local archive README and checksum file were read without extracting or rewriting the archive. The archive's SHA-1 member checksums were not recomputed in this audit; the adapter's pinned archive SHA-256 was independently computed and matched.

## 2. Frozen feature pool and binary transformation

The domain defines **18** features, but an individual Quarto [InstanceSpec](../phase0_foundation.py#L554) selects **exactly four** of them. The complete 18-feature pool is supplied to strict instance validation to measure alternative valid quartets and structural classes. It is not correct to say each instance has 18 selected piece attributes. `InstanceSpec` stores the four ordered selected feature IDs, 16 source entity IDs, and their signatures ([phase0_foundation.py](../phase0_foundation.py#L554); [instance_builder.py](../domain_adapters/instance_builder.py#L106)).

For every feature, the source is the corresponding hierarchical `features.csv` column (family/statistic/coordinate). The bit is `source_value > frozen_threshold`; equality is false. Thresholds were frozen from the seed-11 sample; they were not recalculated on seed 23. Missing values are rejected, not imputed. The source rows and experiment reports record no missing selected values. The pool order is frozen and hashed; it determines the order in which the reports enumerate the 3,060 quartets. The documented evidence says the pool was frozen for the seed-11 feasibility work, but does **not** document why these particular 18 columns were selected out of the 518-column feature matrix or establish an acoustic rationale for their coordinates/statistics.

| Feature ID | FMA source column | Seed-11 threshold | Recorded descriptor interpretation |
|---|---|---:|---|
| `fma:chroma_cens:mean:01` | `chroma_cens / mean / 01` | 0.25517144799232483 | CENS chroma-family descriptor; mean |
| `fma:chroma_cqt:median:11` | `chroma_cqt / median / 11` | 0.4525887370109558 | Constant-Q transform chroma-family descriptor; median |
| `fma:chroma_stft:skew:05` | `chroma_stft / skew / 05` | 0.3928850293159485 | Short-time Fourier transform chroma-family descriptor; skew |
| `fma:mfcc:kurtosis:08` | `mfcc / kurtosis / 08` | 0.15643799304962158 | Mel-frequency cepstral coefficient family; kurtosis |
| `fma:rmse:min:01` | `rmse / min / 01` | 0.00003314237983431667 | Root-mean-square energy family; minimum |
| `fma:spectral_bandwidth:min:01` | `spectral_bandwidth / min / 01` | 290.3798522949219 | Spectral bandwidth family; minimum |
| `fma:spectral_centroid:kurtosis:01` | `spectral_centroid / kurtosis / 01` | 6.258625030517578 | Spectral centroid family; kurtosis |
| `fma:spectral_contrast:skew:07` | `spectral_contrast / skew / 07` | -0.40135782957077026 | Spectral contrast family; skew |
| `fma:spectral_rolloff:max:01` | `spectral_rolloff / max / 01` | 9463.8427734375 | Spectral rolloff family; maximum |
| `fma:tonnetz:skew:05` | `tonnetz / skew / 05` | 0.015766769647598267 | Tonal centroid (Tonnetz) family; skew |
| `fma:zcr:skew:01` | `zcr / skew / 01` | 2.4203286170959473 | Zero-crossing-rate family; skew |
| `fma:chroma_cens:kurtosis:12` | `chroma_cens / kurtosis / 12` | -0.17919006943702698 | CENS chroma-family descriptor; kurtosis |
| `fma:chroma_cqt:kurtosis:08` | `chroma_cqt / kurtosis / 08` | -0.7438324689865112 | Constant-Q transform chroma-family descriptor; kurtosis |
| `fma:chroma_stft:std:09` | `chroma_stft / std / 09` | 0.26742768287658691 | Short-time Fourier transform chroma-family descriptor; standard deviation |
| `fma:mfcc:skew:15` | `mfcc / skew / 15` | 0.003920631017535925 | Mel-frequency cepstral coefficient family; skew |
| `fma:spectral_contrast:max:01` | `spectral_contrast / max / 01` | 59.43647766113281 | Spectral contrast family; maximum |
| `fma:tonnetz:skew:03` | `tonnetz / skew / 03` | 0.020528830587863922 | Tonal centroid (Tonnetz) family; skew |
| `fma:chroma_cens:skew:03` | `chroma_cens / skew / 03` | 0.2518020570278168 | CENS chroma-family descriptor; skew |

Exact declarations and transformations are in [fma_adapter.py](../domain_adapters/fma_adapter.py#L20) (lines 20–62, 206–280, 281–427). The feature-pool hash is `1f2f4b59f1edda91ac7cfacfd55bc383d9362167b668b02a57e96d090a5600be`; the threshold-configuration hash is `dfcc00b3b4e780e4271007ae6164792d51824b95a651647d7c3bf7502a9052a6`.

## 3. Instance construction and validation contract

The FMA adapter delegates construction and validation to the generic dataset adapter and `GenericInstanceBuilder`; the FMA-specific code defines source loading, binary features, provenance, and the complete 18-feature eligible pool ([fma_adapter.py](../domain_adapters/fma_adapter.py#L281); [dataset_adapter.py](../domain_adapters/dataset_adapter.py#L177)). Strict acceptance is exactly:

```text
id_level_count > 1 AND structural_count > 1
```

The validator first requires 16 distinct known entity IDs and four distinct known selected feature IDs. It verifies the recorded signature of every entity against the domain values and the selected feature order, then counts all eligible four-feature combinations that cover signatures 0–15 exactly once and groups structural aliases ([instance_builder.py](../domain_adapters/instance_builder.py#L106)). [`GenericInstanceBuilder._build_strict_instance()`](../domain_adapters/instance_builder.py#L532) enforces the same two-count acceptance predicate. Thus, for these instances, the strict invariant is 16 entities, exactly four selected features from the 18-feature pool, and one entity per signature.

The stored scans enumerate all `C(18,4) = 3,060` initial quartets per sample in the frozen feature-pool order. Each feasible quartet has one deterministic entity selection; no alternative entity selections were tested. The saved seed-11 report specifies `random.Random(11)` for those selections. This is not identical to calling the current [FMAAdapter.build_instance()](../domain_adapters/fma_adapter.py#L478) with `seed=11`: the current strict builder shuffles candidate quartets when a seed is provided and then uses that RNG for entity selection. With no seed it chooses the first sorted entity per signature. Reconstruct a recorded candidate from its row if exact reproduction is required; do not assume the adapter's default search returns the same saved candidate. The adapter's default `instance_id` is the reusable literal `fma_instance_0`, so a real run must supply a deliberate stable identifier.

## 4. Saved candidate-instance inventory

| Saved experiment | Track sample | Candidate quartets / feasible candidates | Strictly accepted | Rejected by the two-count rule | Duplicate selected entity sets |
|---|---:|---:|---:|---:|---:|
| Seed-11 pilot | 25,000 | 3,060 / 3,060 | 541 (17.68%) | 2,519 | 0 |
| Seed-23 disjoint holdout | 25,000 | 3,060 / 3,060 | 609 (19.90%) | 2,451 | 0 |
| **Distinct retained total** | **50,000 disjoint sample IDs** | **6,120** | **1,150** | **4,970** | **0 reported within either scan** |

The counts agree with the exact acceptance predicate for every candidate row. A read-only audit of the saved records found:

- 16 distinct entity IDs and four distinct selected feature IDs in every candidate row.
- Signature values 0 through 15 exactly once in every row.
- 3,060 unique candidate specifications in each sample and no cross-sample candidate overlap.
- 541 seed-11 and 609 holdout rows with both counts greater than one; all other rows fail at least one count.

“6,120 instances” here means **distinct candidate gameplay specifications encoded in the retained JSONL rows**, not 6,120 standalone `InstanceSpec` artifacts. The rows contain the selected quartet, 16 source IDs in signature order, the signature list, and validation counts. They do not contain a stable `instance_id` or `public_seed`; the complete raw source matrix is in the separately retained archive. No FMA-specific standalone instance registry or saved `InstanceSpec` artifact was found in the repository's FMA file set. The exact all-time number of FMA candidates ever generated is unknown beyond these persisted scans.

There are duplicate *representations* in the artifact set, not additional candidates:

1. [The recovered seed-11 JSONL](diagnostics/fma_feasibility_seed11_20261109_204633_336807.jsonl) is the complete report (3,060 candidate rows).
2. [The earlier seed-11 JSONL](diagnostics/fma_feasibility_seed11_20261109_203057_634004.jsonl) is a duplicate candidate stream (same candidate contents), but has a non-JSON physical line 2 from the failed readback/error record. The recovered report records 3,060 recovered candidates and says the validator calls were not repeated.
3. [The first-accepted inspection](diagnostics/fma_first_accepted_instance_inspection.md) is a separate inspection of seed-11 candidate ordinal 3; it is not a new candidate.
4. [The holdout JSONL](diagnostics/fma_holdout_seed23_20261109.jsonl) is the distinct scan. Its summary was assembled from the flushed candidate rows after a summary-field mismatch; the report says no candidate or validator call was repeated.

The candidate JSONL rows span seed-11 lines 3-3062 and holdout lines 2-3061; their summaries are the final records. The seed-11 recovered summary is line 3063; the holdout summary is line 3062. The corresponding [holdout Markdown report](diagnostics/fma_holdout_seed23_20261109.md) gives the experimental design and limitations.

## 5. Strongest saved candidate evidence (not a selection)

No candidate was selected or executed for this audit.

**Seed-11 ordinal 3** is the strongest individually documented record. It is the first accepted seed-11 candidate, with selected features:

```text
fma:chroma_cens:mean:01
fma:chroma_cqt:median:11
fma:chroma_stft:skew:05
fma:spectral_bandwidth:min:01
```

Its source IDs in signature order are:

```text
53194, 104583, 74557, 111359, 112679, 10811, 139817, 149118,
70026, 107833, 47152, 151991, 36515, 69954, 134635, 43525
```

The [saved inspection](diagnostics/fma_first_accepted_instance_inspection.md) says it independently read these IDs and source columns from the matching local archive, applied the frozen thresholds, and called the existing validator; it reports `id_level_count=2`, `structural_count=2`, accepted, and exact 0–15 signature coverage. It also labels the acoustic interpretation limited/unclear: these are median-split descriptor coordinates, not established musical categories.

**Seed-23 ordinal 9** is the first accepted holdout candidate. It uses `fma:chroma_cens:mean:01`, `fma:chroma_cqt:median:11`, `fma:chroma_stft:skew:05`, and `fma:chroma_cens:kurtosis:12`; its row records 16 distinct IDs, 0–15 signatures, and both counts equal to 2. This candidate is recorded in the holdout JSONL but was not separately reproduced in the Markdown inspection. Neither candidate is asserted to be suitable or chosen for the next match.

## 6. Source identifiers, hidden features, and audit traceability

The FMA adapter uses each numeric FMA track ID as the `PublicEntity.entity_id` and label in the trusted domain. In a match, [`MatchSession`](../phase0_foundation.py#L959) generates a unique UUIDv4 per source ID, creates the UUID-to-piece mapping, orders public entities by those public UUIDs, and splits the four selected feature IDs two per player ([phase0_foundation.py](../phase0_foundation.py#L998)). Public observation entities, legal actions, and history use the per-match UUIDs, not the original track IDs or internal piece IDs ([phase0_foundation.py](../phase0_foundation.py#L1118)). The public audit contains public identifiers; feature ownership and evaluator mappings are restricted ([phase0_foundation.py](../phase0_foundation.py#L1230)). Thus, source track IDs are not intended to appear in public prompts or actions.

Feature IDs are semantically descriptive (they name FMA feature families/statistics/coordinates). The private observation provides only the active player's two `owned_features` and related feedback; the other player's ownership is not included in that private payload ([phase0_foundation.py](../phase0_foundation.py#L1008); [private_observation()](../phase0_foundation.py#L1154)). The actual numeric feature values and source metadata are not public gameplay observations.

There is a **restricted audit provenance gap**: the live session retains source-to-public UUID mapping, while the saved restricted audit includes `entity_to_piece` keyed by public UUID and the validation record's source `entity_ids`, but does not serialize the source-ID-to-public-UUID pair map. The validator record stores the sorted source IDs and aggregate selected-signature coverage, not the per-source signature map ([InstanceQuartetValidation](../domain_adapters/instance_builder.py#L48); [phase0_foundation.py](../phase0_foundation.py#L1246)). Consequently, a saved audit can validate replay and evaluator piece mapping without fully linking each public UUID back to its FMA source track. This does not expose source IDs publicly, but it limits post-match source-level provenance from the snapshot alone.

## 7. Current match and Kaggle readiness

### Workspace pilot runner

[`TournamentRunner.run_match()`](../tournament_harness.py#L870) accepts an explicit adapter and an `InstanceSpec`; [`run_two_match_pilot()`](../tournament_harness.py#L1066) runs both starting-player assignments. But [`run_pilot()`](../tournament_harness.py#L1605) does not supply either. After security and model-connectivity preflights it raises, “No dataset adapter instance was configured,” explicitly refusing both QM9 and synthetic fallback; the code after that raise is unreachable. Therefore the current workspace runner will use **no FMA instance**.

The retained [restricted match log](../experiments/pilot_tournament/restricted_match_log.json#L1103) records `qm9_pilot_hf_ring_db_0001` (for both saved match entries), not an FMA candidate. It is historical QM9 evidence only and is not included in the FMA candidate counts.

### Kaggle Task and staging

- The current workspace [Task](../kaggle_task/quarto_two_model_match.py#L650) checks the source snapshot, imports the agent/harness, checks for `domain_adapters.zip`, then unconditionally raises that a validated real dataset adapter instance is required and synthetic smoke execution is disabled. It never constructs an FMA adapter/instance or calls `runner.run_match`. The later match/result block is unreachable; `result` and `instance` are used there without a preceding assignment.
- Staging integrity is internally correct: all 8 [manifest.json](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json) payload hashes match, all 5 [domain_adapters.zip](../kaggle_dataset_staging/quarto-two-model-source-v1/domain_adapters.zip) member hashes and sizes match the manifest, and [manifest.sha256](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.sha256) matches `manifest.json` (manifest SHA-256 `c14e910714d3542650de12e962f25281110336f1d132a612b08c77ffbfbd4bf2`). The five packaged adapter modules also match their current workspace counterparts.
- Internal integrity is not workspace parity. Current workspace versus staged hashes differ for the Task (`fee22413127c3885bb8ab418bc10b8def6312753067ffdbc9c1eba640ff8e896` vs `67951954334b96cb579831f21a8d97ba6f759467a049f2b3bb273bf235a9da4b`), [phase0_foundation.py](../phase0_foundation.py#L1) (`f1b74fc34c9ad979ca6523d91d52e2765746265a544a7275053057d2a70aed4c` vs `2bf58d9fcdc4c0d1532e47c14decf1bd704cc822d7d8f87750ea97c4944e7279`), and [tournament_harness.py](../tournament_harness.py#L1) (`1870c5dd86786bf5b6f07e1f5f95bcbd36d82a205450165ff402d683357d050d` vs `dda903c9ae7863d34c61a05deb3d92df8a2112cc54f0473bcbbad7264b310b16`). The staged Task's [`_verify_task_source()`](../kaggle_task/quarto_two_model_match.py#L401) compares the executing Task hash with the staged manifest, so running the current workspace Task against that snapshot fails integrity before match setup; running the staged Task reaches its own fail-closed guard ([staged Task](../kaggle_dataset_staging/quarto-two-model-source-v1/quarto_two_model_match.py#L587)).
- The manifest explicitly excludes local datasets/data. [data/fma_metadata.zip](../data/fma_metadata.zip) is not present in the staged payload. The current Kaggle Task cannot load the real FMA source even if its fail-closed guard were removed.
- The staged dependency list contains `kaggle_benchmarks==0.6.2`. The adapter package eagerly imports FMA and QM9 modules in [domain_adapters/__init__.py](../domain_adapters/__init__.py), but both adapter modules use standard-library imports and the FMA constructor is lazy; no FMA archive is read merely by importing the package. This is not the present blocker.

**Result:** the Task is safer than a synthetic benchmark masquerading as real, but it cannot execute a genuine FMA two-model match. Hash correctness of the snapshot does not cure source staleness or missing real-data provisioning.

## 8. Test and execution evidence

No test suite, adapter `load_domain()` on the production archive, new sample generation, tournament, model call, Kaggle hosted Task, upload, or publication was run in this audit. No dependencies were installed.

The available FMA adapter suite is [test_fma_adapter.py](../tests/test_fma_adapter.py) and contains six test methods. Its fixture creates a temporary 16-track synthetic FMA-shaped ZIP; it covers archive hash checks, frozen threshold/tie behavior, deterministic and disjoint sampling, strict generation, and lazy construction. It does **not** by itself establish the saved 25,000-track feasibility counts or prove a production FMA two-model run. The file was inspected, not executed.

Read-only checks performed for this report included hashing the local archive and staged payloads, reading the archive README/member list, parsing and cross-checking the saved JSONL candidate records, and comparing staged/current source hashes. These are inventory checks, not tests of a live match.

## 9. Worktree integrity

The pre-report baseline was `main` at `fc7e5d355162c81c267eb3d02462539bc228311`: six tracked files modified, 105 untracked files, no staged files, and no deletions. The FMA adapter and its test were tracked and unchanged; the archive, extracted FMA metadata, and diagnostic reports were pre-existing untracked data/artifacts. The requested report did not exist at baseline.

This audit made no source, test, dataset, manifest, staging, configuration, or Git-history changes. The only file created for the task is this requested report. Final status was checked after creation; branch and HEAD are unchanged, the six existing tracked modifications remain, no files are staged or deleted, and the untracked-file count is 106 (the 105 pre-existing files plus this report). No pre-existing dirty changes were reverted or overwritten. No staging, commit, reset, checkout, restore, clean, rebase, branch switch, dependency installation, or external upload occurred.

## 10. Blockers and minimal sequence before a real two-model test

1. **BLOCKER — no runnable real-instance path.** Neither workspace `run_pilot()` nor the Kaggle Task selects or supplies an FMA adapter and accepted instance; both fail closed. The post-raise code is not an execution path.
2. **BLOCKER — stale Kaggle snapshot and absent source data.** Refresh staging from the intended current workspace versions, verify the Task and runtime hashes agree, and provision the exact pinned FMA archive through an approved real-data input. Do not remove the fail-closed guard until that path verifies and validates a real instance.
3. **HIGH — no durable selected instance identity.** Candidate rows have complete gameplay mapping content but no stable `instance_id` or `public_seed`; the adapter default ID is reusable. Before a match, explicitly identify and persist a chosen candidate's quartet, source IDs, signatures, source hash, sample membership hash, feature/threshold hashes, and unique instance ID. This audit intentionally does not choose a candidate.
4. **HIGH — incomplete post-match source linkage.** If the evaluator requires mapping public match entities back to source tracks, preserve the source-ID-to-public-UUID mapping only in restricted evaluator data and test that it remains absent from public outputs.
5. **MEDIUM — incomplete provenance and selection rationale.** Record the exact upstream FMA metadata release and applicable dataset/metadata license. Document why the 18 columns were chosen and preserve the original bounded candidate-generation procedure or a reproducible manifest.
6. **MEDIUM — bounded validation evidence.** Reconstruct one explicitly selected saved candidate from the pinned archive, run current adapter/Phase 0 validation, then run focused local tests and a two-starting-player match through [`TournamentRunner.run_match()`](../tournament_harness.py#L870). Only after the local path passes should a separately scoped hosted Task test be considered.

The smallest safe implementation order is: (1) choose and uniquely identify a saved accepted candidate; (2) reconstruct and validate it against the pinned archive using current code; (3) retain restricted source-to-public mapping and verify the public boundary; (4) update staging from current code and provision the pinned data without altering the generic adapter design; (5) replace the Task's unconditional stop only with a fail-closed, validated FMA construction path; and (6) run the two-player/two-starting-player local test before any hosted benchmark. This audit does not declare the project ready for that test.
