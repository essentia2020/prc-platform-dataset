# Classification scheme — PRC Platform Dataset 1.4.0

This document defines the inclusion criteria, the two classification axes,
the register-row conventions and the controlled vocabularies used in
`config/platforms.yaml`. It is the decision rule book; `docs/decisions.md`
records how each rule was applied to individual platforms.

## Definition of the PRC model

The dataset follows the definition of the Publish–Review–Curate (PRC) model
given by Corker, Waltman and Coates (2024): research works are first made
public (publish), then evaluated in the open (review), and finally curated
through recommendations, assessments or approval statuses (curate), with the
three functions decoupled from one another and from any single journal.
Platforms enter the register when their documented workflow follows this
sequence, irrespective of whether they call themselves journals, servers,
services or communities.

## Inclusion criteria (numbered)

A candidate enters the register only if it satisfies all three criteria.
`failed_criterion` in `config/excluded_candidates.yaml` refers to these
numbers.

1. **Publish-first sequence.** The research work is publicly available
   (posted or published) before, or independently of, the outcome of the
   evaluation; the evaluation does not gate the work's first public
   appearance. Conventional pre-publication peer review fails this criterion
   and is recorded as a comparator (`comparator: true`), never as a register
   row.
2. **Public evaluation or curation output.** The platform or service
   produces review reports, recommendations, assessments, approval statuses
   or curation statements that are publicly accessible and attributable to
   the platform or service.
3. **Verifiable workflow.** The publish–review–curate arrangement is
   documented on the platform's own website at the verification date and can
   be classified on both axes below, possibly with `provisional: true`.

Availability of Crossref or Sciety records is **not** an inclusion criterion.
It determines `register_status` (`quantified` / `register_only`), not
membership in the register.

## Axis 1 — who initiates the evaluation (`initiation_class`)

| Code | Class | Definition | Operational test |
|---|---|---|---|
| `author_initiated` | Author-initiated evaluation | The authors submit the work (or a preprint) to the platform and thereby request evaluation; the platform organises reviewing (invited or volunteered reviewers) only for submitted works. | Submission or posting on the platform is the only route by which a work enters evaluation; spontaneous or platform-invited reviewers of submitted works do **not** change the class. |
| `community_initiated` | Community-initiated evaluation | Reviewers, curators or the service itself select already-public works hosted elsewhere for evaluation; author consent is not a prerequisite (though authors may be notified). | The platform describes selecting or identifying works; there is no author submission route, or submission is incidental. |
| `mixed` | Mixed | Two entry routes for **works** coexist and both produce a non-trivial share of evaluations: authors can request evaluation of their work, and the community or service also selects works that were not requested. | Both an author request route and a documented selection or curator-identification route for works hosted elsewhere. Reserved for genuine dual-entry services; never a residual category. |

Decision rules applied in this release:

- Reviewer recruitment (invited, volunteered, crowd, automated invitation)
  never changes the class; only the entry route of the **work** matters.
- Authors' ability to suggest or exclude reviewers, to opt out, or to
  withdraw is a variation of author submission.
- A documented "request a review" button on a service that otherwise selects
  works is a second entry route; the class is `mixed` only if the request
  route is documented as producing evaluations, otherwise it is noted and the
  class stays `community_initiated` with a confidence below `high`.
- Transfer of a preprint from a server by the authors (for example a
  bioRxiv-to-platform transfer) is author submission.

## Axis 2 — workflow configuration (`prc_configuration`)

The second axis describes how the three PRC functions are arranged around
the evaluated work. It is independent of axis 1 and is reported separately;
the two axes are never merged into one label. The rationale for treating
workflow configuration as a separate dimension of peer-review reform is set
out in Kochetkov (2026), which I use here as the conceptual source for this
axis; the operational definitions below are specific to this dataset.

| Code | Configuration | Definition | Operational test |
|---|---|---|---|
| `core_publish_first` | Core publish-first model | The platform publishes or posts the work, organises public review and issues a curation output (assessment, recommendation, status) **without** an accept/reject decision after review. | No post-review decision that removes the work or withholds its reviewed form; every reviewed work receives its public reviews and curation output. |
| `approval_threshold` | Approval-threshold model | The work is public from submission; reviewers assign public approval statuses; a threshold on those statuses (for example two approvals) triggers indexing, a "version of record" or another formal status. | A documented numeric or categorical threshold on public review outcomes; works below the threshold remain public. |
| `hybrid_public_discussion` | Hybrid public-discussion model | A public discussion or refereeing phase on the posted work is followed by a conventional, binding editorial accept/reject decision. | Public reports or comments on the posted work **and** a binding editorial decision that determines whether a final article appears. |
| `review_or_curation_service` | Review or curation service | The service evaluates or curates works that are published or posted elsewhere; it neither hosts the work nor takes a publication decision. | Evaluation output refers to an external object (preprint or article) and the service's output is a review, recommendation, highlight or statement, not a publication. |

Decision rules applied in this release:

- `binding_publication_decision` is **derived** from the configuration
  (`hybrid_public_discussion` → true; all other configurations → false) in
  `src/analyse/`; it is never entered by hand in `config/platforms.yaml`.
- A platform with an optional, author-triggered formal step (for example a
  version of record that requires a review threshold) is classified by the
  rule that governs that step (`approval_threshold`), and the optional nature
  is recorded in `configuration_note`.
- A row whose configuration cannot be resolved from the platform's own
  documentation keeps `provisional: true`, is excluded from
  configuration-stratified aggregates and is listed as an open question.
- Clear `provisional` when a classification ruling is made; medium or low
  confidence alone does not set it. D-013 explicitly retains the VeriXiv
  flag until Crossref review deposits are confirmed.
- JMIRx Med is `core_publish_first` (medium), `overlay_journal`, by D-016:
  no public discussion precedes its decision. This row-specific ruling
  qualifies the general definition above; the configuration-derived
  `binding_publication_decision` is not an independent observation of
  whether an editorial acceptance decision exists.
- SciPost counts final articles. Copernicus counts discussion preprints
  entering public discussion for hand-verified journals; rejected
  discussion preprints are not categorically invisible in that series.

## Register rows are observation series

A register row is an **observation series** defined by one organisation, one
counting event and one extraction selector. One organisation may own several
rows (for example two Qeios rows, linked by `organisation_id = qeios`) when
different counting events are observed. Series are comparable over time
within a row, never between rows, and rows of one organisation are never
summed.

Each row declares its event map:

| Field | Meaning |
|---|---|
| `launch_year` | Year the platform (or the relevant service) started operating. |
| `model_since` | Year from which the classified model applies; `null` while unresolved, including a run-derived start under D-017. |
| `model_note` | Documented workflow or venue changes and decisions; site-renaming history is recorded here. |
| `coverage_start_year` | First eligible observation year; may be unset only with an explicit run-derived policy, never interpreted as zero. |
| `coverage_end_year` | Last year of the series; `null` for an open series ending at `analysis_cutoff_date`. |
| `data_source` | `crossref` / `sciety` / `both` / `none`. |
| `eligibility_events` | Event(s) a work must have, dated on or before the cutoff and present in the completed retrieval, to be included. |
| `counting_event` | `first_public_posting` / `earliest_qualifying_evaluation` / `final_article`. |
| `counting_event_date_field` | Source date field(s), in priority order, used for the counting event. |
| `extraction_selector` | Crossref owner prefix and/or journal ISSN, record types and DOI patterns and/or Sciety group slug used by `src/extract/`. An `issn` selector is used where the Crossref `prefix` filter (current owner) does not isolate the row; it always comes with a `doi_regex`. |
| `register_status` | `quantified` (reproducible selector and qualifying records) / `register_only` (eligible, but no adequate machine-readable selector). |

Initial mandatory event rules:

| Register row type | Eligibility event(s) | Counting event |
|---|---|---|
| Hosted publish-first work | Public posting and any additional row-specific condition | First public posting |
| Qeios hosted works | First public posting plus at least one qualifying review | First public posting |
| VeriXiv | First preprint posting plus at least one qualifying public review | First preprint posting |
| Gates Open Research | v1 publication in the series ending 2024 | v1 publication |
| External review service, including Qeios external works | Qualifying public evaluation of an already-public target | Earliest qualifying evaluation |
| Sciety review or curation service | Qualifying docmap evaluation output | Earliest qualifying evaluation output |
| SciPost | Published work that underwent the public-refereeing workflow | Final article `issued` date |
| Copernicus interactive review | Entry into public discussion for a hand-verified journal | Discussion-preprint posting |
| MedEd Publish | Eligible version-1 or base posting | First posting / base-record `issued` date |

## Evidence fields (per row)

| Field | Values | Meaning |
|---|---|---|
| `prc_role` | `integrated_platform` / `review_service` / `curation_service` / `overlay_journal` | Functional role of the row's organisation. |
| `publish_arrangement`, `review_arrangement`, `curation_arrangement` | `platform_own` / `external_preprint_server` / `partner_journal` / `none` / `unknown` | Who performs each PRC function for the works in this row. |
| `output_types` | subset of `reviewed_preprint`, `version_of_record`, `recommendation`, `review_report`, `approval_status`, `assessment_statement`, `highlight` | Public outputs produced by the row. |
| `public_review_reports` | `true` / `false` / `unknown` | Full review texts are public. |
| `approval_status_public` | `true` / `false` / `unknown` | A per-work approval or recommendation status is public. |
| `summary_assessment` | `true` / `false` / `unknown` | An editorial summary statement (assessment, recommendation text) is public. |
| `reviewer_identity_disclosed` | `always` / `optional` / `never` / `unknown` | Whether reviewer names are published. |
| `version_linked_review` | `true` / `false` / `unknown` | Reviews are tied to a specific version of the work. |
| `review_to_object_relation` | `crossref_is_review_of` / `sciety_docmap` / `both` / `none` / `unknown` | Machine-readable link from evaluation to work. |
| `public_author_response` | `true` / `false` / `unknown` | Authors' responses are published alongside reviews. |
| `review_has_doi` | `true` / `false` / `unknown` | Evaluation outputs receive DOIs. |
| `data_status` | `machine_readable` / `not_machine_readable` / `defunct` / `partial_coverage` | Reason behind `register_status`; required when `register_only`. |
| `status` | `active` / `dormant` / `closed` | Operating status at `verified_on`. |
| `evidence_url`, `verified_on` | URLs; ISO date | Platform-website evidence and access date. |

`unknown` is permitted wherever the platform's documentation is silent;
values are never inferred from third-party descriptions. Recognition fields
use a single column each; `_policy` / `_observed` pairs are introduced only
if both concepts are collected and approved by an explicit user ruling.

## Confidence levels

`classification_confidence` and `configuration_confidence` take `high`,
`medium` or `low`:

- `high` — the platform's own documentation states the entry route (axis 1)
  or the decision structure (axis 2) unambiguously.
- `medium` — the documentation supports the class but leaves one material
  element implicit (for example the share of each entry route, or whether a
  formal step is optional); the note column states the gap.
- `low` — the documentation is contradictory or silent on a defining
  element; the class is a best reading and is listed as an open question.

Every `medium` or `low` assignment has a reason in `classification_note` or
`configuration_note` and an entry in `docs/decisions.md`. An approved
assignment retains that confidence without remaining provisional.

## Controlled vocabularies

The vocabularies above are declared once more, machine-readably, in the
`register_meta` block of `config/platforms.yaml`; `src/common/register.py`
rejects any row whose values fall outside them. `discipline_scope` uses
`life_sciences`, `physical_sciences`, `social_sciences`, `metaresearch`,
`multidisciplinary` (extendable only through `register_meta`). `country_of_operator` is free
text (the country of the operating legal entity).

## Reference

Corker, K. S., Waltman, L., & Coates, J. (2024). Understanding the
Publish-Review-Curate (PRC) Model of Scholarly Communication. MetaArXiv.
https://doi.org/10.31222/osf.io/h7swt

Kochetkov, D. (2026). Peer Review at the Crossroads. Learned Publishing,
39(2), e2046. https://doi.org/10.1002/leap.2046
