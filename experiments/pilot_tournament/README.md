# Quarto QM9 pilot tournament

This folder is the default output location for the two-match, two-model Classic
pilot. The harness constructs one instance from the locally frozen QM9 artifacts,
then reuses that instance for both matches with the player/model assignments
reversed.

Run from the repository root after the focused harness tests pass:

```powershell
python -B .\tournament_harness.py
```

The harness uses the configured local Ollama service at
`http://localhost:11434`. It first sends a non-private connectivity smoke test
to each model and does not start either match unless both smoke tests pass. It
does not install, pull, or download models. Optional limits and output location:

```powershell
python -B .\tournament_harness.py --timeout 60 --wall-clock-timeout 900 --max-actions 32 --output-dir .\experiments\pilot_tournament
```

The `gemma4:31b-cloud` model can transmit each requesting player's private
feature IDs and game prompt to its cloud provider. The harness never sends
QM9 SMILES or structural metadata. Public prompts use a bounded projection of
the Controller's live observation and omit its full entity roster. This is a
trusted-host boundary, not isolation from arbitrary code running in the same
Python process.

Outputs are separated by sensitivity:

- `public_report.json` contains match-level outcomes, validation status,
  aggregate counts, and the cloud-data boundary.
- `restricted_match_log.json` contains prompts, raw model responses, and audit
  snapshots. Keep it local and handle it as restricted data.
- `security_report.json` contains synthetic preflight checks and their known
  limitations.

Provider errors, invalid actions, timeouts, audit failures, and replay failures
are reported as failures; they are never converted into a winner. These two
matches are a pilot, not a scientific evaluation or leaderboard result.
