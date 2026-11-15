# Email draft: FMA metadata and feature rights clarification

**To:** FMA dataset maintainers

**Subject:** Clarification on FMA metadata/features licensing for a derived Quarto benchmark

Hello FMA maintainers,

We are preparing a small Quarto benchmark instance based on the FMA metadata archive and would appreciate any source-level clarification you are able to provide. We understand that you are not required to provide legal advice; a pointer to relevant documentation or a suitable contact would also be helpful.

The FMA README describes `fma_metadata.zip` as containing metadata and features, says that metadata is released under CC BY 4.0, and separately notes that the dataset is “meant for research purposes.” Our local copy matches both published archive checksums:

- SHA-1: `f0df49ffe5f2a6008d7dc83c6915b31835dfe733`
- SHA-256: `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265`

The proposed use is limited to the approved, fixed 16-entity Quarto instance `fma_seed11_candidate_ordinal_0003_v1`. It uses four selected columns from `features.csv`:

- `chroma_cens / mean / 01`
- `chroma_cqt / median / 11`
- `chroma_stft / skew / 05`
- `spectral_bandwidth / min / 01`

Each selected value is binarized using a fixed threshold (`value > threshold`; equality is false). The benchmark does not load, play, or distribute MP3 audio, and it does not use Echonest fields. The selected values are precomputed librosa-derived features, so we are seeking clarification about their status rather than assuming that rights in the underlying recordings are irrelevant.

Could you please clarify, to the extent you can:

1. Does the CC BY 4.0 metadata license stated in the FMA README cover `fma_metadata/features.csv`, including its precomputed librosa-derived feature vectors?
2. Does that license permit commercial use and redistribution of selected or transformed feature values, subject to the CC BY 4.0 attribution and other applicable conditions?
3. Does “meant for research purposes” express a separate contractual restriction, or is it descriptive guidance consistent with the README’s explicit CC BY 4.0 grant for metadata?
4. Are there known third-party rights, exclusions, or other permissions to consider for feature vectors derived from artist-licensed recordings?
5. Is there a preferred attribution statement for commercial or public benchmark use?

For attribution, we plan to cite the FMA paper—Michaël Defferrard, Kirell Benzi, Pierre Vandergheynst, and Xavier Bresson, “FMA: A Dataset for Music Analysis,” ISMIR 2017—and link to the FMA repository and CC BY 4.0:

- Repository: https://github.com/mdeff/fma
- Paper: https://arxiv.org/abs/1612.01840
- CC BY 4.0: https://creativecommons.org/licenses/by/4.0/

Our repository review verified the archive identity and the selected feature columns, but its conclusion is **conditionally confirmed**, not definitive commercial clearance. We have not concluded that all audio-derived feature data is cleared for every use. Any clarification or pointer you can share would help us decide how to proceed and how to attribute the dataset appropriately.

Thank you for your time,

Quarto -hidden information project team
