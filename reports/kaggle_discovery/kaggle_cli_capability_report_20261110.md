# Kaggle CLI Capability and Model Catalog Discovery

Assessment date: 2026-11-10

## Executive finding

The installed Kaggle CLI returned 200 pages (10,000 records) for the unfiltered `createTime` listing and reported no next-page token on its final page. That result set is **not a complete global catalog**: supplemental `--search gemma-3` and `--owner google` queries returned the public references `google/gemma-3` and `google/gemma-4`, neither of which appears in the 10,000 saved references, and each filtered query itself had another page available. The list endpoint's terminal token therefore does not establish global completeness.

The CLI-visible account has 30 GPU hours and 20 TPU hours remaining, plus Benchmark Model Proxy quotas. This verifies quota balances, not that any particular accelerator or Notebook runtime can be allocated. No Notebook, model download, Benchmark, inference request, or Quarto match was run.

## 1. CLI and authentication environment

| Item | Observed |
|---|---|
| Kaggle CLI | 2.2.5 |
| Python | 3.14.0, CPython |
| Operating system | Windows 11 x64 |
| Authentication | Read-only model, quota, Notebook-list, and Benchmark metadata requests succeeded. `kaggle auth status` is not a supported command. No credential was printed or saved. |
| Top-level CLI groups | `competitions`, `datasets`, `kernels`, `models`, `files`, `forums`, `benchmarks`, `config`, `auth`, `quota`, and `search` |

`kaggle models list --help` exposes `--page-size` (maximum 200), `--page-token`, JSON/CSV output, `--sort-by`, `--search`, and `--owner`. Sort choices include `hotness`, `downloadCount`, `voteCount`, `notebookCount`, and `createTime`. The installed CLI's list records contain `id`, `ref`, `title`, `subtitle`, and `author`; the normalized CSV derives `owner`, `model_slug`, and `full_model_reference`. The list does not return a model card, publisher field, license, visibility, framework, or version metadata.

The CLI help for `models instances list` describes a four-component variation reference, while the installed implementation successfully used an `owner/model` reference for the model-level listing. Variation and version identifiers in the inventory were taken from returned Kaggle API metadata, not guessed.

## 2. Catalog enumeration and completeness

The original unfiltered command was:

```text
kaggle models list --sort-by createTime --page-size 200 --format json
```

The following token pages were fetched until the CLI returned no next-page token:

| Statistic | Result |
|---|---:|
| Pages returned | 200 |
| Requested page size | 200 |
| Observed records per page | 50 |
| Raw records | 10,000 |
| Unique references in the returned set | 10,000 |
| Duplicate references in the returned set | 0 |
| Records missing a reference | 0 |
| Terminal page had a next-page token | No |
| Retries in the completed enumeration | 0 |

**Completeness verdict: incomplete global inventory.** The 10,000-record query reached its own terminal page, but the filtered-list evidence shows that the terminal result set does not include every model retrievable through the same catalog interface. Specifically, `google/gemma-3` and `google/gemma-4` were returned by `kaggle models list --search gemma-3 --page-size 200 --format json`; the owner-filtered command `kaggle models list --owner google --page-size 200 --format json` also showed a next-page token. These supplemental queries establish omissions; they are not being used as a substitute for an unfiltered enumeration.

The exact stopping condition was the unfiltered CLI returning no next-page token after page 200, at 10,000 records. There is no global continuation cursor after that response. A redundant unfiltered API walk was attempted later; it ended after 11 pages / 550 records with a remote connection reset. That incomplete recheck does not replace the first completed 200-page retrieval.

The first pass did not retain every intermediate page token or page digest, so separate initial-pass repeated-token/page counts cannot be independently re-audited from the saved export. The completed result had no duplicate references. The partial second walk observed no repeats in its 11 pages. Opaque page tokens are not included in the reports.

### Catalog family inventory

Counts below are case-insensitive substring matches over `ref`, `title`, and `subtitle` in the 10,000-record export. They overlap and are not family totals or an exhaustive count of all Kaggle-hosted models.

| Search term | Matching records |
|---|---:|
| Gemma | 197 |
| Qwen 3 | 304 |
| Qwen (all matched spellings) | 478 |
| DeepSeek | 40 |
| Mistral | 24 |
| Llama | 117 |
| Phi | 32 |
| Granite | 2 |
| OLMo | 22 |
| GPT-OSS | 21 |

The normalized catalog retains every available list field and does not fabricate descriptions, publishers, versions, framework, licenses, or access status.

## 3. Variations, versions, and model-card coverage

Variation/version APIs are per-model; the installed CLI exposes no global variation inventory. Complete variation/version queries across 10,000 references would require thousands of additional model-specific requests. Instead, the following coverage was collected after the catalog pass:

| Coverage | Result |
|---|---:|
| Model references from the 10,000-record set queried | 12 |
| Additional public model references found by filtered search | 2 |
| Total model references queried | 14 |
| Variation records retrieved | 120 |
| Version records retrieved | 165 |
| Model-version file lists successfully retrieved | 13 |
| File metadata records retrieved | 163 |
| File-list permission failures | 1 |

The 12 selected catalog entries cover Gemma 4, Qwen 3, DeepSeek R1, Mistral, Llama, Phi, and GPT-OSS. Each selected entry returned one variation and one version. For the two search-discovered Google models, all variation and version records were retrieved:

| Model | Variations | Versions | File metadata |
|---|---:|---:|---|
| `google/gemma-3` | 61 | 80 | Selected Transformers file-list request returned HTTP 403 |
| `google/gemma-4` | 47 | 73 | Retrieved for one selected version (8 file records) |

The detailed raw records, CLI command strings, lookup statuses, available license metadata, and file names/sizes are in [model_variations_raw.json](./model_variations_raw.json) and [model_variations.csv](./model_variations.csv). The CSV marks version creation dates as unavailable when the API did not return one; model update times and per-file creation dates are preserved where present. Public visibility and license labels below mean the API's metadata only, not a successful weight download or independent license verification.

The Gemma 3 file-list endpoint returned `403 Client Error: Forbidden` and “You don't have access to this resource” for the selected public variation. This is recorded as an account/API access limitation, not treated as an empty file list.

## 4. Account quotas and visible capabilities

| Capability | Account-visible result | Interpretation |
|---|---|---|
| GPU accelerator quota | 0.00h used; 30.00h remaining of 30.00h; refresh 2026-11-14 | Quota only; does not show a GPU allocated to a Notebook. |
| TPU accelerator quota | 0.00h used; 20.00h remaining of 20.00h; refresh 2026-11-14 | Quota only; does not show a TPU allocated to a Notebook. |
| Benchmark Model Proxy daily quota | $0.00 used; $10.00 remaining | Quota metadata only; no inference was run. |
| Benchmark Model Proxy monthly quota | $0.00 used; $100.00 remaining | Quota metadata only; no inference was run. |
| Owned Notebook listing | 2 records visible | Listing does not demonstrate current or future runtime resources. |
| Benchmark task listing | No tasks visible (`kaggle benchmarks tasks list --all`) | Does not establish that the Kaggle Benchmark service is unavailable. |
| Benchmark Model Proxy model listing | 37 model slugs visible | Registered names only; not a model-weight catalog or proof of callable access. |

The CLI documentation describes Benchmarks as using Kaggle Model Proxy. `kaggle benchmarks auth` provisions Model Proxy environment credentials and can write them to an environment file; it was not run because this task forbids credential creation/persistence. No Model Proxy request was made. External provider API credentials, billing, and internet reachability from a future Notebook were not tested.

Kaggle Models and Benchmark Model Proxy are different interfaces: the former exposes model assets/variations/versions; the latter exposes hosted inference slugs and a separate quota. A model in one list is not thereby present or callable in the other.

### Account-visible Model Proxy names

These are the exact slugs and display names returned by `kaggle benchmarks tasks models`. Their presence is not evidence that the same models exist in Kaggle Models or that a request will succeed.

| Slug | Display name |
|---|---|
| `gemini-3.8-flash` | Gemini 3.8 Flash |
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 |
| `claude-haiku-5-5` | Claude Haiku 5.5 |
| `claude-opus-4-5-20251101` | Claude Opus 4.5 |
| `claude-opus-4-6-default` | Claude Opus 4.6 |
| `claude-opus-4-7-default` | Claude Opus 4.7 |
| `claude-opus-4-8-default` | Claude Opus 4.8 |
| `claude-opus-5-default` | Claude Opus 5 |
| `claude-opus-5-5-default` | Claude Opus 5.5 |
| `claude-sonnet-4-6-default` | Claude Sonnet 4.6 |
| `claude-sonnet-5-default` | Claude Sonnet 5 |
| `claude-sonnet-5-5` | Claude Sonnet 5.5 |
| `gemini-2.5-flash` | Gemini 2.5 Flash |
| `gemini-2.5-pro` | Gemini 2.5 Pro |
| `gemini-3-flash-preview` | Gemini 3 Flash Preview |
| `gemini-3.1-flash-lite-preview` | Gemini 3.1 Flash-Lite Preview |
| `gemini-3.1-pro-preview` | Gemini 3.1 Pro Preview |
| `gemini-3.5-flash-lite` | Gemini 3.5 Flash-Lite |
| `gemini-3.6-flash` | Gemini 3.6 Flash |
| `gemini-4-argon` | Gemini 4 Argon |
| `gemma-4-26b-a4b-it` | Gemma 4 26B A4B |
| `gemma-4-31b-it` | Gemma 4 31B |
| `gpt-5.4-2026-03-05` | GPT-5.4 |
| `gpt-5.4-mini-2026-03-17` | GPT-5.4 mini |
| `gpt-5.4-nano-2026-03-17` | GPT-5.4 nano |
| `gpt-5.5-2026-04-23` | GPT-5.5 |
| `gpt-5.6-luna` | GPT-5.6 Luna |
| `gpt-5.6-sol` | GPT-5.6 Sol |
| `gpt-5.6-terra` | GPT-5.6 Terra |
| `gpt-6-astra` | GPT-6 Astra |
| `gpt-6-luna` | GPT-6 Luna |
| `gpt-6-sol` | GPT-6 Sol |
| `gpt-6.1-sol` | GPT-6.1 Sol |
| `gpt-oss-120b` | gpt-oss-120b |
| `grok-4.5-0708` | Grok 4.5 |
| `grok-4.6` | Grok 4.6 |
| `grok-4.7` | Grok 4.7 |

## 5. Notebook and accelerator capabilities

### Officially documented

The Kaggle CLI kernel documentation (accessed 2026-11-10; accelerator list dated September 2026) documents these accelerator identifiers:

- `NvidiaTeslaT4` (documented as GPU T4 ×2)
- `NvidiaTeslaA100`
- `NvidiaL4`
- `TpuV5E8`
- `NvidiaL4X1`
- `TpuV6E8`
- `NvidiaH100`
- `NvidiaRtxPro6000`

The documentation notes that some accelerators are restricted to specific competitions or Kaggle admins. These are platform-documented options, not verified account entitlements.

Notebook metadata documents `enable_gpu`, `enable_internet`, and `machine_shape`, plus `dataset_sources`, `competition_sources`, `kernel_sources`, and `model_sources`. The model source format is `owner/model/framework/variation/version`. The CLI exposes a `--timeout` option for `kernels push` and says a global maximum applies, but this inspection did not establish the numeric maximum. `kernels output` retrieves outputs; no Notebook push, execution, or output retrieval was performed.

### Account visibility and runtime unknowns

The quota endpoints expose GPU/TPU hours but not accelerator allocation or eligibility. No Notebook was launched, so the following remain **UNKNOWN**: actual GPU/TPU visibility and VRAM, RAM, disk space, session/runtime limits, internet connectivity, package installation capability, and candidate-model loadability or latency.

The inspected CLI did not expose account-level storage/download limits or a numeric Notebook runtime cap. No per-model VRAM requirement field was returned; the inventory has package byte counts and framework labels only. The candidate Kaggle Model variations appear to be asset sources for local inference, while Model Proxy entries are hosted inference options; actual download access, required runtime packages, external-provider requirements, and inference behavior were not tested.

## 6. Candidate models surfaced by the inventory

No final two-model pair is selected. Catalog/model visibility is not proof of weight-download access or executable inference.

| Priority | Candidate | Metadata evidence | Main caveat |
|---:|---|---|---|
| 1 | `greymatter69/qwen3-8b-q4km` | Model title says Qwen3 8B; `GGUF`, variation `q4_k_m`, version 1; one `.gguf` file at 5,225,374,496 bytes; Kaggle variation metadata says Apache 2.0 and public. | Community upload; source identity/hash was not independently checked. Requires a compatible GGUF runtime; not installed or tested. |
| 2 | `corethrive/deepseek-r1-distill-qwen-1.5b` | PyTorch variation `pytorch`, version 1; 3,561,250,212 bytes across 5 files; Kaggle metadata says Apache 2.0 and public. | Smaller model may have weaker strategic reasoning; load and structured-output behavior unknown. |
| 3 | `dineshkumar0705/gemma-4-31b-it-qat-w4a16` | Gemma 4 31B QAT W4A16; Transformers variation `w4a16-ct`, version 1; 23,297,596,043 bytes across 9 files; Kaggle metadata says Apache 2.0 and public. | The 23.3 GB payload leaves memory-fit uncertainty even on larger documented accelerators; runtime overhead and actual accelerator eligibility are unknown. |
| 4 | `kentarctic/phi-4-mini-instruct` | Transformers variation `official-from-huggingface`, version 1; 7,693,980,414 bytes across 46 files; Kaggle metadata says MIT and public. | Model card description/source revision was not available in the returned details; provenance and actual loadability need confirmation. |
| 5 | Model Proxy `gemma-4-26b-a4b-it` and `gemma-4-31b-it` | Both registered slugs appear in the account-visible Model Proxy list; the separate Proxy quota is visible. | Hosted identities are not pinned to a revision in this listing. Credentials must be provisioned; no inference or response-format test was made. |

Other inspected entries expose meaningful blockers:

- `professorice/mistral-small-4-119b-2603`: vLLM/NVFP4, 70,846,528,425 bytes; its model card describes a 119B-A6B model. Too large to assume practical on an untested single Notebook accelerator.
- `nvidia/qwen3-8-flash-next-nvfp4`: 132,734,506,847 bytes across 25 files; no practical single-accelerator fit is established.
- `giridharan17/deepseek-r1-32b`: its only listed file is a 20,183-byte Notebook, not model weights.
- `romanromenskyi/gemma-4-e4b-it-ipsupport`: model metadata labels the framework `OTHER` and describes an MLX build; compatibility with Kaggle's Linux GPU runtime is unverified.
- `guoqingu/gpt-oss-20b-gguf`: the title says GGUF but the variation metadata says Transformers; resolve this mismatch before selecting it.
- `danbth/llama-3-2-3b-instruct`: Kaggle metadata says MIT. The relationship between that metadata and the upstream Llama terms was not independently verified, so it is not treated as cleared for use.

The official `google/gemma-3` and `google/gemma-4` model cards are available through filtered search despite their omission from the unfiltered 10,000 records. Their variation/version inventories are included in the raw variation report. The API reports a Gemma license with `agreementRequired=true` for Gemma 3; this is a restriction signal, not proof that the account accepted it. The selected Gemma 3 file-list request returned HTTP 403.

## 7. Exact commands and sources

Commands used (pagination tokens and credentials omitted):

```text
python --version
python -c "import platform; print(platform.platform()); print(platform.python_implementation())"
kaggle --version
kaggle --help
kaggle auth --help
kaggle auth status                         # unsupported; no token output
kaggle models list --help
kaggle models list --sort-by createTime --page-size 200 --format json [--page-token <opaque-token>]
kaggle models list --search gemma-3 --page-size 200 --format json
kaggle models list --owner google --page-size 200 --format json
kaggle models instances list <owner/model> --page-size 200 --format json
kaggle models instances versions list <owner/model/framework/variation> --page-size 200 --format json
kaggle models instances versions files <owner/model/framework/variation/version> --page-size 200 --format json
kaggle quota --format json
kaggle benchmarks quota --format json
kaggle benchmarks tasks models
kaggle benchmarks tasks models --help
kaggle benchmarks tasks list --all
kaggle benchmarks auth --help              # help only; auth was not invoked
kaggle kernels list --mine --page-size 200 --format json
kaggle kernels push --help
kaggle kernels output --help
kaggle kernels pull --help
```

Official documentation consulted:

- [Kaggle CLI Models commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/models.md)
- [Kaggle CLI Benchmarks commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/benchmarks.md)
- [Kaggle CLI Kernels commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md)
- [Kaggle kernel metadata schema](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md)
- [Kaggle model metadata schema](https://github.com/Kaggle/kaggle-cli/blob/main/docs/models_metadata.md)

## 8. Verified, not verified, and unknown

**VERIFIED**

- Kaggle CLI 2.2.5 and authenticated read-only access for the metadata operations listed above.
- The unfiltered listing returned 200 pages / 10,000 records and terminated without a next-page token.
- 10,000 unique references were present in that exported result set.
- Filtered catalog queries exposed public Google Gemma references outside the unfiltered result; the global catalog export is therefore incomplete.
- Account-visible GPU/TPU quota, Model Proxy quota and 37 Proxy model slugs.
- `google/gemma-3`: 61 variations / 80 versions; `google/gemma-4`: 47 variations / 73 versions.
- File metadata was read without downloading model weights; Gemma 3's selected file endpoint returned 403.

**NOT VERIFIED**

- Complete global Models catalog and exhaustive variations/versions for all catalog entries.
- Successful weight downloads, model execution, GPU memory fit, latency, structured JSON behavior, or reproducible local inference.
- Model Proxy inference access, provider identity/revision pinning, external provider/API access, or billing behavior beyond the exposed quota amounts.
- Acceptance or satisfaction of model-specific license/access conditions.

**UNKNOWN**

- Actual Kaggle Notebook accelerator, RAM, disk, VRAM, internet, package-install, and session availability.
- Which documented accelerators are eligible for this account.
- Whether any candidate can run under the account's eventual Notebook runtime.

## 9. Deliverables and safety

Created:

- `reports/kaggle_discovery/models_catalog_raw.json`
- `reports/kaggle_discovery/models_catalog.csv`
- `reports/kaggle_discovery/model_variations_raw.json`
- `reports/kaggle_discovery/model_variations.csv`
- `reports/kaggle_discovery/discovery_summary.json`
- `reports/kaggle_discovery/kaggle_cli_capability_report_20261110.md`

No model weights were downloaded; no Kaggle Notebook was created, started, or executed; no Benchmark or external model API was called; no Quarto match or private game-data prompt was run; no credentials were printed, retrieved, or saved. No files were staged or committed.

**Discovery outcome: NOT COMPLETE FOR GLOBAL CATALOG** — the 10,000-record listing reached its terminal page, but filtered queries prove the global inventory is incomplete. Account capability metadata and a bounded model shortlist are documented; Notebook runtime and model execution feasibility remain unverified.
