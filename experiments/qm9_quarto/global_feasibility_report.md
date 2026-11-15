# QM9 global feasibility diagnostic

## Executive summary

- Eligible gameplay features: 18
- Total feature quartets examined: 3,060
- Globally feasible semantic quartets: 203
- After exact dataset duplicate handling: 203
- After complement equivalence handling: 203
- Game-structurally distinct global quartets: 1
- Constructive 16-entity samples generated: 203
- Unique constructive entity sets: 198

This is a measured result from the current frozen QM9 matrix under the experiment definitions. It shows that the previous zero-valid-quartet outcome in 1,024 random 16-element samples was not proof of global infeasibility, but it does confirm that the feature space is highly constrained and that random sampling is a poor way to discover valid samples.

## Methodology

1. Load the frozen feature matrix and registry.
2. Keep only rows with `eligible_for_gameplay == true`.
3. Enumerate all 3,060 possible quartets of the 18 eligible features.
4. For each quartet, compute the 4-bit signature for every eligible molecule.
5. Require the quartet to cover all 16 signature classes at least once in the full eligible population.
6. Reject any quartet whose features are exact duplicates or complements at the dataset level.
7. Reject any quartet that contains a full-dataset implication pair such as `A -> B`.
8. Canonicalize the surviving quartet set under bit permutation and global bit complement to count game-structural distinctness.
9. Construct deterministic samples by selecting the earliest `source_id` for each signature class `0..15`.

## Result counts

- Total combinations examined: 3,060
- Global feasible semantic quartets: 203
- Remaining after exact dataset duplicate handling: 203
- Remaining after complement equivalence: 203
- Game-structurally distinct quartets: 1

## First surviving quartets

1. contains_hydrogen, contains_fluorine, contains_ring, contains_double_bond
2. contains_hydrogen, contains_fluorine, contains_ring, contains_carbonyl
3. contains_hydrogen, contains_fluorine, contains_aromatic_ring, contains_double_bond
4. contains_hydrogen, contains_fluorine, contains_aromatic_ring, contains_carbonyl
5. contains_hydrogen, contains_fluorine, contains_double_bond, contains_triple_bond

## Constructive sample generation

A deterministic construction rule was used for every surviving quartet: for each signature class `0..15`, choose the earliest `source_id` whose four-bit signature equals that class. This yields one valid 16-element sample per surviving quartet.

- Constructive samples generated: 203
- Unique entity sets: 198
- Unique structural quartet classes: 1
- Most repeated entities across the deterministic constructions are not evidence of a hidden mapping; they are a byproduct of the same signature classes repeatedly appearing as the earliest valid representatives.

## Why the 1,024 random samples failed

The failure was not a proof of global infeasibility. The measured data show:

- only 203 of 3,060 candidate quartets are globally feasible (6.63%)
- a valid sample must realize all 16 signature classes in a sample of 16 entities
- the random draw therefore had to hit a narrow feature-pattern arrangement within a large population

This is a combination of global feature scarcity and sparse class coverage. The random-sample result was therefore a real failure mode for the tested sampling method, but not a global negative result for the QM9 feature space.

## Answer to the required questions

1. Does at least one globally feasible quartet exist? Yes. There are 203.
2. If yes, how many? 203 globally feasible semantic quartets.
3. How many game-structurally distinct quartets exist? 1.
4. Can we construct valid 16-entity samples? Yes. Deterministic construction produced 203 valid samples from the surviving quartets.
5. Why did the 1,024 random samples fail? Because the valid space is a small minority of the feasible feature pool and the random 16-element draw must simultaneously cover all 16 signatures; the random sample method therefore rarely lands in the valid region.
6. Is QM9 still a viable first benchmark domain? It remains viable as a scientific-data domain, but only with explicit global feasibility checks and deterministic sample construction. It is not viable as a benchmark if the protocol relies on ad hoc random 16-element sampling without global feasibility screening.

The full surviving quartet list and detailed per-quartet counts are in `global_feasibility_results.json`.
