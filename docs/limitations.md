# Limitations — PRC Platform Dataset 1.4.0

## Source coverage

- **Crossref** covers only platforms that deposit DOIs and, for reviews,
  only those depositing `peer-review` records with `is-review-of`
  relations. Platforms whose reviews live only on their own site or on
  hypothes.is are invisible or undercounted. MedEd Publish is the documented
  case: posted works only; no reviewed-works series can be reconstructed.
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
  `is-preprint-of` in the preprint record.
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
  VeriXiv remains explicitly provisional pending Crossref review-deposit
  confirmation. Pending source selectors cannot publish quantitative
  values even when the classification itself is approved.
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
