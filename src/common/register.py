"""Platform register loader, validator and CSV exporter.

``config/platforms.yaml`` and ``config/excluded_candidates.yaml`` are the only
hand-edited register files.  Their CSV counterparts are generated artefacts:

    python -m src.common.register --export     # rewrite both CSV files
    python -m src.common.register --check      # exit 1 if a CSV is stale
    python -m src.common.register --validate   # vocabulary and event-map checks

Edits to a CSV are never read back into the YAML.  The exporter is
deterministic (fixed column order, fixed list separator, LF line endings) so
that ``tests/test_platforms_csv_in_sync.py`` can compare bytes.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from src.common.config import CONFIG_DIR

PLATFORMS_YAML = CONFIG_DIR / "platforms.yaml"
PLATFORMS_CSV = CONFIG_DIR / "platforms.csv"
EXCLUDED_YAML = CONFIG_DIR / "excluded_candidates.yaml"
EXCLUDED_CSV = CONFIG_DIR / "excluded_candidates.csv"

LIST_SEPARATOR = "; "

#: Column order of ``config/platforms.csv``.  Nested ``extraction_selector``
#: is serialised as compact JSON in one column; list fields are joined with
#: ``LIST_SEPARATOR``.
PLATFORM_COLUMNS: Sequence[str] = (
    "row_id",
    "row_label",
    "organisation_id",
    "organisation_name",
    "prc_role",
    "status",
    "launch_year",
    "model_since",
    "model_note",
    "coverage_start_year",
    "coverage_end_year",
    "discipline_scope",
    "country_of_operator",
    "initiation_class",
    "classification_confidence",
    "classification_note",
    "prc_configuration",
    "configuration_confidence",
    "configuration_note",
    "provisional",
    "publish_arrangement",
    "review_arrangement",
    "curation_arrangement",
    "output_types",
    "public_review_reports",
    "approval_status_public",
    "summary_assessment",
    "reviewer_identity_disclosed",
    "version_linked_review",
    "review_to_object_relation",
    "public_author_response",
    "review_has_doi",
    "editorial_decision_observed",
    "review_disclosure_timing",
    "data_source",
    "register_status",
    "data_status",
    "doi_prefix",
    "doi_pattern",
    "doi_version_pattern",
    "sciety_group_slug",
    "extraction_selector",
    "eligibility_events",
    "counting_event",
    "counting_event_date_field",
    "evidence_url",
    "verified_on",
)

EXCLUDED_COLUMNS: Sequence[str] = (
    "candidate_id",
    "candidate_name",
    "operator",
    "candidate_type",
    "reassess_by",
    "failed_criterion",
    "comparator",
    "verification_status",
    "reason",
    "machine_readable_source",
    "evidence_url",
    "verified_on",
)

#: Fields every register row must declare explicitly (register-row event map
#: plus classification and evidence fields).
REQUIRED_ROW_FIELDS: Sequence[str] = (
    "row_id",
    "organisation_id",
    "prc_role",
    "status",
    "launch_year",
    "model_note",
    "coverage_start_year",
    "coverage_end_year",
    "discipline_scope",
    "country_of_operator",
    "initiation_class",
    "classification_confidence",
    "prc_configuration",
    "configuration_confidence",
    "provisional",
    "publish_arrangement",
    "review_arrangement",
    "curation_arrangement",
    "output_types",
    "public_review_reports",
    "approval_status_public",
    "summary_assessment",
    "reviewer_identity_disclosed",
    "version_linked_review",
    "review_to_object_relation",
    "public_author_response",
    "review_has_doi",
    "editorial_decision_observed",
    "review_disclosure_timing",
    "data_source",
    "register_status",
    "data_status",
    "eligibility_events",
    "counting_event",
    "counting_event_date_field",
    "extraction_selector",
    "evidence_url",
    "verified_on",
)

#: Fields whose value must come from a ``register_meta`` vocabulary.
VOCABULARY_FIELDS: Mapping[str, str] = {
    "initiation_class": "initiation_classes",
    "prc_configuration": "prc_configurations",
    "prc_role": "prc_roles",
    "data_source": "data_sources",
    "register_status": "register_statuses",
    "data_status": "data_statuses",
    "status": "statuses",
    "classification_confidence": "confidences",
    "configuration_confidence": "confidences",
    "publish_arrangement": "arrangements",
    "review_arrangement": "arrangements",
    "curation_arrangement": "arrangements",
    "reviewer_identity_disclosed": "reviewer_identity_values",
    "review_to_object_relation": "review_to_object_relations",
    "discipline_scope": "discipline_scopes",
    "editorial_decision_observed": "editorial_decision_values",
    "review_disclosure_timing": "review_disclosure_timings",
}

#: Three-valued observed signals: ``true`` / ``false`` / ``unknown``.
SIGNAL_FIELDS: Sequence[str] = (
    "public_review_reports",
    "approval_status_public",
    "summary_assessment",
    "version_linked_review",
    "public_author_response",
    "review_has_doi",
)

COUNTING_EVENTS: Sequence[str] = (
    "first_public_posting",
    "earliest_qualifying_evaluation",
    "final_article",
)

#: Which data sources require which selector block.
SELECTOR_REQUIREMENTS: Mapping[str, Sequence[str]] = {
    "crossref": ("crossref",),
    "sciety": ("sciety",),
    "both": ("crossref", "sciety"),
    "none": (),
}


class RegisterError(ValueError):
    """Raised when a register file violates its schema or vocabularies."""


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_yaml(path: Path | str) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, Mapping):
        raise RegisterError(f"{path}: top level must be a mapping")
    return data


def load_platforms(path: Path | str = PLATFORMS_YAML) -> list[dict[str, Any]]:
    """Return the validated list of register rows."""
    data = load_yaml(path)
    rows = data.get("platforms")
    meta = data.get("register_meta")
    if not isinstance(rows, list) or not isinstance(meta, Mapping):
        raise RegisterError(f"{path}: expected keys 'register_meta' and 'platforms'")
    validate_platforms(rows, meta)
    return [dict(r) for r in rows]


def load_excluded(path: Path | str = EXCLUDED_YAML) -> list[dict[str, Any]]:
    data = load_yaml(path)
    rows = data.get("excluded_candidates")
    if not isinstance(rows, list):
        raise RegisterError(f"{path}: expected key 'excluded_candidates'")
    validate_excluded(rows)
    return [dict(r) for r in rows]


def platforms_by_row_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {r["row_id"]: r for r in rows}


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_year(value: Any) -> bool:
    return isinstance(value, int) and 1990 <= value <= 2100


def validate_platforms(rows: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> None:
    """Raise ``RegisterError`` on the first schema or vocabulary violation."""
    errors: list[str] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows):
        label = row.get("row_id", f"<row {idx}>")
        if label in seen:
            errors.append(f"{label}: duplicate row_id")
        seen.add(label)
        for name in REQUIRED_ROW_FIELDS:
            if name not in row:
                errors.append(f"{label}: missing field {name}")
        for name, vocab in VOCABULARY_FIELDS.items():
            if name in row and row[name] not in meta.get(vocab, []):
                errors.append(f"{label}: {name}={row[name]!r} not in register_meta.{vocab}")
        if "provisional" in row and not _is_bool(row["provisional"]):
            errors.append(f"{label}: provisional must be a boolean")
        for name in SIGNAL_FIELDS:
            if name in row and not (_is_bool(row[name]) or row[name] == "unknown"):
                errors.append(f"{label}: {name} must be true, false or unknown")
        for name in ("launch_year",):
            if name in row and not _is_year(row[name]):
                errors.append(f"{label}: {name} must be a four-digit year")
        start = row.get("coverage_start_year")
        start_policy = (row.get("extraction_selector") or {}).get("coverage_start_policy")
        if not _is_year(start) and not (
            start is None
            and start_policy == "first_qualifying_event_year_from_completed_run"
        ):
            errors.append(f"{label}: coverage_start_year needs a year or an explicit run-derived policy")
        if "coverage_end_year" in row and row["coverage_end_year"] is not None and not _is_year(row["coverage_end_year"]):
            errors.append(f"{label}: coverage_end_year must be a year or null")
        if row.get("model_since") is not None and not _is_year(row.get("model_since")):
            errors.append(f"{label}: model_since must be a year or null")
        if _is_year(row.get("launch_year")) and _is_year(row.get("coverage_start_year")):
            if row["coverage_start_year"] < row["launch_year"]:
                errors.append(f"{label}: coverage_start_year precedes launch_year")
        if row.get("coverage_end_year") is not None and _is_year(row.get("coverage_start_year")):
            if row["coverage_end_year"] < row["coverage_start_year"]:
                errors.append(f"{label}: coverage_end_year precedes coverage_start_year")
        outputs = row.get("output_types")
        if not isinstance(outputs, list) or not outputs:
            errors.append(f"{label}: output_types must be a non-empty list")
        else:
            bad = [o for o in outputs if o not in meta.get("output_types", [])]
            if bad:
                errors.append(f"{label}: output_types {bad} not in register_meta.output_types")
        if row.get("counting_event") not in COUNTING_EVENTS:
            errors.append(f"{label}: counting_event must be one of {COUNTING_EVENTS}")
        events = row.get("eligibility_events")
        if not isinstance(events, list) or not events:
            errors.append(f"{label}: eligibility_events must be a non-empty list")
        urls = row.get("evidence_url")
        if not isinstance(urls, list) or not urls or not all(str(u).startswith("http") for u in urls):
            errors.append(f"{label}: evidence_url must be a non-empty list of URLs")
        selector = row.get("extraction_selector")
        if not isinstance(selector, Mapping):
            errors.append(f"{label}: extraction_selector must be a mapping")
        else:
            needed = SELECTOR_REQUIREMENTS.get(row.get("data_source"), ())
            for block in needed:
                if block not in selector:
                    errors.append(f"{label}: data_source={row.get('data_source')} requires extraction_selector.{block}")
            for block in ("crossref", "sciety"):
                spec = selector.get(block, {})
                if spec.get("selector_status", "").startswith("pending_") and row.get("register_status") == "quantified":
                    errors.append(f"{label}: pending selector cannot publish quantitative values")
            if label == "copernicus_interactive_public_peer_review" and row.get("register_status") == "quantified":
                journals = selector.get("crossref", {}).get("journals", [])
                if not journals or any(
                    not j.get("evidence_url") or not j.get("verified_on") or not j.get("discussion_selector")
                    for j in journals
                ):
                    errors.append(f"{label}: quantification requires per-journal evidence and discussion selectors")
        if row.get("register_status") == "quantified" and row.get("data_source") == "none":
            errors.append(f"{label}: quantified rows need a machine-readable data_source")
        if row.get("register_status") == "register_only" and row.get("data_status") not in (
            "not_machine_readable", "defunct", "partial_coverage",
        ):
            errors.append(f"{label}: register_only rows must state data_status as the reason")
        if (row.get("status") == "closed" and row.get("coverage_end_year") is None
                and "closure date not stated" not in str(row.get("model_note") or "")):
            # D-071: a closed row whose closure date is not stated on the platform's own
            # pages keeps an open series to the cutoff (D-024 convention) and says so.
            errors.append(f"{label}: closed rows need coverage_end_year, or a model_note stating "
                          "'closure date not stated' (D-071)")
    if errors:
        raise RegisterError("platform register invalid:\n  " + "\n  ".join(errors))


def validate_excluded(rows: Sequence[Mapping[str, Any]]) -> None:
    errors: list[str] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows):
        label = row.get("candidate_id", f"<candidate {idx}>")
        if label in seen:
            errors.append(f"{label}: duplicate candidate_id")
        seen.add(label)
        for name in EXCLUDED_COLUMNS:
            if name != "reassess_by" and name not in row:
                errors.append(f"{label}: missing field {name}")
        fc = row.get("failed_criterion")
        if fc is not None and fc not in (1, 2, 3):
            errors.append(f"{label}: failed_criterion must be 1, 2, 3 or null")
        if "comparator" in row and not _is_bool(row["comparator"]):
            errors.append(f"{label}: comparator must be a boolean")
        if row.get("comparator") is True and fc != 1:
            errors.append(f"{label}: comparators fail criterion 1 by definition")
        if row.get("verification_status") not in ("verified", "pending", "not_verifiable"):
            errors.append(f"{label}: verification_status must be verified / pending / not_verifiable")
    if errors:
        raise RegisterError("excluded-candidates register invalid:\n  " + "\n  ".join(errors))


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

def _cell(value: Any) -> str:
    """Serialise one YAML value for the flat CSV (empty string for null)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, list):
        return LIST_SEPARATOR.join(_cell(v) for v in value)
    return " ".join(str(value).split())


def render_csv(rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> str:
    """Render rows as CSV text with a fixed column order and LF endings."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(columns)
    for row in rows:
        unknown = set(row) - set(columns)
        if unknown:
            raise RegisterError(f"{row.get('row_id', row.get('candidate_id'))}: unexpected field(s) {sorted(unknown)}")
        writer.writerow([_cell(row.get(c)) for c in columns])
    return buffer.getvalue()


def render_platforms_csv(path: Path | str = PLATFORMS_YAML) -> str:
    return render_csv(load_platforms(path), PLATFORM_COLUMNS)


def render_excluded_csv(path: Path | str = EXCLUDED_YAML) -> str:
    return render_csv(load_excluded(path), EXCLUDED_COLUMNS)


README_TABLE_HEADER = (
    "| Row (`row_id`) | Organisation | Axis 1 (confidence) | Axis 2 (confidence) | Source | Counting event | Coverage | Data status |"
)


def render_readme_table(path: Path | str = PLATFORMS_YAML) -> str:
    """Markdown platform table embedded in README.md (kept in sync by a test)."""
    lines = [README_TABLE_HEADER, "|---|---|---|---|---|---|---|---|"]
    for p in load_platforms(path):
        start = p["coverage_start_year"]
        coverage = f"{start if start is not None else 'run-derived'}–{p['coverage_end_year'] or 'cutoff'}"
        provisional = " (provisional)" if p["provisional"] else ""
        lines.append(
            f"| `{p['row_id']}` | {p['organisation_name']} | `{p['initiation_class']}` ({p['classification_confidence']}) "
            f"| `{p['prc_configuration']}` ({p['configuration_confidence']}){provisional} | {p['data_source']} "
            f"| {p['counting_event']} | {coverage} | {p['data_status']} |"
        )
    return "\n".join(lines) + "\n"


def export(write: bool = True) -> dict[str, bool]:
    """Regenerate both CSV files.  Returns ``{csv_path: changed}``."""
    results: dict[str, bool] = {}
    for yaml_path, csv_path, renderer in (
        (PLATFORMS_YAML, PLATFORMS_CSV, render_platforms_csv),
        (EXCLUDED_YAML, EXCLUDED_CSV, render_excluded_csv),
    ):
        fresh = renderer(yaml_path)
        current = csv_path.read_text(encoding="utf-8") if csv_path.exists() else None
        changed = current != fresh
        if write and changed:
            csv_path.write_text(fresh, encoding="utf-8", newline="\n")
        results[str(csv_path.relative_to(CONFIG_DIR.parent))] = changed
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--export", action="store_true", help="rewrite platforms.csv and excluded_candidates.csv")
    group.add_argument("--check", action="store_true", help="exit 1 if a generated CSV differs from a fresh export")
    group.add_argument("--validate", action="store_true", help="validate both YAML registers only")
    group.add_argument("--readme-table", action="store_true", help="print the Markdown platform table used in README.md")
    args = parser.parse_args(argv)

    try:
        if args.readme_table:
            print(render_readme_table(), end="")
            return 0
        if args.validate:
            load_platforms()
            load_excluded()
            print("registers valid")
            return 0
        results = export(write=args.export)
    except RegisterError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for path, changed in results.items():
        state = ("rewritten" if args.export else "STALE") if changed else "up to date"
        print(f"{path}: {state}")
    if args.check and any(results.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
