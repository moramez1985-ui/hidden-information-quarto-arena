# FMA Independent Holdout Feasibility - Seed 23

## Experimental design

This fixed-feature, fixed-threshold holdout tests whether the seed-11 structural-ambiguity results recur on unseen tracks. It reuses the exact 18 feature IDs, source columns, feature-pool order, original seed-11 median thresholds, strict binary rule, deterministic one-entity-per-signature construction logic, and existing `validate_instance_quartets()` implementation. No feature or threshold was reselected or optimized.

- Archive: `D:\CODES\quarto\data\fma_metadata.zip`; 358,412,441 bytes; SHA-256 `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265` (matches original: **True**).
- Original report: `reports\diagnostics\fma_feasibility_seed11_20261109_204633_336807.jsonl`; seed 11; 25,000 tracks.
- Holdout seed: 23; sample size 25,000; Python 3.14.0, pandas 3.1.1, NumPy 2.5.4.
- Ordered feature-pool SHA-256: `1f2f4b59f1edda91ac7cfacfd55bc383d9362167b668b02a57e96d090a5600be`.
- Threshold-configuration SHA-256: `dfcc00b3b4e780e4271007ae6164792d51824b95a651647d7c3bf7502a9052a6`.
- Binary rule: `value > original seed-11 median`; ties are false.
- Candidate order: `itertools.combinations` over the frozen feature-pool order; exactly 3,060 quartets.
- Entity selection: existing generic deterministic builder helper; local `random.Random(11)`, one selection per feasible quartet.
- Acceptance: `id_level_count > 1 AND structural_count > 1`.

## Disjoint sampling proof

- Reconstructed seed-11 IDs with `sorted(Random(11).sample(sorted(all_numeric_track_ids), 25000))`; membership SHA-256 `d0e1496b677d2f5c7aa7bb2870ba4eb388cdfea2298b3dd3893a1d0942724610`.
- Removed all seed-11 IDs before sampling the holdout from sorted remaining IDs with `Random(23)`, then sorted holdout IDs.
- Holdout contains 25,000 distinct IDs; intersection with seed 11 is 0; membership SHA-256 `05a78b176c2eb2c703a63207506cc58468e32f9bdf1ac43835e82471a5de31a5`.
- All 450,000 frozen source values were finite; no holdout rows were dropped or imputed.

## Frozen features and thresholds

| Feature ID | Original source column (family / statistic / coordinate) | Original seed-11 threshold |
|---|---|---:|
| `fma:chroma_cens:mean:01` | `chroma_cens / mean / 01` | 0.25517144799232483 |
| `fma:chroma_cqt:median:11` | `chroma_cqt / median / 11` | 0.45258873701095581 |
| `fma:chroma_stft:skew:05` | `chroma_stft / skew / 05` | 0.39288502931594849 |
| `fma:mfcc:kurtosis:08` | `mfcc / kurtosis / 08` | 0.15643799304962158 |
| `fma:rmse:min:01` | `rmse / min / 01` | 3.3142379834316671e-05 |
| `fma:spectral_bandwidth:min:01` | `spectral_bandwidth / min / 01` | 290.37985229492188 |
| `fma:spectral_centroid:kurtosis:01` | `spectral_centroid / kurtosis / 01` | 6.2586250305175781 |
| `fma:spectral_contrast:skew:07` | `spectral_contrast / skew / 07` | -0.40135782957077026 |
| `fma:spectral_rolloff:max:01` | `spectral_rolloff / max / 01` | 9463.8427734375 |
| `fma:tonnetz:skew:05` | `tonnetz / skew / 05` | 0.015766769647598267 |
| `fma:zcr:skew:01` | `zcr / skew / 01` | 2.4203286170959473 |
| `fma:chroma_cens:kurtosis:12` | `chroma_cens / kurtosis / 12` | -0.17919006943702698 |
| `fma:chroma_cqt:kurtosis:08` | `chroma_cqt / kurtosis / 08` | -0.74383246898651123 |
| `fma:chroma_stft:std:09` | `chroma_stft / std / 09` | 0.26742768287658691 |
| `fma:mfcc:skew:15` | `mfcc / skew / 15` | 0.0039206310175359249 |
| `fma:spectral_contrast:max:01` | `spectral_contrast / max / 01` | 59.436477661132812 |
| `fma:tonnetz:skew:03` | `tonnetz / skew / 03` | 0.020528830587863922 |
| `fma:chroma_cens:skew:03` | `chroma_cens / skew / 03` | 0.25180205702781677 |

## Comparison with seed 11

| Metric | Seed 11 | Seed 23 holdout |
|---|---:|---:|
| Sample size | 25,000 | 25,000 |
| Sample overlap | N/A | 0 |
| Candidate quartets | 3,060 | 3,060 |
| Feasible candidates | 3,060 | 3,060 |
| `id_level_count > 1` | 590 | 653 |
| `structural_count > 1` | 541 | 609 |
| `id_level_count > 1`, `structural_count = 1` | 49 | 44 |
| Strictly accepted | 541 (17.68%) | 609 (19.90%) |
| Acceptance-rate difference | N/A | +2.22 percentage points |

### ID-level count distribution

| Count | Seed 11 | Seed 23 holdout |
|---:|---:|---:|
| 1 | 2,470 | 2,407 |
| 2 | 453 | 514 |
| 3 | 90 | 99 |
| 4 | 31 | 31 |
| 5 | 9 | 8 |
| 6 | 4 | 0 |
| 7 | 2 | 1 |
| 8 | 1 | 0 |

### Structural-class count distribution

| Count | Seed 11 | Seed 23 holdout |
|---:|---:|---:|
| 1 | 2,519 | 2,451 |
| 2 | 411 | 476 |
| 3 | 87 | 97 |
| 4 | 30 | 27 |
| 5 | 7 | 9 |
| 6 | 4 | 0 |
| 7 | 2 | 0 |

### Rejection-count distribution

Counts are candidate-level reason incidences and can overlap. `no_signature_coverage` is reported separately for infeasible candidates; those candidates receive no validator call.

| Rejection category | Seed 11 | Seed 23 holdout |
|---|---:|---:|
| `no_signature_coverage` | 0 | 0 |
| `only_one_id_level_quartet` | 2,470 | 2,407 |
| `only_one_structural_class` | 2,519 | 2,451 |

## Interpretation and limitations

The holdout produced 609 accepted candidates (19.90%), versus 541 (17.68%) in seed 11. Its structural-count distribution is `{1: 2451, 2: 476, 3: 97, 4: 27, 5: 9}`, compared with `{'1': 2519, '2': 411, '3': 87, '4': 30, '5': 7, '6': 4, '7': 2}` in seed 11. The result supports conditional recurrence of structural ambiguity on this disjoint sample, but the acceptance rate and distribution should be compared rather than treating a nonzero result alone as generalization.

The conclusion is limited to one 25,000-track holdout, the frozen seed-11 feature pool and thresholds, and one deterministic entity selection per feasible quartet. It does not test alternative selections, other thresholds, other feature sets, all FMA tracks, or musical validity. The generic validator establishes combinatorial structure, not acoustic or musical meaningfulness.

## Integrity and runtime

- Evaluated all 3,060 quartets; feasible 3,060; validator calls 3,060.
- Strictly accepted: 609; duplicate entity selections across quartets: 0.
- Elapsed time through the last candidate record: 472.151 seconds.
- JSONL was parsed back before finalization and contains one record per ordinal; validated candidates contain 16 distinct IDs covering signatures 0 through 15 exactly once.
- No source code, source archive, or original report was modified; no downloads, audio processing, genre features, model calls, tournaments, or alternative-selection search were used.

## Conclusion

Structural ambiguity recurs conditionally on this disjoint holdout using the frozen features and thresholds. The holdout acceptance rate is not lower than seed 11.
A second independent holdout is the smallest next experiment for assessing sample-to-sample stability.
