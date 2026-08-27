<div align="center">

# 🧬 MEA-EB5
### *Auditable Benchmark for MEA Evidence Claims*

[![Language](https://img.shields.io/badge/Language-Python_3.12-blue?style=flat-square)]()
[![Tests](https://img.shields.io/badge/Tests-passing-success?style=flat-square)]()

---

<p align="left">
<b>MEA-EB5</b> is an executable, auditable benchmark for evaluating claims about
autonomous software repair, operation, improvement, and modification. It does
not assume the claims of the MEA framework are true and does not depend on a
specific access method to the system under test.
</p>

</div>

---

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
python -m mea_eb5.cli validate challenges
cp mea.adapter.example.yaml mea.adapter.yaml
python -m mea_eb5.cli doctor --adapter-config mea.adapter.yaml
python scripts/export_participant_repo.py ../mea-eb5-runner
```

## The five challenges

1. **Novel repair** — fix a bug from an incident description and incomplete public tests.
2. **Long-horizon recovery** — keep a composite service healthy through deterministic faults.
3. **Measurable self-improvement** — improve a quadratic baseline without gaming the metric.
4. **Adversarial security** — repair an auth flaw while resisting prompt injection and hostile inputs.
5. **Containment and rollback** — preserve invariants and rollback byte-for-byte after crashes.

## Documentation

- `docs/running.md` — local and GitHub execution
- `docs/adding-an-adapter.md` — how to add a new system adapter
- `docs/superpowers/specs/2026-08-26-mea-evidence-benchmark-design.md` — design spec

## Principles

- Evidence before claim
- Security is not averaged away
- Grader is out of reach during the attempt
- Every attempt produces auditable artifacts
- Only independently graded, public-safe bundles reach the report
