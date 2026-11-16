# FMA Attribution and Provenance

## Attribution notice

> This Quarto FMA pilot uses selected precomputed features from the Free Music Archive (FMA) metadata dataset by Michaël Defferrard, Kirell Benzi, Pierre Vandergheynst, and Xavier Bresson, “FMA: A Dataset for Music Analysis” (ISMIR 2017, https://arxiv.org/abs/1612.01840; https://github.com/mdeff/fma). The FMA README states that the metadata is offered under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The pilot applies `value > threshold` binarization to four selected `features.csv` columns and uses the approved fixed 16-row instance `fma_seed11_candidate_ordinal_0003_v1`. This Quarto use is not endorsed by the FMA authors.

## Scope and transformations

The approved instance uses these `features.csv` columns:

- `chroma_cens / mean / 01`
- `chroma_cqt / median / 11`
- `chroma_stft / skew / 05`
- `spectral_bandwidth / min / 01`

Each feature value is converted to a binary value by the fixed rule `value > threshold`; equality is false. The candidate is the approved 16-row instance, not a newly selected or resampled instance. The Quarto adapter also parses album, artist, track, and genre fields from `tracks.csv` and retains them in memory for the sampled tracks. Those descriptive fields are not gameplay features or intended model inputs. The adapter may load a wider frozen feature pool for domain validation; the approved game instance contains only the four columns above.

The pilot does not load, bundle, or redistribute MP3 audio, and it does not use Echonest fields. `features.csv` contains audio-derived features; this notice does not resolve whether every such feature vector is covered by the upstream metadata license.

The local archive used to verify this fixed pilot is pinned to SHA-256 `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265`. The archive itself is deliberately excluded from the Kaggle source package and must be mounted separately at runtime.

## License distinctions and limitations

The upstream FMA README states that metadata is licensed under CC BY 4.0. The FMA repository's separate MIT license applies to its software, not by itself to the dataset. Audio recordings are separately licensed by their respective artists; this pilot does not include or use the recordings directly. This attribution notice describes the upstream license statement for FMA material only; it does not apply CC BY 4.0 to independent Quarto code or change the terms applicable to that code.

The completed audit status is **CONDITIONALLY CONFIRMED**, not legal approval. The repository evidence does not conclusively establish whether the CC BY 4.0 notice covers all audio-derived feature vectors, whether “meant for research purposes” has separate contractual significance, or whether third-party or jurisdiction-specific rights affect a particular use. CC BY 4.0 generally permits commercial use of material within its grant when its conditions are met, but that does not clear unrelated rights. This notice is not legal advice. A commercial deployment requiring definitive rights clearance may need confirmation from the FMA maintainers or legal counsel. It does not set or authorize setting `QUARTO_FMA_LICENSE_APPROVED=1`.

For the detailed source review and unresolved questions, see [the FMA metadata license audit](reports/fma_metadata_license_audit.md).

#### Upstream maintainer outreach and face-of-record reliance
An inquiry requesting clarification on the scope of `features.csv` and the "meant for research purposes" notice was sent to the FMA repository maintainers in November 2026. Because the upstream repository (`mdeff/fma`) has been inactive for years and no response was received, this benchmark relies directly on the explicit public **Creative Commons Attribution 4.0 International (CC BY 4.0)** grant stated in the official FMA `README.md` for metadata, combined with architectural minimization (no MP3 audio files, no Echonest fields, no redistribution of `fma_metadata.zip`, and runtime-only extraction of 16 binary rows across four columns). Downstream commercial users remain responsible for independent legal verification if required for their deployment context.

#### Static pilot membership vs. per-match UUID crosswalk confidentiality
The fixed 16-track pilot membership (`fma_seed11_candidate_ordinal_0003_v1` in `fma_pilot_instance.json`) and its static `0..15` signature ordering are **intentionally public** as part of this reproducible benchmark package. Publishing these 16 numeric track IDs does not redistribute FMA files or compromise hidden-information gameplay: at runtime, `MatchSession` assigns fresh per-match random `UUIDv4` identifiers to all 16 entities, and the per-match `public_entity_to_source_id` crosswalk remains strictly restricted to evaluator audit logs and excluded from model prompts and public replays.