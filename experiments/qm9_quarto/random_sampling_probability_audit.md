# Random sampling probability audit

## Independent validation
- Eligible feature count: 18
- Eligible population size: 133884
- Total quartets evaluated: 3060
- Globally feasible quartets: 203

## Requested exact per-quartet formula
The audit requirement specifies the ordered-draw formula:

P = 16! * product(n_i) / C(N, 16)

This value is reported exactly as specified. It is not the unordered-subset probability; it is the ordered-draw count form specified in the task.

Summary over the 203 surviving quartets:
- minimum: 9.392817391636e-26
- median: 4.158902475165e-03
- mean: 1.587116137807e+03
- maximum: 7.494474962056e+04

## Monte Carlo estimate of success probability
Using 100,000 uniformly sampled 16-molecule subsets with seed 20261108:
- estimated probability that a sample admits at least one valid quartet: 0.000000000000e+00
- 95%% upper bound (zero successes in 100,000 draws): 3.000000000000e-05
- expected successful samples in 1,024 draws: 0.000000
- probability of zero successes in 1,024 draws: 1.000000000000e+00

## Structural equivalence
- Abstract canonical game-structure classes: 1
- Entity-labelled partition classes: 198
- Bit-permutation and independent bit-complement invariance check: passed

## Constructive validation
- Constructive samples checked: 203
- Unique entity sets: 198
- All samples contain 16 distinct source entities: yes
- Each signature class occurs exactly once in each sample: yes

## Interpretation
The subset-level random-sample estimate is effectively zero in 100,000 draws, which quantitatively explains the earlier zero-success result in 1,024 draws. The ordered-draw formula is retained exactly as specified for the per-quartet audit, but the Monte Carlo subset estimate is the benchmark-relevant probability.
