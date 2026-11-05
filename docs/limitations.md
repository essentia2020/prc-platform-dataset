# Limitations — PRC Platform Dataset 1.4.0

## Source coverage

- **Crossref** covers only platforms that deposit DOIs and, for reviews,
  only those depositing `peer-review` records with `is-review-of`
  relations. Platforms whose reviews live only on their own site or on
  hypothes.is are invisible or undercounted. MedEd Publish is the documented
  case: posted works only; no reviewed-works series can be reconstructed.
  Emerald Open Research is the second case: its review records were
  withdrawn from Crossref at the re-hosting (D-046, DQ-013), so the row has
  150 works and 0 evaluation records by observation. JMIRx Med deposits its
  review reports and author responses as `journal-article` companion items
  rather than `peer-review` records (D-050, DQ-014); they are excluded from
  the work count and no reviewed-works series is attempted.
- **Sciety** covers only groups that have joined Sciety and only from their
  joining date; earlier activity of those groups (for example early PREreview
  and preLights activity) is missing. The docmaps index additionally covers
  only the groups Sciety has enabled for docmaps, group by group (eleven
  groups in the index of 2026-10-28). Register rows whose only selector is a
  Sciety group absent from the index (Review Commons and PeerRef in run_20261027_01; 
  PeerRef alone in run_20261102_01) publish no count: `source_not_covering` (D-058), never a
  zero, although their Sciety group pages list evaluations. The Unjournal
  (D-063), MetaROR (D-064, superseding D-025) and Review Commons (D-065)
  left this set: their evaluations are Crossref `peer-review` records with
  `is-review-of` (MetaROR under its own prefix 10.70744; The Unjournal
  under the PubPub prefix 10.21428 with the community stem `d28e8e57`;
  Review Commons under the EMBO prefix 10.15252 with the stem `rc.`), so
  Crossref is the primary source and the absent Sciety group is kept as a
  cross-check only (D-037). PeerRef remains the only row in the set.
- **SciPost** is observed through final published works, not every submission.
  **Copernicus** instead counts discussion-preprint entry into public
  discussion (D-015), so rejected discussion preprints are not categorically
  invisible. Journal-level verification is complete (D-027), but EGUsphere
  preprints without any D-032 attribution signal cannot be attributed to the
  journal-review scope. The EGUsphere-era part of the series is a yearly
  lower bound labelled `partial_known_scope` (DQ-010); an incoming Crossref
  peer-review relation is sufficient even without a journal title or
  `is-preprint-of` in the preprint record. The yearly unattributed
  EGUsphere totals rise sharply in the cutoff year (run_20261026_01:
  13 / 2 / 5 / 15 / 561 for 2022–2026): a discussion preprint acquires its
  journal signal only when the final article or its review relations are
  deposited, so the most recent year is dominated by publication lag rather
  than by a change in attribution quality.
  JMIRx Med retains final-article counting despite its `core_publish_first`
  classification ruling; Access Microbiology counts preprint posting, with 
  its coverage start re-derived from every complete run (2022 in `run_20261102_01`; D-017).
- **Two rows count only works with a posted-content record (D-060).** eLife
  deposits Reviewed Preprints as `posted-content` and the version of record
  of the same stem as `journal-article`; the prefix also carries the
  journal's pre-model articles (journal-article only, 2012 onwards;
  16,075 stems in run_20261027_01), which are not Reviewed Preprints and are
  excluded as `no_posting_record`. Access Microbiology deposits the preprint
  as `posted-content` with an empty container-title and the accepted
  versions and version of record as `journal-article`; conference abstracts
  under the same stem family and articles published before the preprint
  model are outside the row. Both series therefore measure the
  publish-first model only, not the journals' total output; a Reviewed
  Preprint or an Access Microbiology preprint whose posted-content record
  was never deposited is missed.
- **Deposition practice changes over time.** For Qeios, registration of
  reviews of external works in Crossref largely ceased after 2022, and
  metadata deposition for hosted works became discontinuous after 2024;
  both Qeios rows therefore carry `partial_coverage`, and later years
  understate activity. Other platforms may show similar, undocumented
  discontinuities; these are logged in `data/processed/data_quality_log.csv`
  as they are observed.
- **Rows with `data_status partial_coverage`** (their series are lower
  bounds, and the group cells they enter are lower bounds, D-061):
  `prelights`, `prereview` and `peerref` (as recorded in the register),
  `qeios_hosted_works` and `qeios_external_works` (the deposition
  discontinuities above), and `the_unjournal` (D-063: only evaluations the
  Unjournal registers as Crossref `peer-review` records with `is-review-of`
  are observable — 42 of 106 records under the community stem on
  2026-10-31; its `journal-article` evaluation summaries carry no relation
  and are not counted, and evaluations published without a Crossref record
  are missed).

### Pending external requests

As of 2026-11-02, sciety/sciety#4254 is the only open request about source
coverage. No outcome is claimed for that request.

- sciety/sciety#4254 (opened 2026-10-31): PeerRef into the Sciety docmaps
  index and, if no obstacle, MetaROR, Review Commons and The Unjournal for
  the cross-check scopes. The Sciety docmaps allow-list is the only machine
  route for PeerRef; a direct request to PeerRef follows if Sciety declines.

### Answered external requests

- The Unjournal (e-mail of 2026-10-31, answered 2026-10-31, D-063):
  the service confirmed the composition of the 13 journal-article records.
  The requested dataset link and counting rules were sent on 2026-11-02,
  after repository publication. Whether is-review-of and the ISSN will be
  added to the existing deposits remains unconfirmed; the correspondence
  is answered, not evidence that those corrections have been made.

## Event history and retrieval

- The dataset reconstructs event history from the metadata present in the
  recorded retrieval window. It does not claim to reproduce the metadata
  observable on the analysis cutoff date. Metadata deposited, corrected or
  linked after the cutoff may add or move historical events, so a later
  retrieval can change a historical series.
- Date semantics differ between sources. Crossref `issued` (and `posted`
  for posted content) is used as the event date; `created`, `deposited` and
  `indexed` are provenance diagnostics only. Sciety evaluations are dated by
  the evaluation `published` date. Peer Community In recommendation DOIs
  carry the recommendation date, not the preprint posting date. Incomplete
  dates are treated as intervals; events whose interval contains the cutoff
  are retained but not counted.
- The cutoff year is a partial year (`year_to_date`) unless the cutoff is
  31 December; a lower value in that year is never evidence of decline.
- Crossref cursor walks over tens of pages can skip records between cursor
  steps while `total-results` stays constant (F1000Research reviews under
  10.5256: 31 and 205 of 30,197 records missing in two walks of 2026-10-27).
  Such a scope is retrieved in issued-date windows of at most a few pages
  each, with the window totals checked against the unwindowed total before
  and after the pass (D-057). Records without an issued date would fall
  outside every window; the partition check would then fail the scope
  rather than count the remainder.
- Emerald Open Research is observed through records re-registered under 10.1108/EOR-* after the platform closed; the original 10.35241 DOIs are Crossref aliases of these primaries and are returned once. A primary carries the issued date of the last original version, so a work whose versions span two calendar years is counted in the later year; titles carry no version tag and the share of such works cannot be determined from the permitted sources (data-quality log, date_semantics). Three title-level journal records returned by the ISSN query are excluded by record type.

## Register coverage versus quantitative coverage

Register coverage is systematic and includes verified services without
machine-readable records; quantitative coverage is restricted to rows with
reproducible selectors in Crossref or Sciety. Counts therefore describe the
machine-readable part of the PRC landscape, not the whole of it.

## Lower-bound group cells

A class, configuration or all-rows cell is blank only for states the
pipeline can and must resolve before release: a member row whose eligible
range covers that year carries `unknown_scope` or `pending_run` (coverage
start not yet observed) or `selector_no_match` (a selector defect, D-047),
or that member's extraction is incomplete or failed. Rows outside their
eligible range and rows with an observed zero never block the sum (D-038).
Every blank group cell names the blocking rows and statuses in the
`blocking_rows` column and in a footnote of the Markdown table.

Known properties of the sources do not blank a cell (D-061, amending D-038
and D-058). The cell is published as a lower bound and names the rows:

- `lower_bound_rows` — members with `data_status partial_coverage`
  (`prelights`, `prereview`, `qeios_hosted_works`, `qeios_external_works`,
  `the_unjournal` from D-063) or a `partial_known_scope` cell (the EGUsphere
  attribution of `copernicus_interactive_public_peer_review`) are counted;
  their series are lower bounds, so the group cell is one.
- `excluded_rows` — quantified Sciety rows whose group is absent from the
  run's docmaps index snapshot (`peerref`; D-058) are not counted
  (`the_unjournal` was in this set until D-063, `metaror` until D-064 and
  `review_commons` until D-065 made Crossref their primary source). The row keeps
  `register_status quantified`, its own cells stay `not_observable` with
  the D-058 note, and the group cell is published without it.

Such a cell carries `coverage = partial_coverage` (or
`partial_known_scope` when that is the only lower-bound status present and
nothing is excluded); Figures 2, 3, 6 and 8 draw it with a dotted hatch and
name the rows once in the footer. A group cell whose in-range members are
all excluded stays blank, never a zero. The row-level table and the
coverage matrix remain fully populated; a complete row keeps `year_to_date`
in the cutoff year, a `partial_coverage` row keeps `partial_coverage`
there, with `partial_year = true` in both cases.

## Platforms and services not covered quantitatively

Verification of the candidates below is recorded in
`config/excluded_candidates.yaml` (`verification_status`, `reason`); the
list is completed before the release freeze.

| Candidate | Why not covered |
|---|---|
| ScreenIT | automated screening, not peer evaluation (D-026 exclusion) |
| GigaScience, GigaByte, PeerJ | conventional pre-publication review with published reports; comparators |
| ScienceOpen | register-only row `scienceopen_reviews` (D-028): criteria met, no selector in the permitted sources yet |
| EMBO Press / Early Evidence Base | aggregator of reviewed preprints produced by other services; would duplicate register rows |
| PubPeer | unstructured post-publication comments; no machine-readable evaluation records |
| ResearchHub | excluded on criterion 3 (D-028): the platform's own pages describe two different workflows on the verification date |
| hypothes.is-only journal clubs | heterogeneous, no operator-level documentation, no machine-readable records |
| Episciences overlay journals | not verifiable in this pass (documentation site unreachable); expected to fail criterion 1 or 2 |
| Peeriodicals | register-only row `peeriodicals` (D-028): operational, public reviews and decisions, no identifiers in the permitted sources |
| Octopus | register-only row `octopus` (D-028): publish-first with open reviews; DOIs through DataCite, outside the permitted sources |
| Researchers.One | about page not reachable at verification; not verifiable |
| Sinai Immunology Review Project | project domain no longer resolves; not verifiable |
| bioRxiv / medRxiv comment sections | reader comments, not service-attributable evaluation outputs |

## Classification

- Classification reflects publicly documented workflows at the verification
  date (`verified_on` in `config/platforms.yaml`); platforms may change
  models. Where a change is documented, `model_since` and the notes record
  it, and the classification applies to the current model.
- Confidence is separate from ruling status. D-012 through D-026 are
  decided, and medium or low confidence alone does not set `provisional`.
  VeriXiv's review deposit was confirmed in run_20261026_01 (D-051); the
  row is quantified and its provisional flag was cleared by D-071.
  Pending source selectors cannot publish quantitative values even when
  the classification itself is approved.
- A VeriXiv preprint and its Gates Open Research Version of Record are
  paired only through the Crossref relations `is-preprint-of` (on the
  preprint) and `has-preprint` (on the version-1 article); either side
  suffices and the side(s) observed are recorded (D-041). Pairs that
  neither record asserts stay two works in the row series and in the
  overlap table; the OpenAlex pair signal (D-066) counts how many of these
  residual works share one OpenAlex work id and reports the number in the
  data-quality log without pairing them. Since D-071 cleared the VeriXiv
  flag, the deduplicated tables count a paired work once, on the row of
  its earliest counting event (in the published tables of
  run_20261102_01, produced while the flag was set, the paired works sit
  on the Gates Open Research row; the local re-run moves them).
- Cross-row preprint and version pairs other than VeriXiv / Gates Open
  Research are not paired (D-068). In run_20261102_01, 105 distinct
  canonical-identifier pairs are linked by `has-preprint` and/or
  `is-version-of` relations deposited on work records of different
  register rows (87 pairs by `has-preprint`, 104 by `is-version-of`; the
  two sets overlap). Deduplication works on canonical work identifiers, so
  each side is a separate work in the deduplicated group tables and the
  all-rows series is overstated by at most 105 works over 2017–2026; row
  series are unaffected. The pairs by row combination (107 row-specific
  occurrences, because two identifier pairs appear in two row
  combinations):

  | Row A | Row B | Pairs |
  |---|---|---|
  | arcadia_science | elife_reviewed_preprints | 30 |
  | review_commons | elife_reviewed_preprints | 34 |
  | prelights | elife_reviewed_preprints | 17 |
  | prereview | elife_reviewed_preprints | 13 |
  | rapid_reviews_infectious_diseases | elife_reviewed_preprints | 5 |
  | biophysics_colab | elife_reviewed_preprints | 2 |
  | life_science_editors | elife_reviewed_preprints | 1 |
  | life_science_editors_foundation | elife_reviewed_preprints | 1 |
  | pci_recommendations | elife_reviewed_preprints | 1 |
  | qeios_external_works | elife_reviewed_preprints | 1 |
  | ncrc | wellcome_open_research | 1 |
  | rapid_reviews_infectious_diseases | wellcome_open_research | 1 |

  The relations are correspondence candidates, not a ruling that every
  version or preprint assertion warrants a merge; the preset row DQ-019
  records the count and the generalised pairing is listed under Future
  work.
- OpenAlex is a diagnostic source (D-041, D-066). The volume check
  compares each quantified Crossref row's included works with OpenAlex by
  DOI and, where a source id is configured, with the source's own yearly
  counts; a difference is recorded in the data-quality log and never
  corrects a series, a coverage status or a register field. OpenAlex's
  ingestion lag and its own source assignment mean that a work absent
  from OpenAlex or counted under another year is expected for recent
  years; the rows are observations, not errors. "Not found" in the 
  OpenAlex volume check means "no record under this DOI", which for 
  versioned and merged records is expected: Access Microbiology and 
  eLife reviewed preprints are counted on versioned DOIs, and OpenAlex 
  answers a Copernicus discussion-paper DOI with the record of the merged 
  final article (run_20261102_01: 57 219 of 67 054).
- Seven venues on the F1000 infrastructure entered the register as
  provisional rows (flags cleared by D-071 on 2026-11-05) after run_20261026_01 found their works and reviews in
  the complete 10.12688 / 10.21956 walks (D-052): Stosunki Międzynarodowe –
  International Relations, Nuclear Science and Technology Open Research,
  Digital Twin, Molecular Psychology, Materials Open Research, Cobot and
  Bioethics Open Research. Statuses were confirmed against Crossref and the
  venue sites on 2026-10-27: three active, Digital Twin closed (2021–2025),
  Molecular Psychology, Cobot and Materials Open Research dormant (last new
  submission 2025-01-27, 2024-11-18, 2024-06-03; no Taylor & Francis
  continuation). Materials Open Research opened for submissions in November
  2021 and published its first articles in 2022, so its 2021 cell is an
  observed zero. Digital Twin continues since 2025 as a conventional Taylor
  & Francis journal under 10.1080; only the platform period (about 90
  records, 38 of them now owned by the continuing journal) is counted and
  the row is selected by ISSN because part of its 10.12688 DOIs changed
  owner. D-071 cleared the provisional flags after the venues' own
  workflow pages were re-read on 2026-11-05 and recorded Molecular
  Psychology as closed (closure date not stated; open series to the
  cutoff) and the Taylor & Francis continuation of Digital Twin as a
  single-anonymous workflow outside the row.
- Some platform websites could not be read automatically at verification
  (robots restrictions or parsing failures); for those rows the notes name
  the secondary evidence used (operator pages, Sciety group descriptions)
  and the row is marked for confirmation.

## Platform-specific metadata issues

Platform-specific metadata issues (placeholder `is-review-of` targets,
retrospective deposits, version suffixes, withdrawn records, date-precision
problems) are logged in `data/processed/data_quality_log.csv` with their
effect on counts and the handling applied; the log is summarised here at the
release freeze.

- **Placeholder review targets (MetaROR).** Reviews of a preprint whose
  DOI is registered with DataCite (arXiv, OSF) cannot carry a Crossref
  `is-review-of` relation to that DOI, so MetaROR points them at its own
  placeholder DOI `10.70744/MetaROR.placeholder01` (one manuscript in the
  probe of 2026-10-31; D-064). Such records are kept with `record_flag
  placeholder_target`, create no work and are counted per run in the
  `placeholder_relation` row of the data-quality log; the reviewed
  manuscripts are absent from the `metaror` series.
- **Evaluation summaries without a relation (The Unjournal).** Thirteen 
  journal-article records under the community stem d28e8e57 (10 author 
  responses and 3 evaluation summaries, per the service's reply of 2026-10-31) 
  carry no relation at all and no ISSN, so they lie outside the peer-review 
  walk and are neither counted nor flagged; author responses are not evaluations 
  and would never add a work, so the uncounted evaluations are the three summaries 
  (probe of 2026-10-31: 106 records under the stem
  including the title-level `journal` record, 42 `peer-review` with
  `is-review-of` to 36 distinct external targets; DQ-016); the evaluation
  count per work is a lower bound.
- **Report dates at transfer (Review Commons).** The Crossref `issued` date
  of a Review Commons report is the publication date of the report package
  at transfer to a journal (mandatory since 2022-06-01), not the date of
  review, so the `review_commons` series lags review and may cluster on
  posting days (DQ-017; D-065).
- **Owner prefix versus DOI string.** The Crossref `prefix` filter selects
  by current owner, not by the string of the DOI. Three rows in
  run_20261026_01 declared a prefix that owns none of the venue's records
  (MedEd Publish → 10.12688, Open Research Europe → 10.68336, NIHR Open
  Research → 10.3310) and would have published zeros. A quantified row whose
  complete scopes match no record now yields `not_observable` /
  `selector_no_match` (D-047), and `tools/check_register_prefixes.py`
  resolves one known work DOI and one known review DOI per row before an
  extraction to compare owner prefix and member with the declared scopes.
  For Sciety rows the analogous ambiguity (empty response because the group
  is not in the index) is resolved by the run's own index snapshot
  (`source_not_covering`, D-058).
- **Repeated slashes in deposited DOIs.** MedEd Publish deposited one 2021
  article as `10.15694//mep.2021.000035.1` with three reviews targeting the
  same double-slash string (D-053, DQ-015). Canonical identifiers use the
  collapsed form; the deposited string is kept in `work_id` /
  `source_record_id` and flagged `repeated_slash`.
- **Duplicate relation assertions.** Crossref returns most `is-review-of`
  relations twice (asserted by subject and by object). The review interim
  keeps both lines with an `asserted_by` column; normalisation collapses
  them to one relation per (review, target), so relation line counts in the
  interim are roughly twice the number of unique pairs.
