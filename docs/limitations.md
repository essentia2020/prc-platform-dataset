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
  and preLights activity) is missing.
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
  its coverage start to be established by the completed local run.
- **Deposition practice changes over time.** For Qeios, registration of
  reviews of external works in Crossref largely ceased after 2022, and
  metadata deposition for hosted works became discontinuous after 2024;
  both Qeios rows therefore carry `partial_coverage`, and later years
  understate activity. Other platforms may show similar, undocumented
  discontinuities; these are logged in `data/processed/data_quality_log.csv`
  as they are observed.

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
- Emerald Open Research is observed through records re-registered under 10.1108/EOR-* after the platform closed; the original 10.35241 DOIs are Crossref aliases of these primaries and are returned once. A primary carries the issued date of the last original version, so a work whose versions span two calendar years is counted in the later year; titles carry no version tag and the share of such works cannot be determined from the permitted sources (data-quality log, date_semantics). Three title-level journal records returned by the ISSN query are excluded by record type.

## Register coverage versus quantitative coverage

Register coverage is systematic and includes verified services without
machine-readable records; quantitative coverage is restricted to rows with
reproducible selectors in Crossref or Sciety. Counts therefore describe the
machine-readable part of the PRC landscape, not the whole of it.

## Blank cells in group series

A class or configuration cell is blank only when a member row whose
eligible range covers that year carries `unknown_scope` or `pending_run`
(coverage start not yet observed), `partial_coverage` (a series known to be
a lower bound), or an incomplete extraction scope. Rows outside their
eligible range and rows with an observed zero never block the sum (D-038).
Every blank group cell names the blocking row and status in the
`blocking_rows` column and in a footnote of the Markdown table. Because
several community-initiated and author-initiated rows carry
`partial_coverage` (Qeios, PREreview, preLights, Gates Open Research,
PeerRef), their group series are blank for the years those
rows are in range; the row-level table and the coverage matrix remain fully
populated.

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
  row is quantified and remains provisional until its first flattening.
  Pending source selectors cannot publish quantitative values even when
  the classification itself is approved.
- Seven venues on the F1000 infrastructure entered the register as
  provisional rows after run_20261026_01 found their works and reviews in
  the complete 10.12688 / 10.21956 walks (D-052): Stosunki Międzynarodowe –
  International Relations, Nuclear Science and Technology Open Research,
  Digital Twin, Molecular Psychology, Materials Open Research, Cobot and
  Bioethics Open Research. Their workflow pages were only partly readable at
  verification; the platform-period and status fields rest on the F1000
  venue list and on the deposited records and are marked for confirmation.
  Digital Twin continues since 2025 as a conventional Taylor & Francis
  journal under 10.1080 with a closed platform period (2021–2025); only the
  platform period is counted and the row is selected by ISSN because part of
  its 10.12688 DOIs are now owned by the continuing journal.
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

- **Owner prefix versus DOI string.** The Crossref `prefix` filter selects
  by current owner, not by the string of the DOI. Three rows in
  run_20261026_01 declared a prefix that owns none of the venue's records
  (MedEd Publish → 10.12688, Open Research Europe → 10.68336, NIHR Open
  Research → 10.3310) and would have published zeros. A quantified row whose
  complete scopes match no record now yields `not_observable` /
  `selector_no_match` (D-047), and `tools/check_register_prefixes.py`
  resolves one known work DOI and one known review DOI per row before an
  extraction to compare owner prefix and member with the declared scopes.
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
