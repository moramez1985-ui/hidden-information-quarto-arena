# First Accepted FMA Instance — Musical Inspection

## Provenance and reproduction

- Experiment report: `reports/diagnostics/fma_feasibility_seed11_20261109_204633_336807.jsonl`
- Local source archive: `data/fma_metadata.zip`
- Archive size: 358,412,441 bytes
- Archive SHA-256: `d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265`
- Source identified in the archive README: [FMA project](https://github.com/mdeff/fma). No network access or download was used for this inspection.
- Dataset used by the experiment: 25,000 tracks, sampled with seed 11 from the sorted track IDs; feature values were thresholded at sample medians.
- The report contains 3,060 candidates and 541 accepted candidates. This inspection uses the first accepted candidate in that deterministic record order: validator call 3, quartet ordinal 3.

The report’s first accepted candidate was not replaced. Its recorded status is accepted, with `id_level_count = 2`, `structural_count = 2`, two structural classes, no rejection reasons, and the following initial feature quartet:

1. `fma:chroma_cens:mean:01`
2. `fma:chroma_cqt:median:11`
3. `fma:chroma_stft:skew:05`
4. `fma:spectral_bandwidth:min:01`

The exact selected entity IDs, in signature order, are `53194`, `104583`, `74557`, `111359`, `112679`, `10811`, `139817`, `149118`, `70026`, `107833`, `47152`, `151991`, `36515`, `69954`, `134635`, and `43525`.

### Independent reproduction

I read those exact IDs and the four recorded source columns from the local `features.csv`, applied the report’s thresholds using `value > threshold`, and checked every resulting binary value. I then constructed a 16-entity domain containing the complete recorded 18-feature pool and called the existing `validate_instance_quartets()` on the exact candidate. The call returned:

- `id_level_count = 2`
- `structural_count = 2`
- `accepted = true`
- valid quartets: the recorded quartet above, and the same first three features with `fma:rmse:min:01` substituted for `fma:spectral_bandwidth:min:01`
- two distinct structural classes

The report’s recorded counts and acceptance status therefore reproduce. The selected quartet’s original four-bit signatures each occur exactly once. In the table, feature values are listed in quartet order; signature strings use the validator’s integer representation, where the first listed feature is bit 0 (the rightmost character in the four-character signature).

## Feature interpretation

The threshold is the sample median recorded in the experiment. A feature bit is 1 only when the source value is strictly above that threshold; ties map to 0.

| Feature ID | Original FMA column (family / statistic / coordinate) | Threshold | Acoustic interpretation and limitations |
|---|---|---:|---|
| `fma:chroma_cens:mean:01` | `chroma_cens` / mean / `01` | 0.25517144799232483 | CENS is a normalized chroma-family representation, broadly describing pitch-class energy. This is the mean statistic for source coordinate `01`. The archive does not identify that coordinate as a particular pitch, nor document extraction settings; the median split is not a musical key or note-presence label. |
| `fma:chroma_cqt:median:11` | `chroma_cqt` / median / `11` | 0.4525887370109558 | CQT chroma summarizes pitch-class-related energy using a constant-Q representation. This is the median statistic for source coordinate `11`. The coordinate-to-pitch mapping and processing parameters are not specified in the archive; above-median does not mean a pitch is audibly present. |
| `fma:chroma_stft:skew:05` | `chroma_stft` / skew / `05` | 0.3928850293159485 | STFT chroma is a pitch-class-related spectral descriptor. Skew describes asymmetry in the distribution represented by this source coordinate, not a direct musical property. The coordinate mapping and aggregation details are not available in the archive. |
| `fma:spectral_bandwidth:min:01` | `spectral_bandwidth` / min / `01` | 290.3798522949219 | Spectral bandwidth is generally interpreted as spectral spread around a centroid; this column is its minimum statistic. Minimum values may be especially sensitive to quiet frames, silence, or processing choices. The archive does not specify units or exact extraction settings, so the numeric threshold should not be read as a calibrated perceptual boundary. |

The four pairwise Pearson correlations in the experiment sample are small (absolute values approximately 0.003–0.086). That is evidence against strong *linear* redundancy among these four continuous columns in this sample, but it does not establish semantic independence or musical interpretability.

## The 16 tracks

Titles, artists, albums, and genre annotations below come from the archive’s `tracks.csv`; genre names are the labels associated with its listed genre IDs in `genres.csv`. Missing `genre_top` and album values are shown as `—`, not inferred. Genre annotations were not used as gameplay features.

Each feature cell shows `raw value (bit)`, in this order:

- **CENS mean 01** = `fma:chroma_cens:mean:01`
- **CQT median 11** = `fma:chroma_cqt:median:11`
- **STFT skew 05** = `fma:chroma_stft:skew:05`
- **Bandwidth min 01** = `fma:spectral_bandwidth:min:01`

| Signature | Track ID | Title | Artist | Album | `genre_top` / supplied genre labels | CENS mean 01 | CQT median 11 | STFT skew 05 | Bandwidth min 01 |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| `0000` | 53194 | Milorganite | Mittimus | Biosolid Saturday | — / Experimental; Free-Jazz; Improv | 0.229334 (0) | 0.383029 (0) | 0.135851 (0) | 0.000000 (0) |
| `0001` | 104583 | on the edge to here & now | Macon Tights | Field Studies | — / Industrial; Glitch; IDM | 0.364528 (1) | 0.350153 (0) | 0.268346 (0) | 207.818298 (0) |
| `0010` | 74557 | Radial Glia | Ubik | My Room Is The World | Electronic / Electronic | 0.198179 (0) | 0.549240 (1) | 0.058576 (0) | 281.543396 (0) |
| `0011` | 111359 | 286_030321 | ps | Everything Is Useless Without You | — / Noise; Industrial | 0.357665 (1) | 0.535160 (1) | -0.056494 (0) | 0.000000 (0) |
| `0100` | 112679 | Orchestral #2 | Steve Combs | Principal Photography | — / Experimental; Instrumental | 0.189009 (0) | 0.331142 (0) | 0.720167 (1) | 0.000000 (0) |
| `0101` | 10811 | WKRP | DJ BrownBum | — | Hip-Hop / Hip-Hop | 0.284779 (1) | 0.426430 (0) | 0.744800 (1) | 0.000000 (0) |
| `0110` | 139817 | typing | johnny_ripper | JONA | — / Experimental; Ambient Electronic; Minimalism | 0.175478 (0) | 0.615700 (1) | 0.854322 (1) | 0.000000 (0) |
| `0111` | 149118 | Blue Introduction | K. Sparks | The Blue Tape | Hip-Hop / Hip-Hop | 0.259557 (1) | 0.538403 (1) | 0.550068 (1) | 0.000000 (0) |
| `1000` | 70026 | Beta Wave | Automating | Somnambulist | — / Experimental; Drone; Ambient | 0.201346 (0) | 0.423568 (0) | 0.358794 (0) | 704.643433 (1) |
| `1001` | 107833 | Stunna Shades | The Honorable Sleaze | Summer Fresh XE | Hip-Hop / Hip-Hop | 0.332431 (1) | 0.322840 (0) | 0.295930 (0) | 452.221130 (1) |
| `1010` | 47152 | Cannibal Walk | Blank Realm | Live at WFMU on Brian Turner's Show, April 19th 2011 | Rock / Psych-Rock | 0.225509 (0) | 0.556147 (1) | 0.171008 (0) | 389.925629 (1) |
| `1011` | 151991 | At the laundry service | OsO4 | Gimme A Minute | Electronic / Electronic | 0.500593 (1) | 0.484960 (1) | 0.382167 (0) | 1091.070190 (1) |
| `1100` | 36515 | Intro | Lou Barlow | Lou Barlow + The Missingmen Live @ WFMU on Cherry Blossom Clinic, Sept. 4th 2010 | Spoken / Banter | 0.211277 (0) | 0.326363 (0) | 1.090631 (1) | 437.915527 (1) |
| `1101` | 69954 | I Know Your Name | Bee and Flower | Live on WFMU's Imaginary Radio 8-26-12 | Rock / Indie-Rock | 0.430491 (1) | 0.257344 (0) | 0.569048 (1) | 611.633057 (1) |
| `1110` | 134635 | Abigél | Kisbalishin Kerület | Kisbalishin Kerület - S​/​T | — / Avant-Garde; Noise; Psych-Rock | 0.248443 (0) | 0.603841 (1) | 1.016731 (1) | 644.694031 (1) |
| `1111` | 43525 | XO | Talk Normal | Live at WFMU on Beastin' the Airwaves with Keili, Dec. 17th 2010 | Rock / Noise-Rock | 0.263622 (1) | 0.735605 (1) | 2.020989 (1) | 704.605042 (1) |

## Assessment

### A. Mathematical validity

- **16 distinct entities:** verified.
- **Signature coverage:** independently recomputed from the four source columns and recorded thresholds; each of the 16 signatures occurs exactly once.
- **ID-level count:** 2 valid feature-ID quartets.
- **Structural count:** 2 structural classes under the existing validator’s equivalence rule.
- **Acceptance:** independently reproduced as true because both counts exceed 1.

### B. Acoustic and musical interpretability

The feature families are recognizable acoustic descriptors, but the selected columns mix different statistics (mean, median, skew, minimum) and opaque coordinate indices. Median thresholding creates relative high/low flags; it does not create established musical categories. In particular, the archive does not document the coordinate-to-pitch mapping or enough extraction details to give these four flags a precise perceptual interpretation.

The track metadata show a heterogeneous selection: supplied labels include Hip-Hop, Electronic, Rock, Spoken/Banter, Experimental, Industrial, Noise, Ambient, and other tags. That diversity is an observation about FMA annotations, not proof of what the recordings sound like. Some `genre_top` values are missing. No audio was listened to, and no genre, title, artist, or album metadata was used in the validation.

There are plausible acoustic *measurements* represented—chroma-related statistics and spectral spread—but no demonstrated coherent musical theme among these 16 tracks. The all-signatures-once construction is mathematical balancing, not evidence that the tracks are perceptually or musically balanced.

## Verdict

**Mathematically valid but musically weak or unclear.** The first accepted candidate is exactly reproduced under the existing strict validator, but the median-split coordinates do not establish musically meaningful distinctions or a coherent theme. Further FMA benchmark work is justified as a controlled prototype of the generic architecture, not yet as a validated music-meaning benchmark. A small follow-up should compare these feature-derived distinctions with domain-expert or listening-based judgments before drawing stronger musical conclusions.

### Limitations

- This is one candidate from one deterministic 25,000-track sample and one fixed 18-feature pool.
- The acoustic columns are metadata features; no audio was downloaded, listened to, or reprocessed.
- The archive does not document coordinate-to-pitch mappings or all feature-extraction parameters.
- Median-based binary flags are sample-relative.
- Genre labels are incomplete annotations and were not treated as ground truth for acoustic meaning.
