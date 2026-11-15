# FMA Metadata Attribution Implementation

**Status:** Implemented and locally validated. No legal approval is claimed.

## Summary

Added a reusable FMA attribution and provenance notice to the Quarto documentation and the Kaggle source snapshot. The notice preserves the audit's **CONDITIONALLY CONFIRMED** conclusion, identifies the pilot's actual feature selection and threshold transformation, distinguishes metadata from code and audio licenses, and leaves unresolved rights questions explicit. The FMA archive and its hash pins were not changed.

## Files changed

| File | Change |
|---|---|
| [README.md](../README.md) | Added a link to the attribution notice and summarized the conditional audit conclusion and commercial-use caveat. Existing README changes were preserved. |
| [FMA_ATTRIBUTION.md](../FMA_ATTRIBUTION.md) | Added the repository-level attribution, feature provenance, license distinctions, and limitations. |
| [staged ATTRIBUTION.md](../kaggle_dataset_staging/quarto-two-model-source-v1/ATTRIBUTION.md) | Added the corresponding notice to the source package so it travels with the staged files. |
| [root Task source](../kaggle_task/quarto_two_model_match.py) | Added `ATTRIBUTION.md` to the exact expected source-snapshot file set. No match, model, or engine behavior changed. |
| [staged Task source](../kaggle_dataset_staging/quarto-two-model-source-v1/quarto_two_model_match.py) | Kept identical to the root Task source and updated its same exact-file allowlist. |
| [staging manifest](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.json) | Added attribution status/scope metadata and the staged notice's payload hash/size; updated payload count and rights-gate language. The FMA archive remains explicitly excluded. |
| [manifest checksum](../kaggle_dataset_staging/quarto-two-model-source-v1/manifest.sha256) | Refreshed SHA-256 for the updated manifest. |
| This report | Recorded the implementation, attribution text, checks, and remaining caveats. |

No changes were made to the approved instance artifact, its provenance, the FMA archive, the selected model pair, or Quarto engine behavior.

## Exact attribution text

> This Quarto FMA pilot uses selected precomputed features from the Free Music Archive (FMA) metadata dataset by Michaël Defferrard, Kirell Benzi, Pierre Vandergheynst, and Xavier Bresson, “FMA: A Dataset for Music Analysis” (ISMIR 2017, https://arxiv.org/abs/1612.01840; https://github.com/mdeff/fma). The FMA README states that the metadata is offered under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The pilot applies `value > threshold` binarization to four selected `features.csv` columns and uses the approved fixed 16-row instance `fma_seed11_candidate_ordinal_0003_v1`. This Quarto use is not endorsed by the FMA authors.

This same attribution statement is present in the repository notice and staged notice.

## Provenance and license distinctions documented

- The four approved columns are `chroma_cens / mean / 01`, `chroma_cqt / median / 11`, `chroma_stft / skew / 05`, and `spectral_bandwidth / min / 01`; the fixed rule is `value > threshold`, with equality false.
- The candidate remains the approved fixed 16-row instance. No reselection, resampling, or source archive replacement occurred.
- The adapter parses album, artist, track, and genre metadata from `tracks.csv` and retains it in memory for the sample. Those fields are not gameplay features or intended model inputs. The staged Task result does not include that descriptive metadata.
- The pilot does not load or redistribute MP3 audio and does not use Echonest fields. The metadata archive is excluded from staging and must remain a separately mounted runtime input.
- The upstream README's CC BY 4.0 statement for metadata is distinguished from the FMA repository software's MIT license and the separate licenses chosen by artists for audio recordings. The notice does not apply CC BY 4.0 to independent Quarto code.
- The legal scope is not overstated: coverage of every audio-derived feature vector, the meaning of “meant for research purposes,” and third-party or jurisdiction-specific rights remain unresolved. CC BY 4.0 generally permits commercial use for material within its grant when its conditions are met, but this is not legal advice or definitive clearance. Commercial deployment requiring definitive rights clearance may need confirmation from FMA maintainers or legal counsel.
- Neither the notice nor this implementation sets or authorizes setting `QUARTO_FMA_LICENSE_APPROVED=1`.

The full source analysis remains in [the completed FMA license audit](fma_metadata_license_audit.md).

## Validation results

1. **Manifest JSON:** parsed successfully.
2. **Manifest checksum:** `manifest.sha256` matches `manifest.json` SHA-256 `cdbff019c1c700a7bb8e12040f4cf942471b334960886f43a1205b698455a4b7`.
3. **Payload inventory:** 11 staged payload files exactly match the `included_files` inventory; each file's SHA-256 and byte size match its manifest entry.
   The staged `ATTRIBUTION.md` is 3,399 bytes with SHA-256 `9297a2b92fb7a1a48c809451dd6d9f482f58b58f08d610ab6c68eb4238c3e6d8`.
4. **Snapshot validator:** the production `_validate_source_snapshot` function returned `true` using a stubbed `kaggle_benchmarks` module. This did not invoke the Task function, a hosted Task, or any model.
5. **Task parity:** root and staged `quarto_two_model_match.py` are byte-identical.
6. **Adapter archive:** all five listed members match the manifest inventory and existing archive validation.
7. **FMA archive exclusion:** no `fma_metadata.zip` exists in the staged source directory. The pinned archive SHA-256 remains `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265`.
8. **Formatting:** `git diff --check` passed; the new Markdown files and manifest were checked for whitespace and JSON validity.

No broad test suite was run: changes are documentation and snapshot-inventory metadata only. The directly relevant production snapshot validator was exercised without running the Kaggle Task. No dependencies were installed, no upload or publication occurred, and no live Kaggle Task or model was used.

## Remaining legal caveats

The implementation documents—but does not resolve—the audit's conditional status. The upstream README supports CC BY 4.0 treatment of FMA metadata, but the repository evidence does not conclusively determine whether every audio-derived feature vector is covered, whether the research-purpose wording has separate contractual effect, or whether third-party and jurisdiction-specific rights affect a particular use. Do not treat the documentation, package manifest, or runtime acknowledgment variable as a legal determination.
