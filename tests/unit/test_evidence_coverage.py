"""Tests for evidence coverage checker."""

from __future__ import annotations

from scripts.check_evidence_coverage import missing_acceptance_ids


def test_unmapped_acceptance_id_fails_coverage(tmp_path: object) -> None:
    spec = tmp_path / "spec.md"
    evidence = tmp_path / "evidence.md"
    spec.write_text("- [ACC-001] grader independente\n", encoding="utf-8")
    evidence.write_text("# Evidence map\n", encoding="utf-8")
    assert missing_acceptance_ids(spec, evidence) == ["ACC-001"]


def test_mapped_acceptance_id_passes(tmp_path: object) -> None:
    spec = tmp_path / "spec.md"
    evidence = tmp_path / "evidence.md"
    spec.write_text("- [ACC-002] testes ocultos\n", encoding="utf-8")
    evidence.write_text("[ACC-002] covered by test_hidden.py\n", encoding="utf-8")
    assert missing_acceptance_ids(spec, evidence) == []
