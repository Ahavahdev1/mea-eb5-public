# Running MEA-EB5

## Repository split

Use two repositories:

1. **Private evaluator** — this complete tree. It contains hidden graders,
   controls, the grade workflow, and publication workflow.
2. **Engineer runner** — generated from an allowlist. It contains only public
   fixtures, runner code, adapter example, and the benchmark workflow.

Create the engineer-visible tree without copying files manually:

```bash
python scripts/export_participant_repo.py ../mea-eb5-runner
```

The exporter excludes every `grader/`, `controls/`, private workflow, and
private design document. Its integration test also checks this boundary.

## Configure the real MEA

The official path runs the MEA in Docker. Host execution is opt-in and exists
only for local adapter tests.

```bash
cp mea.adapter.example.yaml mea.adapter.yaml
# Replace image with the real immutable MEA image digest and adjust command.
mea-eb5 doctor --adapter-config mea.adapter.yaml
```

The MEA command receives `--goal-file /workspace/.mea-eb5-goal.txt`. Its image
must be public or already cached on the ephemeral runner; the attempt job has
no secrets. Only `/workspace` is mounted. Network, privilege escalation,
Docker socket access, and a writable root filesystem are disabled.

## Local quality gates

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m mea_eb5.cli validate challenges
python -m mea_eb5.cli run \
  --challenge 01_novel_repair \
  --adapter cli \
  --adapter-config mea.adapter.yaml \
  --attempt-only \
  --seeds 1
python -m mea_eb5.cli reproduce runs/<run-id>/manifest.json
```

## GitHub flow

1. In the engineer runner repository, dispatch **Benchmark attempts**.
2. Use `smoke` for five parallel jobs (five challenges × one seed).
3. Use `release` for 25 jobs (five challenges × five seeds).
4. Give the public workflow's numeric run ID to the evaluator.
5. In the private evaluator repository, dispatch **Private grading** with the
   source repository and run ID. Configure its protected `private-grader`
   environment with `ATTEMPT_READ_TOKEN` when cross-repository access needs it.
6. Dispatch **Publish evaluated report** with the private grade run ID. Configure
   `GRADE_READ_TOKEN` only when the evaluated artifact is in another repository.

Raw archives are private and retained for 14 days. Evaluated bundles contain
only `manifest.json` and independent `score.json`, and are retained for 90 days.
Pages downloads evaluated bundles only and never executes submitted files.
The private workflow builds its digest-pinned grader image before downloading
candidate artifacts, then grades each run in a separate no-network, read-only,
resource-limited container that can mount only that run.

## Interpretation

- `FUNCTIONAL_FAIL` — hidden behavior failed.
- `SAFETY_FAIL` — a security or integrity gate failed; it is never averaged away.
- `INVALID_GRADER` — control validation failed; do not publish a leaderboard.
- `INVALID_RUN` — evidence is malformed or its hashes do not match.
- `INFRA_FAILURE` — runner infrastructure failed or timed out.

An official result must have `grader_provenance: INDEPENDENT`. Attempt-only
scores are deliberately marked `NÃO TESTADA` and `SELF_REPORTED`.
