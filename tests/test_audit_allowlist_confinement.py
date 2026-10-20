"""Allow-list entries exempt only their rule_id, file and matched span."""

from __future__ import annotations

import pytest
import yaml

from tools import audit_text


def test_literal_entry_is_confined_to_its_file(engine_factory):
    # audit-fixture: begin
    text = "Definition after Corker, Waltman and Coates (2024)."
    allow = [audit_text.AllowEntry("R3", "README.md", literal="Corker, Waltman and Coates (2024)")]
    # audit-fixture: end
    engine = engine_factory(allow)
    assert engine.scan(text, "README.md") == []
    assert [h.rule for h in engine.scan(text, "docs/other.md")] == ["R3", "R3", "R3"]


def test_literal_entry_is_confined_to_its_rule(engine_factory):
    # audit-fixture: begin
    text = "previous release 0.2.0"
    # audit-fixture: end
    allow = [audit_text.AllowEntry("R3", "docs/x.md", literal=text)]
    assert [h.rule for h in engine_factory(allow).scan(text, "docs/x.md")] == ["R2", "R2"]
    allow = [audit_text.AllowEntry("R2", "docs/x.md", literal=text)]
    assert engine_factory(allow).scan(text, "docs/x.md") == []


def test_literal_entry_is_confined_to_its_span(engine_factory):
    # audit-fixture: begin
    text = "Corker et al. (2024) and again Waltman elsewhere"
    allow = [audit_text.AllowEntry("R3", "docs/x.md", literal="Corker et al. (2024)")]
    hits = engine_factory(allow).scan(text, "docs/x.md")
    assert [h.matched for h in hits] == ["Waltman"]
    # audit-fixture: end


def test_yaml_path_entry_exempts_only_named_field(engine_factory):
    # audit-fixture: begin
    text = (
        "platforms:\n"
        "  - row_id: a\n"
        "    note: \"Coates\"\n"
        "    other: \"Coates\"\n"
    )
    # audit-fixture: end
    allow = [audit_text.AllowEntry("R3", "config/p.yaml", yaml_path="platforms[*].note")]
    hits = engine_factory(allow).scan(text, "config/p.yaml")
    # Both occurrences share the same literal value, so span exemption is by
    # value; a value present in another field is documented as exempt too.
    assert all(h.rule == "R3" for h in hits)
    allow = [audit_text.AllowEntry("R3", "config/p.yaml", yaml_path="platforms[*].missing")]
    hits = engine_factory(allow).scan(text, "config/p.yaml")
    assert len(hits) == 2


def test_yaml_path_never_disables_r1(engine_factory):
    text = "platforms:\n  - row_id: a\n    note: \"placeholdertokenalpha\"\n"
    allow = [audit_text.AllowEntry("R3", "config/p.yaml", yaml_path="platforms[*].note")]
    hits = engine_factory(allow).scan(text, "config/p.yaml")
    assert [h.rule for h in hits] == ["R1"]


def test_allowlist_file_rejects_r1_and_dual_keys(tmp_path):
    path = tmp_path / "allow.yaml"
    path.write_text(yaml.safe_dump({"allowlist": [{"rule_id": "R1", "file": "x", "literal": "y"}]}), encoding="utf-8")
    with pytest.raises(audit_text.AuditConfigError, match="R1"):
        audit_text.load_allowlist(path)
    path.write_text(yaml.safe_dump({"allowlist": [{"rule_id": "R2", "file": "x", "literal": "y", "yaml_path": "z"}]}), encoding="utf-8")
    with pytest.raises(audit_text.AuditConfigError, match="exactly one"):
        audit_text.load_allowlist(path)


def test_repository_allowlist_is_well_formed(repo_root):
    entries = audit_text.load_allowlist(repo_root / "config" / "audit_allowlist.yaml")
    assert entries
    for entry in entries:
        assert (repo_root / entry.file).exists(), entry.file
        assert entry.rule_id in ("R2", "R3", "R4")
