# Decision log — PRC Platform Dataset 1.4.0

Numbered record of every design, classification and process decision. Each entry states the date, the question, the options considered, the decision, the evidence URL(s) and who decided. Every entry, D-001 through D-065 and Q-1 through Q-5, carries decided_by: researcher. D-027 through D-031 document preparation choices; D-032 through D-035 record the decisions on extraction, 2026-10-20, and govern their implementation; D-036 through D-041 record the decisions on normalisation, analysis and reporting, 2026-10-20; D-042 records the decision on repository history, 2026-10-20; D-043 and D-044 record the decisions of 2026-10-26 on two register rows whose Crossref records changed owner or primary identifier; D-045 records the decision of 2026-10-26 on Crossref walk completion and per-scope tolerance; D-046 through D-054 record the decisions of 2026-10-27 on the structural findings of run_20261026_01 (withdrawn review records, owner prefixes and the selector_no_match guard, evaluation records deposited under work types, companion items, VeriXiv, seven provisional F1000-infrastructure rows, repeated-slash DOIs, the Rapid Reviews cross-check); D-055 and D-056 record the decisions of 2026-10-27 on the audit boundary for harvested text and on keeping harvested records outside the repository; D-058 records the decision of 2026-10-28 on verifying Sciety index coverage per run; D-060 through D-062 record the decisions of 2026-10-28 to 2026-10-31 on the posting-record gate, group cells as lower bounds and the Gates Open Research data_status (D-059 was merged into D-061); D-063 through D-065 record the decisions of 2026-10-31 on Crossref peer-review records as the primary source for The Unjournal, MetaROR and Review Commons. Confidence and decision status are independent: a decided classification may retain medium or low confidence without being provisional.
Decision entries in this log are identified by decision number, date and subject.

---

## D-001: Qeios: two register rows with separate classifications

- **Date:** 2026-10-19
- **Decided by:** researcher
- **Question:** How should Qeios be represented, given that it hosts works
  under its own DOI prefix and also registers public reviews of works hosted
  elsewhere?
- **Options considered:** (a) one row for the organisation; (b) two rows,
  one per counting event, linked by `organisation_id`; (c) hosted works only.
- **Decision:** (b). Two register rows with separate classifications:

| Field | `qeios_hosted_works` | `qeios_external_works` |
|---|---|---|
| `organisation_id` | qeios | qeios |
| `prc_role` | integrated_platform | review_service |
| Axis 1 `initiation_class` | `author_initiated`, confidence `medium` | `community_initiated`, confidence `medium` |
| Axis 2 `prc_configuration` | `approval_threshold`, confidence `medium` | `review_or_curation_service`, confidence `high` |
| `counting_event` | first public posting of a hosted work that has ≥1 deposited public review | earliest public Qeios review of a work hosted outside 10.32388 |
| `status` / coverage | `active`; `partial_coverage` (deposition discontinuity after 2024) | `dormant` (registration of external reviews largely ceased after 2022); `partial_coverage` |
| `evidence_url` | https://www.qeios.com/publishing-policy ; https://www.qeios.com/about ; https://www.qeios.com/plans | https://www.qeios.com/publishing-policy plus the Crossref `is-review-of` targets themselves |

- **Rationale:** For hosted works, evaluation is triggered by the authors'
  act of posting on the platform; the platform then invites reviewers
  (including automated invitation) and admits volunteered reviews, which is
  the same structure as other author-submission platforms, so spontaneous
  reviewers do not make the class `mixed`. The optional Version-of-Record
  step requires at least four reviews with average ratings above a defined
  threshold, which places the hosted series in `approval_threshold`; the
  `configuration_note` states that the step is optional and author-triggered
  and that the Version of Record may be published by its authors. For
  external works, the reviewed articles and preprints were never submitted
  to the platform and were selected by the platform or its reviewers; the
  selection mechanism is not documented on the current website, hence
  confidence `medium` and `model_since` noting the 2021–2022 concentration.
  A hosted work is included only when its first public posting and at least
  one qualifying public review are dated on or before `analysis_cutoff_date`
  and present in the completed retrieval. The two rows are never summed;
  `cross_platform_overlap.csv` must show zero overlap between them by
  construction (pipeline test).
- **Evidence:** https://www.qeios.com/publishing-policy ;
  https://www.qeios.com/about ; https://www.qeios.com/plans

## D-002: SciPost: `author_initiated` (high) / `hybrid_public_discussion` (high)

- **Date:** 2026-10-19
- **Decided by:** researcher
- **Question:** How is SciPost classified on both axes, and what is its
  counting event?
- **Options considered:** (a) `core_publish_first` (public refereeing of a
  posted submission); (b) `hybrid_public_discussion` (public refereeing
  followed by a binding editorial decision); (c) comparator (conventional
  journal).
- **Decision:** `author_initiated` (high) on axis 1;
  `hybrid_public_discussion` (high) on axis 2.
- **Rationale:** After an Editor-in-charge is assigned, a public Submission
  Page is opened for invited and contributed reports, comments and author
  replies; the Editorial College then takes a binding publish-or-reject
  decision by vote. Public discussion followed by a conventional editorial
  decision is the defining test of `hybrid_public_discussion`. The
  `configuration_note` records the differences from Copernicus: the
  Submission Page may be removed from public view after rejection or
  withdrawal unless the authors ask to keep it, and the editorial
  recommendation itself is not public. Consequently the `counting_event` is
  publication of the work (Crossref `journal-article` under 10.21468,
  excluding `10.21468/scipost.report.*`): rejected submissions are not
  deposited, so the series measures published works that underwent public
  refereeing, not all submissions. Evidence fields:
  `public_review_reports = true`, `reviewer_identity_disclosed = optional`,
  `public_author_response = true`, `summary_assessment = false`,
  `approval_status_public = false`. Authors' ability to suggest or exclude
  referees is a variation of author submission and does not
  create a second entry route.
- **Evidence:** https://scipost.org/submissions/editorial_procedure ;
  https://scipost.org/submissions/editorial_workflow ;
  https://scipost.org/EdCol_by-laws

## D-003: Licensing split

- **Date:** 2026-10-20 (user ruling)
- **Decided by:** researcher
- **Question:** Which licences apply to code and to data, and with which
  directory scopes?
- **Options considered:** (a) MIT for code, CC BY 4.0 for data with the
  directory scopes below; (b) a single licence for everything; (c) CC0 for
  data.
- **Decision:** (a). `LICENSE` = MIT, scope `src/`, `tools/`, `tests/`.
  `LICENSE-DATA` = CC BY 4.0, scope `config/`, `data/processed/`,
  `reports/`, `docs/`. README has a "Licensing" section naming both files
  and their directory scopes; `data/raw/` responses carry the source terms
  recorded in `config/sources.yaml`.
- **Evidence:** https://opensource.org/license/mit ;
  https://creativecommons.org/licenses/by/4.0/

## D-004: Repository-history audit

- **Date:** 2026-10-20 (user ruling)
- **Decided by:** researcher
- **Question:** Is the repository new (history audit from the first commit)
  or pre-existing (history rewrite or a documented starting revision)?
- **Options considered:** (a) new repository, audit covers every commit
  from the initial commit; (b) pre-existing repository with history rewrite;
  (c) pre-existing repository with a documented starting revision.
- **Decision:** (a). The repository is new. `tools/audit_text.py --history`
  covers all commits from the initial commit; no starting-revision
  limitation is documented. History rewriting remains prohibited without
  explicit user approval.
- **Evidence:** not applicable (process decision).

## D-005: Raw-response storage

- **Date:** 2026-10-20 (user ruling)
- **Decided by:** researcher
- **Question:** Are immutable raw responses tracked in Git, stored with
  Git LFS, or kept outside the repository with checksums tracked?
- **Options considered:** (a) outside the repository, checksums tracked;
  (b) Git LFS; (c) tracked in Git.
- **Decision:** (a). `data/raw/` is excluded from Git. Both manifests — the
  run-level `data/manifests/<run_id>.json` and the accepted-page
  `data/manifests/<run_id>/<walk_id>.manifest.jsonl` — are tracked. Each
  manifest records the SHA-256 of every accepted
  `page_<n>/attempt_<k>.response.json.gz`; `reports/CHECKSUMS.txt`
  references the manifests rather than duplicating hashes.
  `tests/test_manifest_checksums_match.py` verifies bytes against the
  manifests when a local raw store is present (`PRC_RAW_STORE`); otherwise it
  skips with an explicit "raw store absent" message and never passes
  silently. The raw-response archive is deposited as a separate Zenodo
  record linked to the release.
- **Evidence:** not applicable (process decision).

## D-006: Zenodo concept record

- **Date:** 2026-10-20 (user ruling)
- **Decided by:** researcher
- **Question:** Will release 1.4.0 use a new Zenodo concept record or
  become a version of an existing concept record?
- **Options considered:** (a) new concept record, no related-identifier
  link to any other dataset record; (b) reuse of an existing concept record.
- **Decision:** (a). New concept record; no related-identifier link to any
  other dataset record. `CITATION.cff` contains no placeholder text: the
  `doi` field is omitted until the DOI is reserved in the
  Zenodo draft and inserted before release freeze. One related identifier is
  added to the Zenodo metadata and to `CITATION.cff:references`: the
  conference presentation registered under R3 in
  `config/audit_allowlist.yaml`, relation `isSupplementTo`. The presentation
  is outside the repository audit and its content is not quoted.
- **Evidence:** https://doi.org/10.5281/zenodo.22787722

## D-007: Project structure

- **Date:** 2026-10-20 (user ruling)
- **Decided by:** researcher
- **Question:** Is the proposed repository layout approved?
- **Options considered:** the proposed tree; amendments listed below.
- **Decision:** Approved with amendments: `src/common/log.py` (not
  `logging.py`); tracked `data/manifests/`; `.gitignore` excludes
  `data/raw/`, `data/interim/`, `logs/` (keeping `.gitkeep`),
  `.audit_tokens.txt` and `*.audit_tokens*`; `LICENSE-DATA` at the root;
  `--tokens` overrides `PRC_AUDIT_TOKENS` and the audit fails if both are set
  and differ; `tests/test_audit_self_clean.py` fails on a missing, empty or
  zero-token token file; `tests/test_platforms_csv_in_sync.py`,
  `tests/test_audit_self_clean.py` and
  `tests/test_manifest_checksums_match.py` are part of the test listing.
- **Evidence:** not applicable (process decision).

## D-008: Audit tokens (R1) and voice rule (R4)

- **Date:** 2026-10-20 (user ruling)
- **Decided by:** researcher
- **Question:** How are R1 tokens matched, and which process words belong
  to R1 or R4?
- **Options considered:** substring matching; word-boundary matching;
  moving tool-related words to R4.
- **Decision:** R1 matches on regular expressions with word boundaries by
  default; multi-word tokens use `\s+`; all-caps abbreviations are
  case-sensitive, all other tokens case-insensitive. At adoption, the names
  of the five decision reviews and the wording describing how decisions are
  collected were not included in the local token list, because they were
  required vocabulary of this log. Tool
  names and tool-role words are R4 patterns, not R1 tokens. The token file
  is authored and kept locally outside the repository; its content is never
  echoed in any repository file or report.
- **Evidence:** not applicable (process decision).

## D-009: Limitations as a separate file

- **Date:** 2026-10-20 (user ruling)
- **Decided by:** researcher
- **Question:** Are limitations kept in `docs/limitations.md` or folded
  into README?
- **Options considered:** (a) separate file with a short README section
  linking to it; (b) README only.
- **Decision:** (a). `docs/limitations.md` is kept; README contains a short
  "Limitations" section that links to it, not a copy.
- **Evidence:** not applicable (process decision).

## D-010: One field for the data source

- **Date:** 2026-10-20 (user ruling)
- **Decided by:** researcher
- **Question:** The register-row event map and the register description
  used two names for the same field.
- **Options considered:** keep both; harmonise to one.
- **Decision:** One field, `data_source` (`crossref` / `sciety` / `both` /
  `none`), used everywhere: `config/platforms.yaml`, the data dictionary and
  the register-row event map.
- **Evidence:** not applicable (schema decision).

## D-011: Permitted citations

- **Date:** 2026-10-20 (user ruling)
- **Decided by:** researcher
- **Question:** Which conceptual sources may be cited, where, and in which
  voice?
- **Options considered:** one source only (PRC definition); two sources
  (PRC definition plus workflow-configuration axis).
- **Decision:** Both. The first source is the sole source for the PRC
  definition (README "Definition", `config/classification_scheme.md`). The
  second is the conceptual source for the workflow-configuration axis; it is
  the dataset author's own article and is cited in README "Related
  publications" and in `config/classification_scheme.md` (axis 2 rationale)
  in first-person or neutral voice only — never as third-person
  self-reference; one positive R4 fixture covers this pattern. Both are
  registered in `config/audit_allowlist.yaml` under R3 with exact
  bibliographic strings and are listed in `CITATION.cff:references`
  (together with the presentation of D-006). Author name, ORCID and
  affiliation are legitimate in `CITATION.cff` and are not R1 tokens.
- **Evidence:** see `config/audit_allowlist.yaml` (R3 entries).

---

## Decisions, 2026-10-20: platform classification

All entries below record decisions, 2026-10-20. Approval of a method is distinct from
completion of its evidence checks; outstanding checks are stated explicitly.

## D-012: F1000-platform stems: which rows, and splitting of merged sites

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Which F1000-platform stems form register rows, and are
  the renamed sites (Health Open Research, formerly AMRC Open Research;
  Open Research Africa, formerly AAS Open Research) kept as one row each or
  split by DOI stem?
- **Options considered:** (a) one row per currently operating site, with
  DOI-stem patterns covering the former stems (proposed); (b) one row per
  historical stem; (c) a single F1000-platform row.
- **Decision:** (a). One row per current site, with former DOI stems covered
  by `doi_pattern`; site-renaming history belongs in `model_note`.
  Rows: F1000Research, Wellcome Open Research, Gates
  Open Research, Open Research Europe, HRB Open Research, NIHR Open Research,
  Health Open Research, Open Research Africa, Routledge Open Research
  (`medium`, own site not parsed), MedEd Publish (separate counting rule),
  Emerald Open Research (`closed`). Stem patterns are in
  `doi_pattern` and `extraction_selector.crossref.doi_regex`. D-013 specifies
  the separate Gates and VeriXiv series.
- **Evidence:** https://f1000research.com/about ;
  https://www.f1000.com/resources-for-researchers/where-to-publish-your-research/f1000-publishing-venues/

## D-013: Gates Open Research: model change (VeriXiv) in 2024

- **Date:** 2026-10-20
- **Status:** decided; deposit verification remains open for VeriXiv
- decided_by: researcher
- **Question:** Since August 2024 new submissions are first posted as
  preprints on VeriXiv and published on Gates Open Research after passing
  peer review. Does the row keep `approval_threshold` with `model_since =
  2024` and a provisional coverage note, or is a second row needed for the
  VeriXiv stage?
- **Options considered:** (a) one row, configuration unchanged, note and
  `provisional: true` until the first local run shows where the first
  public posting is registered (proposed); (b) second row for VeriXiv
  preprints; (c) close the series at 2024.
- **Decision:** (b). Two series share `organisation_id: gates_f1000`:
  `gates_open_research` has configuration `approval_threshold`, counts v1
  publication, and ends in 2024; `verixiv` counts first preprint posting
  conditional on at least one public review and has `model_since: 2024`.
  VeriXiv remains provisional until Crossref peer-review deposits are
  confirmed by the local run. Both the posting and the qualifying review
  must be dated on or before the cutoff and present in the completed
  retrieval. Non-zero Version-of-Record/preprint overlap between the two
  rows is expected and reported, not a pipeline error. Work identity across
  their distinct DOIs requires explicit correspondence, never a title-only
  match. The zero-intersection test remains specific to the two Qeios rows.
- **Evidence:** https://gatesopenresearch.org/about

## D-014: Emerald Open Research: closure year

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** The platform site no longer lists approval statuses and the
  content is re-hosted on Emerald Insight as volume 1 (2023); the closure
  date is not stated on the platform site.
- **Options considered:** (a) `status = closed`, `coverage_end_year =
  2023`, `configuration_confidence = medium` (proposed); (b) wait for the
  first local run and set the end year from the last `issued` date.
- **Decision:** (a). `status: closed`, `coverage_end_year: 2023`.
  Retain `configuration_confidence: medium`; clear `provisional`.
- **Evidence:** https://emeraldopenresearch.com/about ;
  https://www.emerald.com/insight/publication/issn/2631-3952

## D-015: Copernicus interactive public peer review: journal list and counting event

- **Date:** 2026-10-20
- **Status:** decided; journal-level verification remains to be completed
- decided_by: researcher
- **Question:** (i) Which Copernicus journals operate interactive public
  peer review (all EGU journals use EGUsphere from 1 January 2025; earlier,
  journal-specific discussion forums)? (ii) Is the counting event the final
  article (`issued`) or the discussion preprint?
- **Options considered:** (i) journals showing a "Preprints" forum on the
  publisher's journal index (proposed) versus a hand-verified list per
  journal; (ii) final article (comparable with SciPost; proposed) versus
  discussion preprint (captures rejected submissions, but the preprint DOI
  stems differ by journal and era).
- **Decision:** Use a hand-verified journal list with an `evidence_url` for
  each journal: interactive review is journal-specific. Count the discussion
  preprint at entry into public discussion, not the final article.
  `configuration_note` must distinguish this from SciPost's final-article
  rule. A generic publisher index is not evidence of interactive review for
  every journal. Discussion preprints may remain observable after rejection;
  no blanket rejected-submission invisibility claim applies to this series.
  Verify journal-specific discussion DOI patterns and EGUsphere journal
  attribution before enabling quantification. Stand-alone EGUsphere records
  without evidence of entry into the selected journal workflows are not
  automatically included.
- **Evidence:** https://publications.copernicus.org/services/public_peer_review.html ;
  https://www.egusphere.net/about/faqs.html

## D-016: JMIRx Med: `mixed` / `core_publish_first` (both medium)

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Editors prospect medRxiv preprints and authors may
  self-nominate; reports are published only with the accepted article.
- **Options considered:** axis 1 `mixed` (proposed) or `author_initiated`
  (if prospecting is marginal); axis 2 `hybrid_public_discussion` (proposed)
  or exclusion as a comparator (if the publicly posted preprint is not
  considered the platform's own publish step).
- **Decision:** `mixed` (medium) on axis 1; `core_publish_first` (medium)
  on axis 2; `prc_role: overlay_journal`. No public discussion precedes the
  decision. Clear `provisional`. This is an explicit row-specific ruling,
  not a claim that an editorial decision is absent; the approved derived
  binding-decision mapping remains a configuration-derived variable.
  The final-article counting event is unchanged by this classification ruling.
- **Evidence:** https://support.jmir.org/hc/en-us/articles/360034752692-What-is-JMIRx ;
  https://xmed.jmir.org/

## D-017: Access Microbiology: configuration and `model_since`

- **Date:** 2026-10-20
- **Status:** decided; coverage start resolved in run_20261102_01 (2022, see below).
- decided_by: researcher
- **Question:** Preprint posted before review, reports and decision
  published with DOIs after a conventional accept decision; the start year of
  the open-research-platform model could not be confirmed on the Society's
  site.
- **Options considered:** `hybrid_public_discussion` (proposed, medium)
  versus `core_publish_first`; `coverage_start_year = 2023` versus the first
  year observed in the local run.
- **Decision:** `hybrid_public_discussion` (medium). Clear `provisional`;
  take the series start year from the completed local run, not from 2023.
  Until then `model_since` and `coverage_start_year` are unset. Resolve the
  observed start from qualifying preprint events, not the journal's launch
  year or registration timestamps; do not infer unobserved zeros.
- **Evidence:** https://sciety.org/groups/access-microbiology/about ;
  https://www.microbiologyresearch.org/content/journal/acmi/about
- **Resolved 2026-11-02 (run_20261102_01):** the first posted-content posting
  year is 2022 (DQ-run_20261102_01-025; 850 unique works to the cutoff, none
  outside the eligible range); 2019–2021 are `not_applicable` (pre-model
  articles and abstracts, D-060), not observed zeros. `model_since` and
  `coverage_start_year` stay null under `coverage_start_policy`
  `first_qualifying_event_year_from_completed_run`: every complete run
  re-derives the start and records it in the data-quality log, so a register
  value would duplicate it. The register is amended only if a later run
  resolves a different year.

## D-018: PREreview: `community_initiated` (medium) versus `mixed`

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Any researcher may review any preprint, and a documented
  "request a PREreview" route is open to anyone including authors; a request
  does not commission a review.
- **Options considered:** (a) `community_initiated`, medium (proposed:
  reviewers still self-select); (b) `mixed`.
- **Decision:** (a). `community_initiated` (medium); retain
  `review_or_curation_service` and clear `provisional`.
- **Evidence:** https://prereview.org/request-a-prereview

## D-019: Biophysics Colab: `mixed` (low)

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Curators consider preprints in scope and engage reviewers
  with the authors' consent; authors may also approach the service. The share
  of each route is undocumented.
- **Options considered:** (a) `mixed`, low (proposed); (b)
  `community_initiated` with consent noted; (c) `author_initiated`.
- **Decision:** (a). `mixed` (low); retain `review_or_curation_service`.
  Low confidence records evidence uncertainty, not a pending classification
  ruling; `provisional: false`.
- **Evidence:** https://www.sciencecolab.org/biophysics-colab

## D-020: Life Science Editors Foundation and Life Science Editors: inclusion and class

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Both Sciety groups publish signed editorial assessments of
  preprints; the foundation reviews work of scientists from under-represented
  groups, the company's assessments may be a paid author service. The
  foundation's own site could not be read; the company has no documented
  workflow page.
- **Options considered:** (a) keep both rows as `mixed` (low),
  `provisional: true` (proposed); (b) foundation only; (c) move the company
  to `config/excluded_candidates.yaml` (criterion 3).
- **Decision:** (a). Keep both rows as `mixed` (low) and
  `review_or_curation_service` (medium). Apply Q-3: clear `provisional`
  because the inclusion and classification ruling is now made. Retain the
  evidence limitations in the notes.
- **Evidence:** https://sciety.org/groups/life-science-editors-foundation/about ;
  https://www.lifescienceeditors.org/foundation ;
  https://sciety.org/groups/life-science-editors/about

## D-021: The Unjournal: `mixed` (medium)

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** The service identifies and solicits research and also
  accepts author submissions through documented forms.
- **Options considered:** (a) `mixed`, medium (proposed); (b)
  `community_initiated`.
- **Decision:** (a). `mixed` (medium); retain `review_or_curation_service`.
  `provisional: false`.
- **Evidence:** https://www.unjournal.org/about

## D-022: ASAPbio crowd review rows: status and overlap with PREreview

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Crowd reviews (2021–2024) were posted on PREreview and
  appear as separate Sciety groups (English-language crowd; SciELO
  Portuguese-language crowd). Are both rows kept, with `status = dormant`,
  and the overlap with the PREreview row reported?
- **Options considered:** (a) two rows, `community_initiated` (medium),
  overlap reported in `cross_platform_overlap.csv` (proposed); (b) one row;
  (c) fold into PREreview.
- **Decision:** (a). Keep two dormant series with `community_initiated`
  (medium). Report their overlap with PREreview in
  `cross_platform_overlap.csv`; do not treat shared evaluations as an error.
  Clear `provisional`.
- **Evidence:** https://asapbio.org/crowd-preprint-review

## D-023: Arcadia Science: operating status

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** The starting hypothesis was that the service ceased in
  2025; the Sciety group shows evaluation activity through October 2026.
- **Options considered:** (a) `status = active`, as observed (proposed);
  (b) `dormant`.
- **Decision:** (a). `status: active`. Record in `model_note` that the
  "ceased 2025" hypothesis is refuted: only the publishing venue moved in
  December 2025. This dated correction is recorded as a user ruling, 2026-10-20; it
  must not be converted into a service-closure date.
- **Evidence:** https://sciety.org/groups/arcadia-science ;
  https://research.arcadiascience.com/

## D-024: PeerRef: dormant service

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Authors request journal-independent review; the latest
  Sciety activity is dated 2023 and the service site shows no new activity.
- **Options considered:** (a) `status = dormant`, `partial_coverage`,
  open series (proposed); (b) `closed` with `coverage_end_year = 2023`.
- **Decision:** (a). `status: dormant`, `data_status: partial_coverage`,
  and an open series (`coverage_end_year: null`); not a 2023 closure.
- **Evidence:** https://www.peerref.com/ ; https://sciety.org/groups/peerref

## D-025: MetaROR: data source

- **Date:** 2026-10-20
- **Status:** decided; superseded by D-064 (Crossref selector confirmed by probe of 2026-10-31)
- decided_by: researcher
- **Question:** MetaROR publishes reviews and curation statements via
  Sciety; whether it also deposits Crossref peer-review records is unknown.
- **Options considered:** (a) `data_source = sciety` (proposed); (b)
  `both`, to be confirmed in the first local run.
- **Decision:** (a). `data_source: sciety` until the local run provides
  evidence supporting an additional Crossref selector.
- **Evidence:** https://metaror.org/about/ ; https://metaror.org/how-it-works/

## D-026: Excluded candidates and pending verifications

- **Date:** 2026-10-20
- **Status:** decided; pending candidate checks remain required
- decided_by: researcher
- **Question:** ScreenIT (automated screening), GigaScience, GigaByte and
  PeerJ (pre-publication review with published reports) are proposed as
  exclusions; the candidates named in `docs/limitations.md` (ScienceOpen,
  EMBO Early Evidence Base, PubPeer, ResearchHub, hypothes.is journal clubs,
  Episciences, Peeriodicals, Octopus, Researchers.One, Sinai Immunology
  Review Project, preprint comment sections) are recorded with
  `verification_status: pending` or `not_verifiable`.
- **Options considered:** (a) accept the exclusions and complete the
  pending verifications before approving the extraction scripts, adding `register_only` rows
  where criteria 1–3 are met (proposed); (b) leave the pending candidates as
  limitations only.
- **Decision:** (a). Accept the exclusions of ScreenIT, GigaScience,
  GigaByte and PeerJ. Complete the pending candidate verifications before
  approving the extraction scripts. Add `register_only` rows for candidates satisfying criteria
  1–3 without an adequate permitted-source selector; do not treat absence
  of machine-readable records as a substantive exclusion criterion.
- **Evidence:** `config/excluded_candidates.yaml` (per-candidate URLs).

## Q-1: Analysis cutoff

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Which analysis cutoff should be used?
- **Options considered:** 2026-09-30; 2025-12-31; another specified date.
- **Decision:** Keep `analysis_cutoff_date: 2026-09-30`. Label 2026 as
  `year_to_date`, set `partial_year: true`, and identify the exact cutoff
  in analytical output metadata.
- **Evidence:** not applicable (analysis parameter).

## Q-2: Repository URL and DOI

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** When should the public repository URL be added?
- **Options considered:** now; when the DOI is reserved, before release freeze.
- **Decision:** Add the repository URL together with the
  reserved DOI before release freeze. Omit these fields until their real values are available;
  no placeholders in `CITATION.cff`.
- **Evidence:** not applicable (release metadata decision).

## Q-3: Provisional flag

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Does confidence below high imply a provisional classification?
- **Options considered:** confidence-driven provisional status; explicit
  unresolved-ruling status.
- **Decision:** Clear `provisional` on ruling. Medium confidence alone never
  sets `provisional`; retained low or medium confidence documents uncertainty.
  D-013 explicitly retains VeriXiv's provisional status pending deposit
  confirmation. Coverage and selector readiness are separate from
  classification confidence and must not be concealed by clearing a flag.
- **Evidence:** not applicable (classification governance).

## D-027: Copernicus: hand-verified journal list and discussion-preprint selectors

- **Date:** 2026-10-20
- **Status:** decided; confirmed by user ruling, 2026-10-20
- decided_by: researcher
- **Question:** Which Copernicus journals operate interactive public peer
  review, and how are their discussion preprints selected (D-015)?
- **Method:** every journal listed on the publisher's journal index was
  checked on its own `peer_review/` page; the DOI stems on each journal's
  preprint listing page were recorded as descriptive evidence.
- **Result:** 29 journals verified as operating interactive public peer
  review (each with `evidence_url`, `verified_on` and two
  `journal_specific_doi_regex` entries); 10 journals verified as
  conventional review and listed under
  `journals_not_using_interactive_review` with their own evidence URL.
  Three DOI regimes exist: `<stem>d-<volume>-<page>-<year>` (former
  Discussions journals, 2001 onwards), `<stem>-<year>-<number>` (journal
  discussion forums) and `egusphere-<year>-<number>` (EGUsphere; all EGU
  journals from 2025-01-01, several journals earlier; journals of other
  owners keep their own stems).
- **Options considered:** (a) `register_only` until every regime can be
  attributed; (b) `quantified` with the journal-specific regimes attributed
  by DOI and an explicit EGUsphere attribution rule whose carrying field is
  confirmed in the local run; (c) count every EGUsphere preprint.
- **Decision:** (b). `register_status: quantified`, `data_status:
  machine_readable`, `selector_status: verified_journal_list`. EGUsphere also
  hosts stand-alone preprints without journal relation (community comments
  only), so an EGUsphere preprint counts only when its Crossref record is
  attributed to a verified journal (`relation.is-preprint-of` resolving to
  a verified-journal article, or the journal title in `container-title` /
  `group-title`); unattributed EGUsphere preprints are reported per year in
  the quality log (DQ-010) and never counted. (c) is rejected because it
  would count works that never entered interactive review. The attributed
  series is a lower bound in the EGUsphere regime; D-032 governs attribution
  and also accepts an incoming Crossref peer-review relation as evidence.
- **Evidence:**
  https://publications.copernicus.org/services/public_peer_review.html;
  https://www.egusphere.net/about/faqs.html; per-journal URLs in
  `config/platforms.yaml`.

## D-028: Disposition of the pending candidates (D-026)

- **Date:** 2026-10-20
- **Status:** decided; confirmed by user ruling, 2026-10-20
- decided_by: researcher
- **Question:** Which of the pending candidates satisfy inclusion criteria
  1–3 on their own websites?
- **Decision:**
  - ScienceOpen — criteria 1–3 met (post-publication public reviews of
    indexed works by named members; author-invited reviews also exist):
    new row `scienceopen_reviews`, `register_only`, `data_source: none`
    until Crossref review deposits are confirmed in a later pass.
  - Octopus — criteria 1–3 met (publish-first record with a public Peer
    Review publication type); DOIs are minted through DataCite, outside the
    permitted sources: new row `octopus`, `register_only`.
  - Peeriodicals — criteria 1–3 met (editor-selected existing works,
    solicited public reviews, published decisions; collections updated in
    2025): new row `peeriodicals`, `register_only`; previously marked
    `not_verifiable`, now verified.
  - ResearchHub — excluded, criterion 3: the platform's own pages describe
    two different workflows on the verification date (preprint-first open
    paid review versus a registered-reports journal reviewing funding
    proposals); re-assess when the documentation stabilises.
  - PubPeer — excluded, criterion 2 (user commenting, no structured output
    attributable to the service, no identifiers).
  - EMBO Early Evidence Base — excluded, criterion 2 (aggregator of
    evaluations produced by other register rows).
  - Episciences — `not_verifiable` in this pass (documentation site did not
    respond; about page silent on the review sequence).
  - Sinai Immunology Review Project — `not_verifiable` (domain does not
    resolve).
  - hypothes.is journal clubs, Researchers.One and preprint comment
    sections remain as recorded in D-026.
- **Evidence:** per-candidate URLs in `config/excluded_candidates.yaml` and
  `config/platforms.yaml`.

## D-029: Sciety retrieval: per-publisher index and group identity

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** How is each Sciety group retrieved and recognised?
- **Options considered:** (a) one full-index walk filtered locally; (b) one
  paginated walk per group with the documented
  `index?publisheraccount=<group page URL>` filter, verified locally
  against the docmap `publisher.account.id`.
- **Decision:** (b). The group page URL (`https://sciety.org/groups/<slug>`)
  is the scope key; the group id shown on each group page is stored as
  `group_id` so that docmaps are accepted under either account form.
  Publisher-account mismatches hard-fail normalisation under D-034.
  The slug of the Rapid Reviews\Infectious Diseases group is
  `rapid-reviews-covid-19` (the former slug returns 404) and was corrected.
- **Evidence:** https://sciety.org/docmaps/v1/ (endpoint documentation);
  group pages linked from `config/platforms.yaml`.

## D-030: Crossref retrieval scopes and interim attribution

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** How are Crossref walks organised for rows sharing a prefix?
- **Decision:** One cursor walk per scope `works__<prefix>__<type>`; rows
  are split from a shared scope by their DOI regex (never by bare prefix).
  Peer-review scopes include the separate review prefixes declared by rows
  (`review_doi_prefix`, for example 10.21956 for the F1000 family). A review
  record is attributed to a row by its targets (`is-review-of` DOI matching
  the row's work selector), by an explicit `review_doi_regex`, by
  `container-title`, or — for `qeios_external_works` — by targets outside
  the row prefix. Review records claimed by no row are kept in
  `crossref_peer_reviews__unattributed__<prefix>.csv`; a fourth target flag
  `missing` marks records without any `is-review-of` relation. Rows with a
  pending selector (VeriXiv) are not extracted until the selector is
  confirmed.
- **Evidence:** `src/extract/selectors.py`; `docs/data_dictionary.md` §4.

## D-031: Walk life cycle, manifests and selection

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Decision:** Every attempt (accepted or rejected) is stored before the
  next request; files are opened in exclusive-create mode so no raw file is
  ever overwritten. Walk manifests are append-only JSONL named
  `<source>__<scope>__<walk_id>.manifest.jsonl` under
  `data/manifests/<run_id>/`; a definitive 4xx (other than 429) after page
  1, or a source payload reporting an unusable cursor, closes the walk as
  `incomplete_restarted` and a new walk starts from the initial cursor (at
  most three restarts per invocation); an exhausted attempt budget closes
  the walk as `failed`. A walk left `in_progress` by an interrupted process
  is closed as `incomplete_restarted` at the next invocation, never resumed.
  Crossref completion requires terminal page evidence and the first-page
  total check (D-035); Sciety follows the separate continuation rule
  (D-034). Only complete
  walks are flattened; an interim file for a row is written only when none
  of the row's scopes is blocked, and the stage exits with an error naming
  the blocked rows. HTTP 429 and 5xx are retried with the configured
  backoff, honouring `Retry-After` and the `X-Rate-Limit-*` headers.
- **Evidence:** `src/common/{http,raw_store,manifest,walk}.py`; tests in
  `tests/test_raw_store_and_walks.py`.

## Implementation note: location of the eligibility and cell conventions

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Decision:** The cutoff rule, the event map and tie-break, the
  four-valued evaluation identity, the parent-resolution check, the
  configuration-derived `binding_publication_decision` and the cell
  conventions (blank versus zero, `not_observable` priority, partial year,
  additivity) are implemented once in `src/common/eligibility.py` and
  `src/common/aggregates.py` so that the boundary tests exercise the exact
  functions later used by `src/analyse/`.
- **Evidence:** `tests/test_eligibility_rules.py`,
  `tests/test_aggregate_conventions.py`, `tests/test_dates_cutoff.py`.

## D-032: Copernicus attribution and coverage

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Which signals attribute an EGUsphere preprint (C-1)?
- **Options:** attributed lower-bound series; all EGUsphere preprints;
  register-only fallback.
- **Decision:** attributed lower-bound series. Any of `is-preprint-of` to a
  verified journal article, a verified journal title in the record, or a
  Crossref peer-review record with `is-review-of` targeting the preprint is
  sufficient. Store all matching signals in `attribution_basis` per record.
  Pre-EGUsphere discussion DOIs are attributed by DOI pattern. Unattributed
  preprints remain in interim with `included=false` and
  `exclusion_reason=no_journal_attribution`.
- **Coverage:** `coverage_matrix` marks affected years `partial_known_scope`
  with the lower-bound limitation. The separate `partial_year` field
  retains the cutoff-year flag. Use the register-only fallback only if none
  of the three signals appears in the completed local run.
- **Implementation:** rebuild attribution after both works and review scopes
  complete; record signals, selected walks and yearly unattributed totals in
  the run manifest. An attributed interim record has blank `included`
  pending final cutoff and eligibility checks, not an automatic inclusion.
- **Authority:** C-1 ruling (user ruling, 2026-10-20); controls the attribution rule
  in D-027. The code-location note is retained without a decision number so
  D-032 through D-035 correspond to C-1 through C-4; Git history is unchanged.

## D-033: Candidate dispositions and ResearchHub reassessment

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Confirm the candidate dispositions (C-2)?
- **Options:** accept D-028; change individual candidate dispositions.
- **Decision:** accept D-028. ResearchHub remains excluded and carries
  `reassess_by: documentation_stabilised_before_release_freeze` in `config/excluded_candidates.yaml`; expose
  the optional scheduling field in the CSV export.
- **Authority:** C-2 ruling (user ruling, 2026-10-20).

## D-034: Sciety pagination and publisher integrity

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Group-filtered walk or full-index walk (C-3)?
- **Decision:** paginated walk per group using
  `publisheraccount=<group URL>`. Record the decoded query parameters,
  including that parameter, in every request sidecar. Preserve it across
  continuation pages. At the normalisation boundary, any docmap with an
  absent or different publisher account causes a hard failure, including
  docmaps without evaluation outputs; silent dropping is forbidden.
  Configured UUID and slug URLs identifying the same group are equivalent.
- **Fallback:** full-index retrieval with explicit group partitioning;
  never silently change retrieval scope after a filtered response fails.
- **Completion:** separate from Crossref. Validate every `articles` array,
  follow configured continuation links until absent/null, and require no
  unresolved `has_more` indicator. Empty pages with a continuation do not
  terminate the walk. Malformed or conflicting continuation values, endpoint
  or group changes and repeated continuation URLs fail. Continuation-field
  paths are configuration assumptions to confirm during the local run.
- **Authority:** C-3 ruling (user ruling, 2026-10-20); governs D-029.

## D-035: Crossref completion and restart budget

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Completion and restart conditions (C-4)?
- **Options:** three restarts per invocation; manual restart after each
  rejected cursor.
- **Decision:** retain the three-restart budget and immutable walk ids.
  Complete only when a page returns fewer items than requested `rows`
  (including an empty following page) AND the accepted-page item total
  equals the first page's `total-results`. An empty first page is complete
  only when `total-results == 0`. Any nonzero tolerance must be configured
  with a reason and recorded in the manifest; default tolerance is zero.
  Missing `next-cursor` is an anomaly, never completion evidence by itself.
- **Manifest:** record the rule, terminal evidence, first-page total,
  accepted item total, difference, tolerance and reason. Preserve page-level
  anomalies. Total mismatches withhold the scope and dependent rows.
- **Configuration test:** assert no `sort` with cursor pagination; runtime
  URL construction rejects that combination as well.
- **Authority:** C-4 ruling (user ruling, 2026-10-20); governs D-031. Sciety completion
  is defined independently in D-034.

---

## Decisions, 2026-10-20: normalisation, analysis and reporting

## D-036: Requirement of a qualifying evaluation is read from the register

- **Date:** 2026-10-20
- **Status:** decided (user ruling, 2026-10-20: option (c) accepted)
- decided_by: researcher
- **Question:** How does the analysis know that a posting-counted row also
  needs at least one qualifying public evaluation on or before the cutoff
  (Qeios hosted works; VeriXiv once quantified)?
- **Options:** (a) a hard-coded list of row ids in the analysis module;
  (b) a new boolean register field; (c) derive the requirement from the
  existing `eligibility_events` text with a fixed pattern and a test that
  pins the derived set.
- **Decision:** (c). `requires_evaluation()` matches `at least one
  [qualifying] [public] review|evaluation` in `eligibility_events`; rows
  counted by `earliest_qualifying_evaluation` never need the extra gate.
  `tests/test_binding_decision_consistent.py` pins the derived set to
  exactly `{qeios_hosted_works, verixiv}` by set equality and size, so any
  change to the set — additions included — fails the test until the register
  edit is reviewed and the pin is updated deliberately.
- **Authority:** instruction §9.2 (register-row event map); user ruling, 2026-10-20.

## D-037: Cross-check scopes never block a row

- **Date:** 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Does an incomplete `role: cross_check` scope (for example
  Sciety for eLife, Crossref for Rapid Reviews) withhold the row's counts?
- **Options:** (a) every scope of a row blocks; (b) only primary (counting)
  scopes block; cross-check scopes are reported separately.
- **Decision:** (b). `src/common/run_state.py` derives `extraction_status`
  from primary scopes only; the state of cross-check scopes is written to
  `analysis_manifest.json` and `normalisation_summary.json`. A cross-check
  scope that is not complete confirms nothing: evaluation identity stays
  `doi_confirmed` or `source_only`, never `cross_source_confirmed`.
- **Authority:** instruction §9.4, §9.6, §9.7.

## D-038: Group cells, blocking statuses and deduplication by earliest event

- **Date:** 2026-10-20
- **Status:** decided; amended by D-061 (group cells): `partial_coverage` members no longer blank a group cell, they are counted and named in `lower_bound_rows`.
- decided_by: researcher
- **Question:** How are class and configuration cells formed when a member
  row cannot contribute, and to which row is a work shared by several rows
  attributed in the deduplicated tables?
- **Options:** (a) sum the available rows and footnote the gap; (b) blank
  the group cell when a member row blocks it; attribute a shared work to the
  row holding its earliest counting event.
- **Decision:** (b), amended. A group cell is blank only if a member row
  whose eligible range covers the year carries `unknown_scope` or
  `pending_run` (source observability) or `partial_coverage` (coverage) for
  that year, or if that member's extraction is not complete (an incomplete
  or failed scope never contributes to any output, §9.4). `not_applicable`
  and `observed_zero` members never block the sum. Every group table carries
  a `blocking_rows` column (`row_id:status; …`) and its Markdown twin lists
  each blank cell with the blocking row and status as a footnote.
  Deduplicated tables attribute a shared work to the row holding its
  earliest counting event (ties: earlier interval start, then `row_id`); the
  all-rows table also publishes the per-class attribution used by Figure 3.
  Access Microbiology: until the first local run its years from launch
  onwards are `pending_run`, not `unknown_scope`; after a complete run the
  observed first counting year becomes `model_since` / the coverage start
  (to be written into the register, with the run recorded in the
  data-quality log) and earlier years become `not_applicable`. A complete
  run without any qualifying event leaves the row `unknown_scope`.
- **Tests:** `tests/test_total_equals_sum_of_years.py` (sum rule, blocking
  vocabulary, `not_applicable` members never blank a group,
  `partial_coverage` member blanks and is named in the footnote).
- **Authority:** instruction §6, §8.3, §9.4; user ruling, 2026-10-20.

## D-039: Vocabulary additions, including the transient `pending_run`

- **Date:** 2026-10-20
- **Status:** decided (user ruling, 2026-10-20: accepted, `pending_run` added)
- decided_by: researcher
- **Question:** What do `extraction_status` and `source_observability_status`
  say for register-only rows, for a complete scope whose coverage start is
  unresolved, and for a run-deferred coverage start before the first run?
- **Decision:** `extraction_status = not_applicable` for rows without any
  primary scope; `source_observability_status = unknown_scope` for complete
  scopes with an unresolved start and `pending_run` before the first
  complete run of such a row; `observation_status` keeps `register_only` and
  `not_applicable` as distinct values. Figure 4 draws `register_only` as its
  own category. `pending_run` is transient: the release test
  `tests/test_release_no_pending_run.py` asserts that it is absent from every
  file under `reports/tables/`.
- **Authority:** instruction §8.3, §9.4; docs/data_dictionary.md §6;
  user ruling, 2026-10-20.

## D-040: Data-quality log — single file, preset rows immutable, run rows identified

- **Date:** 2026-10-20
- **Status:** decided (user ruling, 2026-10-20: accepted with amendments)
- decided_by: researcher
- **Question:** How do observed counts reach `data_quality_log.csv`?
- **Decision:** one file. Preset rows (`origin = preset`) are never
  overwritten by a run. The analysis stage appends one row per observed
  (`row_id`, `issue_type`) with `origin = run`, the `run_id`, the selected
  `walk_id`(s) of the row's primary scopes, `status = observed` and
  `issue_id = DQ-<run_id>-<nnn>`; rows of the same `run_id` are replaced on
  re-run, rows of other runs are kept. Measured issue types:
  `placeholder_relation`, `withdrawn_record`, `missing_event_date`,
  `ambiguous_cutoff_date`, `retrospective_deposit`, Copernicus
  `partial_source_coverage`, and `other` for a coverage start resolved from
  the run. OpenAlex-based diagnostics (Q-4 / D-041) may only appear here.
- **Tests:** `tests/test_data_quality_log_single_file.py`.
- **Authority:** instruction §5.1, §8.10; user ruling, 2026-10-20.

## D-041: Overlap correspondence basis and the Gates / VeriXiv pair

- **Date:** 2026-10-20
- **Status:** applied 2026-11-02 (user ruling, 2026-10-20 on Q-4: option a;
  implemented after VeriXiv deposit confirmation, D-051, and before
  release freeze; run_20261102_01 onwards)
- decided_by: researcher
- **Question:** On what basis does `cross_platform_overlap.csv` establish
  that two rows count the same work?
- **Decision:** `canonical_work_id` equality now, recorded in the
  `correspondence_basis` column. After VeriXiv deposit confirmation and before 
  release freeze the Gates Open Research /
  VeriXiv pairs are resolved from both sides — `is-preprint-of` on the
  VeriXiv record and `has-preprint` on the Gates Open Research record —
  because reciprocal relations were partially missing from the Crossref REST
  API between November 2025 and March 2026; a pair established from either
  side counts, and the side(s) observed are recorded in
  `correspondence_basis`. OpenAlex may be used only as a diagnostic in the
  data-quality log, never as a source for `cross_platform_overlap.csv`.
- **Implementation (2026-11-02):** pairs come from Crossref relations only:
- `is-preprint-of` on the VeriXiv posted-content record and `has-preprint`
  on the Gates Open Research version-1 record. A pair asserted by either
  side counts; `correspondence_basis` records the sides observed
  (`is_preprint_of`, `has_preprint`, `is_preprint_of+has_preprint`). The
  paired work takes the article's canonical identifier on both rows and
  its evaluation relations follow it, so the preprint keeps its qualifying
  review. Row series are unchanged; the deduplicated tables count the pair
  once, on the row of its earliest counting event (while VeriXiv is
  provisional it is outside those tables, so the pair sits with the Gates
  Open Research row there); `cross_platform_overlap.csv` carries one line
  per pair. Targets outside either row's DOI pattern, non-DOI targets and
  records related to several counterparts (conflicts, logged) never pair;
  titles never pair. Declared in `extraction_selector.crossref.preprint_pair`
  on the VeriXiv row; built in `src/common/preprint_pairs.py` from
  `relation_json` of both rows' interim work records. The residual (no
  relation from either side) is the input of the OpenAlex pair signal of
  D-066, which never establishes a pair and in run_20261102_01 found none
  on the residual.
- **Evidence:** `tests/test_preprint_pairs.py` (7 tests: one side each,
  both sides, no relation with identical titles, conflict, foreign and
  non-version-1 targets); `normalisation_summary.json` → `preprint_pairs`
  (n_pairs, by_basis, n_conflicts).
- **Authority:** D-013; docs/data_dictionary.md §6; user ruling, 2026-10-20.

## D-042: Repository history starts at the first published commit

- **Date**: 2026-10-20
- **Status:** decided
- decided_by: researcher
- **Question:** Does the published repository history include the preparatory working commits made before the first local data run?
- **Options considered:** (a) publish the full working history; (b) start the published history at one consolidated initial commit and keep the working history in a private archive.
- **Decision:** b. The published history begins at the initial commit. The preparatory working history is not published and is retained outside the repository. This complements D-004: the history audit covers every published commit from the initial commit onward.
- **Evidence:** not applicable (process decision).

## D-043: MedEdPublish: records under the former prefix are retrieved through the owner prefix

- **Date:** 2026-10-26
- **Status:** decided
- decided_by: researcher
- **Question:** Works posted on the AMEE platform (2016 to November 2021) carry DOIs under 10.15694, and a Crossref query filtered by prefix 10.15694 returns no records. Are these years observable, and how is the row configured?
- **Options considered:** (a) register_only for the row; (b) coverage_start_year 2021; (c) no coverage change, because the Crossref prefix filter selects by current owner and the 10.15694 records are already retrieved within the 10.12688 scope.
- **Decision:** c. The local run holds 1,573 records under 10.15694/ within the completed works__10.12688 scopes, issued 2013–2021 (2016:166, 2017:227, 2018:302, 2019:258, 2020:332, 2021:194), and the ISSN 2312-7996 count of 2,127 is consistent with these plus the 10.12688/mep.* records. launch_year, model_since and coverage_start_year remain 2016; the 94 records of 2013–2015 predate the publish-first open-review model (2016 relaunch) and are not_applicable. The 10.15694 prefix scope is removed from the row's extraction selector as always empty; the DOI regex is unchanged. data_status is reviewed: posting records are complete for 2016 onward, so partial_coverage is replaced by machine_readable unless a reason other than the absence of AMEE-era review records is documented; the absence of review records 2016–2021 stays in the data-quality log and limitations.
- **Evidence:** https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/ (prefix = DOI owner prefix); https://www.crossref.org/blog/what-can-often-change-but-always-stays-the-same/ (DOIs keep their prefix after title transfer); https://mededpublish.org/articles/11-1 (2016 relaunch, transfer to F1000 in November 2021); local interim counts and ISSN count as stated.

## D-044: Emerald Open Research: quantified through an ISSN-based scope

- **Date:** 2026-10-26
- **Status:** decided; implementation of the version-correspondence rule for the 10.12688 launch record pending.
- decided_by: researcher
- **Question:** The platform's DOIs under 10.35241 are aliased in Crossref to primaries under 10.1108/EOR-*, registered in 2024 after re-hosting on Emerald Insight. Do the primaries preserve the original publication dates, and can the row be quantified?
- **Options considered:** (a) register_only, data_status not_machine_readable; (b) quantify through the 10.1108 primaries retrieved by ISSN, with the issued date as counting event.
- **Decision:** Decision: b. A request for an aliased 10.35241 DOI returns the 10.1108 primary; the primary keeps the original dates (example 10.1108/eor-03-2023-0018, issued 2022-11-03, created 2024-01-17; created is diagnostic only). The ISSN 2631-3952 query returns 154 records: 151 journal-article (issued 2019:19, 2020:53, 2021:30, 2022:32, 2023:17) and 3 title-level journal records, excluded by type. The row is quantified through an ISSN-based scope (issn:2631-3952, type journal-article) with selector 10.1108/eor-; coverage 2019–2023, status closed (D-014), data_status machine_readable. Counting event: the earliest issued date among the work's retrieved records (§5.1 rule); other records of the work carry record_flag later_version. One work has two records: 10.12688/emeraldopenres.13140.1 (issued 2019-06-07, relation.new_version → 10.35241/emeraldopenres.13140.2, which Crossref resolves to 10.1108/eor-03-2023-0005, issued 2019-12-09). It is counted once, at 2019-06-07, with canonical_work_id 10.1108/eor-03-2023-0005 and correspondence_basis version_stem+alias+relation; the row holds 150 unique works. For every other primary no other record is retrievable, so its own issued date is the counting event. Because a primary carries the issued date of the last original version, a work whose versions span calendar years is counted in the later year; titles carry no version tag, so the share of such works is not recoverable — recorded as a date_semantics row in the data-quality log. The title-duplicate check returned exactly one pair, the 13140 case above; no unresolved pairs remain.

 
- **Evidence:** https://community.crossref.org/t/adding-redirects-for-aliased-dois-in-the-rest-api/13138 (aliased DOI resolves to the prime record); https://www.emerald.com/eor (closure); https://api.crossref.org/works/10.35241/emeraldopenres.14791.1 and https://api.crossref.org/works?filter=issn:2631-3952&rows=0 (results as stated, retrieved 2026-10-26); https://api.crossref.org/works/10.12688/emeraldopenres.13140.1; https://api.crossref.org/works/10.35241/emeraldopenres.13140.2 (resolves to 10.1108/eor-03-2023-0005).

## D-045: Crossref completion: terminal evidence and per-scope total tolerance

- **Date:** 2026-10-26
- **Status:** decided
- decided_by: researcher
- **Question:** The first local run closed five scopes as failed. Three ended on a short non-empty page far below total-results with the total stable (10.1099 journal-article at pages 13 and 29 of 72; 10.2196 journal-article at page 20 of 44; 10.1162 journal-article at page 31 of 57). Two ended with a small total mismatch while total-results moved during the walk (10.12688 journal-article: −21 of 30,184; 10.5194 posted-content: +4 of 238,421). How are the two situations handled under D-035?
- **Options considered:** (a) treat a short page as terminal and raise the tolerance for every scope; (b) a short non-empty page is not terminal — follow next-cursor until an empty items list or an absent next-cursor — and set tolerances only for scopes whose total-results demonstrably moved; (c) split large scopes into created-date windows.
- **Decision:** b. This makes the "including an empty following page" clause of D-035 explicit and is not a change of rule. Terminal evidence is an empty items list or an absent next-cursor; short pages are recorded as page-level anomalies and counted in short_pages. Every cursor request repeats the full query with the next-cursor of the immediately preceding page. total_tolerance stays 0 by default; config/sources.yaml carries total_tolerance_overrides for works__10.12688__journal-article (50) and works__10.5194__posted-content (25), each with a reason stating that the result set is not stable during multi-minute cursor walks on the current Crossref REST API; tests/test_request_rejection.py pins exactly this set of overrides and requires a non-empty reason. The three short-page scopes completed on re-walk with delta 0 (71,761; 56,184; 43,236 records). Option c is kept in reserve for scopes that fail the total check repeatedly.
- **Evidence:** walk_end lines in data/manifests/run_20261026_01 for the five scopes named; https://community.crossref.org/t/changes-to-cursors-filtering-and-sorting-in-the-rest-api/16246 (cursor behaviour since 24 August 2026); https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/ (no next-cursor at the end of a result set).

## D-046: Emerald Open Research review records withdrawn at source
**Context:** run_20261026_01 found 150 works and 0 evaluation records for
`emerald_open_research`. The known review handle
10.21956/emeraldopenres.14208.r26506 now carries HS_ALIAS to
10.1108/EOR-03-2023-0005 (set 2025-11-19), the article's own primary DOI;
Crossref REST returns 404, `issn:2631-3952,type:peer-review` = 0, DataCite
404, and none of the 22,612 10.21956 review records carries the
`emeraldopenres` stem. 
**Decision:** the evaluation count of the row is 0 by
observation and the row carries the preset `no_review_records` entry
(DQ-013). The alias is not resolved as `has-review`: that would equate an
evaluation identifier with a work identifier. No additional scope is
declared. Limitations name the case beside MedEd Publish; the analysis-plan
rule on Emerald review attribution is qualified accordingly.

## D-047: NIHR Open Research owner prefix 10.3310; selector_no_match guard
**Context:** the row selected 10.12688/nihropenres; 10.12688/nihropenres.14023.1
returns 404. NIHR Open Research is registered under 10.3310 (ISSN 2633-4402:
522 journal-articles, 956 peer-review records), a prefix shared with the
NIHR Journals Library (3,513 journal-articles). The run published
`observed_zero` for 2021–2026 and `unique_works_to_cutoff = 0`. 
**Decision:**
(a) the selector moves to 10.3310 with a stem regex for works and reviews,
scopes `works__10.3310__journal-article` and `works__10.3310__peer-review`;
(b) a quantified row whose selector matches zero records across all its
complete scopes yields `not_observable` with
`source_observability_status = selector_no_match` and a data-quality entry,
never `observed_zero`; the row blocks every group it belongs to. The zeros
of run_20261026_01 for this row are not observations and are not committed.
Open Research Europe showed the same condition (0 work records) and is
covered by D-048.

## D-048: Review and work scopes by owner prefix: F1000Research 10.5256, Open Research Europe 10.68336 
**Context:** F1000Research review records are
deposited under 10.5256 (member 2560; 30,184 records) and were not walked.
Open Research Europe records — works 10.12688/openreseurope.* and reviews
10.21956/openreseurope.* — are owned by prefix 10.68336 (member 13904;
2,596 journal-articles, 5,198 peer-review records) and are invisible to the
10.12688 / 10.21956 owner-prefix walks; the run produced 0 works and 0
reviews for the row. 
**Decision:** the Crossref `prefix` filter selects by
current owner, not by DOI string; every row declares the owner prefixes
that hold its records. F1000Research adds `review_doi_prefix 10.5256`;
Open Research Europe uses `prefix 10.68336` for works and reviews. Review
attribution remains relation-based. The equality of 30,184 (10.5256
peer-review) and 30,184 (10.12688 journal-article in the run; 30,185 live
on 2026-10-27) is a coincidence of two unrelated populations. Rows with
ownership split across prefixes (Digital Twin, Cobot: part of the 10.21956
review records owned by 10.1080) declare every owning prefix with a stem
regex.

## D-049: Peer Community In evaluation records are journal-article records
**Context:** the 10.24072 peer-review walk is complete with 0 items.
PCI deposits recommendations, reviewer reports and decisions as
`journal-article` records in "Peer Community in …" containers
(10.24072/pci.<community>.<id>, .revNN, .dN, .arN); 3,725 of 4,374 carry
`is-review-of`. 
**Decision:** recommendation records selected by
`evaluation_doi_regex ^10\.24072/pci\.[a-z]+\.\d+$` are the row's
evaluation records; the works are their external targets. Reviewer
reports, decisions and Peer Community Journal articles are neither works
nor evaluations of the row. Evaluation records deposited under a work type
are a general selector facility (`evaluation_record_types`,
`evaluation_doi_regex`).

## D-050: JMIRx Med: no review records; companion items excluded
**Context:** `prefix:10.2196,type:peer-review` is complete with 0 items. Of the
622 journal-article records under ISSN 2563-6316, 316 are titled "Peer
Review of …" and 104 "Authors' Response to Peer Reviews of …"; the run
counted 618 works where the article population is about 202. 
**Decision:** the
row declares `no_review_records` (DQ-014) and no peer-review scope;
work-type records matching `companion_title_regex` are excluded as
`companion_item` and logged as `companion_record`. Final-article counting
is unchanged (D-016).

## D-051: VeriXiv deposit confirmed; selector enabled; D-041 scheduled
**Context:** run_20261026_01 found 314 unique 10.21956/verixiv.* review records
targeting 185 unique 10.12688/verixiv.*.n preprints, all valid, reviews
issued 2024–2026; the preprints are `posted-content` without
container-title and `works__10.12688__posted-content` is complete (922
items). 
**Decision:** D-013's condition is met. `pending_deposit_confirmation`
is lifted; the row is `quantified`, `machine_readable`, with a
stem-regex-only selector over `posted-content` and `peer-review`;
`provisional: true` remains until the first VeriXiv flattening. Review
stems differ from preprint stems, so attribution is relation-based. D-041
(Gates Open Research / VeriXiv correspondence) is scheduled before the
release freeze.

## D-052: Seven F1000-infrastructure venues enter the register as provisional rows
**Context:** 927 unattributed 10.21956 reviews target
stems absent from the register (stomiedintrelat 360, nuclscitechnolopenres
206, digitaltwin 125, molpsychol 95, materialsopenres 53, cobot 50,
bioethopenres 38); their works are in the complete 10.12688 walk,
unassigned. 
**Decision:** Stosunki Międzynarodowe – International Relations,
Nuclear Science and Technology Open Research, Digital Twin, Molecular
Psychology, Materials Open Research, Cobot and Bioethics Open Research are
added as `author_initiated` / `approval_threshold` rows with
`provisional: true`, stem regex selectors, declared review prefixes and
sample DOIs. Digital Twin is closed as a platform (2021–2025) and
continues as a conventional Taylor & Francis journal under 10.1080, which
is outside the row; because part of its records changed owner, it is
selected by ISSN scope. Venues not on the F1000 venues page (Digital Twin,
Molecular Psychology, Materials Open Research, Cobot) carry status fields
marked for confirmation. The rows leave provisional status at their first
flattening or move to `excluded_candidates` if criteria 1–3 fail on
inspection.
Statuses confirmed: three active (Stosunki Międzynarodowe, Nuclear Science and Technology OR, Bioethics OR), one closed (Digital Twin, 2021–2025), three dormant (Molecular Psychology — last new submission 2025-01-27; Cobot — 2024-11-18; Materials Open Research — 2024-06-03).

## D-053: Repeated slashes in deposited DOIs 
**Context:** three MedEd
Publish reviews 10.21956//mep.18871.r26923–r26925 target
10.15694//mep.2021.000035.1; both strings carry a double slash in
Crossref. `target_flag` was empty and the article was absent from the
interim; one 2021 work was missing. 
**Decision:** the validator flags runs of
slashes (`repeated_slash`); canonical identifiers use the collapsed form
while `source_record_id`, `work_id`, `doi_original` and `target_id_raw`
keep the deposited string; the condition is logged as `malformed_doi`
(DQ-015) and is non-blocking.

## D-054: Rapid Reviews cross-check selects reviews by DOI regex and external target
**Context:** the register prefix check found that the venue
deposits peer-review records 10.1162/2e3983f5.<hash> with `is-review-of`
→ external preprints and no container-title, while the same reports also
appear as journal-article records in "Rapid Reviews COVID-19". A
container-title selector cannot be tested on a bare target DOI; the former
prefix fallback would have claimed the review and decision records of
every other MIT Press journal (e.g. 10.1162/qss.a.493/v3/review1) and
rejected the venue's own. 
**Decision:** `record_types: [peer-review]`,
`review_doi_regex ^10\.1162/2e3983f5\.`, `target_filter: external`;
container-title selectors never fall back to a prefix test on target DOIs.
The Crossref role of the row stays `cross_check`; Sciety remains primary.

## D-055 — Audit scope excludes harvested text

- **Date:** 2026-10-27
- **Status:** decided
- decided_by: researcher
- **Question:** On the populated tree `tools/audit_text.py` reported 3,725 hits
  (R1=192, R2=2,063, R3=3, R4=1,467), all inside
  `data/processed/records_*.csv`, in titles and abstracts of harvested works;
  zero hits elsewhere; the run took 9.9 minutes. How is harvested third-party
  text treated by the audit?
- **Options considered:** (a) allow-list the affected spans; (b) a path-level
  boundary excluding harvested files; (c) leave the audit as is.
- **Decision:** b. Harvested content is third-party text that cannot be edited and
  is not the repository's own voice. `is_text_candidate` skips
  `data/processed/records_*.csv` and `data/manifests/*` (`SKIP_GLOBS`), for the
  working-tree and the history scan alike; this is a path-level boundary of
  the same kind as `data/raw` and `data/interim`, not an exemption. R1 has no
  exemptions; the private token list is reviewed so that it carries
  identifiers only, not dictionary words.
- **Evidence:** audit log of 2026-10-27 (3,725 hits before the change, 0 after);
  commit dbb648e.

## D-056: Harvested records leave the repository; a release archive per run
**Context:** `data/processed/records_*.csv`, `works_included.csv`,
`analysis_manifest.json` and `normalisation_summary.json` were never
tracked; `git add -A` after the structural fixes would have committed them.
They are third-party content of tens of megabytes per run, not the
repository's own text, and D-005 already keeps raw responses outside Git.
**Decision:** tracked: `config/`, `docs/`, `data/processed/data_quality_log.csv`
(presets and run rows), `data/manifests/` (page digests), `reports/tables/`,
`reports/figures/`, the checksums file. Release archive, one per run,
deposited on Zenodo and linked to the release: `data/processed/records_*.csv`,
`works_included.csv`, `normalisation_summary.json`, `analysis_manifest.json`,
`data/interim/*` and a copy of `data/manifests/<run_id>/`; the archive DOI
and the SHA-256 of every file go into README (Data availability) and the
checksums file. `.gitignore` lists the four processed-layer families. No
history rewrite is involved (D-004, D-042): the files were never committed.

## D-057: Windowed retrieval for `works__10.5256__peer-review` (D-045 option c)
Two shape-consistent walks of this scope on 2026-10-27 (31 non-empty pages and an
empty terminal page, no repeated cursor) accepted 30,166 and 29,992 of 30,197
records; `total-results` was stable in the first walk and moved within
[29,370; 30,197] in the second. The cursor decodes to a (timestamp, DOI) keyset,
and a yearly created-date probe sums to the unwindowed total with difference 0,
so the deficit is cursor-step loss on replica or index inconsistency, not deposit
or deletion during the walk. A tolerance (option a/b, 25 proposed) would accept
an arbitrary loss and is rejected. The scope is retrieved as date windows
instead: one cursor walk per window at tolerance 0, the unwindowed total probed
before and after the pass, and the scope complete only when every window walk is
complete and the window totals sum to both probes. Windows are issued-date
calendar quarters from 2012Q3 through the cutoff quarter with an open guard on
each side (59 windows, largest 1,426 records, two pages); created dates were
rejected because 26,752 of the records are created in 2025 and 3,445 in 2026.
The pass is recorded as one composite walk of the scope (page lines renumbered,
window provenance per line, window set and probes in the completion block) plus
one walk per window sub-scope, and judged by `check_walk_shape` with composite
rules (windows complete, partition deltas 0, no DOI on two pages across windows).
`windowed_scopes` and `total_tolerance_overrides` are mutually exclusive per
scope. `run_20261026_01` is extended, not replaced: cutoff, register and policy
are unchanged; the per-scope `software` record in the run manifest documents the
commit of each extension.
- Extended 2026-11-02 (run_20261102_01): `works__10.5194__peer-review`
  (delta −39 of 212,958) and `works__10.7554__peer-review` (delta −30 of
  84,395 against a tolerance of 25) both closed with a stable total-results,
  the cursor-step loss of this decision, and are retrieved from this run on
  as monthly issued-date windows (quarters were projected at 5,400–6,700
  and 3,200–4,700 records; the 131 and 179 monthly windows walked in this
  run hold at most 2,618 and 1,758 records, at most three non-empty pages
  each). The D-045 override for `works__10.7554__peer-review` is withdrawn: its stated cause,
  deposition during the walk, is not what the walk observed; two overrides
  remain (`works__10.12688__journal-article`, `works__10.5194__posted-content`).
  `works__10.21956__peer-review` (delta +1, total-results 22,652 → 22,653)
  is a deposition during the walk and is re-walked without a rule change.

## D-058: Source coverage of a Sciety group is verified per run; an absent group is `source_not_covering`, never a zero

- **Date:** 2026-10-28
- **Status:** decided; amended by D-061 (group cells). Source follow-up open:
  e-mail to connect@sciety.org of 2026-10-28 (unanswered on 2026-10-31) and sciety/sciety#4254 of 2026-10-31, narrowed the same day to PeerRef after Crossref routes were confirmed for MetaROR (D-064), The Unjournal (D-063) and Review Commons (D-065).
- decided_by: researcher
- **Question:** How is an empty per-group Sciety response distinguished from a group the docmaps index does not carry?
- **Options:** (a) treat as observed zero; (b) treat as `selector_no_match` (D-047); (c) verify against the unfiltered index per run and record `source_not_covering`.
- **Decision:** (c). The Sciety docmaps index lists only the groups Sciety has enabled for
docmaps, group by group (sciety/sciety#2161, #1088); eleven groups on
2026-10-28. An empty per-group response is therefore ambiguous. Each run
retrieves the unfiltered index once (scope `index__all`, stored
immutably, SHA-256 per page in the run manifest) and records for every
group scope whether the group is present and with how many docmaps
(`index_coverage`). A quantified row whose primary scopes are all Sciety
groups absent from that snapshot publishes no count: cells
`not_observable` with `source_observability_status=source_not_covering`,
group sums blocked, one data-quality row naming the snapshot. The
condition describes the source, not the platform and not the selector; a
group present in the index that yields zero items keeps
`selector_no_match` (D-047). When the index walk is incomplete, coverage
is `unverified` and D-047 applies unchanged. Alternative primary sources
for such rows are register decisions, not analysis defaults. Rule 6 of
`tools/check_walk_shape.py` reports the same condition per walk.
- **Follow-up (2026-10-31):** Crossref probes of 2026-10-31 showed that two of
  the four absent groups register their evaluations with Crossref: MetaROR
  under prefix 10.70744 (277 peer-review records, each with is-review-of,
  issued 2024-11-20 to 2026-10-15) and The Unjournal under
  10.21428/d28e8e57 (42 peer-review records with is-review-of; 13
  journal-article records without a relation). Their source question moves to
  the register (D-063 proposal; D-025 to be revised). Review Commons registers its reports under 10.15252 (EMBO Press, member 79; 5,629 peer-review records, each with is-review-of) and moves to D-065. PeerRef alone has no admissible alternative source; the condition persists until Sciety enables docmaps for the group. The request is tracked in sciety/sciety#4254, opened on 2026-10-31 and narrowed to PeerRef the same day; by the precedent of sciety/sciety#2161 (2023-03-24) enabling a group is an allowlist change.
  A reply or closure of the issue is recorded here as the status of the
  source, not as a change of any row's classification.
- **Evidence:** run_20261027_01; index snapshot 2026-10-28 ~05:10 UTC, 5,398 docmaps, 11 groups, SHA-256 a9eba43264284203fe0d0605ec22ab927a490ab281cc330a1ab19f599bc3ed77; sciety/sciety#2161, #1088. Affected rows: `metaror`, `review_commons`, `peerref`, `the_unjournal`.   sciety/sciety#2161, #1088; sciety/sciety#4254 (opened 2026-10-31);
  Crossref probes 2026-10-31 (members 9621, 51568 and 79; prefixes 10.21428,
  10.70744, 10.15252).
- **Authority:** instruction §9.4, §9.6; D-037, D-047.

## D-059: merged into D-061, not implemented separately.
Its mechanism (per-row attribution table, `svg.hashsalt`, limitation sentence) is implemented under D-061 for every group table and Figures 2, 3, 6, with one `count` column published as the lower bound and `rows_not_observable` split into `blocking_rows` and `excluded_rows`.

## D-060: Posting-record gate, alternative selector signals, eligible-range totals

Date: 2026-10-28
Status: applied
decided_by: researcher

### Context
In run_20261027_01 two first-public-posting rows counted the wrong population. eLife (`unique_works_to_cutoff` 20,877, `first_year_with_data` 2012): 16,075 journal-article-only stems are pre-model articles, not Reviewed Preprints; 4,864 stems have a posted-content record. Access Microbiology (2,268 works from 2019): the conjunctive `doi_regex` + `container_titles` selector dropped all 1,797 posted-content records (empty container-title) and admitted 1,299 conference abstracts; the D-017 run-derived start (2019) came from abstracts and pre-model articles. `register_summary` and the deduplicated group series also counted included works dated outside their rows' eligible range, while the row cells correctly carried `not_applicable`.

### Decision
(1) A first-public-posting row whose `eligibility_events` text names the record type `posted-content` admits a work only through a posted-content record; journal-article records of the same stem are later versions and never supply the counting date; a work without a posted-content record is excluded as `no_posting_record`. The rule is read from the register, never keyed on a row id; it currently gates `elife_reviewed_preprints` and `access_microbiology`. (2) For work records `doi_regex` and `container_titles` are alternative signals, as for review records; with `prefix`/`issn` alone the container-title remains the required discriminator. Access Microbiology selects by `^10\.1099/acmi\.0\.\d+(\.v\d+)?$` alone (abstracts excluded; a container-title would readmit them), `sample_work_doi` `10.1099/acmi.0.000460.v1`. (3) `register_summary.first_year_with_data`, `last_year_with_data`, `unique_works_to_cutoff`, the deduplicated group series and the overlap table cover each row's eligible range only; included works outside it are reported in `n_works_outside_eligible_range` and `works_included.in_eligible_range`. (4) eLife `coverage_start_year` and `model_since` = 2022: six Reviewed Preprint postings dated 2022 precede the January 2023 launch (pilot); the 2023 boundary is refuted by the run. Access Microbiology keeps `first_qualifying_event_year_from_completed_run`, now resolved from posted-content records only.

### Consequences
eLife ≈ 4.9k works 2022–2026 instead of 20,877; Access Microbiology ≤ 880 works from the first preprint year; early all-row and class dedup cells lose works counted outside their rows' ranges; the D-017 start is re-derived in the re-run. Rows whose `first_year_with_data` preceded the start for date reasons only (PREreview, Qeios hosted works, MedEdPublish, PCI) are unaffected in their cells; their register start years remain open register questions.
The descriptive `doi_pattern` of `access_microbiology` was tightened to `^10\.1099/acmi\.0\.\d+` in the same hunk (accepted 2026-10-30). Test `test_data_quality_row_names_the_snapshot` now filters the single-file data-quality log by the fixture `run_id` (D-040 keeps rows of other runs, so the test was sensitive to the working-tree log).

## D-061: Group cells as lower bounds; source_not_covering excluded, partial_coverage counted

- **Date:** 2026-10-30
- **Status:** applied
- decided_by: researcher
- **Context:** Finding 1 of the run_20261027_01 review: every all-rows cell 2017–2026 and most class cells were blank because `partial_coverage` members (D-038) and `source_not_covering` members (D-058) blocked the sum, although both states are known properties of the sources that no further run resolves. Two defects accompanied it: the cutoff year replaced a row's `partial_coverage` by `year_to_date` (so the 2026 group cells opened while 2025 stayed blank), and the offline fixture copied run rows of the repository data-quality log.
- **Decision:**
  - A group cell is blank only for states the pipeline can and must resolve before release: `unknown_scope`, `pending_run`, `selector_no_match`, extraction `incomplete` or `failed` (`blocking_rows`).
  - `partial_coverage` is treated exactly like `partial_known_scope`: the member is counted and named in `lower_bound_rows`; the cell is a lower bound. Amends D-038.
  - `source_not_covering` rows keep `register_status quantified` and their own cells stay `not_observable` with the D-058 note; the group cell is published without the row and names it in `excluded_rows`. Amends D-058.
  - Group `coverage`: `complete` / `year_to_date` when both lists are empty; `partial_known_scope` when that is the only lower-bound status present and nothing is excluded; otherwise `partial_coverage`. A row cell keeps its coverage status in the cutoff year; `partial_year` and `year_label` carry the year-to-date fact. The offline fixture is seeded with preset data-quality rows only.
- **Rejected:** moving the four absent Sciety rows to `register_only` (their quantified status and D-058 cells are correct); alternative sources for them in this release (Q-5).
- **Consequences:** all cells of `unique_works_all_rows_year` 2017–2026 and of the author_initiated and community_initiated class series open as lower bounds; `mixed` 2023–2026 opens without The Unjournal; `community_initiated` 2026 keeps its count and becomes `partial_coverage`. Figures 2, 3, 6 draw lower-bound cells with a dotted hatch and name the rows. New `unique_works_all_rows_by_row_year.csv`. No re-extraction.

## D-062: Gates Open Research `data_status` corrected to `machine_readable`

- **Date:** 2026-10-31
- **Status:** applied
- decided_by: researcher
- **Context:** `config/platforms.yaml` carried `data_status: partial_coverage` for `gates_open_research` without a recorded reason: D-013 defines the series boundary (v1 series to 2024) and its counting events, not a coverage gap; no decision, register note or data-quality row names one. Under D-061 the flag alone made the `author_initiated` and `approval_threshold` cells of 2017–2018 lower bounds. The 2017–2024 v1 series is complete in Crossref (508 works in run_20261027_01).
- **Decision:** `data_status: machine_readable`. The series boundary stays in `model_note` (D-013). A `partial_coverage` flag requires a recorded reason in the register or the data-quality log.
- **Consequences:** `author_initiated` and `approval_threshold` 2017–2018 become `complete`; the row leaves `lower_bound_rows` for 2017–2024. The 53 works outside the eligible range remain an open register question (series boundary), unrelated to coverage.

## D-063: The Unjournal — Crossref peer-review records are the primary source

- **Date:** 2026-10-31
- **Status:** proposed; applied at the next extraction
- decided_by: researcher
- **Question:** The Sciety group is absent from the docmaps index (D-058),
  so the row published no count in run_20261027_01. The Unjournal
  deposits its evaluations through PubPub under the shared prefix
  10.21428, stem d28e8e57, as peer-review records with is-review-of to
  external works (NBER, SSRN, AEA and others). Can Crossref carry the row?
- **Options considered:** (a) wait for the index; (b) data_source both
  with the Sciety scope as a second primary; (c) Crossref primary with
  Sciety as cross-check.
- **Decision:** (c), encoded as data_source both, extraction_selector
  crossref.role primary, sciety.role cross_check (the register's
  convention for a Crossref-primary row with a Sciety cross-check, as
  for eLife, PCI and Access Microbiology). Selector: prefix 10.21428,
  type peer-review, review_doi_regex ^10\.21428/d28e8e57\., target_filter
  external. On a shared prefix the declared review_doi_regex together
  with target_filter external is the selector; a bare prefix never is
  (D-054 lineage).   Counting event unchanged: earliest_qualifying_evaluation
  on issued. data_status partial_coverage: only evaluations deposited as
  Crossref peer-review records with is-review-of are observable (42 of
  106 records under the stem on 2026-10-31); evaluation summaries and
  manager reports deposited as journal-article records without a relation
  are outside the walk and are not counted, and evaluations published
  without a Crossref record are missed, so the series and the group cells
  it enters are lower bounds (D-061, DQ-016). coverage_start_year 2023.
  An ISSN-based scope is not possible: ISSN 3071-2173 is absent from every
  record, including the title-level record of the series. The Sciety
  scope stays as cross-check and never blocks the row (D-037).
- **Evidence:** api.crossref.org/members/9621;
  https://sciety.org/groups/the-unjournal; https://www.unjournal.org/about;
  probe of 2026-10-31 (prefix 10.21428, stem d28e8e57, 16 pages of
  14,048 prefix records): 106 records = 42 peer-review, 49 component,
  13 journal-article, 1 posted-content, 1 journal (title-level record
  10.21428/d28e8e57, created 2023-03-16, no ISSN); all 42 peer-review
  carry is-review-of -> 36 distinct external targets (10.3386: 28,
  10.2139: 7, 10.1257: 6, 10.1038/10.1080/10.3200: 1 each; by year
  2023:17 2024:12 2025:11 2026:2); 13 journal-article records without
  relation; ISSN 3071-2173 in 0 records;
  data/manifests/probes/unjournal_probe_2026-10-31.json;
  data/manifests/probes/crossref_probes_2026-10-31.txt. Request to the
  service for is-review-of on summaries and for the ISSN sent 2026-10-31.

## D-064: MetaROR — Crossref peer-review records are the primary source

- **Date:** 2026-10-31
- **Status:** proposed; applied at the next extraction
- decided_by: researcher
- **Question:** D-025 kept data_source sciety until a local run supported
  a Crossref selector. The probe of 2026-10-31 found 277 peer-review
  records under 10.70744, each with is-review-of to an external preprint,
  continuous from 2024-11-20; the Sciety group is absent from the docmaps
  index and inactive since November 2024.
- **Options considered:** (a) keep sciety and wait for the index;
  (b) data_source both with the Sciety scope as a second primary;
  (c) Crossref primary with Sciety as cross-check.
- **Decision:** (c), encoded as data_source both with
  extraction_selector.crossref.role primary and sciety.role cross_check;
  data_source crossref alone would remove the Sciety scope from the run.
  Selector: prefix 10.70744, type peer-review, review_doi_regex
  ^10\.70744/metaror\., external targets. Counting event unchanged
  (earliest_qualifying_evaluation on issued); data_status
  machine_readable; no partial_coverage; coverage_start_year 2024.
  Targets under 10.70744/metaror.placeholder are flagged
  placeholder_target, excluded from the work universe, counted in the
  data-quality log (placeholder_relation) and named in limitations: the
  reviewed manuscripts with DataCite-registered DOIs (arXiv, OSF) are
  absent from the series. The Sciety scope stays as cross-check and never
  blocks the row (D-037). Supersedes D-025.
- **Evidence:** api.crossref.org/members/51568;
  api.crossref.org/works?filter=prefix:10.70744 (278 on 2026-10-31:
  277 peer-review, 1 posted-content);
  https://metaror.org/set-of-metaror-manuscripts-with-a-datacite-doi/;
  https://sciety.org/groups/metaror; data/manifests/probes/crossref_probes_2026-10-31.txt.

## D-065: Review Commons — Crossref peer-review records are the primary source

- **Date:** 2026-10-31
- **Status:** proposed; applied at the next extraction
- decided_by: researcher
- **Question:** The Sciety group is absent from the docmaps index (D-058).
  A probe of 2026-10-31 found 5,629 peer-review records under 10.15252
  (EMBO Press, member 79), stem rc., every sampled record with is-review-of
  to a bioRxiv or medRxiv preprint, issued 2020–2026.
- **Options considered:** (a) wait for the index; (b) EEB docmaps as a
  third source; (c) Crossref primary with Sciety as cross-check.
- **Decision:** (c), encoded as data_source both, crossref primary, sciety
  cross_check. Selector prefix 10.15252, type peer-review, review_doi_regex
  ^10\.15252/rc\., external targets, sample 10.15252/rc.2023168736. Counting
  event unchanged. data_status machine_readable, no partial_coverage,
  coverage_start_year 2020; 2019 is not_applicable. issued is the
  publication date of the report package at transfer, not the date of
  review; recorded in configuration_note and limitations. Author responses
  (has-reply, same stem and type) never add a work. EEB is not admitted as
  a source: its range pages mix journal-publication docmaps with service
  docmaps (390 Review Commons docmaps for 2022–2023 against 2,020 Crossref
  report records, consistent at manuscript level; 9 PeerRef docmaps
  against roughly 35 works on the Sciety group page), and its terms of use
  are not stated. It may serve as a diagnostic only.
- **Evidence:** api.crossref.org/works?filter=prefix:10.15252,type:peer-review
  (5,629 on 2026-10-31; by year 2020:312 2021:519 2022:912 2023:1108
  2024:998 2025:1018 2026:762); api.crossref.org/members/79;
  api.crossref.org/works/10.15252/rc.2023168736;
  data/manifests/probes/crossref_probes_2026-10-31.txt;
  data/manifests/probes/reviewcommons_sample200_2026-10-31.json
  (SHA-256 7B22A6F4…76A7, data/manifests/probes/SHA256SUMS);
  data/manifests/probes/eeb_slugs_2022-2023.txt.

## D-066: OpenAlex: three permitted functions

- **Date:** 2026-11-02
- **Status:** decided; (a) and (b) applied as stage `openalex_diagnostics`,
  run_20261102_01 onwards
- decided_by: researcher
- **Question:** Which uses of OpenAlex are permitted, and where do their
  results appear?
- **Options considered:** (a) OpenAlex as a diagnostic only, results confined
  to the data-quality log (D-040, D-041); (b) OpenAlex as a secondary
  counting source for rows the two permitted sources do not cover (Q-5);
  (c) no OpenAlex use before release.
- **Decision:** a. Exactly three functions. Each diagnostic result is one row
  in `data_quality_log.csv`; nothing from OpenAlex enters `records_*.csv`,
  `works_included.csv`, any table or figure.
  - (a) Volume check. For every quantified Crossref row, the included works 
    of the run are resolved in OpenAlex by the DOI of their counting record 
    (counting_record_id; version suffix included — OpenAlex has no record for 
    a version-stripped stem) and counted per row and counting year; where
    `config/sources.yaml` lists an OpenAlex source id for the row
    (`openalex.source_ids`), the source's yearly work count is retrieved
    as well. The deltas against the row series are recorded as one run row
    per row (`issue_type: openalex_volume_check`, `status: observed`,
    `n_records_affected` = works not found in OpenAlex; 0 is a valid
    observation). A delta is a diagnostic: it never corrects a series, a
    coverage status or a register field.
  - (b) Gates Open Research / VeriXiv pair signal. For every included
    VeriXiv preprint and Gates Open Research v1 article that carries no
    Crossref correspondence after D-041 (empty `correspondence_basis`),
    the DOIs resolved under (a) are compared; when a preprint and an
    article map to one OpenAlex work id, the fact is recorded as one run
    row on the Gates Open Research row (`issue_type: openalex_pair_signal`,
    `n_records_affected` = number of such pairs; both residual sizes and
    the DOI pairs in `description`). The pair is not added to
    `cross_platform_overlap.csv`; `correspondence_basis` keeps the Crossref
    values only.
  - (c) Enrichment for the article (topics, countries, citations) is done
    outside the release pipeline on the CWTS OpenAlex dump, carries its own
    snapshot date and is not part of the 1.4.0 outputs. One preset row
    (`issue_type: other`, `status: template`, inserted with
    `tools/append_dq_rows.py`) names the snapshot date and the dump
    location once the enrichment is run; no run row exists for it, because
    no `run_id` applies.
- **Implemented 2026-11-02 (run_20261102_01).** Code 78e64cd (lookup by 
  counting-record DOI), 668b95a (--force-new-walk reaches the stage). 
  The first pass of the stage (walks w01) resolved the canonical stems 
  from work_doi and found nothing for every row with versioned DOIs; 
  its rows were discarded, the walks stay in the manifests as the trace. 
  Results come from walks w02.
  - Findings.
    - (a) Volume check, 32 rows. F1000-type rows resolve almost completely: 
      Wellcome Open Research 6 of 4 067 not found, Open Research Europe 3 
      of 1 577, F1000Research 33 of 11 964; publication year agrees with the 
      counting year in 99.9% of the found works. Rows counted on versioned 
      DOIs resolve partially: Access Microbiology 563 of 850 not found, eLife 
      reviewed preprints 209 of 4 043 — OpenAlex carries one record per work, 
      not per version. Copernicus: 67 054 DOIs requested, 66 852 works returned, 
      9 835 matched. OpenAlex answers a discussion-paper DOI with the record of 
      the merged final article (primary DOI 10.5194/acp-…, 95 of 100 on the 
      first page); the unmatched 57 219 are therefore merges, not gaps, and the 
      matched 9 835 are discussion papers without a published article. A volume 
      check for Copernicus needs the source-year counts, i.e. OpenAlex source 
      ids of the discussion journals in openalex.source_ids. The map is still 
      empty, so no row has source counts yet.
    - (b) Pair signal on the residual of D-041: 80 VeriXiv and 509 Gates Open 
      Research works resolved, 0 pairs share an OpenAlex work id. 
      OpenAlex does not merge a VeriXiv preprint with its Gates version; 
      the residual cannot be reduced from this source.
    - Follow-ups. (1) Row text for rows where the walk returned near as many 
      works as DOIs requested but few matched, naming the merge; (2) fill 
      openalex.source_ids for Copernicus discussion journals, Access Microbiology and 
      eLife if a source-level check is wanted; (3) docs/limitations.md: one 
      sentence that "not found" in the OpenAlex volume check means "no record 
      under this DOI", which for versioned and merged records is expected.
      Follow-up (2) deferred, 2026-11-02. Source-year counts add nothing for 
      F1000-type rows (the DOI resolution already finds 99.9% with the year 
      agreeing), are not comparable for Access Microbiology and eLife (the 
      OpenAlex source is the whole journal, the row counts posted-content works 
      only, D-060), and for Copernicus would repeat the merge problem: source_years 
      filters on primary_location.source.id, and a merged record's primary location 
      is the final article. A Copernicus check would need locations.source.id, 
      some 40 verified source ids for 29 journals in three DOI regimes, and would 
      still compare different objects. openalex.source_ids stays empty for 1.4.0; 
      README "Future work" keeps the item.

- **Access:** OpenAlex requires an API key since 2026-02-13 (`mailto` is
  ignored). The key is read from `PRC_OPENALEX_API_KEY`, never from a
  tracked file, and is sent in the `Authorization` header; the request
  sidecar records the header name only, and a test asserts that the key
  string is absent from every file under `data/raw/openalex`, the
  manifests, the logs and the processed layer. Rate 5 requests/s
  (configured; the API allows 30 with a key); cost 0.10 USD per 1 000
  list calls, within the 1 USD/day free budget for the volume at hand
  (≈150 k DOIs → ≈1 550 calls); hard cap
  `openalex.budget.max_requests_per_run: 4000`; a capped walk is closed as
  failed and yields no row. Raw responses go to
  `data/raw/openalex/<scope>/<run_id>/…` under D-031 (immutable, SHA-256
  per page in the walk manifest); the summary sits under
  `openalex_diagnostics` in the run manifest, not under `scopes`, so the
  row-state logic of D-037 never sees these scopes and a failed walk blocks
  nothing. The stage runs after `analyse` and must be run again after any
  re-run of `analyse`; complete walks are reused without requests.
- **Vocabulary:** two `issue_type` values in `docs/data_dictionary.md`
  (`openalex_volume_check`, `openalex_pair_signal`); `append_dq_rows.py`
  reads the enum from the dictionary. `config/sources.yaml` gains an
  `openalex` block (base URL, auth header, per-request cap 100, rate,
  budget, source-id map, pair rows, `role: diagnostic`, terms URL).
  README "Future work" item 3 and D-041 point to this entry.
- **Rejected:** (b) would make OpenAlex a counting source, contrary to the
  permitted-source rule of the analysis plan; (c) would leave D-041 without
  the residual check the limitations need.
- **Evidence:** `src/extract/openalex_diagnostics.py`;
  `tests/test_openalex_diagnostics.py` (11 tests);
  https://help.openalex.org/api/authentication/ ;
  https://help.openalex.org/access/pricing/ ;
  https://help.openalex.org/api/deprecations/ (read 2026-11-02).

## Q-4: Cross-DOI work correspondence for Gates Open Research / VeriXiv

- **Date:** 2026-10-20
- **Status:** method decided by user ruling, 2026-10-20 (option (a), both sides);
  implementation pending until the VeriXiv
  review deposit is confirmed; resolved before release freeze — see D-041
- decided_by: researcher
- **Question:** Which relation types and which source (Crossref `relation`
  on the article, on the preprint, or both) establish the correspondence,
  and is the overlap reported per work pair or per year?
- **Options:** (a) `is-preprint-of`/`has-preprint` resolved from both
  records, pair level; (b) additionally OpenAlex linkage; (c) defer until
  the VeriXiv selector is confirmed.
- **Ruling:** (a). OpenAlex only as a diagnostic in the data-quality log.

## Q-5: alternative sources for Sciety groups absent from the docmaps index

- **Date:** 2026-10-30
- **Status:** partly resolved; PeerRef open, not for this release
- decided_by: researcher
- **Question:** MetaROR, Review Commons, PeerRef and The Unjournal list evaluations on their Sciety group pages and own sites, but are absent from the docmaps index. Which admissible source, if any, would carry them, and under what register entry?
- **Decision so far:** none in 1.4.0. The rows stay `quantified` / `source_not_covering`; group cells exclude and name them (D-061).   Update 2026-10-31: Crossref selectors are available for MetaROR and The
  Unjournal (D-058 follow-up, D-063); Review Commons and PeerRef depend on
  sciety/sciety#4254.
- Update 2026-10-31: Crossref selectors adopted for The Unjournal (D-063), MetaROR (D-064) and Review Commons (D-065), all applied at the next extraction. PeerRef remains source_not_covering and depends on sciety/sciety#4254; a direct request to the service follows if Sciety declines.
