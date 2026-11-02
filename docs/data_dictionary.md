# Data dictionary — PRC Platform Dataset 1.4.0 (schema)

This document defines every file family of the dataset: file-name pattern,
one line per column with name, type, allowed values, source field and an
example. It describes the schema only; values are produced by the local
pipeline run.

Conventions: CSV files are UTF-8, comma-separated, LF line endings, header
row, `""` for missing values (never the literal string `null`); booleans are
`true` / `false`; dates are ISO-8601 (`YYYY-MM-DD`), timestamps ISO-8601 UTC
(`YYYY-MM-DDTHH:MM:SSZ`). Every analytical table carries a header comment
line `# snapshot: <run_id>, cutoff <analysis_cutoff_date>, additivity <…>`.

## 1. Source register (`config/sources.yaml`)

| Source | Endpoint | Filters | Licence / terms | Rate limit | Coverage limits | Reproducibility |
|---|---|---|---|---|---|---|
| Crossref REST API | `https://api.crossref.org/works` | `prefix:<doi_prefix>`, `type:journal-article` / `posted-content` / `peer-review`; cursor pagination, `rows=1000`, `mailto` polite pool | metadata reusable without restriction (see `licence_url` in `config/sources.yaml`) | polite pool; honour `Retry-After` and rate-limit headers | only Crossref-registered DOIs; `peer-review` only where deposited with `is-review-of`; member-supplied dates of year/month/day precision | current index state; raw store + manifests fix a run |
| Sciety docmaps | `https://sciety.org/docmaps/v1/index` | by group (`publisheraccount`) where supported | open; evaluation texts stay with the groups | 1 request/s | only groups that joined Sciety, from their join date | current state; full index stored per run |
| OpenAlex API (diagnostic only, D-041, D-066) | `https://api.openalex.org/works` | `filter=doi:<a>|<b>|…` (at most `per_request_cap` = 100 DOIs per request, `select` of four fields); `filter=primary_location.source.id:<S…>&group_by=publication_year` | CC0 metadata; API key required since 2026-02-13, read from `PRC_OPENALEX_API_KEY` and sent in a header, never stored | `rate_limit.max_requests_per_second` (5; the API allows 30 with a key) and `budget.max_requests_per_run` (hard cap, 4 000) | OpenAlex's own ingestion state; a DOI absent there is a diagnostic observation, never a correction | current index state; responses stored immutably per run; nothing enters a record file, table or figure — results are rows in `data_quality_log.csv` only |

## 2. Register tables

### 2.1 `config/platforms.yaml` → `config/platforms.csv`

One line per register row (observation series). Lists are joined with `; `;
`extraction_selector` is compact JSON.

| Column | Type | Allowed values | Example |
|---|---|---|---|
| `row_id` | string (snake_case, unique) | — | `qeios_hosted_works` |
| `row_label` | string | — | `Qeios — hosted works` |
| `organisation_id` | string | — | `qeios` |
| `organisation_name` | string | — | `Qeios Ltd` |
| `prc_role` | enum | `integrated_platform`, `review_service`, `curation_service`, `overlay_journal` | `integrated_platform` |
| `status` | enum | `active`, `dormant`, `closed` | `active` |
| `launch_year` | integer | 1990–2100 | `2019` |
| `model_since` | integer or empty | year | `2023` |
| `model_note` | string or empty | workflow, site-renaming or venue-change notes | D-012 site-renaming note |
| `coverage_start_year` | integer or empty | ≥ `launch_year`; empty requires explicit run-derived policy | `2019` |
| `coverage_end_year` | integer or empty | empty = open series to cutoff | `` |
| `discipline_scope` | enum | `life_sciences`, `physical_sciences`, `social_sciences`, `metaresearch`, `multidisciplinary` | `life_sciences` |
| `country_of_operator` | string | free text | `United Kingdom` |
| `initiation_class` | enum | `author_initiated`, `community_initiated`, `mixed` | `author_initiated` |
| `classification_confidence` | enum | `high`, `medium`, `low` | `medium` |
| `classification_note` | string | — | — |
| `prc_configuration` | enum | `core_publish_first`, `approval_threshold`, `hybrid_public_discussion`, `review_or_curation_service` | `approval_threshold` |
| `configuration_confidence` | enum | `high`, `medium`, `low` | `medium` |
| `configuration_note` | string | — | — |
| `provisional` | boolean | — | `false` |
| `publish_arrangement`, `review_arrangement`, `curation_arrangement` | enum | `platform_own`, `external_preprint_server`, `partner_journal`, `none`, `unknown` | `platform_own` |
| `output_types` | list | `reviewed_preprint`, `version_of_record`, `recommendation`, `review_report`, `approval_status`, `assessment_statement`, `highlight` | `review_report; version_of_record` |
| `public_review_reports`, `approval_status_public`, `summary_assessment`, `version_linked_review`, `public_author_response`, `review_has_doi` | tri-state | `true`, `false`, `unknown` | `true` |
| `reviewer_identity_disclosed` | enum | `always`, `optional`, `never`, `unknown` | `always` |
| `review_to_object_relation` | enum | `crossref_is_review_of`, `sciety_docmap`, `both`, `none`, `unknown` | `crossref_is_review_of` |
| `data_source` | enum | `crossref`, `sciety`, `both`, `none` | `crossref` |
| `register_status` | enum | `quantified`, `register_only` | `quantified` |
| `data_status` | enum | `machine_readable`, `not_machine_readable`, `defunct`, `partial_coverage` | `partial_coverage` |
| `doi_prefix` | string or empty | Crossref prefix | `10.32388` |
| `doi_pattern` | regex or empty | selects the row's DOIs | `^10\.32388/` |
| `doi_version_pattern` | regex or empty | group 1 = canonical stem | `^(10\.32388/[a-z0-9]+)(?:\.\d+)?$` |
| `sciety_group_slug` | string or empty | slug in `https://sciety.org/groups/<slug>` | `prereview` |
| `extraction_selector` | JSON | keys `crossref` and/or `sciety`; `crossref` holds `prefix` (owner prefix or list) and/or `issn` (journal ISSN; requires `doi_regex` or `container_titles`), `record_types`, optional `scope_keys` (record type → `prefix`/`issn`, required when both keys are declared; peer-review scopes are always prefix-based), `doi_regex`, `container_titles` (for work records the two are alternative signals, as for review records: a DOI matching `doi_regex` is in scope whatever its container-title, a record under the walked prefix or ISSN whose container-title is listed is in scope whatever its DOI; with `prefix`/`issn` alone the container-title is the required discriminator — D-060), `review_doi_prefix` (prefix or list of owner prefixes walked for review records), `review_doi_regex`, `evaluation_record_types` with `evaluation_doi_regex` (evaluation records deposited under a work type, e.g. PCI recommendations as `journal-article`), `companion_title_regex` (work-type records that are review reports or author responses, excluded as `companion_item`), `sample_work_doi`, `sample_review_doi` (one known DOI each for `tools/check_register_prefixes.py`), `journals`, `target_filter`, `notes` | `{"crossref":{…}}` |
| `eligibility_events` | list | free text per event | `first public posting; ≥1 qualifying review` |
| `counting_event` | enum | `first_public_posting`, `earliest_qualifying_evaluation`, `final_article` | `first_public_posting` |
| `counting_event_date_field` | string | source field priority | `posted -> issued` |
| `evidence_url` | list of URLs | platform's own pages | `https://www.qeios.com/publishing-policy` |
| `verified_on` | date | — | `2026-10-20` |

`extraction_selector.coverage_start_policy =
first_qualifying_event_year_from_completed_run` permits an unset start
for Access Microbiology under D-017. It blocks eligible-range zero filling
until qualifying events resolve the start; `model_since` is not inferred
from the journal's launch year.

An extraction selector with `selector_status: pending_deposit_confirmation`
or `pending_journal_verification` cannot have `register_status: quantified`.
For Copernicus, `extraction_selector.crossref.journals` is the hand-verified
list: each entry must contain `evidence_url`, `verified_on`, and
`discussion_selector`. `candidate_journal_titles` is not an executable
filter. The VeriXiv review deposit was confirmed in run_20261026_01
(D-051); the row stays `provisional: true` until its first flattening.

A quantified Crossref row whose selector matches zero records across all
of its complete scopes publishes no count: every cell is `not_observable`
with `source_observability_status=selector_no_match` and the run appends a
`selector_no_match` data-quality row (D-047). The condition marks a
selector defect (owner prefix, pattern or record type), not an observed
zero. `tools/check_register_prefixes.py` compares the declared scopes with
the Crossref prefix and member of `sample_work_doi` / `sample_review_doi`
before an extraction.

A quantified Sciety row is subject to a second check (D-058). The Sciety
docmaps index lists only the groups Sciety has enabled for docmaps, so an
empty per-group response is ambiguous on its own. Each run walks the
unfiltered index once (scope `index__all`) and records per group scope
whether the group is present in that snapshot (`index_coverage`, §3.3). A
row whose primary scopes are all Sciety groups absent from the snapshot
publishes no count: every cell is `not_observable` with
`source_observability_status=source_not_covering` and the run appends a
`source_not_covering` data-quality row naming the snapshot. The condition
marks a source that does not carry the group, not a selector defect and
not an observed zero; a group present in the index that yields zero items
keeps `selector_no_match`. When the index walk is not complete, coverage is
`unverified` and the D-047 rule applies unchanged. A row whose primary
source is Crossref and whose Sciety group is a cross-check only (The
Unjournal since D-063, MetaROR since D-064, Review Commons since D-065;
`data_source = both`) records the absent group as `not_in_index` on the cross-check scope and is observable through
its Crossref scopes; a cross-check never blocks a count (D-037).

A `review_doi_regex` declared together with `target_filter: external` is
the row's selector on a shared prefix: a `peer-review` record under the
walked prefix that does not match the pattern is not the row's, whatever
its target (D-063; the Unjournal stem `d28e8e57` under the PubPub prefix
10.21428, the Rapid Reviews stem under the MIT Press prefix 10.1162, the
Review Commons stem `rc.` under the EMBO prefix 10.15252). Author
responses deposited as `peer-review` records with `is-reply-to` and the
same `is-review-of` target (Review Commons) are evaluation records of the
row; they share the target with the referee reports and never add a work.

A first-public-posting row whose `eligibility_events` text names the
record type `posted-content` admits a work only through a posted-content
record (D-060; read from the register as the review requirement of D-036
is, never keyed on a row id). Journal-article records of the same stem
(accepted versions, versions of record) stay in the work and never supply
its counting date; a work with no posted-content record is excluded as
`no_posting_record`. The gate separates eLife Reviewed Preprints from the
journal's pre-model articles and Access Microbiology preprints from
articles published before the preprint model; rows whose postings are
deposited as `journal-article` (F1000-style version 1, Copernicus
discussion papers) do not name the type and are not gated.

`extraction_selector.crossref.work_correspondences` holds explicit
record-level correspondences: `primary_doi`, `alias_doi`, `version_stem`,
`version_relation` (`from_doi`, `to_doi`, `type`, `asserted_by`),
`correspondence_basis` and `evidence_urls`. Each entry documents a
version-relation edge to an aliased DOI and its primary; only those
explicitly listed identifiers map to that primary. No title matching,
network lookup or event-date imputation is performed by this mapping.

`extraction_selector.crossref.preprint_pair` (on a preprint row; D-013,
D-041) names the row that publishes the Version of Record
(`article_row`) and the Crossref relation read on each side
(`relation_from_preprint`, default `is-preprint-of`, on this row's
`posted-content` records; `relation_from_article`, default `has-preprint`,
on the article row's records of version `article_version`, default 1). A
pair asserted by either side counts; a target that matches neither row's
`doi_regex`, a non-DOI target and a record related to several
counterparts (conflict, logged by the normalisation stage) never pair.
The paired work takes the article's canonical identifier on both rows
(`canonical_work_id`, `work_doi`), and `correspondence_basis` records the
side(s) observed: `is_preprint_of`, `has_preprint` or
`is_preprint_of+has_preprint`. Row series are unchanged; the deduplicated
tables count the pair once, on the row of its earliest counting event, and
`cross_platform_overlap.csv` carries one line per pair. Titles never pair,
and OpenAlex is never consulted for pairing.

### 2.2 `config/excluded_candidates.yaml` → `config/excluded_candidates.csv`

| Column | Type | Allowed values | Example |
|---|---|---|---|
| `candidate_id` | string | unique | `peerj` |
| `candidate_name` | string | — | `PeerJ` |
| `operator` | string | — | `PeerJ Inc.` |
| `candidate_type` | string | free text | `journal_transparent_review` |
| `failed_criterion` | integer or empty | `1`, `2`, `3`; empty while pending | `1` |
| `comparator` | boolean | `true` only with `failed_criterion = 1` | `true` |
| `verification_status` | enum | `verified`, `pending`, `not_verifiable` | `verified` |
| `reason` | string | — | — |
| `machine_readable_source` | enum | `crossref`, `sciety`, `none` | `sciety` |
| `evidence_url` | list of URLs | — | — |
| `verified_on` | date | — | `2026-10-20` |

## 3. Raw layer (`data/raw/`, outside Git) and manifests (`data/manifests/`, tracked)

```
data/raw/crossref/<scope>/<run_id>/<walk_id>/page_<n>/attempt_<k>.response.json.gz
data/raw/crossref/<scope>/<run_id>/<walk_id>/page_<n>/attempt_<k>.request.json
data/raw/sciety/<scope>/<run_id>/<walk_id>/page_<n>/attempt_<k>.response.json.gz
data/raw/sciety/<scope>/<run_id>/<walk_id>/page_<n>/attempt_<k>.request.json
data/raw/openalex/<scope>/<run_id>/<walk_id>/page_<n>/attempt_<k>.response.json.gz   # diagnostic (D-066)
data/raw/openalex/<scope>/<run_id>/<walk_id>/page_<n>/attempt_<k>.request.json
data/manifests/<run_id>/<run_id>.json                                   # run-level manifest
data/manifests/<run_id>/<source>__<scope>__<walk_id>.manifest.jsonl     # walk manifest
data/manifests/probes/<name>_<date>.{json,txt}                          # one-off probe outputs cited as evidence
data/manifests/probes/SHA256SUMS                                        # checksums of the probe files
```

`scope` = `works__<prefix>__<record_type>` (Crossref; one walk per owner
prefix and record type, shared by every row declaring that prefix) or
`works__issn_<issn>__<record_type>` (Crossref; one walk per journal ISSN
and record type, for rows whose records are owned by a shared prefix or
whose original DOIs are aliases of re-registered primaries) or
`evaluations__<group_slug>` (Sciety; one paginated walk per group) or
`index__all` (Sciety; the unfiltered docmaps index, one walk per run as the
coverage probe of D-058) or `works_by_doi__<row_id>` / `source_years__<row_id>`
(OpenAlex, D-066; one walk per register row, each page one batch of at
most 100 DOIs or one `group_by` response; completion rules
`openalex_batches_exhausted` and `openalex_group_by_single_page`; the
request sidecar records the authorisation header name with the value
redacted). The Crossref `prefix` filter selects by current owner prefix, so records that
changed owner with a title transfer appear under the acquiring member's
prefix while keeping their DOI string; the row's `doi_regex` decides
membership, never the bare prefix.
Nothing under `data/raw/` is ever overwritten (files are created in
exclusive mode); retries increment `attempt_<k>`; a rejected cursor or an
interrupted walk starts a new `walk_id` from the first page.

`data/manifests/probes/` holds one-off probe outputs that decision entries
cite by file name (API responses, sampled records, slug counts of a range
walk). The files are kept byte for byte as retrieved — including a byte
order mark or CRLF line ends where the retrieving shell wrote them — because
`docs/decisions.md` records their SHA-256; `.gitattributes` exempts
`data/manifests/**` from end-of-line normalisation, and `SHA256SUMS` in the
directory lists the expected digests (checked by the test suite). Probe
files are evidence for a decision, not inputs to any pipeline stage.

### 3.1 Request sidecar `attempt_<k>.request.json`

| Field | Type | Meaning |
|---|---|---|
| `url` | string | full request URL (query included) |
| `headers` | object | request headers (`User-Agent`, `Accept`) |
| `cursor_in` | string | cursor sent (`*` for the first page) |
| `page` | integer | page number within the walk |
| `attempt` | integer | attempt number for this page |
| `sent_at_utc` | timestamp | — |
| `run_id`, `walk_id`, `source`, `scope` | string | identity of the walk |
| `response_status`, `response_headers`, `error` | diagnostics | status and headers of this attempt; transport error text when no response was received |
| `parameters` | object | decoded URL query parameters as arrays; includes `publisheraccount` on every group-filtered Sciety page |

### 3.2 Walk manifest `<source>__<scope>__<walk_id>.manifest.jsonl` (one JSON object per line)

Every line carries the identity fields and a `record` kind: `walk_header`
(first line), `page` (one per accepted page, fields below),
`rejected_attempt` (`page`, `attempt`, `http_status`, `reason`,
`response_path`, `sha256` of the stored rejected response) and `walk_end`
(terminal line: `walk_state`, `reason`, `pages_accepted`, `items_total`,
`ended_at_utc`, `completion`). An `anomaly` line records `code` and `page`.
For Crossref, `short_page` records each non-empty page with fewer items than
requested, including `items_in_page` and `rows`; it is also logged as a
`short_page` event. A continuation on such a page is followed regardless of
whether the running item total already matches. `missing_next_cursor`
remains an anomaly, including on a terminal page.
Crossref `completion` records `rule`, `terminal_evidence` (`empty_page` or
`no_next_cursor`; neither bypasses the item-total check),
`first_page_total_results`, `last_page_total_results`,
`total_results_moved_during_walk` (true when `total-results` took more than
one value across the accepted pages, i.e. the index changed while the walk
ran), `accepted_items_total`, `total_delta`, `total_tolerance`,
`tolerance_reason` (the source-wide values from `config/sources.yaml`, or
the scope's entry in `total_tolerance_overrides`). Each cursor request
repeats the original filter, rows, select and mailto parameters and uses
the `next-cursor` of the immediately preceding response, as required by the
[Crossref cursor notice](https://community.crossref.org/t/changes-to-cursors-filtering-and-sorting-in-the-rest-api/16246).
Sciety uses
`rule=sciety_continuation_exhausted` without a Crossref total requirement.
A manifest without a `walk_end` line is `in_progress` and
is closed as `incomplete_restarted` by the next invocation.

A scope listed in `pagination.windowed_scopes` (D-057) is recorded as one
*composite* walk of the scope with `rule=crossref_windowed_total_checked`
plus one ordinary walk per window sub-scope
`<scope>__<date_field>_<from>_<until>` (`min` / `max` for the open guard
windows) and two `rows=0` probes stored under `<scope>__probe` (page 1
before, page 2 after the pass). The composite's page lines are the window
pages renumbered from 1 and carry `window`, `window_walk_id` and
`window_page` in addition to the fields below; `response_path` points at
the window's raw files. Its `completion` records `date_field`,
`granularity`, `window_count`, `windows` (per window: `label`, `from`,
`until`, `scope`, `walk_id`, `state`, `first_page_total_results`,
`accepted_items_total`, `pages`, `total_delta`, `reason`), `probe_before`
and `probe_after` (`response_path`, `sha256`, `total_results`, `url`,
`requested_at_utc`), `unwindowed_total_before`, `unwindowed_total_after`,
`sum_of_window_totals`, `partition_delta_before`, `partition_delta_after`,
and the single-walk keys (`first_page_total_results` = probe before,
`last_page_total_results` = probe after, `accepted_items_total`,
`total_delta`, `total_results_moved_during_walk`, `total_tolerance` = 0,
`terminal_evidence` = `all_windows_terminal`). The composite is `complete`
only when every window walk is complete and `sum_of_window_totals` equals
both probes; otherwise it is `failed` and the reason names the window(s)
or the partition difference.

| Field | Type | Allowed values | Meaning |
|---|---|---|---|
| `run_id`, `walk_id`, `scope`, `source` | string | `source`: `crossref` / `sciety` | identity of the walk |
| `page` | integer | ≥ 1 | page number |
| `accepted_attempt` | integer | ≥ 1 | attempt whose response was accepted |
| `response_path` | string | relative to the raw store root | `crossref/works__scipost/run_x/w01/page_3/attempt_1.response.json.gz` |
| `sha256` | string | 64 hex chars | digest of the accepted response bytes |
| `bytes` | integer | — | size of the accepted response |
| `http_status` | integer | — | — |
| `cursor_in`, `cursor_out` | string | — | pagination state (`cursor_out` empty on the last page) |
| `items_in_page` | integer | — | number of records in the page |
| `accepted_at_utc` | timestamp | — | — |
| `walk_state` | enum | `in_progress`, `complete`, `incomplete_restarted`, `failed` | `in_progress` on page lines; terminal state on the `walk_end` line |

Selection among walks of one scope follows `selected_walk_policy`
(`latest_completed_then_smallest_walk_id`): the complete walk with the
latest `ended_at_utc`, ties broken by the smallest `walk_id`; scopes
without a complete walk have `extraction_status` `incomplete` or `failed`.

### 3.3 Run-level manifest `<run_id>.json`

| Field | Type | Meaning |
|---|---|---|
| `run_id` | string | — |
| `analysis_cutoff_date` | date | copied from `config/run.yaml` at run start |
| `retrieval_started_at`, `retrieval_finished_at` | timestamp | actual retrieval window |
| `selected_walk_policy` | string | from `config/run.yaml` |
| `scopes` | object | keyed `<source>/<scope>`; per scope: `walk_ids` (all), `walk_states`, `selected_walk_id`, `selection_reason`, `extraction_status` (`complete` / `incomplete` / `failed`), `completed_at`, `pages`, `items`, `completion`, `anomalies`, `recorded_at`, `software` (as below, in effect when the entry was written); a windowed scope (D-057) adds `window_set` (`date_field`, `granularity`, `first_window_start`, `reason`, `windows`) and each window sub-scope has its own entry with `window_of` and `window`; a Sciety group scope adds `index_coverage` (`status`: `in_index` / `not_in_index` / `unverified`, `docmaps_in_index`, `docmaps_walked`, `index_walk_id`, `index_retrieved_at`; D-058) and the probe scope `sciety/index__all` carries `role: coverage_probe` |
| `sciety_index_snapshot` | object | written by the Sciety stage when the index walk is complete (D-058): `scope`, `walk_id`, `retrieved_at`, `pages`, `docmaps_total`, `page_sha256` (one digest per stored page), `groups` (docmaps per `publisher.account.id` as served, register groups and others alike) |
| `openalex_diagnostics` | object | written by the OpenAlex diagnostics stage (D-066): `role: diagnostic`, `scopes` (per OpenAlex scope: `walk_id`, `state` `complete` / `reused` / `failed`, `reason`, `pages`, `requests`, `sha256` of every stored page), `rows_written`, `requests_used`, `request_cap`, `recorded_at`. OpenAlex scopes are not listed under `scopes` and never set a row's `extraction_status` (D-037) |
| `software` | object | recorded at run start: `python`, `implementation`, `platform`, `executable`, `git_commit` and `git_worktree` (`clean` / `dirty`; `unavailable` when the working copy is not a Git repository). A run extended by later invocations may have been written under several commits; the per-scope `software` field records which |

## 4. Interim layer (`data/interim/`, outside Git)

### 4.1 `crossref_works__<row_id>.csv`

| Column | Type | Source field | Example |
|---|---|---|---|
| `doi` | string | `DOI`, lowercased | `10.32388/abc123.2` |
| `doi_original` | string | `DOI` as returned | `10.32388/ABC123.2` |
| `type` | string | `type` | `posted-content` |
| `title` | string | `title[0]` | — |
| `prefix` | string | `prefix` | `10.32388` |
| `member` | string | `member` | `19384` |
| `container_title` | string or empty | `container-title[0]` | — |
| `created`, `deposited`, `indexed` | timestamp | `*.date-time` | diagnostics only |
| `issued`, `posted`, `published_online`, `published_print` | partial date | `*.date-parts[0]` as `YYYY`, `YYYY-MM` or `YYYY-MM-DD` | `2023-05` |
| `relation_is_review_of` | string | `relation.is-review-of[*].id` joined by `; ` | — |
| `doi_flag` | enum or empty | `repeated_slash` when the deposited DOI contains `//`; `doi` holds the collapsed form, `doi_original` the deposited string (D-053) | — |
| `relation_json` | JSON string | complete Crossref `relation` object, preserving version and has-review evidence | `{}` |
| `retrieved_at_utc` | timestamp | manifest `accepted_at_utc` | — |
| `platform_id` | string | `row_id` | `qeios_hosted_works` |
| `walk_id`, `page`, `accepted_attempt` | provenance | manifest | — |

Interim files are written only from complete walks and only when none of
the row's scopes is blocked; the cutoff is never applied at this layer.
For the Copernicus row the file holds every record matching a verified
journal's regimes or the EGUsphere regime; journal attribution
is refreshed by joining works and incoming review records from selected
complete walks after the peer-review stage. The run manifest `attribution`
object records observed signals, selected walks, effective register status
and yearly unattributed totals. No observed EGUsphere signal in a completed
run triggers the register-only fallback; an incomplete run cannot establish
signal absence.

All Crossref interim CSVs also carry `attribution_basis`, `included` and
`exclusion_reason` (blank when not applicable). Copernicus attribution
bases are semicolon-delimited `doi_pattern`, `is_preprint_of`,
`journal_title`, `peer_review_is_review_of`; retain every match.
Unattributed preprints have `included=false` and
`exclusion_reason=no_journal_attribution`. Attributed records have blank
`included` pending final eligibility and cutoff checks.

### 4.2 `crossref_peer_reviews__<row_id>.csv`

Same columns as 4.1 plus one line per (review DOI, target, `asserted_by`).
Crossref returns most `is-review-of` relations twice, once asserted by the
subject and once by the object; both lines are kept here and collapse to one
relation at normalisation (key: `row_id`, `review_record_id`,
`reviewed_work_id`).

| Column | Type | Meaning |
|---|---|---|
| `target_id_raw` | string | `relation.is-review-of[i].id` as asserted, or the work DOI of an inverse `has-review` edge |
| `target_id_type` | string | `relation.is-review-of[i].id-type` (`doi`, `url`, …), or `doi` for inverse work-side evidence |
| `target_flag` | enum or empty | `placeholder` (generic tokens such as `10.1234/…` or `…/placeholder`, and an operator-named placeholder after a dotted stem such as MetaROR's `10.70744/MetaROR.placeholder01`, matched case-insensitively; D-064), `malformed`, `self_reference`, `missing` (neither review-side nor usable work-side target evidence); empty when valid |
| `asserted_by` | enum or empty | `relation.is-review-of[i].asserted-by` (`subject`, `object`); empty when absent |
| `target_doi_flag` | enum or empty | `repeated_slash` when the asserted target DOI contains `//`; the target is matched on its collapsed form (D-053) |
| `target_relation_type` | enum | `is-review-of` or `has-review`; the latter identifies inverse work-side evidence |

Evaluation records deposited under a work type (PCI recommendations,
`journal-article` under `10.24072/pci.`) are selected by
`evaluation_record_types` + `evaluation_doi_regex` and written to this file
with their deposited `type`; they never enter 4.1.

A review record is attributed to a row by its valid targets (DOI matching
the row's work selector), by an explicit `review_doi_regex`, by
`container-title`, or — for `qeios_external_works` — by targets outside the
row prefix. Records claimed by no row are written to
`crossref_peer_reviews__unattributed__<prefix>.csv` with the same columns.

For rows with documented work correspondences, inverse `has-review` edges
are read from selected complete work walks and used only for retrieved
review records. For Emerald, targets may name v1, the aliased v2, or the
primary; the same documented correspondence supplies the canonical target.
Review and article stems need not match and are never used for attribution.

Sciety publisher validation runs before any docmap flattening, including
docmaps with no outputs. A mismatch or missing account hard-fails
normalisation for a group-filtered response; no mismatching docmap is
silently discarded. With explicitly configured `retrieval_mode: full_index`,
partition the full response by group, then apply the same validation.
The unpartitioned document remains in the raw store.

### 4.3 `sciety_evaluations__<group_slug>.csv`

| Column | Type | Source field | Example |
|---|---|---|---|
| `group_id` | string | docmap `publisher.account.id` | — |
| `group_name` | string | docmap `publisher.name` | `PREreview` |
| `docmap_id` | string | docmap `id` | — |
| `evaluation_index` | integer | position of the evaluation within the docmap | `0` |
| `evaluated_work_doi` | string | input `doi`, lowercased | — |
| `evaluation_id` | string | `sciety:<docmap_id>:<index>` or evaluation DOI | — |
| `evaluation_url` | string | output `url` | — |
| `evaluation_doi` | string or empty | output `doi` when present | — |
| `evaluation_date` | partial date | output `published` | `2024-03-11` |
| `evaluation_type` | string | output `type` (`review-article`, `evaluation-summary`, `author-response`, …) | — |
| `retrieved_at_utc` | timestamp | — | — |
| `platform_id` | string | `row_id` | — |

## 5. Processed layer (`data/processed/`)

### 5.1 `records_<row_id>.csv` (record level)

Written by `src/normalise/clean_and_normalise.py` for every row whose
primary scopes are complete (one file per row; a row with a blocked scope
gets no file and an older file is removed). Column order is fixed by
`RECORD_COLUMNS` in that module.

| Column | Type | Allowed values / meaning |
|---|---|---|
| `row_id` | string | register row |
| `row_entity_type` | enum | `work_record`, `evaluation_record`, `evaluation_relation` |
| `source` | enum | `crossref`, `sciety` |
| `source_record_id` | string | work DOI or review record id (`= review_record_id` for evaluation rows) |
| `source_container_id` | string or empty | docmap id for Sciety; empty when no container applies |
| `source_record_type` | string | Crossref `type` (`posted-content`, `journal-article`, `peer-review`) or Sciety output `type` |
| `review_record_id` | string or empty | review DOI or `sciety:<docmap_id>:<index>` |
| `relation_type` | enum or empty | `is-review-of`, `has-review` (inverse work-side evidence), `docmap-input`; empty when no relation applies |
| `reviewed_work_id` | string or empty | asserted target, namespaced (`doi:10.32388/abc.2`, `url:…`, `id:crossref:<raw>` for flagged targets) |
| `reviewed_canonical_work_id` | string or empty | canonical target (`doi:10.32388/abc`) |
| `reviewed_work_doi` | string or empty | bare lowercased canonical DOI of the target; empty for `url:`/`id:` targets |
| `work_id`, `canonical_work_id`, `work_doi` | string | for `work_record` rows; `work_id` keeps the DOI as asserted |
| `correspondence_basis` | string or empty | `version_stem+alias+relation` for an explicitly documented primary correspondence; `is_preprint_of`, `has_preprint` or `is_preprint_of+has_preprint` for a preprint/article pair asserted by Crossref relations (D-041; the side(s) observed); empty otherwise; also applies to evaluation targets |
| `source_evaluation_id`, `evaluation_doi`, `canonical_evaluation_id` | string or empty | evaluation identity (`doi:` when a DOI exists, otherwise `id:sciety:…`) |
| `evaluation_url` | string or empty | Sciety output URL; never a counting key |
| `evaluation_identity_status` | enum | `source_only`, `doi_confirmed`, `cross_source_confirmed`, `unresolved` |
| `event_kind` | enum | `posting`, `final_article` (work records, following the row's `counting_event`), `evaluation` |
| `event_date_raw` | string | as asserted by the source (first non-empty field of `counting_event_date_field`; `issued` then `created` for Crossref reviews; `published` for Sciety) |
| `event_date_precision` | enum or empty | `year`, `month`, `day` |
| `event_interval_start`, `event_interval_end` | date or empty | closed calendar interval; empty when no date is asserted |
| `created`, `deposited`, `indexed`, `issued`, `posted` | string or empty | Crossref diagnostics, as asserted |
| `title`, `container_title` | string or empty | `title` is needed for the WITHDRAWN rule |
| `relation_json` | JSON string or empty | full source relation object retained on Crossref work records |
| `record_flag` | enum or empty | `withdrawn`, `placeholder_target`, `malformed_target`, `self_reference_target`, `missing_target`, `later_version` |
| `attribution_basis` | string or empty | Copernicus: `; `-joined signals (see 4.1) |
| `exclusion_reason` | enum or empty | record-level reason carried from extraction (`no_journal_attribution`, `companion_item`) |
| `identifier_flag` | enum or empty | `repeated_slash`: the deposited identifier (work DOI or review target) contained `//`; `source_record_id` and `work_id` keep the asserted string, canonical ids use the collapsed form (D-053) |
| `retrieved_at_utc`, `walk_id`, `page` | string | provenance of the interim line |

`later_version` is informational: a work with several version records keeps
every record and the earliest-dated record carries the counting event.
Flagged relation lines (`*_target`) never join to a work.

Emerald's 13140 work uses `doi:10.1108/eor-03-2023-0005` as canonical
identifier, while v1 `10.12688/emeraldopenres.13140.1` supplies the
2019-06-07 event when retrieved and the primary retains its 2019-12-09
date with `record_flag=later_version`. A primary retrieved alone supplies
its own `issued` date by the same earliest-retrieved-record rule; the
mapping does not manufacture a v1 record or its date. Titles never merge
otherwise unlinked works. DQ-012 records the qualitative date limitation.

De-duplication keys: `work_record` → (`source`, `source_record_id`,
`row_entity_type`); `evaluation_record` → (`source`, `review_record_id`,
`row_entity_type`); `evaluation_relation` → (`source`, `review_record_id`,
`row_entity_type`, `reviewed_work_id`). Every relation resolves to exactly
one parent `evaluation_record` in the same file by (`source`,
`review_record_id`); a dangling relation is a hard failure of the stage.

`normalisation_summary.json` (same directory) lists, per row, the status
(`complete`, `incomplete`, `failed`, `no_source`), blocking scopes and record
counts.

### 5.2 `works_included.csv` (work level)

| Column | Type | Meaning |
|---|---|---|
| `row_id` | string | — |
| `canonical_work_id`, `work_doi` | string | — |
| `correspondence_basis` | string or empty | documented record-level correspondence basis carried from contributing work records (`version_stem+alias+relation`, or the D-041 pair sides `is_preprint_of` / `has_preprint` / `is_preprint_of+has_preprint`); empty when no explicit correspondence applies |
| `included` | boolean | — |
| `in_eligible_range` | boolean or empty | included works only: `true` when `counting_year` lies in the row's eligible range (the work enters a cell, the register summary and the deduplicated group series), `false` when it lies before `eligible_start_year` or after `eligible_end_year` (the cell is `not_applicable`; the work enters no count); empty for excluded works (D-060) |
| `exclusion_reason` | enum or empty | `missing_event_date`, `ambiguous_cutoff_date`, `future_event`, `no_qualifying_review`, `withdrawn`, `later_version`, `register_only`, `no_journal_attribution`, `companion_item` (review report or author response deposited as a work-type record, D-050), `no_posting_record` (gated row without a posted-content record, D-060) |
| `posting_event_date_raw`, `posting_event_date_precision`, `posting_event_interval_start`, `posting_event_interval_end` | see 5.1 | posting event group |
| `eligibility_review_event_date_raw`, `eligibility_review_event_date_precision`, `eligibility_review_event_interval_start`, `eligibility_review_event_interval_end`, `eligibility_review_record_id` | see 5.1 | eligibility-review event group |
| `counting_event_date_raw`, `counting_event_date_precision`, `counting_event_interval_start`, `counting_event_interval_end` | see 5.1 | counting event group |
| `posting_interval_precision`, `eligibility_review_interval_precision`, `counting_interval_precision` | enum | `source` (one record) / `derived` (built from several records; then `*_date_raw` and `*_date_precision` are empty) |
| `contributing_record_ids` | string | `; `-joined source record ids used for a derived interval |
| `counting_year` | integer or empty | year of `counting_event_interval_end` when included |
| `date_order_ambiguous` | boolean | overlapping candidate intervals; tie-break applied |
| `tie_break_source` | string or empty | source record chosen by the tie-break |
| `n_evaluation_records` | integer | unique `canonical_evaluation_id` values |
| `counting_event` | enum | the row's `counting_event` (copied so that every line is self-describing) |
| `posting_record_id`, `counting_record_id` | string or empty | source record ids of the chosen posting and counting records |
| `n_relations_flagged` | integer | flagged relation lines pointing at this work (never joined) |
| `attribution_basis` | string or empty | Copernicus attribution signals observed for the work |
| `counting_record_created`, `counting_record_deposited` | timestamp or empty | Crossref `created` / `deposited` of the counting record (deposition diagnostics) |

Work universe per row: canonical ids of the row's `work_record` lines; for
rows counted by `earliest_qualifying_evaluation` also every unflagged
`reviewed_canonical_work_id`. Relations to targets outside the universe of a
posting-counted row are retained as records and reported in
`analysis_manifest.json` (`n_relation_targets_not_in_row_works`) but create
no work. A work all of whose records are titled WITHDRAWN is excluded with
`withdrawn`; a Copernicus work all of whose records carry
`no_journal_attribution` is excluded with that reason.

**Tie-break for overlapping candidate intervals** (deterministic, in this
order): (1) the record with the finer `event_date_precision`; (2) Crossref
record over Sciety record; (3) `posted-content` over `journal-article`; (4)
the lexicographically smallest `source_record_id`. The analytical interval
remains the conservative interval of the chosen record;
`date_order_ambiguous = true` is recorded.

### 5.3 `data_quality_log.csv`

| Column | Type | Allowed values / meaning |
|---|---|---|
| `issue_id` | string | unique (`DQ-001`, …) |
| `row_id` | string | register row or `all` |
| `issue_type` | enum | `deposition_discontinuity`, `no_review_records`, `partial_source_coverage`, `placeholder_relation`, `retrospective_deposit`, `date_semantics`, `missing_event_date`, `ambiguous_cutoff_date`, `malformed_doi`, `withdrawn_record`, `selector_no_match`, `source_not_covering`, `companion_record`, `openalex_volume_check`, `openalex_pair_signal`, `other` |
| `description` | string | neutral description of the issue |
| `evidence` | string | URL, record id or test name |
| `effect_on_counts` | string | expected direction and scope of the effect |
| `handling` | string | how the pipeline treats affected records |
| `n_records_affected` | integer or empty | filled for run rows; empty for preset rows unless the row records a count observed in a dated probe named in `evidence` (DQ-016) |
| `status` | enum | `template`, `observed`, `resolved` |
| `origin` | enum | `preset` (hand-written, never modified by a run) or `run` |
| `run_id` | string or empty | the run that observed the issue (`run` rows only) |
| `walk_id` | string or empty | `scope=walk_id; …` of the row's selected primary walks (`run` rows only) |

One file (D-040). Preset rows are never overwritten. The analysis stage
appends one `run` row per observed (`row_id`, `issue_type`) with
`issue_id = DQ-<run_id>-<nnn>`, replacing rows of the same `run_id` and
keeping rows of other runs. `analysis_manifest.json` (same directory)
records the cutoff, snapshot window, per-row technical state and
diagnostics.

The OpenAlex diagnostics stage (D-066; runs after `analyse`) adds its own
`run` rows with `issue_id = DQ-<run_id>-oa-<nnn>`, `status` `observed`
and `effect_on_counts` `none (diagnostic)`, replacing only rows of its two
issue types for the same `run_id`:

* `openalex_volume_check` — one row per quantified Crossref register row
  whose included works were resolved in OpenAlex by DOI;
  `n_records_affected` = included works not found in OpenAlex (0 is a
  valid observation); `description` gives, per counting year, the row
  count, the works found, the works whose OpenAlex `publication_year`
  equals the counting year and — where `config/sources.yaml` lists an
  OpenAlex source id for the row — the source's own yearly work count;
  `walk_id` names the OpenAlex walks. A delta is a diagnostic; it never
  corrects a series, a coverage status or a register field.
* `openalex_pair_signal` — one row on the article row of a declared
  `preprint_pair`: among the included works of both rows that carry no
  Crossref correspondence (empty `correspondence_basis`, the residual
  after D-041), the number of preprint/article pairs that map to one
  OpenAlex work id, with the DOI pairs listed in `description`. The pair
  is not added to `cross_platform_overlap.csv`; `correspondence_basis`
  keeps the Crossref values only.

A failed or capped OpenAlex walk produces no row (D-037: a diagnostic
never blocks a row); the outcome is recorded in the run manifest. Because
`analyse` replaces every run row of its `run_id`, the OpenAlex stage must
be run again after any re-run of `analyse`; complete OpenAlex walks are
reused, so the re-run costs no API request.

## 6. Analytical tables (`reports/tables/`)

Common columns: `row_id` / `initiation_class` / `prc_configuration` as
applicable, `year` (integer), `year_label` (`2026 (year_to_date, cutoff
2026-09-30)` for the cutoff year), `count` (integer or empty),
`partial_year` (boolean), `extraction_status` (`complete` / `incomplete` /
`failed`; `not_applicable` for rows without a machine-readable source),
`source_observability_status` (`observable` / `partial_known_scope` /
`unknown_scope` / `pending_run` / `selector_no_match` / `source_not_covering` /
`not_observable`; `selector_no_match` marks a quantified row whose complete
scopes matched no record (D-047) and `source_not_covering` a quantified
Sciety row whose group is absent from the run's docmaps index snapshot
(D-058); `selector_no_match` blocks every group the row belongs to, a
`source_not_covering` row is excluded from its group cells and named there
(D-061); `pending_run` is the
transient state of a run-deferred coverage start before the first complete
run and must be absent from released tables, D-039), `observation_status` (`observed` /
`observed_zero` / `not_observable` / `register_only` / `not_applicable`),
`coverage` (see `coverage_matrix.csv`), `temporal_coverage_status`
(`complete` / `partial` / `not_assessable`), `additivity` (`row_series` /
`row_summed` / `deduplicated`). Every CSV has a Markdown twin with the same
rows, headed by the cutoff, the additivity and the snapshot window.

Group cells (`row_summed` and `deduplicated`) are blank only for states the
pipeline can and must resolve before release (D-061, amending D-038 and
D-058): a member row whose eligible range covers the year carries
`unknown_scope`, `pending_run` or `selector_no_match` (source
observability), or that member's extraction is `incomplete` or `failed`.
Known properties of the sources do not blank a cell; they are published as a
lower bound with the affected rows named in the cell. `not_applicable` and
`observed_zero` members never block the sum. Group tables carry three list
columns of the form `row_id:status; …` (sorted by `row_id`):

- `blocking_rows` — the members above; non-empty exactly when the cell is
  blank;
- `lower_bound_rows` — contributing members in range whose row cell is
  `partial_coverage` or `partial_known_scope`; they are counted, and the cell
  is a lower bound;
- `excluded_rows` — quantified members in range whose source does not carry
  them (`source_not_covering`, D-058); they are not counted, the row keeps
  `register_status quantified` and its own cells stay `not_observable`.

A published group cell's `coverage` is `complete` (or `year_to_date` in the
cutoff year) when both the lower-bound and the excluded list are empty;
`partial_known_scope` when that is the only lower-bound status present and
nothing is excluded; otherwise `partial_coverage`. `temporal_coverage_status`
follows the existing rule. When every member in range is excluded the cell
is blank with `source_observability_status = source_not_covering`, never a
zero. The Markdown twins list every blank cell with its blocking rows
("Blank group cells (D-038)") and every lower-bound cell with its named
rows ("Lower-bound group cells (D-061)"). The `deduplicated` series counts
each `canonical_work_id` once per group, in the year of its earliest
counting event among the group's rows.

Cutoff-year rule (D-061): a row cell keeps its coverage status
(`partial_coverage`, `partial_known_scope`, `complete`) in the cutoff year;
`partial_year = true` and `year_label` carry the year-to-date fact.
`year_to_date` is the `coverage` of a `complete` row cell in the cutoff year
only.

| Table | Key columns | Notes |
|---|---|---|
| `works_by_row_year.csv` | `row_id`, `year` | `additivity = row_series` |
| `works_by_class_year.csv` | `initiation_class`, `year` | `additivity = row_summed`; a work in several rows counts once per row |
| `works_by_configuration_year.csv` | `prc_configuration`, `year` | `additivity = row_summed` |
| `unique_works_by_class_year.csv` | `initiation_class`, `year` | `additivity = deduplicated` on `canonical_work_id`; year of earliest counting event among the class's rows |
| `unique_works_by_configuration_year.csv` | `prc_configuration`, `year` | `additivity = deduplicated` |
| `unique_works_all_rows_year.csv` | `year` | the only all-row total; plus `n_author_initiated_by_earliest_event`, `n_community_initiated_by_earliest_event`, `n_mixed_by_earliest_event` (each work attributed to the class of the row holding its earliest counting event; inputs of Figure 3; the three sum to `count` when the cell is published) |
| `unique_works_all_rows_by_row_year.csv` | `row_id`, `year` | per-row attribution of the all-rows `deduplicated` series (D-059 as merged into D-061): `count` = works whose earliest counting event among all rows lies in this row and year, blank when the row's own cell is not observable; carries `initiation_class`, `prc_configuration` and the row cell's status columns; one line per quantified row and year of its eligible range; attribution is relative to the rows observable in the run, so a `blocking_rows` or `excluded_rows` entry in `unique_works_all_rows_year.csv` for the same year shifts, not removes, the attributed works; sums by class equal `n_<class>_by_earliest_event` of the all-rows table; input of Figure 8 (`fig8_unique_works_by_row_stacked`: one stacked bar per published all-rows year, segments by `row_id` in descending whole-period total, rows with a whole-period total below 1,000 works merged into `Other` and listed in the footer, the year's hatch — `//` cutoff year, dotted lower bound — applied to the whole bar; segments sum to the all-rows `count`) |
| `register_summary.csv` | `row_id` | `organisation_id`, both classes and confidences, `register_status`, `effective_register_status` (after the run-derived Copernicus fallback of D-032; equals `register_status` otherwise), `data_status`, `data_source`, `provisional`, `extraction_status`, `eligible_start_year`, `eligible_end_year`, `first_year_with_data`, `last_year_with_data`, `unique_works_to_cutoff`, `n_works_excluded`, `n_works_outside_eligible_range` (the last six are blank unless the row is quantified, complete and has a resolved coverage start; `first_year_with_data`, `last_year_with_data` and `unique_works_to_cutoff` cover the eligible range only — an included work whose counting year lies outside it enters no cell and is counted in `n_works_outside_eligible_range`, D-060) |
| `coverage_matrix.csv` | `row_id`, `year` | `coverage` ∈ `complete`, `year_to_date`, `partial_coverage`, `partial_known_scope`, `no_data`, `not_applicable` (`year_to_date` only for a `complete` row in the cutoff year, D-061); `note` explains `partial_known_scope` (yearly lower bound) and unresolved coverage starts; EGUsphere attributed series is a yearly lower bound; `partial_year` remains independent |
| `cross_platform_overlap.csv` | `canonical_work_id` | `row_ids` (`; `-joined), `n_rows`, `earliest_row_id`, `earliest_year`, `correspondence_basis` (`canonical_work_id` for identity by canonical identifier alone; `is_preprint_of`, `has_preprint` or `is_preprint_of+has_preprint` for a Gates Open Research / VeriXiv pair asserted by the Crossref relation on the VeriXiv record, on the Gates Open Research record or on both, D-041; `version_stem+alias+relation` where a documented alias correspondence spans rows) |
| `qeios_indicators_by_year.csv` | `year` | `new_hosted_works` (hosted works by first posting year on or before the cutoff, withdrawn excluded, review not required), `hosted_works_with_review`, `review_dois` (distinct review identifiers dated in the year, both Qeios rows), `external_works_reviewed`, `events_registered_after_cutoff_counted`, `events_redeposited_after_cutoff_counted`, `extraction_status`; blank until both Qeios scopes are complete |
| `evidence_features_by_platform.csv` | `row_id` | register fields `row_label`, `organisation_id`, `prc_role`, both classes and confidences, `publish_arrangement`, `review_arrangement`, `curation_arrangement`, `output_types`, the six recognition signals (`public_review_reports`, `approval_status_public`, `summary_assessment`, `version_linked_review`, `public_author_response`, `review_has_doi`), `reviewer_identity_disclosed`, `review_to_object_relation`, `register_status`, `data_status`, `data_source`, `provisional`, and the derived `binding_publication_decision` (`hybrid_public_discussion` → `true`, otherwise `false`; empty for provisional rows) |

`events_registered_after_cutoff_counted` counts included events whose
Crossref `created` date is after the cutoff; `events_redeposited_after_cutoff_counted`
counts included events whose `deposited` date is after the cutoff (may be an
update) and is never described as evidence that the record was absent at the
cutoff.

The two Qeios rows must have zero intersection. In contrast, non-zero
Gates Open Research/VeriXiv Version-of-Record/preprint overlap is expected
under D-013 and must be reported, using explicit work correspondence across
different DOIs rather than DOI equality alone. Do not generalise the Qeios
disjointness requirement to every pair sharing an organisation.

## 7. Logs (`logs/`, outside Git)

`extraction_<run_id>.jsonl`: one JSON object per event with `ts_utc`,
`run_id`, `event` (`pipeline_start`, `stage_start`, `http_attempt`,
`stage_end`, `stage_failed`, `stage_skipped`, `pipeline_end`), and for `http_attempt`:
`scope`, `walk_id`, `page`, `attempt`, `http_status`, `outcome`
(`accepted` / `retry` / `failed` / `restart`).
