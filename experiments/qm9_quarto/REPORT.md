# QM9 Hidden-Feature Quarto Experiment

## Scope and status

This is an offline, reproducible feasibility experiment. It did not modify the existing game engine, benchmark, frozen dataset, or prior experiment files, and it did not start a live game or create a hidden entity-to-piece mapping.

## Dataset provenance and normalization

- Original QM9 source page: https://quantum-machine.org/datasets/
- Source: QM9 original XYZ archive; file ID 3195389 via https://ndownloader.figshare.com/files/3195389.
- Dataset version: Original QM9 release described in Ramakrishnan et al. (2014); archive checksum pinned below.
- Source publication: Ramakrishnan et al., Quantum chemistry structures and properties of 134 kilo molecules, Scientific Data 1 (2014). DOI `10.1038/sdata.2014.22`.
- Publication license: CC BY-NC-SA 4.0 per Crossref metadata; this applies to the article and is not evidence of the separate raw-archive license.
- Preserved archive: `dsgdb9nsd.xyz.tar.bz2` (86,144,227 bytes).
- SHA-256: `3a63848ac80691bdb8d41834b575afad345b9300d7a2db0c38adb7f6eaa8360c`.
- XYZ records in archive: 133,885.
- Successfully parsed and sanitized entities: 133,884.
- Excluded records: 1.
- Repeated source IDs: 0.
- Repeated canonical isomeric structures: 87.
- Non-isomeric graphs with multiple isomeric SMILES: 0.
- License and redistribution terms: The accessible Figshare download response did not expose a license for the raw archive. The article is indexed as CC BY-NC-SA 4.0, but that must not be assumed to license the archive. Verify archive-specific reuse and redistribution terms before redistributing it.

Source identity is preserved independently from canonical graph identity. Records are not merged by canonical SMILES. Canonical isomeric and non-isomeric SMILES, molecular formula, heavy atom count, formal charge, source SMILES/InChI, and explicit/implicit hydrogen counts are included in the entity manifest.

## Scientific feature registry

- Scientifically valid feature definitions: 20.
- Gameplay-eligible features with population variance: 18.
- Constant features retained in the scientific registry: 2.
- Exact semantic duplicate groups: 0.
- Dataset-level exact duplicate pairs: 1.
- Dataset-level complement pairs: 0.

The complete machine-readable registry is in `feature_registry.csv`. It documents graph predicates, RDKit version, sanitization/aromaticity assumptions, hydrogen semantics, prevalence, dependencies, and gameplay eligibility. Correlation is descriptive and is not used as an exclusion criterion.

## Feature dependencies and associations

- Definition-guaranteed or QM9-domain implications recorded: 16.
- Empirical implications observed over the full normalized QM9 population: 44.
- Pairwise phi associations: 153.

Implication constrains validity but does not collapse feature identities. Full-population implication is labeled empirical unless guaranteed by the predicate definitions or QM9 domain. Dataset-level complements and exact duplicates are accounted for separately.

## Random sample and quartet results

- Uniform random samples: 1,024 of 16 entities each, without replacement.
- Public seed: 20261108.
- Samples admitting at least one valid quartet: 0/1,024 (0.000%).
- Maximum raw valid semantic quartets in one sample: 0.
- Sum of raw valid semantic quartets across samples: 0.
- Sum after exact semantic duplicate handling: 0.
- Sum after dataset-level exact duplicate handling: 0.
- Sum after complement-equivalence handling: 0.
- Sum of game-structurally distinct valid quartets across samples: 0.
- Samples with any game-structural class: 0.

Quartet counts and rejection counts are reported by sample in `results.json`; the raw-quartet-count distribution is in `validation_report.json`. A quartet is valid only when all 16 signatures occur exactly once. Game-structural equivalence canonicalizes entity-to-signature mappings under bit permutations and independent global bit complements.

### Quartet rejection accounting (summed over samples)

- `invalid_rejected_by_exact_duplicate_or_complement_constraint`: 0.
- `invalid_rejected_by_full_dataset_logical_dependencies`: 2,629,632.
- `invalid_rejected_by_sample_observed_dependencies`: 433,801.
- `invalid_rejected_by_other_observed_signature_constraints`: 70,007.

## Draft-stage ambiguity

- Successful samples with draft prefixes to analyze: 0.
- Extendable nonterminal ownership-labeled prefixes analyzed: 0.
- Semantic remaining-hypothesis distribution: `{}`.
- Game-structural remaining-hypothesis distribution: `{}`.

The draft state model treats accepted feature identities as an unordered prefix labeled by owner and considers every assignment with two final features per player. No proposer turn schedule is imposed because none is defined in this experiment brief. Counts are hypotheses, not entropy. No ambiguity threshold is imposed.

## Suitability, limitations, and next step

QM9 is a plausible first molecular domain for controlled, graph-defined feature experiments, but it is a computed, highly selected chemical-space dataset rather than a representative sample of all real molecules. A live benchmark should not be claimed based only on the existence of valid quartets; the measured draft ambiguity distribution and source-license status must be reviewed first.

Known limitations include RDKit's chosen aromaticity and sanitization conventions, deliberately narrow SMARTS definitions, empirical rather than universal full-dataset implications, QM9 sampling bias, and the unverified license/redistribution terms. The next step is to verify the authoritative Figshare reuse terms, review feature definitions, and assess whether the measured random-sample and draft distributions meet a pre-registered benchmark criterion.

## Reproducibility

- Python 3.14.0; RDKit 2026.09.1; NumPy 2.5.4; pandas 3.1.1.
- Sample reproducibility: Passed: first sample exactly reproduced from a new generator with the same seed.
- Outputs are confined to `experiments/qm9_quarto/`.
- No game, tournament, engine state, or hidden piece mapping was used.
