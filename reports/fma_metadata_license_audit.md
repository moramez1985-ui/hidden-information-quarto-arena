# FMA Metadata License and Provenance Audit

**Audit date:** 2026-11-14

**Approved instance:** `fma_seed11_candidate_ordinal_0003_v1`

**Final status: CONDITIONALLY CONFIRMED**

This is a repository and source-notice audit, not legal advice or legal approval. The approved local archive is byte-for-byte consistent with both supplied checksum pins, and the pilot's selected gameplay values come from the upstream `features.csv`. The upstream README expressly says FMA metadata is CC BY 4.0, but it does not separately enumerate the licensed files or explain the rights basis for audio-derived feature vectors. Treat the intended use as conditionally supported by the published notice; obtain a rights-holder or legal confirmation before treating it as approved for a commercial or otherwise high-risk release. The Kaggle license acknowledgment was not set.

## 1. Local archive identity and integrity

The local archive [data/fma_metadata.zip](../data/fma_metadata.zip) exists.

| Digest | Local result | Expected/reference | Result |
|---|---|---|---|
| SHA-256 | `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265` | Pinned Quarto value: `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265` | **MATCH** |
| SHA-1 | `f0df49ffe5f2a6008d7dc83c6915b31835dfe733` | Upstream README: `f0df49ffe5f2a6008d7dc83c6915b31835dfe733` | **MATCH** |

The internal `fma_metadata/checksums` file lists SHA-1 values for ten data members. All ten matched the bytes of their corresponding ZIP members. The archive's own `fma_metadata/README.txt` and `fma_metadata/checksums` are not entries in that checksum list.

The ZIP contains:

| Member | Audit relevance |
|---|---|
| `fma_metadata/README.txt` | Describes the archive as part of FMA; says each MP3 is licensed by its artist and points to the checksum list. It does not state the metadata license. |
| `fma_metadata/checksums` | SHA-1 list for the ten data members; all verified. |
| `fma_metadata/not_found.pickle` | Auxiliary lookup data. |
| `fma_metadata/raw_genres.csv`, `genres.csv` | Genre metadata. |
| `fma_metadata/raw_albums.csv`, `raw_artists.csv`, `raw_tracks.csv`, `tracks.csv` | Album, artist, and track metadata. |
| `fma_metadata/features.csv` | Precomputed feature matrix. This is the source of the pilot's four selected gameplay columns. |
| `fma_metadata/raw_echonest.csv`, `echonest.csv` | Echonest-provided audio-feature data, described separately in the upstream README. |

There are no MP3 audio files in this archive. The audio subsets are separate downloads. The archive README's artist-license statement is therefore a warning about the separate audio, not evidence that MP3s are included here or that the metadata archive itself has an artist-by-artist audio license.

## 2. Pilot data lineage and scope

The approved artifact [fma_pilot_instance.json](../fma_pilot_instance.json) fixes the candidate ID, archive digest, four feature IDs and thresholds, and the exact 16-row candidate. [fma_pilot.py](../fma_pilot.py#L24) rejects a different feature list, threshold set, or candidate artifact; it reloads the fixed subset rather than selecting a replacement. Its source provenance points to line 4 of the retained [seed-11 feasibility record](diagnostics/fma_feasibility_seed11_20261109_204633_336807.jsonl#L4).

The four approved source columns are:

| Quarto feature ID | Hierarchical `features.csv` column | Frozen threshold |
|---|---|---:|
| `fma:chroma_cens:mean:01` | `chroma_cens / mean / 01` | `0.25517144799232483` |
| `fma:chroma_cqt:median:11` | `chroma_cqt / median / 11` | `0.4525887370109558` |
| `fma:chroma_stft:skew:05` | `chroma_stft / skew / 05` | `0.3928850293159485` |
| `fma:spectral_bandwidth:min:01` | `spectral_bandwidth / min / 01` | `290.3798522949219` |

I read the three-level header and the 16 approved rows directly from the hashed `features.csv`; each of these four exact column tuples was present once. The adapter's [column selection and feature reader](../domain_adapters/fma_adapter.py#L206) resolve the same tuples and derive Boolean values by comparing each selected feature value to its frozen threshold.

**What is and is not used:**

- **Used in the approved game instance:** the four listed columns from `features.csv`, transformed by the strict `value > threshold` rule. The FMA adapter's frozen pool contains 18 feature definitions and reads those pool values for domain loading/validation; the approved pilot loader then builds the game instance from exactly the four fixed IDs ([feature pool](../domain_adapters/fma_adapter.py#L43), [fixed pilot selection](../fma_pilot.py#L24)). The other 14 are not attributes of this approved instance or intended model inputs. The upstream README describes `features.csv` as common features extracted with librosa.
- **Not used:** Echonest fields. The adapter reads `tracks.csv` and `features.csv`, not `echonest.csv` or `raw_echonest.csv`. The four selected feature families are not Echonest fields.
- **Audio:** no audio is loaded or decoded. The archive has no MP3 members and the adapter records `audio_files_used: false`. The feature vectors are nevertheless audio-derived, so this audit cannot establish that the feature outputs are free of every right that might attach to the underlying recordings.
- **Artist and descriptive metadata:** the adapter parses album title, artist name, track title, top-level genre, and genres from `tracks.csv` for the metadata/feature join and retains those fields for the 25,000-track sample in `track_metadata` ([reader and stored metadata](../domain_adapters/fma_adapter.py#L150)). That is a real in-memory use of metadata. It is not used as a Quarto gameplay feature: `DatasetSourceData.values` is built from the selected feature values, and the adapter marks `descriptive_metadata_used_as_features: false` ([feature-value construction and provenance](../domain_adapters/fma_adapter.py#L350)). The Kaggle Task's returned result contains model/match fields and a public replay, not the adapter's `track_metadata`; it explicitly does not emit a private trace ([Task result construction](../kaggle_task/quarto_two_model_match.py#L795)). Thus artist fields are parsed and retained by the adapter, but are not a model input or an intended published Task-result field.

The feature matrix is a transformed representation of audio, not the audio itself. The dataset README attributes its feature extraction to librosa; Quarto consumes the already-computed CSV values and does not redistribute FMA's extraction code as part of this pilot. Whether any rights in recordings, performances, or other source material constrain particular derived features is not answered by the repository notices.

## 3. Upstream license and notice findings

The upstream [FMA README](https://github.com/mdeff/fma/blob/master/README.md) (accessed 2026-11-14) says:

- `fma_metadata.zip` distributes metadata and features for tracks.
- `features.csv` contains common features extracted with librosa.
- `echonest.csv` contains audio features provided by Echonest for a subset of tracks.
- Metadata is released under the Creative Commons Attribution 4.0 International License (CC BY 4.0).
- The FMA authors do not hold copyright on the audio and distribute it under the license chosen by each artist.
- The dataset is “meant for research purposes.”
- The authors ask users of code or data to cite the FMA work.

The README links the repository's [LICENSE.txt](https://raw.githubusercontent.com/mdeff/fma/master/LICENSE.txt), which grants MIT rights in the repository's **software**. It does not replace the README's separate CC BY 4.0 notice for metadata, and it does not purport to license the audio. The archive-internal README does not contain the CC BY notice or the research-purpose sentence.

### Scope and effect of “meant for research purposes”

The README groups metadata and precomputed features in `fma_metadata.zip`, then expressly states that metadata is CC BY 4.0. That supports the reasonable reading that the distributed metadata package, including its feature table, is offered under CC BY 4.0. However, the notice does not enumerate every CSV or expressly discuss features computed from audio. The archive-internal README is less specific. Accordingly, coverage of `features.csv` is supported by the upstream README's organization and wording, but remains a point to confirm if a definitive rights opinion is required.

“Meant for research purposes” appears as a descriptive statement, not as a defined CC BY condition or an express noncommercial-use clause. CC BY 4.0's deed says sharing and adapting are permitted “for any purpose, even commercially”; the license text grants reproduction, sharing, and adaptation subject to its conditions. The research-purpose sentence should therefore not be silently treated as an extra CC BY restriction, nor ignored as irrelevant context. It may express the authors' expected use, but the README does not explain whether it was intended to qualify the metadata grant or refer to the dataset generally. If planned commercial use depends on that ambiguity, ask the FMA maintainers or counsel rather than resolving it by assumption.

## 4. CC BY 4.0 obligations relevant to this pilot

This is a summary of the official [CC BY 4.0 deed](https://creativecommons.org/licenses/by/4.0/) and [legal code](https://creativecommons.org/licenses/by/4.0/legalcode.en), accessed 2026-11-14. The legal code controls over this summary.

- **Attribution:** if sharing the licensed material, including modified material, give appropriate credit; retain supplied creator, copyright, license, and disclaimer notices where applicable; link to the source and license where reasonably practicable; and do not imply endorsement.
- **Modifications:** identify that changes were made and retain an indication of previous modifications. The pilot binarizes selected feature columns using fixed thresholds and selects a 16-row instance; a publication should identify those transformations.
- **Redistribution:** CC BY 4.0 permits sharing the licensed material and adaptations subject to attribution. Recipients receive the license offer. Do not impose extra legal terms or effective technological measures that restrict rights granted by CC BY 4.0 on the licensed material.
- **Commercial-use assessment (non-legal advice):** the license permits sharing and adaptation for commercial as well as noncommercial purposes; it contains no NonCommercial (NC) restriction. This applies only to material actually within the grant and does not clear unrelated third-party rights.
- **Database rights:** CC BY 4.0 defines Copyright and Similar Rights to include sui generis database rights and Section 4 grants extraction, reuse, reproduction, and sharing of all or a substantial part of a database where the licensor has those rights. Sharing all or a substantial part invokes the attribution conditions; including all or a substantial part in another protected database can make that database adapted material. Whether such rights exist and apply depends on jurisdiction and the licensor's authority.
- **Other rights and disclaimers:** the license does not grant every possible right (for example, publicity, privacy, moral, trademark, or patent rights), and it provides the material without warranties. Attribution does not imply endorsement.

## 5. Intended publication of derived benchmark artifacts

The current Kaggle Task code returns model metadata, match outcome and a projected public replay; it does not return the source track IDs, artist/album/title metadata, raw feature values, the archive, or the restricted evaluator crosswalk. The private trace is marked not emitted. This is an inspection of the local implementation, not evidence of a hosted run or actual publication.

For a publication containing only those match/replay fields, the disclosed output is derived from the FMA-powered instance but does not reproduce the archive or its descriptive metadata. The selected 16-by-4 feature subset is quantitatively small compared with the full feature table, but quantitative size alone does not settle whether an extraction is “substantial” under all database-right regimes, nor whether transformed binary outputs remain protected material. The pilot's thresholds and derived gameplay behavior also come from the dataset. Therefore:

1. Include FMA attribution and a clear modification statement in any public report, benchmark card, Task description, or artifact metadata that describes or distributes results based on this pilot. This is the prudent course and may be required if the published material is treated as licensed or adapted material.
2. Do not publish the FMA archive, raw feature rows, source-ID crosswalk, or retained private trace as part of this result without a separate scope and rights review.
3. If distributing a new dataset with selected source rows or substantially more FMA content, reassess CC BY attribution, database rights, the exact license scope, and any third-party rights first.

**Recommended attribution text:**

> This Quarto pilot uses selected precomputed features from the Free Music Archive (FMA) metadata dataset by Michaël Defferrard, Kirell Benzi, Pierre Vandergheynst, and Xavier Bresson, “FMA: A Dataset for Music Analysis” (ISMIR 2017, https://arxiv.org/abs/1612.01840; https://github.com/mdeff/fma). The upstream README states that the metadata is licensed under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/. Quarto selected four `features.csv` columns, applied fixed threshold binarization, and used an approved 16-row pilot instance. This use is not endorsed by the FMA authors.

Adjust the description if the published artifact uses different features, includes more data, or modifies the process. Retain any source notices that accompany the material being redistributed.

## 6. Independent Library of Congress reference

The supplied [Library of Congress record](https://www.loc.gov/item/2018655052/) was requested on 2026-11-14, but the page and its JSON form returned HTTP 403 to the available reader. Its contents could not be independently inspected and are not relied upon for the license conclusion. In any event, a catalog record would be corroborative provenance, not a substitute for the applicable license notice or rights-holder confirmation.

## 7. Unresolved legal and provenance questions

1. Does the upstream CC BY 4.0 statement clearly cover each file in `fma_metadata.zip`, particularly librosa-derived `features.csv` values, or are there any exceptions not expressed in the README?
2. Did the parties who applied CC BY 4.0 have authority to license all relevant metadata/database rights, and, for the selected feature values, any rights implicated by their derivation from artist-licensed recordings?
3. Was “meant for research purposes” intended only as a description or as a separate contractual/use condition? The public README does not resolve this.
4. Which jurisdiction's database-right rules govern a particular publication, and does the specific derived output constitute a protected or substantial extraction? This audit cannot make that determination.
5. Are there additional privacy, personality, moral, contractual, or other rights concerning the retained artist/track metadata or the audio-derived data that matter to a particular commercial deployment? No such determination is made here.
6. This review did not inspect separate artist licenses for the audio, Echonest terms, or external terms not present in the archive and upstream README. Neither audio nor Echonest fields are used as pilot gameplay inputs.

## 8. Source references and access record

| Source | Access / use |
|---|---|
| [FMA upstream README](https://github.com/mdeff/fma/blob/master/README.md) | Accessed 2026-11-14. Dataset contents, feature extraction, Echonest distinction, archive SHA-1, citation request, metadata CC BY 4.0 notice, audio-license distinction, and research-purpose wording. |
| [FMA upstream LICENSE.txt](https://raw.githubusercontent.com/mdeff/fma/master/LICENSE.txt) | Accessed 2026-11-14. MIT license for the repository's code; separate from the metadata notice. |
| [CC BY 4.0 deed](https://creativecommons.org/licenses/by/4.0/) and [legal code](https://creativecommons.org/licenses/by/4.0/legalcode.en) | Accessed 2026-11-14. Attribution, commercial permission, modification, redistribution, database-right, and other-right terms. |
| [Library of Congress FMA record](https://www.loc.gov/item/2018655052/) | Requested 2026-11-14; HTTP 403. Not independently inspected or relied upon. |
| Local [archive](../data/fma_metadata.zip), [pilot artifact](../fma_pilot_instance.json), [pilot loader](../fma_pilot.py), [FMA adapter](../domain_adapters/fma_adapter.py), and [Task implementation](../kaggle_task/quarto_two_model_match.py) | Inspected locally on 2026-11-14. Local bytes and code establish the pinned archive, selected feature paths, metadata parsing, and intended Task result shape. |

**Final status — CONDITIONALLY CONFIRMED:** the archive identity and pilot data lineage are verified; the upstream README expressly licenses FMA metadata under CC BY 4.0 and CC BY permits commercial reuse when its terms are met. The exact license coverage of audio-derived feature vectors and the ambiguous research-purpose wording, together with third-party/jurisdictional rights, remain outside what repository evidence alone can conclusively establish. No legal approval is claimed.
