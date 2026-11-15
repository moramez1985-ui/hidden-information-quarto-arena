# Kaggle Model Discovery and Pilot Feasibility

**Research date:** 2026-11-10

**Decision:** **READY WITH BLOCKERS**

## Executive summary

Kaggle's public Models catalog is programmatically searchable with the Kaggle
CLI. It currently exposes official model families including Gemma 3, Qwen 3,
Gemma 4, DeepSeek R1, and Mistral Small. Kaggle's Benchmarks interface is
separate: its CLI describes evaluation tasks running against models through the
Kaggle Model Proxy, and this account's task listing was empty.

The strongest catalog-based pair to investigate is Google Gemma 3 4B IT
(`gemma-3-4b-it-qat-q4_0`, version 3) and Qwen3 4B (`4b-awq`, version 1).
Both are in the same parameter class and have versioned Kaggle catalog entries.
They are only a *provisional recommendation*: the exact Kaggle variation
framework and files were not verified, the direct variation/file lookups
returned 404, and no Kaggle Notebook runtime was available to measure GPU,
memory, disk, package, or inference behavior. Gemma's terms and Qwen's Apache
license also differ.

No model weights were downloaded, no provider API was called, no game/private
data was sent to a model, and no match was started. No notebook scaffold was
created because the exact runtime and inference dependencies are not verified.

## 1. Kaggle interfaces and inventory limits

### Kaggle Models

The official CLI installed in the research environment was Kaggle CLI 2.2.5.
Its `kaggle models list` command supports text search, owner filtering, sorting,
page size, and page tokens. The catalog result records identify a model by
`owner/model-slug`; the model and variation/version interfaces are separate.
The CLI model-card command retrieved metadata for public model records without
downloading weights.

The following read-only searches were performed:

| Query | Observed result |
|---|---|
| `kaggle models list --page-size 200 --format json` | First 50 records returned with a next-page token. |
| `--search gemma` | First 50 records returned; official Google Gemma entries included. |
| `--search deepseek` | First 50 records returned; official DeepSeek entries included. |
| `--search qwen` | First 50 records returned; official Qwen entries included. |
| `--search "gemma 3 4b"` | 12 results, including `google/gemma-3`. |
| `--search "llama 3.2 3b"` | Results included `metaresearch/llama-3.2`. |
| `--search "mistral small"` | Results included `mistral-ai/mistral-small-24b`. |
| `--search "Gemma 4"` | First 50 results included `google/gemma-4`. |

A full-catalog page walk was attempted but remained in progress after 180
seconds and was stopped. Therefore, this report gives a candidate-focused
inventory, not an exhaustive count or dump of every Kaggle model. Search
results are catalog visibility, not proof that a particular account can
download or execute every variation.

### Kaggle Benchmarks

The official Kaggle CLI documentation describes Benchmarks as Python evaluation
tasks that run against one or more LLMs through the Kaggle Model Proxy. This
interface is not the Kaggle Models weight catalog and does not establish local
weight availability.

Command run:

```text
kaggle benchmarks tasks list --all
```

Actual result: `No tasks found. Use 'kaggle b t push' to create one.` This is
the current account's task-list result; it is not evidence that Kaggle has no
benchmark service or no proxy-supported models. No Model Proxy credentials were
requested, and no Model Proxy call was made.

### External model APIs

An external model API is a third, distinct route. It needs the provider's own
model endpoint, credentials, terms, and potentially billing. It is not a Kaggle
Models download and is not the same as a Kaggle Benchmark/Model Proxy run.
External APIs were not inventoried or called. Using one would transmit the
requesting agent's private feature payload to that service and would need to be
explicitly disclosed. For this pilot, locally loaded weights are preferable if
the runtime is proven feasible.

### Official interface sources

- [Kaggle CLI Models commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/models.md)
- [Kaggle CLI model variations](https://github.com/Kaggle/kaggle-cli/blob/main/docs/model_variations.md)
- [Kaggle CLI model variation versions](https://github.com/Kaggle/kaggle-cli/blob/main/docs/model_variations_versions.md)
- [Kaggle CLI model metadata and licenses](https://github.com/Kaggle/kaggle-cli/blob/main/docs/models_metadata.md)
- [Kaggle CLI Benchmarks commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/benchmarks.md)
- [Kaggle CLI Kernels commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md)
- [Kaggle Models catalog](https://www.kaggle.com/models)

## 2. Candidate-focused inventory

Kaggle's list endpoint returned model owner, exact model reference, title, and
short description. The separate model-card request supplied the additional
description below. Kaggle's CLI version listing returned variation slug,
version, title, and `private: false`; it did not provide a verified file listing
for the candidate variation paths tried here.

| Exact Kaggle model reference / publisher | Candidate model and available metadata | Kaggle version evidence | Access, format, and resource evidence |
|---|---|---|---|
| [`google/gemma-3`](https://www.kaggle.com/models/google/gemma-3) — Google | Gemma 3 is a family with 1B, 4B, 12B, and 27B variants. The official Gemma 3 card describes text/image input, text output, up to 128K input context for 4B/12B/27B, and Transformers support from 4.50.0. Candidate: 4B instruction-tuned. | CLI variation listing exposed `gemma-3-4b-it-qat-q4_0`, version 3 (versions 1–3 observed), and `gemma-3-4b-it-qat-int4-unquantized`, version 1. Listed as public (`private: false`). | The official Gemma 3 card links the Gemma Terms of Use, not Apache 2.0. Exact Kaggle variation framework, file names, file sizes, download permission, and VRAM requirement remain unverified. If loaded as a local weight file, no external model API is inherently required. |
| [`qwen-lm/qwen-3`](https://www.kaggle.com/models/qwen-lm/qwen-3) — QwenLM | Qwen 3 includes dense 0.6B, 1.7B, 4B, 8B, 14B, and 32B models and 30B-A3B / 235B-A22B MoE models. The official Qwen3-4B card reports 4.0B parameters, 32,768 native context (131,072 with YaRN), and Transformers support. Qwen3 supports reasoning/thinking and instruction-following modes. | CLI variation listing exposed `4b`, version 1, and `4b-awq`, version 1; both were public (`private: false`). The `4b` entry appeared more than once in the response, so framework identity is not inferred from that listing. | Qwen's official release states Apache 2.0 for the Qwen3 family. Exact Kaggle variation framework, files, download permission, and VRAM requirement remain unverified. Upstream Qwen documentation warns that Transformers versions below 4.51.0 can fail; this is not a verified Kaggle-runtime package pin. |
| [`google/gemma-4`](https://www.kaggle.com/models/google/gemma-4) — Google | Official Kaggle model record found. Its card describes open-weight multimodal Gemma 4 and links an Apache 2.0 license. Exact parameter sizes, candidate variation/version, and inference files were not established in this discovery pass. | Model-level catalog record and card retrieved; no exact pilot variation was confirmed. | Not ranked as a pilot model until a concrete variation, version, framework, and file access are confirmed. No VRAM estimate claimed. |
| [`deepseek-ai/deepseek-r1`](https://www.kaggle.com/models/deepseek-ai/deepseek-r1) — DeepSeek | Official model card lists DeepSeek-R1 as a 671B-parameter MoE model with 37B activated parameters and 128K context. The same card lists smaller distilled derivatives. | Model-level catalog record and card retrieved. | The full 671B model is not a practical candidate for an unverified single Kaggle notebook GPU. The card identifies a Model Agreement and derivative licenses vary; not selected. |
| [`mistral-ai/mistral-small-24b`](https://www.kaggle.com/models/mistral-ai/mistral-small-24b) — Mistral AI | Official model card describes Mistral Small 24B, 24B parameters, agent/function-calling capability, and JSON output. | Model-level catalog record and card retrieved. | Apache 2.0 is stated in the card. Local execution may be possible on some configurations, but its storage/VRAM requirements were not established here; not selected ahead of verified 4B-class candidates. |
| [`metaresearch/llama-3.2`](https://www.kaggle.com/models/metaresearch/llama-3.2) — Meta | Model family surfaced in catalog search; this task did not inspect its exact Kaggle variation metadata. | No exact version selected. | Not selected. Specific size, licensing/access conditions, and Kaggle downloadability were not verified in this pass. |

### Candidate variation lookup attempts

The Kaggle variation-version listing returned the candidate slugs/version
numbers above. Attempts to retrieve exact variation metadata and files using
guessed `pyTorch` framework paths returned HTTP 404:

```text
kaggle models instances versions list google/gemma-3/pyTorch/gemma-3-4b-it-qat-q4_0 --format json --page-size 200
kaggle models instances versions list qwen-lm/qwen-3/pyTorch/4b-awq --format json --page-size 200
kaggle models instances get google/gemma-3/pyTorch/gemma-3-4b-it-qat-q4_0 ...
kaggle models instances get qwen-lm/qwen-3/pyTorch/4b-awq ...
kaggle models instances versions files .../1 ...
```

The listing responses contained the matching variation/version records (Gemma
Q4_0 version 3 and Qwen AWQ version 1), but did not establish the framework or
file bundle.

This does not prove that the weights are absent. It means the exact variation
framework/path and downloadable file bundle were not established from the
available CLI calls. No weights or large assets were downloaded.

## 3. Ranked pilot shortlist

### 1. Provisional pair: Gemma 3 4B IT + Qwen3 4B

| Player slot | Requested Kaggle model identity | Reason |
|---|---|---|
| Player 1 | Google Gemma 3, `gemma-3-4b-it-qat-q4_0`, version 3 | Official Google model family, 4B instruction model, versioned catalog entry, quantized-named variation. |
| Player 2 | Qwen3, `4b-awq`, version 1 | Official QwenLM model family, 4B dense model, versioned catalog entry, Apache 2.0 family license, quantized-named variation. |

This pair is the best *catalog-based next candidate*, not a final executable
configuration. Matching the 4B parameter class is more comparable than pairing
24B/671B models with a small model. The two quantization schemes differ
(Gemma QAT/Q4_0 vs. Qwen AWQ), so memory, quantization quality, and latency are
not equivalent. The reported upstream context limits also differ. Neither
structured JSON reliability nor game-playing behavior has been tested; both
require harmless JSON smoke tests before any private feature is sent.

### 2. Lower-memory fallback to investigate

Use the official Gemma 3 1B instruction family and Qwen3 1.7B only if the
runtime cannot support both 4B candidates. Smaller parameter counts make
execution more plausible, but may lower reasoning performance. Exact Kaggle
variation/version and file checks are still required.

### Not selected for this two-model pilot

- Full DeepSeek-R1 671B: unsuitable for the unverified notebook memory budget.
- Mistral Small 24B: defer until actual accelerator memory and weight-file size
  are known.
- Gemma 4: catalog presence is confirmed, but a specific variation and runtime
  requirements were not confirmed.
- The prior OpenCode DeepSeek V4.1 Flash Free / Ollama Gemma 4 Cloud pairing is
  not retained automatically. It is an API/CLI/cloud pairing, not evidence of
  local Kaggle weight execution.

## 4. Kaggle runtime feasibility

### What was observed

- `kaggle --version` returned `Kaggle CLI 2.2.5`.
- `kaggle quota --format json` returned account quota values of GPU 30.00h and
  TPU 20.00h, with 0.00h used at query time and a listed refresh date of
  2026-11-14. This is an account quota response, not a reservation or hardware
  visibility check for a particular notebook.
- The official Kaggle CLI Kernels documentation, marked “Accelerators available
  as of Sep 2026,” lists `NvidiaTeslaT4` (T4 ×2), `NvidiaTeslaA100`,
  `NvidiaL4`, `NvidiaL4X1`, `NvidiaH100`, `NvidiaRtxPro6000`, `TpuV5E8`, and
  `TpuV6E8`. The same documentation warns that some are limited to specific
  competitions or Kaggle admins. These are documented IDs, not proof that any
  is selectable for this account or current notebook.
- The CLI exposes an accelerator selection and a maximum run-time option for
  kernel execution. The docs do not establish the active notebook's session
  limit or resource allocation.
- Kaggle's public Model and Notebook pages are client-rendered. Their initial
  HTML provides summaries but not runtime telemetry or complete model-file
  details.

### What could not be verified

There was no active Kaggle Notebook kernel available to inspect. No GPU was
allocated or exercised. Therefore these remain **unknown**:

- Actual selected GPU type/count and `torch.cuda` visibility.
- GPU VRAM, notebook RAM, and available disk.
- Session time limit and the account's accelerator eligibility for a new
  notebook.
- Notebook internet setting and whether model downloads or package installs
  will be permitted in the intended notebook.
- Exact weight download sizes and whether both candidate model bundles are
  accessible to the account.
- Whether the current Kaggle image has compatible Torch/Transformers/CUDA
  versions, or whether the needed packages can be installed without conflict.

The local research computer's Python 3.14 environment is not evidence about the
Kaggle image. No package installation, model download, or GPU work was attempted.
The Kaggle CLI documentation's Python 3.11+ requirement applies to the CLI, not
to the unobserved notebook runtime.

## 5. Existing Quarto integration and experimental invariants

### Harness and instance

- [`TournamentRunner.run_two_match_pilot`](../tournament_harness.py) uses the
  same `InstanceSpec` and fixed `PILOT_MODEL_BY_PLAYER` assignments for both
  calls. It changes only
  `starting_player` (`player_1`, then `player_2`).
- [`make_qm9_instance`](../tournament_harness.py) reads local
  [`experiments/qm9_quarto`](../experiments/qm9_quarto) artifacts and constructs
  `qm9_pilot_hf_ring_db_0001` using the fixed `FEATURE_IDS`.
  [`GenericInstanceBuilder`](../domain_adapters/instance_builder.py) with
  `seed=None` chooses the first sorted entity for each signature; it is
  deterministic for unchanged input artifacts. The instance is constructed
  once and reused for the pair of matches.
- [`Phase0Controller`](../phase0_foundation.py) assigns the first two instance
  features to player 1 and the next two to player 2. With the current feature
  order, that is `contains_hydrogen` and `contains_fluorine` for player 1, and
  `contains_ring` and `contains_double_bond` for player 2. The assignment is
  unchanged when the starting seat swaps.
- There is no separate serialized pilot `InstanceSpec` input in the notebook
  workflow. The exact selected entity list/signature map is rebuilt from the
  local feature data. A Kaggle run should package the exact source/data snapshot
  and record an instance manifest/hash before accepting results.
- [`QM9Adapter`](../domain_adapters/qm9_adapter.py) expects its
  provenance/configuration JSON files, feature registry and feature matrix. A
  Kaggle bootstrap must include these as versioned private inputs; it should
  not fetch or reconstruct data implicitly.

### Agent contract, privacy, and reporting

- The existing [`AgentAdapter`](../tournament_harness.py) expects a client
  implementing `chat(messages, timeout=...) -> ChatResult`. No local
  Transformers/Kaggle-model client exists in the inspected harness.
- The current configured clients are OpenCode CLI and an Ollama HTTP endpoint.
  [`run_pilot`](../tournament_harness.py) constructs these specific clients and
  uses the existing DeepSeek/OpenCode and Gemma/Ollama model tags. It is not
  ready to load the shortlisted Kaggle weights directly.
- [`AgentAdapter.build_messages`](../tournament_harness.py) sends the bounded
  public-observation projection and only the requesting player's private
  payload. The harness privacy audit checks prompts for restricted keys/data.
  Existing
  [`test_prompt_projection_and_private_payload_are_isolated`](../tests/test_tournament_harness.py)
  and
  [`test_start_player_pair_keeps_model_identity_ownership_and_replay_fixed`](../tests/test_tournament_harness.py)
  cover the privacy projection and matched-seat behavior. This is a trusted
  host boundary, not a sandbox against arbitrary Python model code.
- [Decision Trace](../decision_trace.py) supports optional provider, model name,
  and version fields.
  Kaggle runs must record the actual loaded Kaggle model/variation/version (and
  ideally artifact hashes); the current requested model tags are not proof of
  resolved weight identity.
- Existing run output directories use a UTC timestamp plus a UUID suffix,
  avoiding overwrite of previous run directories. Public report and restricted
  match/audit logs are separate. Kaggle outputs should remain private, and
  restricted prompts/audit information must not be published.
- For local weights, no external model API is needed by the model itself. If a
  Kaggle Model Proxy or another external API is selected instead, that cloud
  execution and transmission of requester-private features must be disclosed.

### Reproducibility caveat

At inspection, the repository was dirty and many relevant files were untracked.
The current `HEAD` alone does not contain all current harness, evaluator, and
pilot files. A notebook that only clones `HEAD` would not reproduce this
working tree. Before setup, make a controlled, allowlisted source snapshot with
a manifest/hash; do not include existing restricted logs, local provider data,
or credentials.

## 6. Required components and notebook bootstrap plan

No Kaggle notebook file was created. A safe eventual notebook can be organized
as follows:

1. **Run manifest and environment check:** record Kaggle notebook ID/version,
   source/data hashes, Python/Torch/Transformers versions, available RAM/disk,
   GPU model/count/VRAM, and internet/accelerator settings. Fail before any
   model or match activity if the selected environment is not the recorded one.
2. **Private, allowlisted inputs:** attach a versioned Quarto source snapshot,
   the required frozen QM9 adapter artifacts, and the two exact Kaggle model
   variation versions. Do not mount old restricted pilot logs or unrelated
   repository artifacts.
3. **Runtime setup:** use a pinned, compatible Python/Torch/Transformers stack
   only after checking the actual Kaggle image and both model cards. Upstream
   references indicate Transformers 4.50.0 or later for Gemma 3 and at least
   4.51.0 to avoid Qwen3 compatibility errors, but this is not yet a tested
   combined Kaggle dependency lock.
4. **Freeze instance:** reconstruct or load the exact `InstanceSpec` once,
   record its `instance_id`, selected feature IDs, 16 entity IDs, seed, and a
   canonical hash; verify both players' private feature ownership.
5. **Local model smoke tests:** load weights without sending game state; make
   a harmless exact-JSON request for each model, validate schema, capture actual
   model/variation/version and response metadata, and check timeout/error paths.
6. **Matched two-game execution:** initialize the existing runner with clients
   implementing the existing `chat` contract, reuse the exact same instance
   and player-to-model/feature mapping, and vary only `starting_player`.
7. **Artifacts and evaluator:** create a unique run directory; keep restricted
   traces/audit logs private; emit a sanitized public report; run the unchanged
   Evaluator v0.1 against the complete artifacts.

The bootstrap cannot yet be completed safely because the current harness is
bound to the old provider clients/model tags, and the Kaggle variation files,
runtime, and package versions have not been verified. This is a blocker to
execution, not a reason to alter the approved two-match design.

## 7. Validation, changes, and remaining blockers

### Commands and outcomes

- Read-only Kaggle model searches and model-card retrievals: completed as
  described above; no model weights downloaded.
- `kaggle benchmarks tasks list --all`: completed; no tasks found for this
  account.
- `kaggle quota --format json`: completed; account quota returned, but no
  hardware/session probe.
- Full public model catalog pagination: not completed; the request remained
  active after 180 seconds and was stopped.
- Unit tests: not run for this documentation/research task. Existing relevant
  harness tests were inspected, not executed.
- Real matches: none.
- Model prompts/private-data requests: none.

### Files

- Created: `reports/kaggle_model_discovery_feasibility_20261110.md`.
- No code, evaluator semantics, game rules, model configuration, or notebook
  files were modified.
- No files were staged or committed.

### Remaining blockers before a real-model pilot

1. Verify account-level access to the exact Gemma/Qwen variation files and
   resolve each variation's exact framework, immutable version, file list, and
   file hashes.
2. Use a Kaggle Notebook to measure actual accelerator availability, VRAM, RAM,
   disk, internet setting, and session constraints without starting a match.
3. Confirm compatible local inference packages and successfully load both
   weights; run harmless exact-JSON and timeout/error smoke tests.
4. Add or configure a local-model client that preserves the existing Agent
   contract and records actual loaded model identity. Do not label a model with
   an unverified requested name.
5. Freeze and hash the exact current Quarto source/data snapshot and generated
   instance; preserve the fixed ownership and change only `starting_player`.
6. Confirm the applicable Gemma terms/access requirements and keep the Kaggle
   notebook and restricted artifacts private.

## Sources

- [Kaggle CLI documentation and command reference](https://github.com/Kaggle/kaggle-cli)
- [Kaggle official Gemma 3 model record](https://www.kaggle.com/models/google/gemma-3)
- [Kaggle official Qwen 3 model record](https://www.kaggle.com/models/qwen-lm/qwen-3)
- [Google Gemma documentation](https://ai.google.dev/gemma/docs/core)
- [Google Gemma 3 instruction model card](https://huggingface.co/google/gemma-3-4b-it)
- [Qwen3 official release announcement](https://qwenlm.github.io/blog/qwen3/)
- [Qwen3-4B model card](https://huggingface.co/Qwen/Qwen3-4B)
- [DeepSeek-R1 model card](https://www.kaggle.com/models/deepseek-ai/deepseek-r1)
- [Mistral Small 24B model card](https://www.kaggle.com/models/mistral-ai/mistral-small-24b)

**READY WITH BLOCKERS**
