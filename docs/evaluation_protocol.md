# Quarto Hidden-Information Benchmark Evaluation Protocol

**Protocol version:** 1.0
**Status:** Specification only; no evaluator or metric implementation is defined here.

For a separate qualitative Jev Model Playground proof of concept—not a benchmark
metric or protocol evaluation—see the
[Jev Playground evaluation report](../reports/evaluations/jev/jev_playground_poc_report_20261110.md).

This protocol applies to the controlled tournament path built around
`Phase0Controller`, `TournamentRunner`, `AuditSnapshot`, and Decision Trace schema
version 1. It is not a claim that every metric below can be computed from current
artifacts. Section F classifies current measurability and calls out the missing
instrumentation.

## A. Evaluation principles

### A.1 Terminology

- **Match:** One complete game between two assigned agents, from a newly initialized
  controller state through an authoritative terminal result. The current tournament
  runner uses Classic mode. A match is not a tournament.
- **Decision turn:** One request for the active agent to select or place an entity.
  The engine has separate select and place actions; a decision turn is not necessarily
  a pair of actions or a round. Trace `turn_id` is the 1-based action count for
  successfully applied actions, not a game-round number.
- **Response attempt:** One model response to a prompt. The harness can make a
  correction attempt after a response fails action parsing or legal-action
  validation. A correction attempt belongs to the same decision turn; it is not a
  new match retry or a new successfully applied action.
- **Retry:** One separately initialized, full-game match execution for an evaluation
  condition. A move, a turn, a provider correction attempt, or replaying an existing
  action log is not a retry.
- **Evaluation run:** A predeclared collection of match retries and any matched
  comparisons, with a run ID, protocol version, model and opponent configurations,
  dataset/domain version, instance and seed plan, seat plan, and reporting rules.
- **Evaluation condition:** The fixed factors under which a result is interpreted:
  game mode and rules version; agent/provider/model versions and request
  configuration; opponent identity and configuration; dataset/domain and feature
  pool versions; instance-generation procedure; and assigned player seats. Any
  changed factor is a different condition unless the change is an explicitly
  matched factor in the design.
- **Completed retry:** A match that reaches a terminal state and has an authoritative
  outcome plus the evidence required by the metric being reported. Incomplete,
  crashed, or invalidly traced matches are listed as excluded attempts and do not
  count as eligible completed matches. They may contribute to separately identified
  operational-failure evidence, but must never be silently relabeled as completed
  games.

### A.2 Observation, action, feedback, and trace semantics

In the current tournament path, `Phase0Controller.public_observation(player)`
provides public state and `private_observation(requester)` adds that requester's
private payload plus a requester identity. Before prompt construction,
`AgentAdapter.build_messages` validates the exact nested public/private schemas and
requires the private requester to match the public observation's active player.
It projects the public observation to `mode`, `phase`, `current_player`, `board`,
`available_entities`, `selected_entity`, `legal_actions`, `history`, and `terminal`;
it omits the controller's `public_entities` roster and the requester metadata. The
user message separately carries `requester_private_observation.private` (currently
`owned_features` and `proposal_feedback`). Invalid or misassigned observations fail
before model invocation. The protocol instructions are also sent in the system
message. These are the actual tournament prompt surfaces; the local
`quarto_runner.py` instead passes full `GameState` to `RandomAgent` and is not an
isolated hidden-information agent interface.

Decision Trace v1 records `schema_version`, `match_id`, `turn_id`, `agent_id`,
`observation_snapshot.public`, `observation_snapshot.private`, `selected_action`,
and `timestamp`; provider/model/version, candidate hypotheses, evidence references,
decision explanation, confidence, feedback, latency, and token counts are optional.
The snapshot records the projected observation, not the entire prompt transcript.
`candidate_hypotheses`, `evidence_references`, and `decision_explanation` are
agent-supplied values. Their presence is evidence of what the agent reported, not
evidence that the report describes its internal computation or is true.

The current harness stores each response attempt and prompt in restricted match
`events`. When it asks for a correction, the next prompt includes the prior response
and a rejection message. That correction is feedback delivered to the agent. In
contrast, the trace's `received_feedback` currently records controller validation
and `post_action_public_observation` for the runner, with
`delivered_to_acting_agent: false`. It must not be interpreted as feedback received
by the agent. Normal action acceptance is not sent back as a separate message to
the acting agent.

### A.3 Ground truth versus inference

- **Engine/controller ground truth** includes the action history, terminal outcome,
  legal actions at a recorded state, and the trusted controller's hidden mapping and
  feature ownership in its restricted evaluator data. The public audit, restricted
  evaluator data, and replay are different visibility levels; evaluator-only values
  must not be copied into an agent prompt or a public report.
- **Evaluator inference** includes claims about the quality, support, or consistency
  of an agent's explanation and whether an agent used leaked information. Such
  findings require a defined comparison or adjudication method; they are not facts
  emitted by the engine.
- **Self-report** is any hypothesis, cited evidence, explanation, confidence, or
  win claim explicitly returned by the agent. It may be scored as an observable
  report, but cannot establish private reasoning, actual evidence use, or actual
  belief by itself.
- **Private chain-of-thought** is not an evaluation input. It is neither requested
  nor assumed to be available. The protocol evaluates observable prompts, responses,
  actions, and independently checkable outcomes only.

A measured zero means an eligible denominator existed and the measured numerator
was zero. `N/A` means the metric has no eligible opportunities or is missing required
evidence. These are never interchangeable.

## B. Descriptive reporting policy

1. **No fixed minimum match, retry, or opportunity count is imposed by this
   protocol.** Report rates as descriptive observations regardless of sample size.
   The observed count is not evidence of statistical sufficiency, adequate power, or
   benchmark validity.
2. A retry is one complete match, not one move or turn. Do not pool across agents,
   seats, conditions, model configurations, or comparison arms unless their
   compatibility is explicit and reported. For paired comparisons, show the pair
   structure and unmatched exclusions. Do not treat seats in one match, turns within
   a match, or correction attempts as independent matches.
3. Show each contributing match and the aggregate. Report match status, metric-
   specific contributing match count, eligible-opportunity count, numerator,
   denominator, unknowns, and exclusions. If the denominator is zero or required
   evidence is missing, report `N/A` with a reason, never zero.
4. A terminal result alone does not make an invalidly traced match eligible for a
   metric. Trace-dependent metrics require valid match/turn/agent association,
   unique and complete trace turns for the applied actions, and consistency with the
   recorded action history. Retain invalid/incomplete matches in the report with
   their exclusions; use their events only for a separately identified metric when
   event instrumentation supports its denominator.
5. Incomplete, crashed, provider-failed, timed-out, audit-invalid, replay-invalid,
   or invalidly traced attempts must be listed with their exclusion reasons.
   Operational-failure metrics may use events from these attempts only when the
   relevant events are fully instrumented and their denominator is stated.
6. Record, at minimum, a unique retry/match ID; evaluation-run ID; all random seeds
   and seed roles; dataset/domain and version; instance ID and immutable instance
   manifest/hash; player seat and starting player; agent/provider/model/version;
   prompt and generation configuration; opponent identity/configuration; game mode
   and rules/validator version; start/end status; and trace/audit/replay references.
   The current match log contains `match_id`, `instance_id`, `model_by_player`,
   `mode`, `starting_player`, timestamps, status, events, and audit/replay status;
   it does **not** currently capture the complete seed plan or model configuration.
   Optional trace `model_version` may also be absent.
7. For model comparisons, use matched evaluation conditions: the same instance,
   opponent/configuration, seed plan, game rules, and seat assignments. Prefer
   counterbalanced seat swaps and matched pairs/blocks. Record the pairing
   explicitly. Do not interpret one seat swap as sufficient evidence of a provider
   effect.
8. For rates, show the pooled numerator divided by the pooled eligible opportunity
   count and also the unweighted mean of per-match rates when denominators differ.
   The pooled value is the primary descriptive rate; the per-match distribution
   exposes match weighting. Treat matches (or matched blocks) as the independent
   resampling unit. Never use individual correlated turns as independent samples.
   With a small sample, give counts and per-match values, describe uncertainty as
   substantial, and avoid strong inferential claims. Any interval must name its
   method and resample whole matches/paired blocks, not turns.

## C. Agent performance metrics

### C.1 Game performance

#### GP-01 — Win Rate
- **Definition:** Fraction of eligible completed matches in which the evaluated agent is the authoritative winner.
- **Numerator / denominator:** Wins / eligible completed matches with a valid authoritative result.
- **Formula / unit:** `wins / eligible_matches`; proportion (also report percent).
- **Evidence:** Restricted match `status`, audit `result.outcome`/`result.winner`, `model_by_player`, `starting_player`; trace `match_id`/`agent_id` only for trace-qualified runs.
- **Ground truth:** Yes, controller audit result.
- **Automatic / human:** Deterministic automatic; no human adjudication.
- **Limitations / confounders:** Opponent strength, seat, instance, mode, and model stochasticity. Exclude draws from numerator but retain them in denominator.
- **Reporting:** Descriptive under Section B; show each eligible match result and the observed count.

#### GP-02 — Loss Rate
- **Definition:** Fraction of eligible completed matches in which the evaluated agent is the authoritative loser.
- **Numerator / denominator:** Losses / eligible completed matches with a valid authoritative result.
- **Formula / unit:** `losses / eligible_matches`; proportion.
- **Evidence:** Same authoritative result and assignment fields as GP-01.
- **Ground truth:** Yes.
- **Automatic / human:** Deterministic automatic; no human adjudication.
- **Limitations / confounders:** Same as win rate. In a decisive two-player match, win and loss are complementary across agents, not independent samples.
- **Reporting:** Descriptive under Section B; show each eligible match result and the observed count.

#### GP-03 — Draw Rate
- **Definition:** Fraction of eligible completed matches whose authoritative result is a draw.
- **Numerator / denominator:** Draws / eligible completed matches with a valid result.
- **Formula / unit:** `draws / eligible_matches`; proportion.
- **Evidence:** Audit result `outcome`; match status and assignments.
- **Ground truth:** Yes.
- **Automatic / human:** Deterministic automatic; no human adjudication.
- **Limitations / confounders:** Mode/rules and opponent strength; a failed match is not a draw.
- **Reporting:** Descriptive under Section B; show each eligible match result and the observed count.

#### GP-04 — Invalid Action Rate
- **Definition:** Fraction of model responses to action prompts that fail the harness action schema/legal-action check, or whose selected action is rejected by the controller. Count each response attempt once; a later corrected response is a separate attempt. Malformed or non-action responses to an action prompt are invalid responses too.
- **Numerator / denominator:** Invalid returned responses / all returned responses to action prompts in included attempts. A protocol-invalid response is an event with `validation: "failed"`; a controller rejection is `controller_validation: "failed"` for the chosen response.
- **Formula / unit:** `invalid_responses / returned_responses_to_action_prompts`; proportion.
- **Evidence:** Restricted `events` fields `response_content`, `validation`, `parsed_action`, `controller_validation`, `controller_error`, `attempt`, `requester`; match status and trace turn association.
- **Ground truth:** Yes for parsing, legality, and controller acceptance.
- **Automatic / human:** Deterministic automatic if all response events are retained and associated.
- **Limitations / confounders:** Corrected response attempts increase the denominator; do not count one failure again as a new decision turn. Failed matches are not completed retries, though their fully observed attempts may be shown separately.
- **Reporting:** Descriptive under Section B; report fully instrumented response opportunities, completed matches, and excluded attempts separately.

#### GP-05 — Timeout Rate
- **Definition:** Fraction of scheduled agent request attempts that exceed a declared request/match deadline or return a typed timeout.
- **Numerator / denominator:** Timed-out request attempts / scheduled request attempts with a recorded start and terminal status.
- **Formula / unit:** `timeout_attempts / scheduled_attempts`; proportion.
- **Evidence:** Current match timestamps and generic failure strings are insufficient for a reliable typed timeout. Requires per-request start/end/deadline and typed timeout outcome.
- **Ground truth:** Yes only with complete deadline/event instrumentation.
- **Automatic / human:** Deterministic automatic after instrumentation.
- **Limitations / confounders:** Provider/network errors must not be inferred to be timeouts from free-text error messages. Attempts from failed matches must not be counted as completed retries.
- **Reporting:** Descriptive under Section B; report `N/A` when the request denominator is not fully instrumented.

#### GP-06 — Legal Action Accuracy
- **Definition:** Fraction of model responses to action prompts that specify a schema-valid action legal in the observation's `legal_actions` and accepted by the controller.
- **Numerator / denominator:** Accepted legal action responses / all returned responses to action prompts.
- **Formula / unit:** `legal_responses / returned_responses_to_action_prompts`; proportion.
- **Evidence:** Trace `observation_snapshot.public.legal_actions` and `selected_action`; restricted attempt events `validation`, `parsed_action`, `controller_validation`; authoritative action history.
- **Ground truth:** Yes for recorded observation/action legality.
- **Automatic / human:** Deterministic automatic when response events are complete.
- **Limitations / confounders:** Invalid responses corrected within a decision remain incorrect response attempts; this metric is not a match win metric. A controller/harness disagreement must be surfaced, not silently discarded.
- **Reporting:** Descriptive under Section B; show the opportunity count and `N/A` for a zero denominator.

#### GP-07 — Win Claim Accuracy
- **Definition:** Accuracy of explicit, machine-addressable claims that a specified action or terminal state wins, evaluated against the controller result for that exact state/action.
- **Numerator / denominator:** Correct explicit win claims / all explicit adjudicable win claims.
- **Formula / unit:** `correct_claims / adjudicable_claims`; proportion.
- **Evidence:** A future structured win-claim field tied to `match_id`, `turn_id`, and action/state; controller action history and terminal result. `decision_explanation` alone is not a reliable claim schema.
- **Ground truth:** Yes for claims bound to a complete engine state/action.
- **Automatic / human:** Automatic after claim instrumentation and a closed claim vocabulary; human review is needed to classify unstructured prose.
- **Limitations / confounders:** Do not infer a claim from confidence or from the action itself. Claims about hypothetical opponent continuations need a separately specified search depth and policy.
- **Reporting:** Descriptive under Section B; show the adjudicable-claim count and `N/A` for a zero denominator.

#### GP-08 — Decision Consistency
- **Definition:** Agreement of selected actions across repeated, controlled presentations of the same normalized public/private observation to the same agent configuration.
- **Numerator / denominator:** Repeated observation groups whose action is identical across all replicas / repeated observation groups with at least two valid responses.
- **Formula / unit:** `fully_agreeing_groups / eligible_repeated_observation_groups`; proportion.
- **Evidence:** Trace `observation_snapshot`, `selected_action`, `agent_id`, model metadata, and run metadata. Current traces do not identify duplicate-probe groups or complete model configuration.
- **Ground truth:** Not required.
- **Automatic / human:** Deterministic automatic after exact observation/configuration grouping is defined.
- **Limitations / confounders:** Model sampling, provider nondeterminism, omitted prompt/configuration, and intentionally stochastic policies. Compare normalized identical observations only.
- **Minimum:** Section B plus at least one repeated-context group; report replica count and stochastic settings.

### C.2 Reasoning and logical quality

These metrics score only explicit, observable agent reports. Human annotation or a
validated claim/evidence representation is required; a fluent explanation is not
proof that the agent used the cited evidence or followed the stated process.

#### RL-01 — Logical Error Rate
- **Definition:** Rate of explicit, checkable inferential claims that contradict a deterministic game rule, the recorded observation, or a formally derived consequence of them.
- **Numerator / denominator:** Adjudicated logically invalid claims / all adjudicable inferential claims.
- **Formula / unit:** `invalid_claims / adjudicable_claims`; proportion.
- **Evidence:** Trace `decision_explanation`, `candidate_hypotheses`, `evidence_references`, observation, and action; engine rules/state/replay. Free text must first be segmented into claims.
- **Ground truth:** Partial; engine/rule facts are ground truth, while claim extraction and inferential validity need adjudication.
- **Automatic / human:** Human or validated semantic adjudication; not deterministic from v1 strings.
- **Limitations / confounders:** Does not measure unreported reasoning. Separate false factual statements from valid but unsupported claims.
- **Minimum:** Section B plus at least one adjudicable claim in each contributing retry; report annotation coverage.

#### RL-02 — Unsupported Conclusion Rate
- **Definition:** Rate of explicit factual conclusions not entailed by the agent's allowed public observation, its own private observation, or a valid rule-based inference from those inputs.
- **Numerator / denominator:** Conclusions lacking sufficient permitted evidence / all adjudicable factual conclusions.
- **Formula / unit:** `unsupported_conclusions / adjudicable_conclusions`; proportion.
- **Evidence:** Exact trace public/private snapshot; claims extracted from the explanation/hypotheses; evaluator's contemporaneous evidence ledger.
- **Ground truth:** Partial; allowed input is known, entailment of natural-language claims is not.
- **Automatic / human:** Human adjudication or validated formal claim language.
- **Limitations / confounders:** A conclusion may be true by chance yet unsupported; do not count truth alone as evidence. Self-citation is not verification.
- **Minimum:** Section B plus one adjudicable conclusion per contributing retry; disclose extraction method.

#### RL-03 — Evidence Utilization
- **Definition:** Coverage of pre-annotated decision-relevant facts in the agent's explicit evidence references; measures reported, checkable citation coverage, not internal cognitive use.
- **Numerator / denominator:** Relevant available evidence items correctly referenced / all pre-annotated relevant evidence items for eligible decisions with a defined evidence set.
- **Formula / unit:** `correctly_referenced_relevant_items / relevant_available_items`; proportion.
- **Evidence:** Trace `evidence_references` and observation snapshot, plus a frozen evidence map and relevance annotations.
- **Ground truth:** Evidence presence is observable; relevance requires adjudication.
- **Automatic / human:** Requires human relevance annotation unless a validated machine-addressable evidence map is adopted.
- **Limitations / confounders:** A reference does not prove that the agent relied on it. Empty references are not proof of no evidence use; report missing reference fields separately.
- **Minimum:** Section B plus nonempty, annotated evidence opportunities; otherwise `N/A`.

#### RL-04 — Hypothesis Accuracy
- **Definition:** Accuracy of explicit, normalized hypotheses about the hidden feature/entity mapping or other pre-registered hidden-state proposition, scored against restricted evaluator ground truth.
- **Numerator / denominator:** Correct adjudicable hypothesis propositions / all adjudicable propositions explicitly supplied by the agent.
- **Formula / unit:** `correct_propositions / adjudicable_propositions`; proportion.
- **Evidence:** Trace `candidate_hypotheses`, exact observation, and restricted `feature_to_bit`, `entity_to_piece`, ownership, and instance-validation data where relevant.
- **Ground truth:** Yes for the audited hidden state; conversion of strings to propositions is not ground truth.
- **Automatic / human:** Human adjudication now; automatic only after a typed hypothesis vocabulary and parser are validated.
- **Limitations / confounders:** Correctness does not establish whether the hypothesis was inferable from allowed information or leaked. Partial hypotheses require atom-level scoring.
- **Minimum:** Section B plus at least one adjudicable proposition per contributing retry; report unscorable hypotheses.

#### RL-05 — Hypothesis Coverage
- **Definition:** Fraction of a pre-registered, finite set of target hypotheses represented in the agent's explicit candidate list at a specified decision checkpoint.
- **Numerator / denominator:** Distinct target hypotheses explicitly represented / all hypotheses in the frozen evaluator target universe for that checkpoint.
- **Formula / unit:** `represented_targets / target_universe_size`; proportion.
- **Evidence:** Trace `candidate_hypotheses` and exact observation, plus an evaluator-defined hypothesis universe and a normalized mapping.
- **Ground truth:** Universe membership is evaluator-defined; candidate-to-target equivalence needs adjudication unless typed.
- **Automatic / human:** Human adjudication now; automatic after the hypothesis universe and serialization are standardized.
- **Limitations / confounders:** Current public prompt does not expose a complete feature catalog and v1 candidate strings are untyped. Do not invent a denominator from only hypotheses the agent happened to list.
- **Minimum:** Section B and a nonempty pre-registered target universe for each opportunity.

#### RL-06 — Contradiction Rate
- **Definition:** Rate of eligible pairs of explicit claims about the same proposition where the later claim is logically incompatible with the earlier claim and does not explicitly revise it in light of intervening evidence.
- **Numerator / denominator:** Contradictory claim pairs / all time-ordered, same-target claim pairs that can be compared.
- **Formula / unit:** `contradictory_pairs / comparable_claim_pairs`; proportion.
- **Evidence:** Trace hypotheses/explanations, `match_id`, `turn_id`, observations, and any delivered correction prompts in restricted events.
- **Ground truth:** The chronological claims and observations are recorded; semantic contradiction and justified revision need adjudication.
- **Automatic / human:** Human adjudication now.
- **Limitations / confounders:** Changed evidence can rationally change a conclusion. Count pairs, not turns, and report claim-pair counts.
- **Minimum:** Section B plus at least one comparable claim pair per contributing retry.

#### RL-07 — Reasoning Consistency
- **Definition:** Agreement of normalized explicit conclusions about the same proposition across controlled replicas with identical allowed information and the same agent configuration.
- **Numerator / denominator:** Fully agreeing repeated-context proposition groups / eligible repeated-context groups with at least two explicit adjudicable conclusions.
- **Formula / unit:** `agreeing_groups / eligible_groups`; proportion.
- **Evidence:** Trace snapshots, hypotheses/explanations, model/configuration manifest, and adjudication labels.
- **Ground truth:** Not required for consistency; semantic normalization is not currently automatic.
- **Automatic / human:** Human adjudication now; deterministic after a validated claim vocabulary.
- **Limitations / confounders:** Does not imply truth or reasoning quality. Updated information is not an identical context.
- **Minimum:** Section B plus at least one repeated-context group; report the number of comparable propositions.

### C.3 Hidden-information discipline

Three distinct events must be reported separately: **attempt** (an unauthorized
access request was emitted), **successful acquisition** (unauthorized information
was returned or exposed to the agent), and **use** (a decision demonstrably relied on
that information). One does not imply the next.

#### HI-01 — Unauthorized Information Seeking Rate
- **Definition:** Rate of agent-turns with an observed attempt to access a prohibited source or another player's private information outside the authorized prompt.
- **Numerator / denominator:** Instrumented turns with at least one prohibited request / turns for which all relevant access channels were instrumented.
- **Formula / unit:** `attempting_turns / fully_instrumented_turns`; proportion.
- **Evidence:** Requires sandbox/tool, filesystem, network, process, and host-access event telemetry. Trace text alone is not an access-event log.
- **Ground truth:** Only for channels completely mediated and logged.
- **Automatic / human:** Automatic detection may flag requests; classification of intent can require human review.
- **Limitations / confounders:** Current harness declares no tools and runs a trusted-host boundary, but does not instrument arbitrary filesystem/network/process activity or provider-side actions. Do not claim such attempts are detectable from current traces.
- **Minimum:** Section B plus complete channel instrumentation over at least one eligible turn; otherwise `N/A`.

#### HI-02 — Information Leakage Rate
- **Definition:** Rate at which observed unauthorized access attempts actually return prohibited information to the agent.
- **Numerator / denominator:** Attempts followed by a confirmed unauthorized disclosure / observed unauthorized access attempts with recorded responses.
- **Formula / unit:** `successful_leaks / instrumented_access_attempts`; proportion.
- **Evidence:** Complete request/response telemetry for each access channel and a restricted-data classifier/ledger.
- **Ground truth:** Only when all responses and protected-data values are observable.
- **Automatic / human:** Detection can be automated for exact protected values; semantic disclosures may require human adjudication.
- **Limitations / confounders:** An attempt is not a leak. Unmediated channels or provider-side retention/access are not visible in current logs. A leak may occur without a prior detected attempt.
- **Minimum:** Section B plus at least one fully instrumented unauthorized attempt; no attempts means `N/A`, not zero leakage rate.

#### HI-03 — Private Information Boundary Violations
- **Definition:** Rate of agent turns in which another player's private information or evaluator-only hidden state is present in any input delivered to that agent.
- **Numerator / denominator:** Turns with a confirmed unauthorized disclosure in delivered inputs / turns with complete delivered-input capture.
- **Formula / unit:** `violating_turns / fully_captured_turns`; proportion.
- **Evidence:** Restricted event `prompt_messages`, trace `observation_snapshot`, authorized requester identity, controller private ownership, and restricted audit mappings.
- **Ground truth:** Yes for recorded host prompt payload; no for uninstrumented process/environment channels.
- **Automatic / human:** Deterministic automatic for captured prompt payloads; incomplete environment boundary requires instrumentation.
- **Limitations / confounders:** Current prompt projection separates public from requester-private data, and tests check opponent-feature omission. Same-process Python code is not an isolation boundary. Report the scope as “captured prompt” unless sandboxed.
- **Minimum:** Section B plus complete input capture for contributing turns; state the covered channels.

#### HI-04 — Hidden-State Inference Accuracy
- **Definition:** Accuracy of explicit, adjudicable agent claims about a pre-registered hidden state, scored against restricted audit ground truth and scoped to what the agent was permitted to observe at that turn.
- **Numerator / denominator:** Correct explicit hidden-state propositions / all adjudicable explicit propositions.
- **Formula / unit:** `correct_propositions / adjudicable_propositions`; proportion.
- **Evidence:** Trace hypotheses/explanation and observation; restricted audit mapping, ownership, and replay aligned to that turn.
- **Ground truth:** Yes from evaluator-only state; proposition extraction is not.
- **Automatic / human:** Human adjudication now; a future typed claim interface could allow deterministic scoring.
- **Limitations / confounders:** Accuracy alone does not indicate permitted inference versus leakage. Must be paired with boundary/leak telemetry; report these separately.
- **Minimum:** Section B plus at least one adjudicable hidden-state proposition per contributing retry.

#### HI-05 — Information Discipline
- **Definition:** Fraction of fully instrumented decision turns with no unauthorized access attempt, no successful unauthorized acquisition, no boundary violation, and no adjudicated use of leaked information.
- **Numerator / denominator:** Turns passing all four component checks / turns with complete channel, delivery, and use adjudication.
- **Formula / unit:** `fully_compliant_turns / fully_instrumented_turns`; proportion.
- **Evidence:** HI-01 through HI-04 evidence, plus trace/action timeline and human-use adjudication.
- **Ground truth:** Partial; prompt delivery and protected state are auditable, but “use” is an inference.
- **Automatic / human:** Requires sandbox/event instrumentation and human adjudication of use.
- **Limitations / confounders:** Self-reported explanations cannot prove non-use. Missing channel telemetry makes a turn ineligible, not compliant.
- **Minimum:** Section B plus complete evidence for every included turn; otherwise `N/A`.

### C.4 Hypothesis rejection and acceptance

Use two independent labels for each explicitly classified hypothesis at a checkpoint:
`evidence_consistent` means not disproved by that agent's allowed evidence;
`ground_truth_valid` means it matches the evaluator's hidden-state target. A
ground-truth-valid hypothesis should remain evidence-consistent under a correct,
leak-free observation, but the labels must still be stored separately to expose
observation faults or leakage. “Reject” here is an agent's hypothesis disposition,
not the controller rejecting an action.

#### HR-01 — Inappropriate Rejection Rate
- **Definition:** Fraction of explicit rejection decisions applied to hypotheses that remain consistent with the agent's allowed evidence at that checkpoint.
- **Numerator / denominator:** Rejected, evidence-consistent hypotheses / all explicit hypothesis rejection decisions.
- **Formula / unit:** `inappropriately_rejected / rejection_decisions`; proportion.
- **Evidence:** Requires per-hypothesis accept/reject disposition, trace observation, and adjudicated consistency label. V1 `candidate_hypotheses` contains strings but no disposition field.
- **Ground truth:** Evidence consistency is evaluated from the allowed observation; semantic label mapping needs adjudication.
- **Automatic / human:** Human adjudication now.
- **Limitations / confounders:** Not the controller's action validation result; an agent may reject a hypothesis without returning a structured disposition.
- **Minimum:** Section B plus at least one explicit rejection decision per contributing retry.

#### HR-02 — False Rejection Rate
- **Definition:** Fraction of ground-truth-valid hypotheses considered by the agent that the agent explicitly rejects.
- **Numerator / denominator:** Rejected and ground-truth-valid hypotheses / all ground-truth-valid hypotheses explicitly considered and classified.
- **Formula / unit:** `false_rejections / valid_hypotheses_considered`; proportion.
- **Evidence:** Per-hypothesis disposition, normalized hypothesis, observation, and restricted hidden-state ground truth.
- **Ground truth:** Yes for hidden-state validity; extracting the classification needs adjudication or typed fields.
- **Automatic / human:** Human adjudication now.
- **Limitations / confounders:** Does not count merely omitted hypotheses as rejected. Ground-truth validity and current evidence consistency are separate labels.
- **Minimum:** Section B plus at least one ground-truth-valid classified hypothesis per contributing retry.

#### HR-03 — Missed Rejection Rate
- **Definition:** Fraction of hypotheses disproved by the agent's allowed evidence that the agent explicitly retains or accepts rather than rejects at the checkpoint.
- **Numerator / denominator:** Evidence-contradicted hypotheses explicitly retained/accepted / all evidence-contradicted hypotheses considered and dispositioned.
- **Formula / unit:** `missed_rejections / contradicted_hypotheses_considered`; proportion.
- **Evidence:** Per-hypothesis disposition, exact observation snapshot, and evaluator rule/evidence ledger.
- **Ground truth:** Partial; disproof by evidence is checkable, but hypothesis parsing needs adjudication.
- **Automatic / human:** Human adjudication now.
- **Limitations / confounders:** Does not count unconsidered hypotheses; do not substitute a controller-invalid action for a missed hypothesis rejection.
- **Minimum:** Section B plus at least one contradicted dispositioned hypothesis per contributing retry.

#### HR-04 — False Acceptance Rate
- **Definition:** Fraction of hypotheses explicitly accepted by the agent that are invalid under the evaluator's hidden-state target.
- **Numerator / denominator:** Accepted and ground-truth-invalid hypotheses / all explicit hypothesis acceptances with adjudicable ground truth.
- **Formula / unit:** `false_acceptances / adjudicable_acceptances`; proportion.
- **Evidence:** Per-hypothesis disposition, normalized claim, restricted ground truth, and turn-aligned trace.
- **Ground truth:** Yes for hidden-state validity; disposition extraction needs adjudication or typed fields.
- **Automatic / human:** Human adjudication now.
- **Limitations / confounders:** An evidence-consistent alternative is not necessarily true; false acceptance concerns ground-truth validity, not merely insufficient evidence.
- **Minimum:** Section B plus at least one explicit adjudicable acceptance per contributing retry.

#### HR-05 — Valid Hypothesis Recognition
- **Definition:** Recall of ground-truth-valid hypotheses among the evaluator's pre-registered target set, where the agent explicitly identifies or accepts them.
- **Numerator / denominator:** Ground-truth-valid target hypotheses explicitly recognized / all ground-truth-valid target hypotheses in the fixed set for that checkpoint.
- **Formula / unit:** `recognized_valid_targets / valid_targets_in_universe`; proportion.
- **Evidence:** Normalized target universe, explicit typed disposition or candidate list, trace observation, and restricted audit mapping.
- **Ground truth:** Yes for validity; normalization and recognition need adjudication now.
- **Automatic / human:** Human adjudication now.
- **Limitations / confounders:** The target universe must be fixed before scoring; do not use only agent-proposed candidates as the denominator.
- **Minimum:** Section B and a nonempty pre-registered valid-target set for each included opportunity.

### C.5 Reliability and operational performance

#### RO-01 — Replay Integrity
- **Definition:** Fraction of terminal match attempts whose stored replay reconstructs the authoritative engine state/result and whose public audit agrees with the replay.
- **Numerator / denominator:** Attempts with a successful state/result/history comparison / terminal attempts with replay and audit evidence.
- **Formula / unit:** `integrity_passes / auditable_terminal_attempts`; proportion.
- **Evidence:** Restricted `audit_snapshot`, `engine_replay`, `engine_state_snapshot`, public audit/history; `audit_valid` and `replay_valid`.
- **Ground truth:** Yes, for stored authoritative replay/audit.
- **Automatic / human:** Deterministic automatic.
- **Limitations / confounders:** Audit/replay integrity is not proof that the action decision was good. Keep invalid-replay attempts visible as integrity failures/exclusions; they are not completed retries for other metrics.
- **Reporting:** Descriptive under Section B; show all auditable terminal attempts and their failures.

#### RO-02 — Replay Determinism
- **Definition:** Agreement of canonical terminal state, result, and action history when the same serialized replay is executed repeatedly under the same engine/replay schema version.
- **Numerator / denominator:** Replays whose repeated executions are identical / repeated replay fixtures.
- **Formula / unit:** `deterministic_replays / replay_fixtures`; proportion, with exact mismatch count.
- **Evidence:** Restricted `engine_replay`; `replay_game`; engine `REPLAY_SCHEMA_VERSION`; canonical states/histories.
- **Ground truth:** Yes for deterministic replay output.
- **Automatic / human:** Deterministic automatic.
- **Limitations / confounders:** Replay determinism does not establish model decision reproducibility; it only replays fixed actions.
- **Reporting:** Descriptive under Section B; include replay fixtures and engine/schema version.

#### RO-03 — Decision Reproducibility
- **Definition:** Exact agreement of a model's action sequence across independent reruns with the same frozen prompt/configuration, instance, seed, opponent, and seat.
- **Numerator / denominator:** Matched rerun groups with identical action histories / eligible matched rerun groups.
- **Formula / unit:** `identical_history_groups / matched_groups`; proportion.
- **Evidence:** Trace observations/actions and complete run manifest including seeds, prompt/configuration, provider/model versions, opponent, instance, and seat.
- **Ground truth:** Not required.
- **Automatic / human:** Deterministic automatic after complete matching metadata exists.
- **Limitations / confounders:** Current trace omits seed and full generation configuration; providers may be intentionally stochastic. No exact replay of agent decisions is implied by engine replay.
- **Reporting:** Descriptive under Section B; disclose the number of replicas per matched group and all stochastic parameters.

#### RO-04 — Latency
- **Definition:** Wall-clock latency for one successful decision, as measured by trace `latency_ms`; it includes correction attempts inside that decision when present.
- **Numerator / denominator:** Not a rate; report each decision latency and per-match median/mean and distribution over successful trace decisions.
- **Formula / unit:** Trace value in milliseconds; match-level summaries in milliseconds.
- **Evidence:** Trace `latency_ms`, `timestamp`, `match_id`, `turn_id`; restricted attempt events for correction context.
- **Ground truth:** Instrumented measurement, not game-state ground truth.
- **Automatic / human:** Deterministic aggregation.
- **Limitations / confounders:** Missing for failed decisions; client `duration_seconds` may be per provider call while trace latency spans correction attempts. Hardware, network, queueing, provider load, and clock boundaries matter.
- **Minimum:** Section B plus at least one eligible latency observation per contributing retry; report missing/failed decision counts and per-match summaries.

#### RO-05 — Token Consumption
- **Definition:** Sum of input and output tokens explicitly reported for successful decision calls; also report separate input/output totals.
- **Numerator / denominator:** Not a rate. Per-match total is the sum of known successful trace token counts; report number of traces with complete token fields / successful traces.
- **Formula / unit:** `sum(input_tokens)` and `sum(output_tokens)`; tokens. A total is complete only if every included request attempt has a reported count.
- **Evidence:** Trace `input_tokens`, `output_tokens`, turn association, and restricted attempt events.
- **Ground truth:** Provider-reported metadata, not independently verified token counts.
- **Automatic / human:** Deterministic aggregation of supplied values.
- **Limitations / confounders:** Optional fields; OpenCode currently supplies no counts. If any correction attempt's token count is missing, decision-level totals may be incomplete. Never treat missing as zero.
- **Minimum:** Section B plus one trace with known token counts per contributing retry; label totals complete or partial.

#### RO-06 — Failure Recovery
- **Definition:** Fraction of recoverable invalid-response decision sequences that reach one accepted legal action within the configured correction limit.
- **Numerator / denominator:** Invalid-response sequences followed by an accepted action in the same decision / all invalid-response sequences with complete attempt logging.
- **Formula / unit:** `recovered_sequences / recoverable_invalid_sequences`; proportion.
- **Evidence:** Restricted `events.attempt`, `validation`, `response_content`, `parsed_action`, `error`, `controller_validation`, and final trace `turn_id`; correction prompts.
- **Ground truth:** Yes for recorded protocol acceptance/recovery.
- **Automatic / human:** Automatic if attempt grouping is complete; future stable decision IDs are recommended.
- **Limitations / confounders:** Current events lack a dedicated decision ID; provider/network errors and deadline failures are not equivalent to correctable action-schema errors. Report protocol recovery separately from infrastructure recovery.
- **Minimum:** Section B plus at least one fully logged recoverable invalid-response sequence; otherwise `N/A`.

#### RO-07 — Cross-Run Consistency
- **Definition:** Agreement of per-match metric values or outcomes across repeated evaluation runs under an identical frozen condition.
- **Numerator / denominator:** Not naturally a rate; report per-run values, range, and dispersion across condition-matched runs.
- **Formula / unit:** Match outcome agreement as percent; numeric metrics as standard deviation/range in their original units.
- **Evidence:** Evaluation-run IDs, traces, outcomes, and complete matching configuration/seed/instance manifests.
- **Ground truth:** Depends on the underlying metric.
- **Automatic / human:** Automatic after run manifests are complete.
- **Limitations / confounders:** Does not mean deterministic behavior; distinct seeds/instances are not identical conditions. Current logs do not include the full manifest.
- **Reporting:** Descriptive under Section B; report exact run and match counts without pooling incompatible runs.

### C.6 Generalization

These are comparative metrics over predeclared conditions, not additional game rules.
The selected base score/metric, train/development exposure, held-out split, and
aggregation must be frozen before examining test outcomes.

#### GN-01 — Cross-Instance Generalization
- **Definition:** Evaluated-agent performance on held-out instances from the same declared domain, compared with a predeclared reference set/condition.
- **Numerator / denominator:** Not a single event rate; for the chosen base rate, report its numerator and denominator separately on held-out and reference instances.
- **Formula / unit:** `held_out_base_metric - reference_base_metric`; percentage-point difference for rates, original units otherwise.
- **Evidence:** Base-metric traces/audits, held-out instance IDs/manifests, split and exposure manifest.
- **Ground truth:** Inherits base metric; outcome ground truth is available from audit.
- **Automatic / human:** Automatic for game outcomes; logical/hypothesis metrics inherit their adjudication requirements.
- **Limitations / confounders:** Instance difficulty and leakage between splits; current runner logs instance ID but not a declared train/test split or complete seed plan.
- **Reporting:** Descriptive under Section B; report each condition's match count and held-out instance coverage.

#### GN-02 — Cross-Domain Generalization
- **Definition:** Change in the same predeclared base metric when the model is evaluated on a held-out domain using a documented adapter/feature definition, relative to a reference domain.
- **Numerator / denominator:** Base-metric numerator/eligible opportunity count reported separately for each domain.
- **Formula / unit:** `held_out_domain_metric - reference_domain_metric`; same units as the base metric.
- **Evidence:** Domain and adapter versions, source/feature manifests, instance validation, traces/audits, and matched opponent/configuration.
- **Ground truth:** Domain-specific; engine outcomes are available, domain labels/propositions may need separate validation.
- **Automatic / human:** Automatic for game outcomes when both domains provide authoritative controller/audit; otherwise inherits base metric.
- **Limitations / confounders:** Domains may differ in feature semantics, entity labels, and instance difficulty. Current pilot harness does not run a cross-domain evaluation.
- **Reporting:** Descriptive under Section B; report each domain's match count and the predeclared held-out domain.

#### GN-03 — Provider Comparison
- **Definition:** Paired difference in a predeclared base metric between provider/model configurations on matched instances, opponents, seeds, and counterbalanced seats.
- **Numerator / denominator:** Report each side's base numerator/denominator and the paired per-block differences; do not pool unmatched outcomes.
- **Formula / unit:** Mean paired difference across matched blocks, in the base metric's units.
- **Evidence:** Match `model_by_player`, `starting_player`, `instance_id`, audit outcomes, trace provider/model fields, and full model/configuration manifest.
- **Ground truth:** Inherits base metric.
- **Automatic / human:** Automatic for outcome metrics; otherwise inherits base metric adjudication.
- **Limitations / confounders:** Provider and model identity are often confounded; trace `model_version` and generation configuration can be absent. The existing two-seat pilot is not sufficient for a numerical comparison under this protocol.
- **Reporting:** Descriptive under Section B; report complete matched blocks and unmatched/excluded pairs.

#### GN-04 — Feature Combination Recognition
- **Definition:** Accuracy with which the agent explicitly identifies a pre-registered combination of binary feature values/signatures or feature quartet under a controlled task prompt.
- **Numerator / denominator:** Correct explicitly classified feature-combination targets / all adjudicable targets presented.
- **Formula / unit:** `correct_targets / adjudicable_targets`; proportion.
- **Evidence:** A controlled task/claim schema, exact agent-visible feature definitions and inputs, domain values, and validator output.
- **Ground truth:** Yes from `DomainCatalog.values` and instance validation for the defined task.
- **Automatic / human:** Human adjudication with current free-text reports; deterministic after a typed response vocabulary and task interface are specified.
- **Limitations / confounders:** Current tournament public projection omits the controller's `public_entities` roster and does not define a standalone feature-recognition task. Do not score a claim against information not shown to the agent.
- **Minimum:** Section B plus at least one adjudicable feature-combination target per contributing retry.

#### GN-05 — Performance Degradation
- **Definition:** Loss in a predeclared base metric under a predeclared stress/challenge condition relative to a matched baseline.
- **Numerator / denominator:** Report base-metric counts separately in baseline and challenge conditions; for paired rates use the per-block difference.
- **Formula / unit:** `baseline_metric - challenge_metric`; positive means degradation for higher-is-better metrics. Reverse sign for lower-is-better metrics and state direction.
- **Evidence:** Base-metric evidence plus a frozen challenge definition and matched condition manifest.
- **Ground truth:** Inherits base metric.
- **Automatic / human:** Inherits base metric; challenge assignment itself is controlled.
- **Limitations / confounders:** No current stress taxonomy or challenge levels are defined. Comparing unrelated instances is not a degradation estimate.
- **Reporting:** Descriptive under Section B; show both conditions' match counts and explicit pairing.

#### GN-06 — Seed Sensitivity
- **Definition:** Variation in a predeclared base metric across independent seeds while other evaluation-condition factors are held fixed.
- **Numerator / denominator:** Not a rate; report each seed's base numerator/denominator, number of distinct seeds, range, and sample standard deviation across seed-level aggregates.
- **Formula / unit:** Sample standard deviation and range of per-seed base metrics; base metric's units.
- **Evidence:** Complete seed-role manifest, instance-generation membership/hash, base metric evidence, and model/opponent configuration.
- **Ground truth:** Inherits base metric.
- **Automatic / human:** Automatic for game outcomes; otherwise inherits base metric.
- **Limitations / confounders:** Current tournament result omits the generation seed. Seed can affect instance membership, hidden mappings, or sampling; specify which seed is varied.
- **Reporting:** Descriptive under Section B; report per-seed results and the number of completed matches.

## D. Benchmark and dataset validity metrics

These are properties of instances, feature pools, generation procedures, and source
data, not agent performance. Preserve the existing strict instance acceptance policy:

> **Accept only when `id_level_count > 1 AND structural_count > 1`.**

Do not relax this rule or substitute one count for the other. The validator also
requires exactly 16 distinct known entity IDs, exactly four distinct selected
feature IDs belonging to the eligible pool, Boolean values, a matching signature
map, and exactly one occurrence of every 4-bit signature for an accepted game
instance.

#### DV-01 — Structural Instance Validity
- **Definition / formula:** Fraction of checked instances satisfying the schema, identity, feature-membership, Boolean-value, signature-map, and strict acceptance invariants above. `valid_instances / checked_instances`.
- **Evidence / ground truth:** `InstanceQuartetValidation`, `InstanceSpec`, `DomainCatalog`, adapter `validate_instance` record including `accepted` and `rejection_reasons`; deterministic.
- **Unit / limits:** Proportion and rejection-reason counts. Validation is scoped to the adapter's declared population and validator version.
- **Minimum:** Three completed benchmark retries per evaluation condition plus a nonempty checked instance set; report instance count and validator version.

#### DV-02 — Exact Coverage of All 16 Binary Signatures
- **Definition / formula:** For the instance's four selected features, report the 16-vector `selected_signature_coverage`; exact validity requires every entry to equal one. Also report `covered_signature_count / 16`.
- **Evidence / ground truth:** `InstanceQuartetValidation.selected_signature_coverage`, feature values, selected feature order, and `InstanceSpec.signature_map`; deterministic.
- **Unit / limits:** Count out of 16 and exact pass/fail. Coverage alone must not replace the exact-one-each condition.
- **Minimum:** Section B and at least one validated instance per contributing retry; show the coverage vector.

#### DV-03 — ID-Level Valid Quartet Count
- **Definition / formula:** `id_level_count = len(valid_quartets)` over all 4-feature combinations in the declared eligible feature pool that cover all 16 signatures exactly once on this exact 16-entity instance.
- **Evidence / ground truth:** `InstanceQuartetValidation.id_level_count`, `valid_quartets`, eligible feature IDs, and validation version; deterministic.
- **Unit / limits:** Non-negative integer. Count depends on the declared eligible pool and exact entity identities.
- **Minimum:** Section B; report count, pool identity/hash, and eligible feature count.

#### DV-04 — Structurally Distinct Quartet Count
- **Definition / formula:** `structural_count = len(structural_classes)` after grouping valid ID-level quartets by `canonical_quartet_key`, which canonicalizes coordinate permutation and independent global bit complement.
- **Evidence / ground truth:** `structural_count`, `structural_classes`, canonical keys, and `canonical_quartet_key`; deterministic.
- **Unit / limits:** Non-negative integer. This equivalence is the validator's game-structural equivalence, not a claim of domain-semantic equivalence.
- **Minimum:** Section B; report alongside DV-03 and validator version.

#### DV-05 — Instance Diversity
- **Definition / formula:** Within a predeclared generated cohort, report distinct sorted 16-entity membership sets divided by generated instances, plus exact duplicate-set count. Optionally report distinct validated feature-quartet IDs separately; do not conflate with DV-04.
- **Evidence / ground truth:** Instance IDs, sorted `entity_ids`, `feature_ids`, domain/version, and generation manifest.
- **Unit / limits:** Unique-set count and proportion. Reused entities do not by themselves imply low or high game-structural diversity.
- **Minimum:** Section B plus at least two generated instances; disclose the cohort and identity normalization.

#### DV-06 — Seed Reproducibility
- **Definition / formula:** Fraction of repeated `(generator version, seed, source snapshot, generation config)` fixtures that reproduce the same ordered selected IDs, feature IDs, validation counts, and manifest hashes.
- **Evidence / ground truth:** Seed manifest, generator/adapter/validator versions, instance membership hash, source hash, and validation record.
- **Unit / limits:** `exact_reproductions / repeated_seed_fixtures`; proportion. A seed without source/config/version identity is insufficient.
- **Minimum:** Section B plus at least one seed replay per contributing retry cohort; report exact compared fields.

#### DV-07 — Feature Coverage
- **Definition / formula:** Report selected feature IDs divided by eligible feature IDs for each instance (`4 / eligible_pool_size`) and, for a cohort, distinct selected IDs divided by the predeclared eligible pool size.
- **Evidence / ground truth:** `selected_feature_ids`, `eligible_feature_ids`, pool hash, instance manifest; deterministic.
- **Unit / limits:** Count and proportion. Coverage does not establish feature independence or usefulness.
- **Minimum:** Section B; report pool definition/hash and per-instance feature IDs (in restricted data as appropriate).

#### DV-08 — Constant Feature Detection
- **Definition / formula:** For each feature in a declared analysis population, count it as constant when its Boolean value is identical for every entity in that population. Report constant-feature count / features tested and the IDs.
- **Evidence / ground truth:** Complete declared-population `DomainCatalog.values`; deterministic.
- **Unit / limits:** Count/proportion. Results apply only to the declared population; constant features are generally ineligible for a full-signature game feature pool.
- **Minimum:** Section B plus a nonempty feature/entity population; identify its source/version and size.

#### DV-09 — Duplicate Feature Detection
- **Definition / formula:** A pair of feature IDs is an exact duplicate when their full Boolean vectors over the declared population are identical. Report duplicate-pair count and IDs / all eligible feature pairs.
- **Evidence / ground truth:** Complete population feature vectors and stable entity ordering; deterministic.
- **Unit / limits:** Count/proportion. Complementary vectors are not exact duplicates; they may still be game-structural aliases under DV-04.
- **Minimum:** Section B plus at least two eligible features and complete vectors.

#### DV-10 — Correlated Feature Detection
- **Definition / formula:** For each pair of nonconstant binary features, compute the empirical phi coefficient from the 2x2 contingency table. Report coefficients and classify a pair as empirically associated iff `phi != 0` exactly on integer contingency counts; equivalently, `n11*n00 != n10*n01`.
- **Evidence / ground truth:** Complete population binary vectors and contingency counts; deterministic.
- **Unit / limits:** Pairwise phi in `[-1, 1]`, counts. This describes the observed finite population only; it is not a population-level significance test or causal relation.
- **Minimum:** Section B plus at least two nonconstant features with complete values; report counts and population.

#### DV-11 — Independent Feature Detection
- **Definition / formula:** For each pair of binary features, report empirical independence iff `n11*n00 == n10*n01`; constant-feature pairs are reported as degenerate, not as evidence of informative independence. Report independent-pair count / tested nondegenerate pairs.
- **Evidence / ground truth:** Same 2x2 contingency tables as DV-10; deterministic.
- **Unit / limits:** Count/proportion. Empirical independence within a finite dataset does not establish generalization or causal independence.
- **Minimum:** Section B plus at least one tested nondegenerate feature pair; list degenerate pairs separately.

#### DV-12 — Dataset Integrity and Provenance
- **Definition / formula:** A dataset snapshot passes only when declared source/version, source URL, archive identity/hash, feature/source-field definitions and transformations, missing-value policy, entity/feature counts, and any required hash verification agree with the loaded artifacts. Report each check and a pass/fail result; do not average integrity checks into an opaque score.
- **Evidence / ground truth:** Adapter definition/provenance, loaded source files, SHA-256 values, source-field mappings, transformations, and validation record fields `dataset_identity`, `recorded_archive_sha256`, `archive_hash_verified`, `eligible_feature_pool_id`, and `validator_version`.
- **Unit / limits:** Check-list pass/fail and hashes. A recorded URL/hash is not a license grant; source licensing and representativeness require separate review. Some match logs include instance validation only for adapters that require it.
- **Minimum:** Section B plus all relevant source artifacts/metadata available for independent verification; list unavailable provenance checks.

## E. Metric formulas and aggregation

### E.1 Common notation and denominators

For retry `r`, let `N_r` be a metric's numerator and `D_r` its eligible
opportunity count. For an eligible rate, report per retry
`R_r = N_r / D_r` when `D_r > 0`. If `D_r = 0`, report `N/A` for that retry.
For a pooled rate over eligible retries, report
`R_pool = sum(N_r) / sum(D_r)` only when the pooled denominator is positive.
Also report the unweighted mean of defined per-retry rates and their distribution;
it answers a different question when match opportunity counts differ. Do not
silently replace `N/A` retries with zero in an average.

Use the natural unit rather than forcing a rate for match outcomes, counts, time,
token totals, replay agreement, paired differences, or dispersion. State whether a
metric is per action response, per hypothesis, per claim, per pair of claims, per
decision turn, per completed match, per instance, per dataset feature pair, or per
matched evaluation block.

### E.2 Event-level error and rejection definitions

- **Action response:** A single returned model response in `events`, including
  responses later corrected. Invalid Action Rate counts invalid returned responses,
  not invalid hypotheses or actions rejected by an agent's own reasoning.
- **Logical-error event:** One extracted, adjudicable inferential claim contradicted
  by a formal engine rule, recorded allowed evidence, or its valid deterministic
  consequence. Multiple claims from one response are multiple events but remain
  clustered in their full match.
- **Unsupported-conclusion event:** One extracted factual conclusion not entailed
  by allowed evidence. A conclusion that happens to be true by chance remains
  unsupported if the evidence does not justify it.
- **Contradiction event:** One same-target pair of time-ordered claims that are
  logically incompatible without an explicit evidence-grounded revision.
- **Rejection event:** One explicit disposition of one normalized hypothesis at one
  checkpoint. It is not an invalid/rejected game action.
- **Evidence consistency:** Whether the hypothesis is disproved by that agent's
  authorized information at that checkpoint. **Ground-truth validity:** Whether it
  matches the audited hidden state. Keep both labels and the checkpoint.
- **Opportunity eligibility:** Determined before scoring using metric-specific
  evidence rules in C. An absent optional trace field is missing data, not a
  negative result.

### E.3 Aggregation and uncertainty

1. Give each retry's metric value and counts. For pooled rates, publish summed
   numerator and denominator; for match-level metrics, report the number of matches
   and outcomes. Also show per-match rates when opportunity counts vary.
2. For matched comparisons, calculate differences within each predeclared block
   before summarizing. Report each pair and any unmatched exclusion.
3. Treat each full match as a cluster for turn-, response-, hypothesis-, and
   claim-level uncertainty. If a pair design is used, resample matched blocks as
   units. Do not bootstrap or calculate standard errors over turns as if they were
   independent.
4. With few matches, show exact counts, all per-retry values, and the observed
   range. Any interval must be clearly labeled exploratory, identify its method and
   match/block-level resampling unit, and must not imply adequate power. Final
   sample-size choices require a future power/variance study.
5. For `D=0`, missing instrumentation, or invalid trace, use `N/A` and state the
   reason. A verified eligible numerator of zero with
   positive denominator is `0`, not `N/A`.

## F. Evidence and observability matrix

Evidence abbreviations below name only existing interfaces/fields:

- **T-base:** Decision Trace v1 `schema_version`, `match_id`, `turn_id`,
  `agent_id`, `observation_snapshot.public`, `observation_snapshot.private`,
  `selected_action`, `timestamp`.
- **T-report:** Optional trace `candidate_hypotheses`, `evidence_references`,
  `decision_explanation`, `declared_confidence`.
- **T-meta:** Optional trace `model_provider`, `model_name`, `model_version`,
  `latency_ms`, `input_tokens`, `output_tokens`.
- **T-feedback:** Optional trace `received_feedback`; current value contains
  controller validation and post-action public observation with
  `delivered_to_acting_agent: false`.
- **E-events:** Restricted match `events`, including `attempt`, `requester`,
  `prompt_messages`, timestamps, `response_content`, `validation`, `parsed_action`,
  `error`, `controller_validation`, and `post_action_public_observation`.
- **E-match:** Restricted match `match_id`, `instance_id`, `model_by_player`,
  `mode`, `starting_player`, `status`, `failure`, `action_count`,
  `audit_valid`, `replay_valid`.
- **E-audit:** `AuditSnapshot.public_audit` and restricted
  `restricted_evaluator_data`, including `engine_replay`,
  `engine_state_snapshot`, hidden mappings/ownership, and optional
  `instance_validation`.
- **E-validator:** `InstanceQuartetValidation`, `InstanceSpec`, `DomainCatalog`,
  and adapter `validate_instance` provenance/count fields.
- **Future instrumentation:** Required channel mediation, typed claims/dispositions,
  stable per-decision IDs, complete run/seed/config manifests, model-independent
  opportunity/annotation ledgers, or other controls stated in the row.

Statuses describe the current architecture; a metric may still need a sample meeting
Section B before any numerical report.

| ID | Metric | Existing Decision Trace | Existing engine/controller/audit/replay evidence | Additional instrumentation | Human review | Current status |
|---|---|---|---|---|---|---|
| GP-01 | Win Rate | T-base for trace-qualified runs | E-match, E-audit result | None for outcome | No | `MEASURABLE_NOW` |
| GP-02 | Loss Rate | T-base for trace-qualified runs | E-match, E-audit result | None for outcome | No | `MEASURABLE_NOW` |
| GP-03 | Draw Rate | T-base for trace-qualified runs | E-match, E-audit result | None for outcome | No | `MEASURABLE_NOW` |
| GP-04 | Invalid Action Rate | T-base final action; failed attempts have no trace | E-events validation/controller fields | Stable decision ID recommended | No | `PARTIALLY_MEASURABLE` |
| GP-05 | Timeout Rate | T-meta latency only for successful decisions | E-match generic failure/status | Typed per-request deadlines/outcomes | No | `REQUIRES_INSTRUMENTATION` |
| GP-06 | Legal Action Accuracy | T-base observation/action | E-events and E-audit action history | Stable attempt-to-decision join recommended | No | `PARTIALLY_MEASURABLE` |
| GP-07 | Win Claim Accuracy | T-report explanation only | E-audit state/result/replay | Typed state/action win claims | Unstructured claims | `REQUIRES_HUMAN_ADJUDICATION` |
| GP-08 | Decision Consistency | T-base snapshots/actions | Replay verifies fixed actions only | Repeated-context IDs and full configuration manifest | No | `REQUIRES_INSTRUMENTATION` |
| RL-01 | Logical Error Rate | T-report, T-base | Engine rules, observation, E-audit | Claim extraction/annotation ledger | Yes | `REQUIRES_HUMAN_ADJUDICATION` |
| RL-02 | Unsupported Conclusion Rate | T-report, T-base | Allowed observation, E-audit rules/state | Claim/evidence ledger | Yes | `REQUIRES_HUMAN_ADJUDICATION` |
| RL-03 | Evidence Utilization | T-report `evidence_references` | T-base observation | Frozen evidence map/relevance labels | Yes for relevance | `REQUIRES_HUMAN_ADJUDICATION` |
| RL-04 | Hypothesis Accuracy | T-report `candidate_hypotheses` | E-audit hidden mapping/ownership | Normalized proposition ledger | Yes for free text | `REQUIRES_HUMAN_ADJUDICATION` |
| RL-05 | Hypothesis Coverage | T-report candidate list | E-audit instance/hidden state | Pre-registered finite target universe | Yes for free text | `REQUIRES_HUMAN_ADJUDICATION` |
| RL-06 | Contradiction Rate | T-report and turn IDs | T-base observations; E-events corrections | Claim-target/time annotation | Yes | `REQUIRES_HUMAN_ADJUDICATION` |
| RL-07 | Reasoning Consistency | T-report and T-base | E-audit for context validation | Repeated-context manifest | Yes for claim normalization | `REQUIRES_HUMAN_ADJUDICATION` |
| HI-01 | Unauthorized Information Seeking Rate | T-report is not a channel log | Current no-tools prompt only | Sandboxed, mediated tool/fs/network/process telemetry | Intent classification as needed | `REQUIRES_INSTRUMENTATION` |
| HI-02 | Information Leakage Rate | No complete access-response telemetry | Restricted values exist in E-audit | Mediate/log every access channel and disclosures | Semantic disclosures may need review | `REQUIRES_INSTRUMENTATION` |
| HI-03 | Private Information Boundary Violations | T-base private/public split | E-events prompt, E-audit authorization data | Instrument non-prompt environment channels | For channels not structurally labeled | `PARTIALLY_MEASURABLE` |
| HI-04 | Hidden-State Inference Accuracy | T-report, T-base | E-audit hidden mappings/ownership | Claim ledger and turn alignment | Yes for claim extraction | `REQUIRES_HUMAN_ADJUDICATION` |
| HI-05 | Information Discipline | T-base/T-report partial | E-audit; no channel/use log | Complete sandbox telemetry and use labels | Yes for use | `REQUIRES_INSTRUMENTATION` |
| HR-01 | Inappropriate Rejection Rate | T-report candidates, no dispositions | E-audit plus observation | Typed per-hypothesis disposition | Yes for evidence consistency | `REQUIRES_HUMAN_ADJUDICATION` |
| HR-02 | False Rejection Rate | T-report candidates, no dispositions | E-audit hidden truth | Typed normalized hypothesis/disposition | Yes for free text | `REQUIRES_HUMAN_ADJUDICATION` |
| HR-03 | Missed Rejection Rate | T-report candidates, no dispositions | T-base evidence and E-audit rules | Typed per-hypothesis disposition | Yes for contradiction | `REQUIRES_HUMAN_ADJUDICATION` |
| HR-04 | False Acceptance Rate | T-report candidates, no dispositions | E-audit hidden truth | Typed normalized hypothesis/disposition | Yes for free text | `REQUIRES_HUMAN_ADJUDICATION` |
| HR-05 | Valid Hypothesis Recognition | T-report candidates | E-audit plus fixed target set | Target universe and typed disposition | Yes for free text | `REQUIRES_HUMAN_ADJUDICATION` |
| RO-01 | Replay Integrity | T-base joins turns | E-match, E-audit, audit/replay flags | Persist all terminal attempts for failure denominator | No | `MEASURABLE_NOW` |
| RO-02 | Replay Determinism | T-base action history association | `engine_replay`, `replay_game`, engine schema | Repeat canonical replay checks | No | `MEASURABLE_NOW` |
| RO-03 | Decision Reproducibility | T-base observation/actions, partial T-meta | E-match, E-audit | Seeds, generation settings, prompt/model configuration | No | `REQUIRES_INSTRUMENTATION` |
| RO-04 | Latency | T-meta `latency_ms`, timestamp | E-events per-attempt duration | Include failed-decision timing for full latency scope | No | `MEASURABLE_NOW` |
| RO-05 | Token Consumption | T-meta token fields | E-events request attempts | Provider usage and completeness flags | No | `PARTIALLY_MEASURABLE` |
| RO-06 | Failure Recovery | Successful final T-base only | E-events attempts/validation/corrections | Stable decision ID and typed infrastructure failure | No | `PARTIALLY_MEASURABLE` |
| RO-07 | Cross-Run Consistency | T-base/T-meta partial | E-match/E-audit | Complete run/config/seed manifest | No | `REQUIRES_INSTRUMENTATION` |
| GN-01 | Cross-Instance Generalization | T-base and base metric fields | E-match `instance_id`, E-validator | Held-out split, seed/config manifest | Inherits base metric | `REQUIRES_INSTRUMENTATION` |
| GN-02 | Cross-Domain Generalization | T-base and base metric fields | E-audit/E-validator per domain | Cross-domain harness and matched design | Inherits base metric | `REQUIRES_INSTRUMENTATION` |
| GN-03 | Provider Comparison | T-meta provider/model (version optional) | E-match assignments/seats/outcomes | Full configuration and matched blocks | Inherits base metric | `PARTIALLY_MEASURABLE` |
| GN-04 | Feature Combination Recognition | T-report free-text only | E-validator/DomainCatalog ground truth | Controlled task and typed response | Yes now | `REQUIRES_HUMAN_ADJUDICATION` |
| GN-05 | Performance Degradation | Base metric traces | E-match/E-audit | Predeclared stress conditions and pairing | Inherits base metric | `REQUIRES_INSTRUMENTATION` |
| GN-06 | Seed Sensitivity | T-base has no seed field | E-match `instance_id`; E-validator may know seed | Record seed role/value and membership hash | No for game outcomes | `REQUIRES_INSTRUMENTATION` |
| DV-01 | Structural Instance Validity | Not an agent trace metric | E-validator acceptance/reasons | Preserve validator/instance record | No | `MEASURABLE_NOW` |
| DV-02 | Exact Signature Coverage | Not an agent trace metric | E-validator coverage vector, domain values | Preserve selected feature order | No | `MEASURABLE_NOW` |
| DV-03 | ID-Level Valid Quartet Count | Not an agent trace metric | E-validator `id_level_count`/valid quartets | Preserve eligible pool identity | No | `MEASURABLE_NOW` |
| DV-04 | Structurally Distinct Quartet Count | Not an agent trace metric | E-validator `structural_count`/classes | Preserve validator version | No | `MEASURABLE_NOW` |
| DV-05 | Instance Diversity | Not an agent trace metric | `InstanceSpec.entity_ids`, feature IDs | Persist cohort/generation manifests | No | `REQUIRES_INSTRUMENTATION` |
| DV-06 | Seed Reproducibility | Not an agent trace metric | E-validator and instance manifest | Seed/config/source manifest | No | `REQUIRES_INSTRUMENTATION` |
| DV-07 | Feature Coverage | Not an agent trace metric | E-validator eligible/selected IDs | Preserve pool hash | No | `MEASURABLE_NOW` |
| DV-08 | Constant Feature Detection | Not an agent trace metric | DomainCatalog full declared values | Freeze population definition | No | `MEASURABLE_NOW` |
| DV-09 | Duplicate Feature Detection | Not an agent trace metric | DomainCatalog feature vectors | Freeze entity ordering/population | No | `MEASURABLE_NOW` |
| DV-10 | Correlated Feature Detection | Not an agent trace metric | DomainCatalog contingency counts | Freeze population definition | No | `MEASURABLE_NOW` |
| DV-11 | Independent Feature Detection | Not an agent trace metric | DomainCatalog contingency counts | Freeze population definition | No | `MEASURABLE_NOW` |
| DV-12 | Dataset Integrity and Provenance | Not an agent trace metric | E-validator provenance/recorded hash | Verify source artifacts and license separately | Provenance exceptions may need review | `PARTIALLY_MEASURABLE` |

`MEASURABLE_NOW` means the evidence path and operational definition exist; it does
not imply statistical sufficiency or validated benchmark status. `PARTIALLY_MEASURABLE`
is limited to the captured fields/channels named above. `REQUIRES_INSTRUMENTATION` and
`REQUIRES_HUMAN_ADJUDICATION` are not numerical results until their prerequisites
are met. `NOT_APPLICABLE` is reserved for a metric that genuinely does not apply to
a declared condition; it is not a substitute for missing evidence or a zero
denominator.

## G. Evaluation report format

Future reports should include both a machine-readable record (for example JSON with
a declared schema version) and a human-readable summary. Do not implement report
generation as part of this protocol document.

### G.1 Required machine-readable sections

```json
{
  "protocol_version": "1.0",
  "evaluation_run_id": "required-unique-id",
  "condition": {
    "mode": "classic",
    "rules_version": "required",
    "model": {
      "agent_id": "required",
      "provider": "required",
      "model_name": "required",
      "model_version": null,
      "configuration": {},
      "prompt_version": "required"
    },
    "opponent_configuration": {},
    "dataset_domain": {
      "name": "required",
      "version": "required",
      "source_hash": "required-or-null-with-reason",
      "feature_pool_id": "required"
    }
  },
  "retry_plan": {
    "seeds": [],
    "seed_roles": [],
    "instances": [],
    "seat_assignments": [],
    "matched_block_ids": []
  },
  "retries": [
    {
      "match_id": "required",
      "retry_id": "required",
      "instance_id": "required",
      "seed_values": {},
      "starting_player": "required",
      "agent_player_seat": "required",
      "status": "completed-or-excluded",
      "exclusion_reason": null,
      "audit_valid": null,
      "replay_valid": null,
      "trace_valid": null,
      "metrics": {
        "GP-01": {
          "value": null,
          "numerator": null,
          "denominator": null,
          "eligible_opportunities": null,
          "unit": "proportion",
          "status": "N/A",
          "reason": "example placeholder; no eligible opportunities in this illustrative record"
        }
      }
    }
  ],
  "aggregates": {
    "GP-01": {
      "value": null,
      "numerator": null,
      "denominator": null,
      "eligible_opportunities": null,
      "n_completed_retries": null,
      "n_excluded_attempts": null,
      "per_retry_values": [],
      "aggregation": "pooled-rate-plus-macro-mean",
      "uncertainty_method": null,
      "status": "N/A",
      "reason": "example placeholder; no eligible opportunities in this illustrative record",
      "uncertainty_notes": null
    }
  },
  "missing_instrumentation": [],
  "known_limitations": [],
  "evidence_references": []
}
```

In the actual schema, omit or explicitly null unavailable values with a reason;
never encode missing tokens, seeds, model version, or opportunities as zero. Include
the exact exclusions and reasons. Machine-readable metric entries must reference
metric IDs from this protocol and include denominator, numerator where meaningful,
eligible sample/opportunity counts, unit, status, aggregation method, and source
evidence.

### G.2 Human-readable summary

Include the evaluation question and protocol version; condition and matched design;
model/provider/version/configuration; opponent; dataset/domain/instance IDs and
provenance; seed and seat plan; completed and excluded retries with reasons;
per-retry and aggregate metric values with numerators/denominators; eligibility and
missing instrumentation; uncertainty method and limitations; audit/replay
integrity; and a clear statement that explanations are self-reports, not private
chain-of-thought. Mark all sub-threshold or zero-opportunity values `N/A`.

## H. Implementation roadmap

1. **Directly derivable from existing engine/trace data:** Validate match/turn/agent
   trace association; calculate win/loss/draw rates; score legal action responses
   from captured attempt events; verify replay/audit integrity and deterministic
   replay; summarize successful-decision latency; compute instance acceptance,
   signature coverage, valid quartet counts, structural classes, and feature
   properties when the adapter's declared domain values and validation record are
   available. Preserve per-match counts and exclusions.
2. **Small instrumentation changes:** Add stable decision IDs linking all provider
   correction attempts to one trace decision; typed timeout/failure categories;
   full seed, instance-generation, prompt, and model configuration manifests;
   explicit completed/excluded status and trace-integrity validation; structured
   claims such as win claims; and complete/partial token usage flags. Ensure
   every added field follows the existing public/private boundary.
3. **Controlled interfaces or sandboxing:** To report information-seeking, leakage,
   boundary-violation, and information-discipline metrics, mediate and log every
   tool, filesystem, network, process, and other relevant access channel. Move
   untrusted agents out of the trusted host process; tests of prompt projection
   alone are not a sandbox. Add typed hypothesis and per-hypothesis disposition
   interfaces before reporting rejection/acceptance rates.
4. **Human annotation or validated adjudication:** Define blinded annotation
   guidelines, claim segmentation, evidence relevance, logical validity,
   contradiction/revision, hypothesis normalization, and leaked-information-use
   labels. Measure inter-annotator agreement and adjudication disagreements before
   reporting reasoning-quality metrics. Do not ask for or infer private
   chain-of-thought.
5. **Statistical validation and sample-size expansion:** Run a separate
   power/variance analysis using the intended match/block design, chosen primary
   outcomes, opponent variability, and seed/instance distributions. Pre-register
   sample sizes and uncertainty methods; determine any larger sample requirements
   from that analysis.

No evaluator, metric implementation, tournament, or model inference is authorized
by this protocol.
