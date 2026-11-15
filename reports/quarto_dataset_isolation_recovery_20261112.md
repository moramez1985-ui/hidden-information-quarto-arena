# Quarto Dataset-Isolation Recovery

**Investigation date:** 2026-11-12  
**Scope:** Historical recovery and current architecture reconciliation; no implementation work.

## Executive summary

The repository does contain substantial dataset-adapter separation work. The current `main` tree has a generic `DatasetAdapterFactory`, immutable dataset definitions/source data, generic instance building and Quartet validation, and separate FMA/QM9 adapter modules. FMA is an optional adapter, not a replacement default. Preserve this implementation.

That work did not, by itself, remove every older QM9 execution path. The current `phase0_foundation.py` still contains QM9-specific checks and wording; `tournament_harness.py` imports `QM9Adapter` and its standalone pilot selects it; the adapter package eagerly imports both dataset adapters. These are current boundary problems, but available Git history shows the QM9 pilot predates the generic factory and was never removed in the history recovered here. They are not evidence that a completed removal was reverted.

The Kaggle fake-model smoke test was explicitly intended to be synthetic and local. Separately, the current Kaggle Task code uses `SyntheticAdapter` in its executable Task path. Earlier requests for that Task explicitly required a real two-model match on a valid accepted instance, so the checked-in Task code conflicts with that requirement. No decision record explains whether the synthetic instance was meant to remain a smoke fixture or was an unintended parallel path. Do not silently treat it as either, and do not connect `DatasetAdapterFactory` to Kaggle merely because the factory exists.

## A. Chronological timeline

Dates below are Git commit dates or session timestamps. The checkpoint histories are not a single linear history; see section E.

| Date | Milestone and evidence | Interpretation |
|---|---|---|
| Nov 7 | Initial `quarto_engine.py` project import (`767d7f97a86909294294abda9a3f1075b3d70879`). The engine defines game rules and state; the current engine has no QM9/FMA/factory references. | Core engine work is separate from dataset adapters. |
| Nov 8 | QM9-specific adapter/validation step (`2375443049100e594ab41993abbbe59bc6ec3b75`). | Initial real-data integration was QM9-specific. |
| Nov 8 | Tournament pilot step (`2f42aaec54f674ea441752e43148bf34f71bf224`) adds `tournament_harness.py` with the QM9 pilot path. The QM9 helper/default and pilot call are present in the earliest available harness snapshot. | QM9 was the active pilot source at that time; this is legacy history, not evidence that the later retirement had already been implemented. |
| Nov 9 | Strict Quartet validator (`7d099e5c8b06952b2ae5c2d401f81da42fce1c5c`). | The reusable combinatorial validator and its tests were established. |
| Nov 9 | Generic adapter/factory checkpoint (`e7e8b1c9dc05a5648edd18b4435c8ae04d480c7b`). | Adds reusable definitions, source-data normalization, explicit loader registration, factory construction, strict generation, and tests for a synthetic generic pipeline and independent datasets. It does not remove the earlier QM9 harness path. |
| Nov 9 | Active `main` HEAD, `feat(fma): add validated real-data instance adapter` (`fc7e5d355162c81c267eb3d02462539bc2283113`). | The current tree contains the generic factory plus FMA as an optional adapter. FMA has accepted-instance and holdout evidence, not a default-selection decision. |
| Nov 10 | `reports/kaggle_model_discovery_feasibility_20261110.md` describes `make_qm9_instance()` and its required local QM9 inputs (around lines 221-240). | A later research report still treats QM9 as the pilot. This conflicts with the retirement decision now supplied by the user; it is not proof of retirement. |
| Nov 12, 08:38 | Session `f3bf3651-4246-473f-9985-014a6fed25ec`, turn 0 requests a local, deterministic Kaggle-adapter/`TournamentRunner` smoke test and explicitly says not to create or execute a Kaggle Task or perform real inference. | This establishes a distinct synthetic plumbing-test purpose. |
| Nov 12, 08:42 | Same session, turn 1 asks to prepare a *real* two-model match, explicitly “not ... a synthetic integration test,” using a valid reproducible instance accepted by Phase 0. Turn 3 repeats the valid-instance requirement for the Task source. | The stated Task intent differs from the earlier local smoke-test scope. |
| Nov 12, 12:42 | Snapshot checkpoint `2187becee46a7a5fc9bf9ed8640b4723e5ddd62c` adds a Kaggle Task, a staged source package and manifest. The Task imports the existing `TournamentRunner`; the staged archive includes `domain_adapters.zip`. | This is packaging and execution integration, not evidence that `DatasetAdapterFactory` was intended to be the Task's selected instance source. |
| Nov 12, 13:05-13:24 | Session `f3bf3651-4246-473f-9985-014a6fed25ec`, turns 17-18, records the earlier QM9-retirement audit and its incomplete recovery of the adapter history. | The session states QM9 retirement as an explicit user decision, but the repository/Git evidence inspected here does not locate a contemporaneous retirement decision log or a commit that removed QM9 from active paths. |
| Nov 12, 15:37 | Checkpoint `29659d054187492415dfdeb0435fb825f4da3675` changes only `kaggle_task/quarto_two_model_match.py` and `tests/test_quarto_two_model_task.py`. | The root Task changed after the staged copy; the staged Task was not changed in this commit. |

### Exact files changed at the relevant implementation steps

The lists below are the exact paths reported by the corresponding Git snapshots.

1. **QM9 adapter/validation, `2375443`:**
   - `domain_adapters/__init__.py`
   - `domain_adapters/instance_builder.py`
   - `domain_adapters/qm9_adapter.py`
   - `phase0_foundation.py`
   - `tests/test_phase1_qm9_adapter.py`

2. **QM9 tournament pilot, `2f42aae`:**
   - `experiments/pilot_tournament/README.md`
   - `experiments/pilot_tournament/public_report.json`
   - `experiments/pilot_tournament/restricted_match_log.json`
   - `experiments/pilot_tournament/security_report.json`
   - `tests/test_tournament_harness.py`
   - `tournament_harness.py`

3. **Generic instance validator, `7d099e5`:**
   - `domain_adapters/instance_builder.py`
   - `tests/test_instance_quartet_validator.py`

4. **Generic adapter/factory checkpoint, `e7e8b1c`:**
   - `domain_adapters/__init__.py`
   - `domain_adapters/dataset_adapter.py`
   - `domain_adapters/qm9_adapter.py`
   - `tests/test_dataset_adapter_factory.py`
   - `tests/test_qm9_instance_validation_integration.py`
   - `tests/test_strict_instance_generation.py`

5. **Current `main` FMA adapter commit, `fc7e5d3`:**
   - `domain_adapters/__init__.py`
   - `domain_adapters/dataset_adapter.py`
   - `domain_adapters/fma_adapter.py`
   - `domain_adapters/instance_builder.py`
   - `domain_adapters/qm9_adapter.py`
   - `phase0_foundation.py`
   - `tests/test_dataset_adapter_factory.py`
   - `tests/test_fma_adapter.py`
   - `tests/test_instance_quartet_validator.py`
   - `tests/test_phase0_foundation.py`
   - `tests/test_qm9_instance_validation_integration.py`
   - `tests/test_strict_instance_generation.py`

6. **Kaggle Task/snapshot creation, `2187bec`:**
   - `kaggle_agent_adapter.py`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/decision_trace.py`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/domain_adapters.zip`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/kaggle_agent_adapter.py`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/manifest.sha256`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/phase0_foundation.py`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/quarto_engine.py`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/quarto_two_model_match.py`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/requirements.txt`
   - `kaggle_dataset_staging/quarto-two-model-source-v1/tournament_harness.py`
   - `kaggle_task/quarto_two_model_match.py`
   - `tests/test_kaggle_adapter_metadata.py`

7. **Later root Task adjustment, `29659d0`:**
   - `kaggle_task/quarto_two_model_match.py`
   - `tests/test_quarto_two_model_task.py`

## B. Intended architecture recovered from the implementation and records

This section separates confirmed implementation structure from design inferences; the qualification of the evidence is in section E.

### Core engine

- `quarto_engine.py` owns Quarto state transitions, legal actions, and replay. It contains no adapter or dataset selection.
- `phase0_foundation.py` defines generic domain/instance/controller contracts and the common match boundary. It currently also retains QM9-name checks and a synthetic contract fixture, so the *engine* is dataset-independent while the broader controller/framework file is not completely free of dataset-specific legacy behavior.

### Dataset adapters

- Dataset-specific ingestion belongs in `domain_adapters/`: `dataset_adapter.py` defines declarative `DatasetDefinition`, normalized `DatasetSourceData`, `DatasetAdapter`, and `DatasetAdapterFactory` (notably lines 49, 162, 177, and 350); `fma_adapter.py` and `qm9_adapter.py` supply source-specific implementations.
- The factory requires explicit source data or an explicitly registered trusted loader; it does not execute loader instructions embedded in definitions. Factory tests cover distinct definitions and an explicit loader (`tests/test_dataset_adapter_factory.py`, especially around lines 162-217).
- Keep FMA optional. The FMA report `reports/diagnostics/fma_first_accepted_instance_inspection.md` records one mathematically accepted instance with `id_level_count=2` and `structural_count=2`, but describes its musical interpretation as weak or unclear. The seed-23 holdout report records 609 strict acceptances out of 3,060 tested quartets. Neither report establishes FMA as the default source.
- QM9 retirement is an active-source decision, not a reason to delete the generic factory or conflate QM9 history with the adapter abstraction.

### Instance generation and validation

- Dataset-aware generic generation and validation are implemented in `domain_adapters/instance_builder.py` (`validate_instance_quartets` at line 106; `GenericInstanceBuilder` at line 269). Dataset adapters expose `build_instance`/`validate_instance`; `DatasetAdapter` applies its declared generation policy.
- The hard acceptance rule is conjunctive: `id_level_count > 1 AND structural_count > 1`. It is enforced by the validator (`instance_builder.py:264`), documented in `docs/evaluation_protocol.md:574-576`, and checked again at the Phase 0 boundary for adapters that require validation (`phase0_foundation.py:1326-1352`).
- The generic controller should enforce this common contract through the adapter capability, not through a dataset name. The current `domain.name == "qm9"` conditions in `phase0_foundation.py` are inconsistent with that separation.

### Tournament execution

- `TournamentRunner.run_match(adapter, instance, assignments, ...)` accepts an adapter and an explicit `InstanceSpec` (`tournament_harness.py:851-871`). That is the generic runner boundary.
- The same module currently imports `QM9Adapter` at module import (`tournament_harness.py:25`), has `make_qm9_instance()` default to `QM9Adapter()` (`:1075-1083`), and calls it from `run_pilot()` (`:1413`). Its CLI invokes the pilot (`:1486-1500` in the current snapshot). This is a legacy active QM9 selection path, not a property of the generic `run_match` API.

### Kaggle Task packaging and execution

- The Task uses `KaggleAgentAdapter` clients injected into the existing `TournamentRunner`; it does not call `DatasetAdapterFactory`.
- The staged ZIP contains `domain_adapters/__init__.py`, the generic builder/factory, FMA, and QM9 modules (`kaggle_task/quarto_two_model_match.py:53-59`; staged manifest entries at lines 14-45). `tournament_harness.py` imports `domain_adapters` at module level, and the package initializer eagerly imports both concrete adapters. This explains a possible import/package dependency; it does not establish that the Task should instantiate the factory or select any specific real dataset.
- The current root Task constructs `SyntheticAdapter`, builds `kaggle_synthetic_classic_v1`, and passes it to `run_match` (`kaggle_task/quarto_two_model_match.py:671-698`). The module-level entrypoint invokes the Task (`:789-790`). This is not merely a test helper.
- The manifest records a successful **offline fake-model** 8-action synthetic smoke and explicitly says real Kaggle inference was not run (`manifest.json:748-754`). It also says the dataset files/reports were excluded. These facts identify the recorded validation as smoke testing, but do not explain why the executable Task still uses the synthetic fixture.

## C. Current files that violate or strain the recovered architecture

1. **`phase0_foundation.py`** — `MatchSession` and `Phase0Controller` special-case `domain.name == "qm9"` and include QM9-specific failure text (`:970-989`, `:1326-1334`). This is dataset-specific policy in the common controller/framework layer. Preserve the generic capability-based strict validation; the name check is not needed to preserve the two-count rule.
2. **`tournament_harness.py`** — top-level import of `QM9Adapter`, `make_qm9_instance()` defaulting to it, and `run_pilot()` selecting it remain reachable from the standalone CLI (`:25`, `:1075-1083`, `:1413`, `:1486-1500`). This conflicts with the supplied QM9-retired decision.
3. **`domain_adapters/__init__.py`** — eager re-exports of `FMAAdapter` and `QM9Adapter` (`:12-14`) mean imports of the package initialize both specific adapters, including when a generic helper is imported. This is coupling, though the adapter implementations themselves remain outside the core files.
4. **`kaggle_task/quarto_two_model_match.py`** — the active Task path uses the four-feature `SyntheticAdapter`, not an accepted dataset adapter (`:671-698`). With exactly four features there is only one possible feature quartet; the fixture therefore cannot satisfy both required counts. The Task does not request strict validation from this fixture.
5. **Staged Task and harness sources** — the staged copy also uses `SyntheticAdapter`, and the staged harness imports/defaults to QM9. The staged archive additionally packages QM9 and FMA. These paths preserve the same issues in the deployable snapshot.

`quarto_engine.py` itself does not show dataset coupling in the current source. `quarto_runner.py` was checked for the targeted QM9/FMA/factory references and none were found. Existing QM9 experiment outputs and the adapter module are historical artifacts; their mere presence is not an active-source violation.

## D. Kaggle `SyntheticAdapter`: what is and is not established

**Confirmed smoke-test intent:** Session `f3bf3651-4246-473f-9985-014a6fed25ec`, turn 0, explicitly requests a local deterministic integration test, says it is not real Kaggle inference, and prohibits creating or executing a Kaggle Task. It specifically asks to use an existing synthetic fixture. The staged manifest independently labels its recorded execution an offline fake-model synthetic smoke.

**Confirmed Task requirement:** In turn 1, the user calls the intended matchup a real two-model match “not ... a synthetic integration test” and requires a valid reproducible instance accepted by Phase 0. Turn 3 repeats that the Task must use valid instance-construction APIs.

**Confirmed current behavior:** Despite that requirement, the executable Task itself builds and runs a synthetic instance and is invoked through `run_quarto_two_model_match.run(llm=kbench.llm)`. Therefore the current Task's `SyntheticAdapter` cannot be described as *only* test infrastructure based on code flow.

**Unresolved intent:** The smoke-test purpose is documented; a decision to leave `SyntheticAdapter` in the deployed Task is not. The evidence supports calling this a Task/requirement mismatch and a likely unintended parallel path, but no decision log explicitly calls it accidental. It is not safe to assert the intended rationale. Do not accept the current synthetic Task as a valid Quarto instance, and do not replace it by wiring in `DatasetAdapterFactory` without a separate, evidenced source-selection decision.

## E. Confirmed facts, hypotheses, and evidence gaps

### Confirmed

- Active branch is `main` at `fc7e5d355162c81c267eb3d02462539bc2283113`; the worktree was already dirty before this report.
- The current source contains the generic factory and adapters under `domain_adapters/`. Its factory and strict-generation tests are present.
- Current acceptance is conjunctive and both counts are explicitly required.
- Current engine rules are dataset-independent; current framework/harness/Task files still contain the couplings listed above.
- The two Kaggle session requests distinguish a local synthetic integration smoke from a real Task that must use a valid accepted instance.
- Current Task code uses synthetic data in the executable match path; its manifest only records fake-model offline validation, not real hosted inference.
- QM9 retirement and FMA optionality are explicit constraints in the current request and the prior audit request (session turn 17).
- The Git tree contains disconnected checkpoint histories. `e7e8b1c` has no merge base with current `HEAD`; current `main` independently contains the factory and FMA integration. Do not present `e7e8b1c` as a direct ancestor of the active FMA commit.
- No Git remote is configured in the manifest, and the authenticated Qodo repository search for “Quarto” returned no accessible repositories. Therefore no Qodo codebase/PR-history facts are available for this repository.

### Hypotheses, not established history

- The present Task's synthetic instance is probably an unintended deviation from its stated valid-instance requirement. This is a strong inference from the request and active code, not an explicit recorded decision.
- The full adapter ZIP may have been included because `TournamentRunner` imports the adapter package, whose initializer eagerly imports the concrete adapters. This is supported by current imports and package contents, but no original architecture decision log states why all members were included.
- QM9 active paths appear to be legacy pilot paths, not a regression from a known completed removal. That classification follows the earliest harness commit and absence of a later removal in recovered Git history; it does not establish the author's intent at every intermediate checkpoint.

### Missing evidence

- No repository ADR, architecture note, TODO, or decision log was found that records the complete adapter-isolation decision or a specific date/commit for QM9 retirement.
- No recovered commit removes QM9 from the harness/core, so the supplied retirement decision's implementation status cannot be backdated to a particular historical change.
- No decision explains whether the executable Kaggle Task's synthetic instance was a temporary smoke fixture, an intentional demonstration workload, or an accidental substitute for the requested accepted data source.
- Older agent session records were discoverable by title/checkpoint metadata, but their transcript contents were not available through the session-context reader in this recovery. The usable detailed session evidence is the Nov 12 local session history and Git checkpoints.
- No tests, benchmarks, or inference were run for this report. Past test counts cited above come only from the staged manifest, not fresh validation.

## F. Minimal ordered remediation plan

This is a preservation-oriented plan, not an authorization to change files.

1. **Freeze the recovered good work:** retain `DatasetAdapterFactory`, dataset definitions/loaders, generic builder, validator, tests, and both-count acceptance unchanged as the baseline. Do not recast this as missing or replace it.
2. **Retire QM9 from active execution only:** remove the hard-coded QM9 default from the active tournament CLI/harness and remove dataset-name policy from the common controller; keep historical QM9 adapter/experiment artifacts outside the active path unless separately directed. Preserve capability-based validation and both thresholds.
3. **Resolve the Task discrepancy before changing Task code:** use the original Task requirement (valid accepted instance) and contemporaneous implementation notes to establish whether `SyntheticAdapter` was temporary smoke infrastructure. If it was, confine it to offline tests; if the intended Kaggle workload is still undecided, do not claim the current Task is a valid benchmark run.
4. **Keep source choice explicit and optional:** do not make FMA the default and do not wire `DatasetAdapterFactory` into Kaggle solely because it exists. Select an adapter only after a documented source decision and verify the resulting exact 16-entity instance satisfies both counts.
5. **Reconcile the staged package after the active path is agreed:** adjust only the source dependency closure needed by that path, preserving the dataset/core boundary and regenerating the manifest/checksum together. Do not propagate stale staged QM9 behavior or silently change snapshot intent.

## Evidence sources inspected

- **Repository notes/reports/docs:** `README.md`; `docs/evaluation_protocol.md`; `reports/kaggle_model_discovery_feasibility_20261110.md`; FMA feasibility/accepted-instance/holdout reports under `reports/diagnostics/`; Kaggle staging `manifest.json`; pilot and QM9 experiment reports; a repository-wide search for architecture, decision, TODO, adapter, QM9/FMA, Task, and instance-validation references.
- **Git:** initial dirty status and active branch/HEAD; `--all` history and roots; exact file lists/statistics for commits `2375443`, `2f42aae`, `7d099e5`, `e7e8b1c`, `fc7e5d3`, `2187bec`, and `29659d0`; merge-base comparison for the disconnected factory checkpoint.
- **Copilot session history/checkpoints:** local session `f3bf3651-4246-473f-9985-014a6fed25ec`, especially turns 0-3 and 17-18; checkpoint summaries including “Preparing Kaggle Match Snapshot” and “Recovering Dataset Isolation History”; available session titles for Nov 8-12 Quarto work.
- **Qodo:** CLI 2.3.1 read-only repository discovery was attempted after the catalog check; no accessible repository matched “Quarto.” No Qodo PR-history lookup was possible without a repository.
- **Current source verification only where needed:** `quarto_engine.py`, `phase0_foundation.py`, `domain_adapters/`, `tournament_harness.py`, `quarto_runner.py`, root and staged Kaggle Task/harness sources, relevant factory/Task tests, and the staged manifest.

## Read-only and Git-state statement

No source file was edited. No test, benchmark, Kaggle inference, dependency installation, Git staging, commit, reset, checkout, or upload was performed. The sole intentional filesystem change for this task is this requested report at `reports/quarto_dataset_isolation_recovery_20261112.md`; because `reports/` was already untracked, this adds one untracked report path. No pre-existing dirty worktree content was altered, and no Git index, commit, branch, or reference was changed.
