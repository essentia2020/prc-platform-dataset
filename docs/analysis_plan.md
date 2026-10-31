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
| First public posting, gated row (`eligibility_events` names `posted-content`; D-060) | `posted-content` only; a work without one is excluded as `no_posting_record` | `posted` → `issued` |
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
  The rule is qualified by the observed state of the source (D-046): the
  Emerald review records were withdrawn from Crossref at the re-hosting
  (REST 404 on the known handle, `issn:2631-3952` + `peer-review` = 0, no
  `emeraldopenres` stem among the 10.21956 review records), so the row
  carries the preset `no_review_records` entry (DQ-013) and its evaluation
  count is 0 by observation. The alias that now redirects the former review
  handle to the article primary is not resolved as `has-review`: that would
  equate an evaluation identifier with a work identifier.
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
  review dated on or before the cutoff. The review deposit was confirmed
  in run_20261026_01 (D-051: 314 unique `10.21956/verixiv.*` reviews
  targeting 185 `10.12688/verixiv.*` preprints); the selector is enabled
  (`posted-content` and `peer-review` under 10.12688 / 10.21956, stem
  regex only) and the row stays provisional until its first flattening.
  Review stems differ from preprint stems, so attribution is relation-based.
  Confirmed Version-of-Record/preprint overlap is expected, reported and
  never a disjointness failure. Preserve both source DOIs and the evidence
  linking them; shared titles alone do not establish work identity.
- **Access Microbiology.** D-017 takes the start year from qualifying events
  in the completed local run, not an assumed 2023 boundary. Keep the
  approved classification separate from this unresolved coverage field;
  no eligible-range zero filling is permitted until the start is resolved.
  D-060: the qualifying event is the posted-content record of an
  `acmi.0.NNNNNN` stem (`.v1`, `.v2` for a revised preprint; empty
  container-title in Crossref); accepted versions are `journal-article`
  records `.vN` and the version of record is the unversioned
  `journal-article` of the same stem, merged by `doi_version_pattern`.
  Conference abstracts under `10.1099/acmi.<meeting>.*` are outside the
  selector; articles published before the preprint model (no posted-content
  record) are excluded as `no_posting_record` and never set the start.
- **eLife — Reviewed Preprints.** D-060: a work enters the row only through
  a posted-content record (the Reviewed Preprint, version 1); the
  `journal-article` version of record of the same stem is merged by
  `doi_version_pattern` and never supplies the counting date. Journal-article
  records without a posted-content record of the same stem are pre-model
  articles (2012 onwards) and are excluded as `no_posting_record`. Six
  Reviewed Preprint postings dated 2022 precede the January 2023 launch
  (pilot), so `coverage_start_year` and `model_since` are 2022.
- **JMIRx Med.** D-016 assigns `mixed` (medium), `core_publish_first`
  (medium), `overlay_journal`, without changing the final-article counting
  event. No public discussion precedes the editorial decision. The
  `JMIRx Med` container also carries the peer-review reports and author
  responses as `journal-article` records with their own DOIs (D-050:
  316 + 104 of 622 records in run_20261026_01); they are excluded as
  `companion_item` by title pattern, logged as `companion_record`, and no
  `peer-review` scope is declared (`no_review_records`, DQ-014).
- **F1000-platform rows.** Version-1 records (`10.12688/<stem>.<id>.1`)
  select the work; later versions, review reports and withdrawn records
  never add works. Reports are collected as evaluation records where
  deposited, from every owner prefix the venue uses for them (D-048):
  10.21956 for most venues, 10.5256 for F1000Research, 10.68336 for Open
  Research Europe (works and reviews; the 10.21956/10.12688 DOI strings of
  that venue are owned by member 13904). NIHR Open Research is registered
  under 10.3310, shared with the NIHR Journals Library, and is selected by
  stem regex (D-047). Seven further venues on the F1000 infrastructure
  (D-052) are provisional rows selected by stem or, for Digital Twin, by
  ISSN after the DOI transfer to the continuing Taylor & Francis journal.
- **Peer Community In.** Recommendations are deposited as
  `journal-article` records under `10.24072/pci.<community>.<id>` with
  `is-review-of` relations (D-049); they are the row's evaluation records
  and the works are the reviewed preprints they target. Reviewer reports
  (`.revNN`), decisions (`.dN`, `.arN`) and Peer Community Journal articles
  (`10.24072/pcjournal.*`) are neither works nor evaluations of the row.
- **Sciety rows.** One docmap may carry several evaluations; each is a
  distinct `evaluation_record` (`sciety:<docmap_id>:<index>` unless a stable
  evaluation DOI exists). Counting event = earliest qualifying evaluation
  output per reviewed work.

## Missingness and publication gates

| State | `unique_works_to_cutoff` | Yearly values | Publication rule |
|---|---:|---:|---|
| `register_only` | empty | empty | register metadata only |
| completed extraction, selector matched no record in any complete scope | empty | empty | blocked: `selector_no_match` plus data-quality row (D-047) |
| completed extraction, zero records, every primary scope a Sciety group absent from the run's docmaps index snapshot | empty | empty | row blocked: `source_not_covering` plus data-quality row (D-058); its group cells publish without the row and name it in `excluded_rows` (D-061) |
| completed extraction, matching records but none in a year of the eligible range | 0 | 0 for that year | may publish |
| completed extraction, no qualifying works after valid exclusions | 0 | 0 for the eligible range only | may publish with quality-log entry |
| incomplete or failed extraction | empty | empty | affected outputs blocked |
| completed extraction with `partial_known_scope` / `unknown_scope` | observed | observed | may publish with coverage limitation |
| completed extraction, row `data_status partial_coverage` or cell `partial_known_scope` | observed | observed | row publishes with coverage limitation; its group cells publish as a lower bound and name it in `lower_bound_rows` (D-061) |

Group cells (class, configuration, all rows) are blank only for states the
pipeline can and must resolve before release: `unknown_scope`,
`pending_run`, `selector_no_match`, extraction `incomplete` or `failed`
(`blocking_rows`). Known properties of the sources — a row with partial
coverage, a yearly lower bound, a source that does not carry the row — are
published as a lower bound with the affected rows named in the cell
(`lower_bound_rows`, `excluded_rows`; D-061, amending D-038 and D-058).

A failed or incomplete cursor walk never produces a count, provisional or
otherwise; downstream analysis stops for every affected register row.
Technical state (`extraction_status`), source observability
(`source_observability_status`), observation status (`observation_status`),
`partial_year` and `count` are independent fields; for a completed
extraction `not_observable` takes priority over `observed_zero`. A
quantified row whose selector matched zero records across all its complete
scopes is a selector defect, never an observed zero: its cells are
`not_observable` / `selector_no_match`, the group series it belongs to stay
blank for those years, and `tools/check_register_prefixes.py` is run
before the next extraction. A quantified Sciety row whose group is absent
from the unfiltered docmaps index retrieved by the same run is a source
that does not cover the group, never an observed zero: its cells are
`not_observable` / `source_not_covering`, the group series are published
without the row and name it, and a count for the row needs an admissible
source named in the register (D-058, D-061).

## Current partial year

The cutoff year is labelled `year_to_date` with the exact cutoff date in
every table header and figure footer, unless the cutoff is 31 December.
Figures draw the partial year with hatched bars. A lower value in the
partial year is never read as a decline. Q-1 fixes the cutoff at
2026-09-30: 2026 has `partial_year: true`; a `complete` row cell is labelled
`year_to_date`, a `partial_coverage` or `partial_known_scope` row cell keeps
its coverage status (D-061).

## Planned tables (`reports/tables/`)

| Table | Content | `additivity` |
|---|---|---|
| `works_by_row_year.csv` | unique works per register row per year | row series |
| `works_by_class_year.csv` | sum of row series within each initiation class | `row_summed` |
| `works_by_configuration_year.csv` | sum of row series within each configuration | `row_summed` |
| `unique_works_by_class_year.csv` | deduplicated on `canonical_work_id` within class; year of earliest counting event among the class's rows | `deduplicated` |
| `unique_works_by_configuration_year.csv` | same, within configuration | `deduplicated` |
| `unique_works_all_rows_year.csv` | the only all-row total (deduplicated); `blocking_rows`, `lower_bound_rows`, `excluded_rows` as in every group table | `deduplicated` |
| `unique_works_all_rows_by_row_year.csv` | per-row attribution of the all-rows total: works whose earliest counting event lies in the row and year (D-059 as merged into D-061); sums by class equal the `n_<class>_by_earliest_event` columns | `deduplicated` |
| `register_summary.csv` | one line per row: both classes, confidences, first/last year with data, `unique_works_to_cutoff`, source, `register_status`, `data_status` | — |
| `coverage_matrix.csv` | row × year: `complete` / `year_to_date` / `partial_coverage` / `partial_known_scope` / `no_data` / `not_applicable` | — |
| `cross_platform_overlap.csv` | works present in more than one row; empty by construction for the two Qeios rows | — |
| `qeios_indicators_by_year.csv` | new hosted works; hosted works with ≥1 public review; all review DOIs; external works reviewed; with deposit-date diagnostics | — |
| `evidence_features_by_platform.csv` | row × configuration, arrangement and evidence fields with confidences | — |

Neither family of class or configuration tables may be summed across
classes or configurations to obtain a grand total. Every table header and
the data dictionary state the `additivity` convention. Each group table
carries `blocking_rows` (non-empty exactly when the cell is blank),
`lower_bound_rows` and `excluded_rows` (`row_id:status; …`); the Markdown
twin carries one footnote per blank cell and one per lower-bound cell.

## Planned figures (`reports/figures/`, PNG 300 dpi + SVG, colour-blind-safe)

1. Annual evaluated works, small multiples by register row, grouped by
   initiation class.
2. Annual totals by initiation class (deduplicated); lower-bound cells
   drawn with a dotted hatch, one footer sentence naming the rows.
3. Share of each initiation class per year (shares within
   `unique_works_all_rows_year.csv`; overlapping works attributed to the
   class of their earliest counting event; attribution relative to the rows
   observable in the run); lower-bound years hatched and named as in 2.
4. Coverage heatmap (row × year).
5. Qeios indicator comparison by year.
6. Annual totals by workflow configuration, small multiples (deduplicated);
   lower-bound convention as in 2.
7. Recognition-signal panels by register row: Panel A three-valued signals
   (`true` / `false` / `unknown`); Panel B `reviewer_identity_disclosed`
   (`always` / `optional` / `never` / `unknown`); separate categorical
   legends; never encoded as ordinal numbers; `binding_publication_decision`
   only as contextual annotation.
8. Annual unique works across all rows, stacked by register row
   (`unique_works_all_rows_by_row_year.csv`; years with a published
   all-rows count only). One bar per year; each work sits in the segment of
   the row holding its earliest counting event, so the segments sum to the
   all-rows total. Rows whose whole-period total is below 1,000 works are
   merged into one dark-grey `Other` segment whose composition is listed in
   the footer; stack order and legend follow descending whole-period totals
   (largest at the bottom). The cutoff year carries the `//` hatch and a
   year whose all-rows cell is a lower bound the dotted hatch, applied to
   the whole bar; the footer names the lower-bound and excluded rows as in
   Figure 2.

   Figure 8 is the counterpart of Figure 1 in Corker, Waltman and Coates
   (2024) (OpenAlex-based platform counts), but the two are not comparable
   number for number. That figure counts submissions per platform as
   OpenAlex records them, so a work reviewed on two platforms, or posted
   and then evaluated, enters each platform's bar; Figure 8 counts each
   work once, in the row of its earliest counting event, from Crossref and
   Sciety records under the register's counting rules (D-040) and only for
   rows observable in the run. Its totals are therefore lower, and a
   segment is the row's share of the deduplicated total, not the row's own
   series (that series is `works_by_row_year.csv` and Figure 1). The
   Unjournal (D-063) and MetaROR (D-064) enter Figure 8 from the first run
   after those decisions (Crossref peer-review records as primary source);
   until then they are named among the excluded rows in the footer.

All figures are recomputed from `data/processed/` tables; no hard-coded
values. Legend swatches are plain: hatches describe cells (partial year,
lower bound), never categories. Small multiples use independent y-axes.

## Implementation map (Stages 4–6)

| Rule | Module | Test file |
|---|---|---|
| Row technical state from the run manifest; cross-check scopes never block | `src/common/run_state.py` | `tests/test_run_state.py` |
| Record-level layer, identifiers, evaluation identity, source-precision dates, flagged targets | `src/normalise/clean_and_normalise.py` | `tests/test_normalise_records.py` |
| Register-row event map (`counting_event`; ≥1 qualifying evaluation read from `eligibility_events`) | `src/analyse/build_aggregates.py::requires_evaluation` | `tests/test_binding_decision_consistent.py` |
| Posting-record gate for first-public-posting rows naming `posted-content` (D-060); `doi_regex` and `container_titles` as alternative work-record signals; register summary and deduplicated group series restricted to each row's eligible range (`in_eligible_range`, `n_works_outside_eligible_range`) | `build_aggregates.requires_posting_record`, `RowAnalysis.counted_works`, `src/extract/selectors.py::CrossrefSelector.matches_work` | `tests/test_posting_record_gate.py` |
| Cutoff rule, missingness gates, tie-break | `src/common/eligibility.py`, `src/common/dates.py` | `tests/test_ambiguous_cutoff_not_counted.py`, `tests/test_eligibility_rules.py` |
| Copernicus register-only fallback applied only to a complete run (D-032) | `build_aggregates.effective_register_status` | `tests/test_binding_decision_consistent.py` |
| Blank vs zero; register-only; incomplete scope; unresolved coverage start | `src/common/aggregates.py::cell_for`, `build_aggregates.row_cells` | `tests/test_register_only_is_blank.py`, `tests/test_incomplete_extraction_blocks_outputs.py`, `tests/test_complete_empty_is_zero.py` |
| Group additivity (D-038 blocking statuses, `blocking_rows`, footnotes), deduplication, no grand total, overlap reporting, Qeios disjointness | `build_aggregates._group_members`, `_group_cells`, `_dedup_cells` | `tests/test_total_equals_sum_of_years.py` |
| Lower-bound group cells (D-061): `partial_coverage` / `partial_known_scope` members counted and named in `lower_bound_rows`, `source_not_covering` members excluded and named in `excluded_rows`, group `coverage` rule, cutoff-year rule for row cells, per-row attribution table, offline fixture seeded with preset data-quality rows only | `build_aggregates.GroupMembers`, `_group_cell`, `_dedup_cells`; `src/common/aggregates.py::cell_for`; `tests/offline.py` | `tests/test_total_equals_sum_of_years.py`, `tests/test_aggregate_conventions.py`, `tests/test_sciety_coverage.py`, `tests/test_data_quality_log_single_file.py`, `tests/test_complete_empty_is_zero.py` |
| Sciety index coverage (D-058): one `index__all` walk per run, `index_coverage` per group scope, `source_not_covering` for rows whose groups are absent from the snapshot; rule 6 of the walk-shape check | `src/extract/sciety_evaluations.py::index_coverage_counts`, `src/common/run_state.py::RowState.source_not_covering`, `build_aggregates.row_cells`; `tools/check_walk_shape.py` (`--sciety-index`) | `tests/test_sciety_coverage.py`, `tests/test_check_walk_shape_sciety.py` |
| Transient `pending_run` absent from released tables (D-039) | `build_aggregates.row_cells` | `tests/test_release_no_pending_run.py` |
| Single data-quality log, preset rows immutable, run rows identified (D-040) | `build_aggregates.update_data_quality_log` | `tests/test_data_quality_log_single_file.py` |
| Walk shape: `total_delta == 0` is necessary, the page sequence is the proof (repeated `cursor_in`, non-empty pages vs `ceil(total-results / rows)`, mid-walk short page, record on two pages; pages missing from the raw store make the last rule inconclusive, never passed) | `src/common/manifest.py::walk_shape_issues`; post-run CLI `tools/check_walk_shape.py --run <run_id> [--raw-root]` | `tests/test_walk_shape.py`, `tests/test_check_walk_shape_cli.py` |
| Windowed walks for a scope whose single cursor walk loses records between cursor steps (D-045 option c, D-057): one cursor walk per date window at tolerance 0, unwindowed `total-results` probed before and after the pass, complete only when every window is complete and the window totals sum to both probes; recorded as one composite walk of the scope plus one walk per window sub-scope | `src/common/windows.py`, `src/common/windowed_walk.py`, `crossref_common.windowed_scope_config`; `config/sources.yaml` `pagination.windowed_scopes` | `tests/test_windowed_walk.py` |
| Deposition diagnostics (Qeios indicators, `created`/`deposited` after cutoff) | `build_aggregates.qeios_indicators` | `tests/test_total_equals_sum_of_years.py` (via tables) |
| Figures 1–8, hatched partial year, dotted lower-bound cells with named rows (Figures 2, 3, 6, 8), stacked all-rows Figure 8 with the `Other` merge, plain legend swatches, independent y-axes in small multiples, SVG ids salted with the run id, categorical panels, checksums | `src/report/make_reports.py` | `tests/test_report_figures.py` |

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
