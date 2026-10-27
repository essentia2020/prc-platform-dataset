# Analysis plan — PRC Platform Dataset 1.4.0

## Research questions

1. **Scale.** How many unique research works per year flow through each
   Publish–Review–Curate (PRC) platform or service that exposes
   machine-readable records?
2. **Initiation.** How do annual volumes compare between author-initiated,
   community-initiated and mixed evaluation (axis 1)?
3. **Configuration.** How do annual volumes compare between the four
   workflow configurations (axis 2: core publish-first, approval threshold,
   hybrid public discussion, review or curation service)?
4. **Coverage.** Which PRC services are verifiable but not quantifiable from
   Crossref or Sciety, and how does that limit the picture?
5. **Transparency features.** Which recognition and transparency features
   (public reports, reviewer identity, author response, DOIs for reviews)
   does each platform exhibit?

## Unit of analysis

The **unique research work per register row (series) per year** of its
earliest qualifying event. Reviews, versions, rounds and responses never
increase counts. A register row is an observation series (one organisation,
one counting event, one extraction selector); series are comparable over
time within a row, never between rows. Rows of the same organisation are
never summed.

Work identifiers follow one namespaced syntax (`doi:<lowercased-doi>`,
`url:<normalised-url>`, `id:<source>:<identifier>`). The asserted target of
an evaluation (`reviewed_work_id`, version suffix retained) is kept apart
from the canonical identifier (`reviewed_canonical_work_id`, version suffix
stripped by the platform-specific pattern); joins, overlap tests and
deduplication use the canonical identifier.

## Inclusion and exclusion

- **Register inclusion** follows the three numbered criteria of
  `config/classification_scheme.md` (publish-first sequence; public
  evaluation or curation output; verifiable workflow). Comparators and
  unverifiable candidates are listed in `config/excluded_candidates.yaml`.
- **Quantification** (`register_status = quantified`) requires a
  reproducible extraction selector and qualifying records in Crossref or
  Sciety; otherwise the row is `register_only` and all analytical values
  stay blank (never zero).
- **Work-level inclusion** applies the event-history rule: a work is included
  only when every event required by its row-specific eligibility rule has an
  event date on or before `analysis_cutoff_date` and the relevant metadata
  are present in the completed retrieval recorded by the run manifest.
  Metadata deposited after the cutoff may establish an earlier qualifying
  event; retrieval dates are never eligibility limits.

## Event dates

Crossref `created`, `deposited` and `indexed` are provenance fields only.
Event-date priority:

| Counting event | Record type | Priority |
|---|---|---|
| First public posting | `posted-content` | `posted` → `issued` |
| First public posting | `journal-article` version 1 / base record | `issued` |
| Earliest qualifying review | Crossref `peer-review` | `issued` |
| Earliest qualifying review | Sciety evaluation | evaluation `published` |
| Final article | `journal-article` | `issued` |

Incomplete dates are closed calendar intervals (`2024` → whole year,
`2024-05` → whole month). A work is included when
`event_interval_end <= analysis_cutoff_date`, excluded as future when
`event_interval_start > analysis_cutoff_date`, and retained but not counted
(`exclusion_reason = ambiguous_cutoff_date`) when the interval contains the
cutoff. A missing permitted event date gives
`exclusion_reason = missing_event_date`. Overlapping candidate intervals
trigger the deterministic source-priority tie-break recorded in
`docs/data_dictionary.md` and `date_order_ambiguous = true`.

## Counting rules per row

General rules are in `config/classification_scheme.md` (event map). Rows
with specific methodology:

- **Qeios — hosted works.** Crossref `journal-article` and `posted-content`
  under prefix 10.32388; `10.32388/<id>.<n>` is canonicalised to
  `10.32388/<id>`; records titled "WITHDRAWN" are dropped. A work qualifies
  only if at least one Crossref `peer-review` record points to it through
  `is-review-of` with an evaluation date on or before the cutoff; the
  counting date is the first public posting (`posted` → `issued` across the
  work's version records). Hosted works without a deposited review stay in
  the raw and interim layers but are excluded from the series.
- **Qeios — evaluations of external works.** `is-review-of` targets of
  10.32388 `peer-review` records that are not 10.32388 DOIs. Targets include
  preprints and published journal articles, so the series describes
  reviewed works in general, not only preprints. One work counts once, at its
  earliest Qeios review. Registration of such reviews largely ceased after
  2022 and metadata deposition became discontinuous after 2024; both rows
  carry `partial_coverage`.
- **MedEd Publish.** Posted works only: version-1 or base records across
  three DOI regimes (`10.15694/mep.<year>.<vol>.<art>` and
  `10.15694/mep.<year>.<art>` base records; `10.15694/mep.<…>.1` versioned
  records; `10.12688/mep.<id>.1` current records), deduplicated on the base
  identifier; withdrawn records and later versions excluded; date = `issued`
  of the version-1 or base record. All three regimes are retrieved through
  the owner prefix 10.12688, to which the 10.15694 records passed with the
  title (the Crossref `prefix` filter selects by current owner). No
  DOI-level review records exist for the AMEE years, so a "reviewed works"
  series cannot be reconstructed; the posted-works series is complete.
  Because 10.12688 is shared with other F1000-platform stems, selection
  uses a DOI-pattern selector, never a bare prefix filter.
- **Emerald Open Research.** Articles retrieved by journal ISSN
  (`2631-3952`, type `journal-article`), selected by
  `^10\.(1108/eor-|12688/emeraldopenres\.)`. The counting event is the
  earliest `issued` among retrieved records of the work, not its
  registration date. The documented 13140 correspondence joins
  `10.12688/emeraldopenres.13140.1` through its `new_version` relation
  to `10.35241/emeraldopenres.13140.2`, an alias of
  `10.1108/eor-03-2023-0005`; the primary supplies the canonical identifier,
  not a privileged event date. The v1 record supplies 2019-06-07 when
  retrieved; the primary retains 2019-12-09 and carries `later_version`.
  A primary with no other retrieved record supplies its own `issued`.
  Titles never establish correspondence. Reviews are attributed through
  `is-review-of` or inverse `has-review` evidence, never shared DOI stems.
- **PREreview.** Unique works with at least one PREreview evaluation in
  Sciety docmaps, dated by the evaluation `published` date, deduplicated on
  the reviewed-work DOI, independent of preprint server.
- **SciPost.** Crossref `journal-article` under 10.21468, excluding
  `10.21468/scipost.report.*`; counting event = final article `issued`.
  Rejected submissions are not deposited.
- **Copernicus.** D-015 counts discussion-preprint entry into public
  discussion, not final publication. Only individually verified journals
  enter the executable selector, with journal-specific evidence URLs and
  discussion DOI/EGUsphere attribution rules (D-027: 29 journals verified,
  10 excluded). The publisher index is a candidate list, not an inclusion
  filter. EGUsphere preprints count only when attributed to a verified
  journal; unattributed records are reported per year
  (`egusphere_unattributed`, DQ-010) and the EGUsphere-era values are
  labelled a lower bound with `partial_known_scope` in `coverage_matrix`.
  Under D-032, any of `is-preprint-of`, a verified journal title or an
  incoming Crossref peer-review `is-review-of` is sufficient; retain all
  signals in `attribution_basis`. Unattributed preprints remain in interim
  with `included=false` and `exclusion_reason=no_journal_attribution`.
  Pre-EGUsphere discussion DOIs use pattern attribution. Register-only
  fallback applies only when none of the three signals is observed in a
  completed local run.
- **Gates Open Research and VeriXiv.** D-013 keeps two rows under
  `organisation_id: gates_f1000`. Gates Open Research counts v1 publication
  through 2024; VeriXiv counts first preprint posting conditional on a public
  review dated on or before the cutoff. VeriXiv review deposits require
  confirmation in the completed local run; until then counts remain blank.
  Confirmed Version-of-Record/preprint overlap is expected, reported and
  never a disjointness failure. Preserve both source DOIs and the evidence
  linking them; shared titles alone do not establish work identity.
- **Access Microbiology.** D-017 takes the start year from qualifying events
  in the completed local run, not an assumed 2023 boundary. Keep the
  approved classification separate from this unresolved coverage field;
  no eligible-range zero filling is permitted until the start is resolved.
- **JMIRx Med.** D-016 assigns `mixed` (medium), `core_publish_first`
  (medium), `overlay_journal`, without changing the final-article counting
  event. No public discussion precedes the editorial decision.
- **F1000-platform rows.** Version-1 records (`10.12688/<stem>.<id>.1`)
  select the work; later versions, review reports (`10.21956/…`) and
  withdrawn records never add works. Reports are collected as evaluation
  records where deposited.
- **Sciety rows.** One docmap may carry several evaluations; each is a
  distinct `evaluation_record` (`sciety:<docmap_id>:<index>` unless a stable
  evaluation DOI exists). Counting event = earliest qualifying evaluation
  output per reviewed work.

## Missingness and publication gates

| State | `unique_works_to_cutoff` | Yearly values | Publication rule |
|---|---:|---:|---|
| `register_only` | empty | empty | register metadata only |
| completed extraction, complete empty result | 0 | 0 for the eligible range only | may publish |
| completed extraction, no qualifying works after valid exclusions | 0 | 0 for the eligible range only | may publish with quality-log entry |
| incomplete or failed extraction | empty | empty | affected outputs blocked |
| completed extraction with `partial_known_scope` / `unknown_scope` | observed | observed | may publish with coverage limitation |

A failed or incomplete cursor walk never produces a count, provisional or
otherwise; downstream analysis stops for every affected register row.
Technical state (`extraction_status`), source observability
(`source_observability_status`), observation status (`observation_status`),
`partial_year` and `count` are independent fields; for a completed
extraction `not_observable` takes priority over `observed_zero`.

## Current partial year

The cutoff year is labelled `year_to_date` with the exact cutoff date in
every table header and figure footer, unless the cutoff is 31 December.
Figures draw the partial year with hatched bars. A lower value in the
partial year is never read as a decline. Q-1 fixes the cutoff at
2026-09-30: 2026 is `year_to_date` with `partial_year: true`.

## Planned tables (`reports/tables/`)

| Table | Content | `additivity` |
|---|---|---|
| `works_by_row_year.csv` | unique works per register row per year | row series |
| `works_by_class_year.csv` | sum of row series within each initiation class | `row_summed` |
| `works_by_configuration_year.csv` | sum of row series within each configuration | `row_summed` |
| `unique_works_by_class_year.csv` | deduplicated on `canonical_work_id` within class; year of earliest counting event among the class's rows | `deduplicated` |
| `unique_works_by_configuration_year.csv` | same, within configuration | `deduplicated` |
| `unique_works_all_rows_year.csv` | the only all-row total (deduplicated) | `deduplicated` |
| `register_summary.csv` | one line per row: both classes, confidences, first/last year with data, `unique_works_to_cutoff`, source, `register_status`, `data_status` | — |
| `coverage_matrix.csv` | row × year: `complete` / `year_to_date` / `partial_coverage` / `no_data` / `not_applicable` | — |
| `cross_platform_overlap.csv` | works present in more than one row; empty by construction for the two Qeios rows | — |
| `qeios_indicators_by_year.csv` | new hosted works; hosted works with ≥1 public review; all review DOIs; external works reviewed; with deposit-date diagnostics | — |
| `evidence_features_by_platform.csv` | row × configuration, arrangement and evidence fields with confidences | — |

Neither family of class or configuration tables may be summed across
classes or configurations to obtain a grand total. Every table header and
the data dictionary state the `additivity` convention.

## Planned figures (`reports/figures/`, PNG 300 dpi + SVG, colour-blind-safe)

1. Annual evaluated works, small multiples by register row, grouped by
   initiation class.
2. Annual totals by initiation class (deduplicated).
3. Share of each initiation class per year (shares within
   `unique_works_all_rows_year.csv`; overlapping works attributed to the
   class of their earliest counting event).
4. Coverage heatmap (row × year).
5. Qeios indicator comparison by year.
6. Annual totals by workflow configuration, small multiples (deduplicated).
7. Recognition-signal panels by register row: Panel A three-valued signals
   (`true` / `false` / `unknown`); Panel B `reviewer_identity_disclosed`
   (`always` / `optional` / `never` / `unknown`); separate categorical
   legends; never encoded as ordinal numbers; `binding_publication_decision`
   only as contextual annotation.

All figures are recomputed from `data/processed/` tables; no hard-coded
values.

## Implementation map (Stages 4–6)

| Rule | Module | Test file |
|---|---|---|
| Row technical state from the run manifest; cross-check scopes never block | `src/common/run_state.py` | `tests/test_run_state.py` |
| Record-level layer, identifiers, evaluation identity, source-precision dates, flagged targets | `src/normalise/clean_and_normalise.py` | `tests/test_normalise_records.py` |
| Register-row event map (`counting_event`; ≥1 qualifying evaluation read from `eligibility_events`) | `src/analyse/build_aggregates.py::requires_evaluation` | `tests/test_binding_decision_consistent.py` |
| Cutoff rule, missingness gates, tie-break | `src/common/eligibility.py`, `src/common/dates.py` | `tests/test_ambiguous_cutoff_not_counted.py`, `tests/test_eligibility_rules.py` |
| Copernicus register-only fallback applied only to a complete run (D-032) | `build_aggregates.effective_register_status` | `tests/test_binding_decision_consistent.py` |
| Blank vs zero; register-only; incomplete scope; unresolved coverage start | `src/common/aggregates.py::cell_for`, `build_aggregates.row_cells` | `tests/test_register_only_is_blank.py`, `tests/test_incomplete_extraction_blocks_outputs.py`, `tests/test_complete_empty_is_zero.py` |
| Group additivity (D-038 blocking statuses, `blocking_rows`, footnotes), deduplication, no grand total, overlap reporting, Qeios disjointness | `build_aggregates._group_members`, `_group_cells`, `_dedup_cells` | `tests/test_total_equals_sum_of_years.py` |
| Transient `pending_run` absent from released tables (D-039) | `build_aggregates.row_cells` | `tests/test_release_no_pending_run.py` |
| Single data-quality log, preset rows immutable, run rows identified (D-040) | `build_aggregates.update_data_quality_log` | `tests/test_data_quality_log_single_file.py` |
| Deposition diagnostics (Qeios indicators, `created`/`deposited` after cutoff) | `build_aggregates.qeios_indicators` | `tests/test_total_equals_sum_of_years.py` (via tables) |
| Figures 1–7, hatched partial year, categorical panels, checksums | `src/report/make_reports.py` | `tests/test_report_figures.py` |

The eligible range of a row is `[max(launch_year, coverage_start_year),
coverage_end_year or cutoff year]`. When `coverage_start_year` is empty and
`extraction_selector.coverage_start_policy` is
`first_qualifying_event_year_from_completed_run`, the start is the earliest
`counting_year` of the row's included works in a complete run (then written
to the register as `model_since` / `coverage_start_year`, earlier years
becoming `not_applicable`). Before the first complete run the row's cells
carry the transient `pending_run`; after a complete run without qualifying
events they carry `unknown_scope`. Both block the group cells the row
contributes to (D-038, D-039).

## Validation steps

- Register validation (`python -m src.common.register --validate`) and CSV
  synchrony tests.
- User-ruling consistency checks for D-012 through D-026 and Q-1 through
  Q-3; pending selectors cannot enable quantitative publication.
- Boundary tests for the cutoff logic, Qeios eligibility, year-only dates,
  register-only blanks, complete-empty zeros, incomplete walks, cursor
  restarts, docmap multiplicity, versioned relations and the four-valued
  identity field.
- Event-map, parent-resolution, binding-decision, URL-canonicalisation,
  evaluation-identity, observability-priority, partial-year, provisional-
  exclusion, Qeios-intersection and additivity tests.
- End-to-end offline run (extraction from fixtures → normalisation →
  analysis → report) shared by the Stage 4–6 tests, once with every scope
  complete and once with a failed scope.
- Manifest checksum verification against a local raw store when present.
- Repository text audit (`tools/audit_text.py --history`) with zero
  unresolved hits before each release review.

## Register coverage versus quantitative coverage

**Register coverage** is systematic: every verified PRC platform or service
appears in `config/platforms.yaml`, including those with
`data_status = not_machine_readable` or `defunct`. **Quantitative coverage**
is restricted to rows with reproducible machine-readable records in Crossref
or Sciety. The two are reported separately (`register_summary.csv`,
`coverage_matrix.csv`) and are never conflated in text or figures.
