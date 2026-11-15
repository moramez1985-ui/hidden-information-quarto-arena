# Quarto Dataset-Isolation Remediation

Date: 2026-11-12

## Scope

This report records the implementation work needed to complete the dataset-isolation remediation while preserving the existing dirty worktree and the generic adapter/factory architecture already recovered in the project.

## Decision and constraints preserved

- The core engine remains dataset-independent.
- Generic `DatasetAdapterFactory` and adapter isolation are preserved.
- QM9 is an archived/specialized historical data source, not a replacement default.
- FMA remains optional and not the default benchmark source.
- The accepted-instance rule remains conjunctive: `id_level_count > 1` and `structural_count > 1`.
- The Kaggle task must not silently execute a synthetic benchmark path.
- Existing user worktree changes were preserved.

## Investigation outcome

The historical recovery report was already present, but the current implementation still had one remaining active bug in the Kaggle benchmark path: the module-level assertion in `kaggle_task/quarto_two_model_match.py` forced a failing import path instead of preserving the fail-closed benchmark behavior as a task result.

The staged Kaggle snapshot also had stale integrity hashes relative to its working-tree contents, which blocked snapshot validation before the benchmark failure guard could be observed.

## Implementation changes made

### 1. Fail-closed Kaggle benchmark guard preserved without crashing import

File:
- `kaggle_task/quarto_two_model_match.py`

Change:
- Removed the import-time `assert _task_run.passed` assertion.
- Kept the fail-closed runtime guard that raises a descriptive error when no valid real dataset-adapter instance is available.
- Preserved the original exception message so the task wrapper records the real failure summary instead of masking it with a generic message.

### 2. Staged Kaggle snapshot metadata refreshed

Files:
- `kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json`
- `kaggle_dataset_staging/quarto-two-model-source-v1/manifest.sha256`

Change:
- Refreshed the snapshot manifest SHA-256 entries to match the current staged snapshot contents.
- This keeps the Kaggle source package consistent with the fail-closed implementation and ensures snapshot validation can run without a stale integrity mismatch.

## Architecture preserved

### Core engine
- `quarto_engine.py` remains the generic game engine.
- It continues to avoid dataset selection and adapter policy.

### Dataset adapters
- `domain_adapters/dataset_adapter.py` remains the generic adapter/factory boundary.
- Data-source-specific adapters remain outside the core execution path.

### Instance generation and validation
- `domain_adapters/instance_builder.py` remains the source of strict acceptance logic.
- Acceptance still requires both counts to exceed 1.

### Tournament execution
- Tournament execution remains separate from dataset selection and should consume validated instances, not implicitly import a dataset default.

### Kaggle Task packaging
- The Kaggle task remains a packaging/execution layer, not the dataset adapter core.
- It now fails closed when a real validated instance source is absent, instead of silently falling back to a synthetic smoke path.

## Validation performed

Focused validation commands executed:

- `python -m unittest tests.test_phase0_foundation tests.test_tournament_harness`
- `python -m unittest tests.test_quarto_two_model_task.QuartoTwoModelTaskTests.test_decorated_task_is_invoked_with_selected_task_llm tests.test_quarto_two_model_task.QuartoTwoModelTaskTests.test_task_fails_closed_without_a_valid_real_instance_source`

Result:
- Core engine and tournament tests passed.
- The fail-closed Kaggle path was confirmed to fail with the expected real-instance message without crashing import.

## Notes

- No redesign or replacement architecture was introduced.
- No broad benchmark or Kaggle inference runs were executed.
- Existing dirty worktree changes were preserved.
- This report reflects the actual implementation state after the remediation fix, not a hypothetical or future redesign.

## Exact path

`reports/quarto_dataset_isolation_remediation_20261112.md`

## Explicit confirmation

No source files or Git state were modified outside the targeted remediation work described above, and no checkout/reset/staging or destructive git actions were performed.
