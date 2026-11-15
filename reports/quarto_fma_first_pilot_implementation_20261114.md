# Quarto FMA First Pilot Implementation

**Status:** Local implementation and offline verification complete. This is not a hosted or real-model benchmark result.

## 1. Approved candidate and provenance

The implementation preserves the approved seed-11 candidate, `fma_seed11_candidate_ordinal_0003_v1`, without searching for or selecting a replacement. Its persisted definition is [fma_pilot_instance.json](../fma_pilot_instance.json#L1), and [fma_pilot.py](../fma_pilot.py#L120) reloads and revalidates it.

- Candidate record: physical line 4, initial quartet ordinal 3, validator call 3, from `reports/diagnostics/fma_feasibility_seed11_20261109_204633_336807.jsonl`.
- Candidate-record SHA-256: `46053e4522f8273202164cda88fdd7743021826c28e3a4312f4c5f4694017a85`.
- Source-report SHA-256: `a1aef3f4822235d949fc3923b10f8c1c0f90d727fce25fabd5242c846aa973f5`.
- Pinned FMA archive SHA-256: `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265`.
- Frozen quartet: `fma:chroma_cens:mean:01`, `fma:chroma_cqt:median:11`, `fma:chroma_stft:skew:05`, and `fma:spectral_bandwidth:min:01`.
- All 16 selected raw feature rows were independently reread from the pinned archive. Recomputed signatures match the retained candidate exactly and cover 0–15.
- Strict validation returned `accepted=true`, `id_level_count=2`, and `structural_count=2`. The acceptance rule was not changed.
- A stable public seed is derived from the fixed candidate ID. The loader restricts the generic builder to the approved 16 rows, verifies the exact entity/signature ordering, then validates against the full loaded FMA domain. The seed does not select or change membership.

## 2. Implementation

- **Persisted loader:** [fma_pilot.py](../fma_pilot.py#L69) rejects missing, extended, or incorrectly typed artifact schemas; checks the pinned archive and frozen feature thresholds; rebuilds only the approved candidate through `GenericInstanceBuilder`; and requires the strict two-count validation result.
- **Restricted provenance:** [phase0_foundation.py](../phase0_foundation.py#L984) accepts an optional one-to-one source-ID map. [get_read_only_audit_view](../phase0_foundation.py#L1255) adds the public-UUID/source-ID crosswalk only to restricted evaluator data. [validate_audit_snapshot](../phase0_foundation.py#L774) checks coverage and uniqueness. Public observation and public audit schemas were not expanded.
- **Privacy preflight:** [run_security_audit](../tournament_harness.py#L1267) can inspect the actual supplied adapter and instance, including source IDs, public observations, public audit, private observations, and generated prompts. Low-entropy signatures are compared as exact scalar values rather than arbitrary substrings: this detects an exact copied signature while avoiding a false positive when a legitimate FMA feature ID ends in coordinate `11`.
- **Runner model identities:** [TournamentRunner](../tournament_harness.py#L850) now accepts two explicit model tags while preserving its prior default tags. This lets the Task attribute players to the exact required Gemini and Claude identities.
- **Kaggle Task:** [_run_quarto_two_model_match](../kaggle_task/quarto_two_model_match.py#L655) no longer stops at the old fail-closed guard or leaves unreachable match code. It requires a separately mounted archive at `QUARTO_FMA_ARCHIVE_PATH`, requires the operator acknowledgment `QUARTO_FMA_LICENSE_APPROVED=1`, loads the fixed instance, runs the real-instance security preflight, then runs one two-model match. It has no SyntheticAdapter fallback. Any preflight, audit, replay, or terminal-result failure fails the Task.
- **Documentation and tests:** [README.md](../README.md#L72) documents the offline test and runtime gates. Focused additions cover crosswalk privacy, exact signature matching, fixed-candidate loading, both starting seats, failure semantics, and Task fail-closed behavior ([Phase 0 tests](../tests/test_phase0_foundation.py#L486), [privacy tests](../tests/test_tournament_harness.py#L391), [FMA pilot tests](../tests/test_fma_pilot.py#L92), [Task tests](../tests/test_quarto_two_model_task.py#L205)).

## 3. Test evidence

All commands below exited 0. Each suite had zero failures, errors, or skips.

| Exact command | Tests | Runtime |
|---|---:|---:|
| `python -B -m unittest discover -s tests -p test_phase0_foundation.py -v` | 27 passed | 0.492 s |
| `python -B -m unittest discover -s tests -p test_tournament_harness.py -v` | 29 passed | 0.370 s |
| `python -B -m unittest discover -s tests -p test_quarto_engine.py -v` | 16 passed | 0.435 s |
| `python -B -m unittest discover -s tests -p test_kaggle_agent_adapter.py -v` | 19 passed | 0.104 s |
| `python -B -m unittest discover -s tests -p test_kaggle_adapter_metadata.py -v` | 2 passed | 0.001 s |
| `python -B -m unittest discover -s tests -p test_decision_trace.py -v` | 8 passed | 0.621 s |
| `python -B -m unittest discover -s tests -p test_fma_pilot.py -v` | 5 passed | 104.742 s |
| `python -B -m unittest discover -s tests -p test_quarto_two_model_task.py -v` | 10 passed | 168.993 s |
| `git diff --check` | passed | — |

Total: **116 tests passed** across the focused suites. The FMA runner test used the real local archive and fixed instance with deterministic fake agents. Both starting-player assignments completed with valid audits and replays, distinct per-match public UUIDs, and no source-ID findings in prompts or public results. A deliberately invalid action produced no winner. The Kaggle Task regression used fake SDK/model handles with the exact configured identities; missing license acknowledgment and missing archive were rejected before model prompts. No live model or hosted Task was called.

## 4. Staging and worktree integrity

The staged source snapshot now contains 10 payload files and five adapter ZIP members. The final manifest checksum, every payload hash, and every adapter-member hash validate. The root and staged Task files are byte-identical; the other staged runtime source files match their reviewed workspace versions. The FMA metadata archive is **not** bundled. The manifest records these facts and the test evidence in [manifest.json](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json#L744); its sidecar checksum is valid.

The Kaggle SDK is declared in the existing staged requirements, but is not installed locally. The FMA adapter and its imported dataset modules use the Python standard library; the Kaggle SDK is the hosted Task dependency. No dependencies were installed.

Worktree baseline before this implementation: branch `main`, HEAD `fc7e5d355162c81c267eb3d02462539bc2283113`, zero staged paths, six already-modified tracked files, 107 pre-existing untracked files, and no deletions. Final branch and HEAD are unchanged. The six pre-existing tracked modifications remain; the FMA implementation and staging/report changes are additions or updates under existing untracked paths. No files were staged or committed, and no reset, checkout, restore, clean, rebase, or branch switch was performed. In particular, the pre-existing `quarto_engine.py` and engine-test changes were not edited by this implementation.

Final `git status --short --branch`:

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
?? fma_pilot.py
?? fma_pilot_instance.json
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
?? tests/test_fma_pilot.py
?? tests/test_hidden_quarto_benchmark.py
?? tests/test_kaggle_adapter_metadata.py
?? tests/test_kaggle_agent_adapter.py
?? tests/test_phase1_qm9_adapter.py
?? tests/test_quarto_two_model_task.py
?? tests/test_tournament_harness.py
?? tournament_harness.py
```

Final `git diff --stat` reports six tracked modified files, 1,142 insertions, and 105 deletions; it does not include untracked files. Qodo's earlier lookup found no accessible Quarto mirror or applicable repository rules, so implementation and verification were grounded in the local checkout.

## 5. Remaining blockers and limitations

1. **FMA licensing is unresolved.** The environment acknowledgment is only a gate, not a legal determination. Do not set it until the archive license and intended use are reviewed.
2. **No hosted execution occurred.** The archive must be separately mounted and hash-verified; the exact Claude registry entry, selected Gemini identity, Kaggle Task runtime, and backing Notebook parity remain runtime checks.
3. **No real-model benchmark result exists.** Offline fake-agent matches establish plumbing, instance reproducibility, privacy, audit, and replay behavior only.
4. **Provider timeout limitation remains.** `llm.prompt()` is not interruptible by the Runner's wall-clock deadline.
5. **No full suite or QM9 integration suite was run.** The executed tests were bounded and focused; no Kaggle upload, publication, hosted inference, dependency installation, or Git mutation occurred.

Qodo-assisted research did not provide a Quarto mirror or additional applicable rules. An automated local-diff review was not submitted because it would transfer this worktree's code and untracked files outside the repository; the final review was performed directly against the local sources and tests.
