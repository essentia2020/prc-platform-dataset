# PRC Platform Dataset 1.4.0

An open, reproducible dataset of research works flowing through
Publish–Review–Curate (PRC) platforms. Platforms are classified on two
independent axes — **who initiates the evaluation** and **workflow
configuration** — and described by a register of evidence fields. Counts are
derived from the Crossref REST API and Sciety docmaps and are organised as
observation series per register row and year.

## Purpose

The dataset answers five questions: how many unique research works per year
flow through each machine-readable PRC platform; how volumes compare between
author-initiated, community-initiated and mixed evaluation; how they compare
between workflow configurations; which PRC services are verifiable but not
quantifiable from the two sources; and which transparency features each
platform exhibits. See `docs/analysis_plan.md`.

## Definition

The dataset follows the definition of the PRC model by Corker, Waltman and
Coates (2024): research works are first made public, then evaluated in the
open, and finally curated through recommendations, assessments or approval
statuses, with the three functions decoupled from one another and from any
single journal. The full decision rules are in
`config/classification_scheme.md`.

## Two classification axes

**Axis 1 — who initiates the evaluation** (`initiation_class`):

| Code | Meaning |
|---|---|
| `author_initiated` | authors submit or post the work and thereby request evaluation; the platform organises reviewing only for submitted works |
| `community_initiated` | reviewers, curators or the service select already-public works hosted elsewhere; author consent is not a prerequisite |
| `mixed` | both an author request route and a documented selection route exist and both produce a non-trivial share of evaluations |

**Axis 2 — workflow configuration** (`prc_configuration`):

| Code | Meaning |
|---|---|
| `core_publish_first` | the platform posts the work, organises public review and issues a curation output without an accept/reject decision |
| `approval_threshold` | public approval statuses; a threshold on them triggers indexing or a formal status; works below it remain public |
| `hybrid_public_discussion` | public discussion or refereeing of the posted work followed by a binding editorial accept/reject decision |
| `review_or_curation_service` | the service evaluates or curates works published or posted elsewhere; no hosting, no publication decision |

The axes are independent and are always reported separately.
`binding_publication_decision` is derived from axis 2 and never entered by
hand. D-016 assigns JMIRx Med to `core_publish_first` (medium) as an
overlay-journal case without public discussion before the decision; this
does not establish absence of an editorial acceptance decision.

## Rows are series, not organisations

A register row is an **observation series**: one organisation, one counting
event, one extraction selector. One organisation may own several rows
(Qeios has two, linked by `organisation_id = qeios`). Series are comparable
over time within a row, never between rows, and rows of one organisation are
never summed. The unit of analysis is the unique research work per row per
year of its earliest qualifying event; reviews, versions, rounds and
responses never increase counts. Gates Open Research and VeriXiv share
`organisation_id = gates_f1000`; confirmed Version-of-Record/preprint overlap
between them is reported, not an error. Only the two Qeios series are required
to be disjoint.

## Platform register

Source of truth: `config/platforms.yaml` (hand-edited). `config/platforms.csv`
is generated from it (`python -m src.common.register --export`) and never
edited by hand. Medium or low confidence alone does not set `provisional`.
Decisions clear that flag. VeriXiv (deposit confirmed in run_20261026_01,
D-051) and the seven F1000-infrastructure venues added after that run
(D-052) were provisional until their first flattening; D-071 cleared the
eight flags on 2026-11-05 after the venues' own workflow pages were
re-read, so no row is provisional in this release. Candidates audited
but not included are in `config/excluded_candidates.yaml`.

| Row (`row_id`) | Organisation | Axis 1 (confidence) | Axis 2 (confidence) | Source | Counting event | Coverage | Data status |
|---|---|---|---|---|---|---|---|
| `elife_reviewed_preprints` | eLife Sciences Publications Ltd | `author_initiated` (high) | `core_publish_first` (high) | both | first_public_posting | 2022–cutoff | machine_readable |
| `f1000research` | F1000 Research Ltd (Taylor & Francis) | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2013–cutoff | machine_readable |
| `wellcome_open_research` | F1000 Research Ltd for Wellcome | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2016–cutoff | machine_readable |
| `gates_open_research` | F1000 Research Ltd for the Gates Foundation | `author_initiated` (high) | `approval_threshold` (medium) | crossref | first_public_posting | 2017–2024 | machine_readable |
| `verixiv` | F1000 Research Ltd for the Gates Foundation | `author_initiated` (high) | `approval_threshold` (medium) | crossref | first_public_posting | 2024–cutoff | machine_readable |
| `open_research_europe` | F1000 Research Ltd for the European Commission | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2021–cutoff | machine_readable |
| `hrb_open_research` | F1000 Research Ltd for the Health Research Board (Ireland) | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2018–cutoff | machine_readable |
| `stosunki_miedzynarodowe` | F1000 Research Ltd for the University of Warsaw (Faculty of Political Science and International Studies) | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2021–cutoff | machine_readable |
| `nuclear_science_technology_open_research` | F1000 Research Ltd for the American Nuclear Society | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2023–cutoff | machine_readable |
| `digital_twin` | F1000 Research Ltd (Taylor & Francis) | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2021–2025 | machine_readable |
| `molecular_psychology` | F1000 Research Ltd (Taylor & Francis) | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2022–cutoff | machine_readable |
| `materials_open_research` | F1000 Research Ltd (Taylor & Francis) | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2021–cutoff | machine_readable |
| `cobot` | F1000 Research Ltd (Taylor & Francis) | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2022–cutoff | machine_readable |
| `bioethics_open_research` | F1000 Research Ltd (Taylor & Francis, with the American Journal of Bioethics) | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2023–cutoff | machine_readable |
| `nihr_open_research` | F1000 Research Ltd for the National Institute for Health and Care Research | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2021–cutoff | machine_readable |
| `health_open_research` | F1000 Research Ltd with the Association of Medical Research Charities | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2019–cutoff | machine_readable |
| `open_research_africa` | F1000 Research Ltd with the Science for Africa Foundation | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2018–cutoff | machine_readable |
| `routledge_open_research` | F1000 Research Ltd / Routledge (Taylor & Francis) | `author_initiated` (medium) | `approval_threshold` (medium) | crossref | first_public_posting | 2021–cutoff | machine_readable |
| `meded_publish` | Association for Medical Education in Europe (AMEE); platform operated by F1000 since 2021 | `author_initiated` (high) | `approval_threshold` (high) | crossref | first_public_posting | 2016–cutoff | machine_readable |
| `emerald_open_research` | Emerald Publishing (platform operated by F1000) | `author_initiated` (high) | `approval_threshold` (medium) | crossref | first_public_posting | 2019–2023 | machine_readable |
| `metaror` | Research on Research Institute (RoRI) and AIMOS | `author_initiated` (high) | `review_or_curation_service` (high) | both | earliest_qualifying_evaluation | 2024–cutoff | machine_readable |
| `pci_recommendations` | Peer Community In (non-profit association) | `author_initiated` (high) | `review_or_curation_service` (high) | both | earliest_qualifying_evaluation | 2017–cutoff | machine_readable |
| `scipost` | SciPost Foundation | `author_initiated` (high) | `hybrid_public_discussion` (high) | crossref | final_article | 2016–cutoff | machine_readable |
| `copernicus_interactive_public_peer_review` | Copernicus Publications (Copernicus GmbH) | `author_initiated` (high) | `hybrid_public_discussion` (high) | crossref | first_public_posting | 2001–cutoff | machine_readable |
| `jmirx_med` | JMIR Publications | `mixed` (medium) | `core_publish_first` (medium) | crossref | final_article | 2020–cutoff | machine_readable |
| `access_microbiology` | Microbiology Society | `author_initiated` (high) | `hybrid_public_discussion` (medium) | both | first_public_posting | run-derived–cutoff | machine_readable |
| `review_commons` | Review Commons (EMBO and ASAPbio) | `author_initiated` (high) | `review_or_curation_service` (high) | both | earliest_qualifying_evaluation | 2020–cutoff | machine_readable |
| `peerref` | PeerRef | `author_initiated` (high) | `review_or_curation_service` (high) | sciety | earliest_qualifying_evaluation | 2022–cutoff | partial_coverage |
| `biophysics_colab` | Science Colab | `mixed` (low) | `review_or_curation_service` (high) | sciety | earliest_qualifying_evaluation | 2021–cutoff | machine_readable |
| `qeios_hosted_works` | Qeios Ltd | `author_initiated` (medium) | `approval_threshold` (medium) | crossref | first_public_posting | 2019–cutoff | partial_coverage |
| `qeios_external_works` | Qeios Ltd | `community_initiated` (medium) | `review_or_curation_service` (high) | crossref | earliest_qualifying_evaluation | 2020–cutoff | partial_coverage |
| `prereview` | PREreview (fiscally sponsored by Code for Science & Society) | `community_initiated` (medium) | `review_or_curation_service` (high) | sciety | earliest_qualifying_evaluation | 2019–cutoff | partial_coverage |
| `prelights` | The Company of Biologists | `community_initiated` (high) | `review_or_curation_service` (high) | sciety | earliest_qualifying_evaluation | 2018–cutoff | partial_coverage |
| `rapid_reviews_infectious_diseases` | MIT Press | `community_initiated` (high) | `review_or_curation_service` (high) | both | earliest_qualifying_evaluation | 2020–cutoff | machine_readable |
| `arcadia_science` | Arcadia Science | `community_initiated` (high) | `review_or_curation_service` (high) | sciety | earliest_qualifying_evaluation | 2022–cutoff | machine_readable |
| `asapbio_crowd_review` | ASAPbio | `community_initiated` (medium) | `review_or_curation_service` (high) | sciety | earliest_qualifying_evaluation | 2021–cutoff | machine_readable |
| `asapbio_scielo_crowd_review` | ASAPbio with SciELO Preprints | `community_initiated` (medium) | `review_or_curation_service` (high) | sciety | earliest_qualifying_evaluation | 2022–cutoff | machine_readable |
| `ncrc` | Johns Hopkins Bloomberg School of Public Health | `community_initiated` (high) | `review_or_curation_service` (high) | sciety | earliest_qualifying_evaluation | 2020–2022 | defunct |
| `life_science_editors_foundation` | Life Science Editors Foundation | `mixed` (low) | `review_or_curation_service` (medium) | sciety | earliest_qualifying_evaluation | 2022–cutoff | machine_readable |
| `life_science_editors` | Life Science Editors | `mixed` (low) | `review_or_curation_service` (medium) | sciety | earliest_qualifying_evaluation | 2022–cutoff | machine_readable |
| `the_unjournal` | The Unjournal | `mixed` (medium) | `review_or_curation_service` (high) | both | earliest_qualifying_evaluation | 2023–cutoff | partial_coverage |
| `scienceopen_reviews` | ScienceOpen GmbH | `mixed` (medium) | `review_or_curation_service` (medium) | none | earliest_qualifying_evaluation | 2014–cutoff | not_machine_readable |
| `octopus` | Octopus Publishing CIC with Jisc | `author_initiated` (high) | `core_publish_first` (medium) | none | first_public_posting | 2022–cutoff | not_machine_readable |
| `peeriodicals` | The PubPeer Foundation | `community_initiated` (medium) | `review_or_curation_service` (high) | none | earliest_qualifying_evaluation | 2018–cutoff | not_machine_readable |

Coverage "cutoff" means an open series ending at `analysis_cutoff_date`
(`config/run.yaml`). `partial_coverage` and `defunct` explain why a row's
counts are limited; `register_only` rows carry blank analytical values,
never zero. A quantified row whose selector matches no record in any of
its complete scopes is a selector defect and publishes no count
(`selector_no_match`, D-047), never a zero. Copernicus counts
discussion preprints of 29 hand-verified journals (D-027); EGUsphere-era
preprints count only when attributed to a verified journal, so that part of
the series is a lower bound. Access Microbiology has a run-derived start
rather than an assumed 2023 boundary. The three `register_only` rows with
`data_source: none` (ScienceOpen, Octopus, Peeriodicals; D-028) satisfy the
inclusion criteria but have no selector in the two permitted sources. A
quantified Sciety row whose group is absent from the docmaps index
retrieved by the same run publishes no count either (`source_not_covering`,
D-058): the index lists only groups enabled for docmaps by Sciety; the
group cells it belongs to are published without it and name it (D-061).
The approved cutoff is 2026-09-30; 2026 is `year_to_date`.

## How to run

Requirements: Python 3.10 or later and the packages in `requirements.txt`
(`pip install -r requirements.txt`). Set `run_id`, `analysis_cutoff_date` and
`mailto` in `config/run.yaml` before each run.

```
python -m src.common.register --validate     # register schema and vocabularies
python -m src.common.register --export       # regenerate both CSV registers
python -m src.run_pipeline --list            # show the stage order
python -m src.run_pipeline --stages all      # run every stage
python -m src.run_pipeline --stages extract_crossref_works --force-new-walk   # new walk despite a complete one
python -m src.run_pipeline --stages normalise,analyse,report                 # offline stages only, from existing interim files
PRC_OPENALEX_API_KEY=<key> python -m src.run_pipeline --stages openalex_diagnostics   # D-066 diagnostics after analyse (contacts the OpenAlex API; rows in data_quality_log.csv only)
python -m pytest                             # test suite (offline; no API is contacted)
python tools/check_register_prefixes.py      # one-off register check: resolves one known work and one known review DOI per quantified Crossref row and compares owner prefix and member with the declared scopes (contacts the Crossref API; run by the maintainer before an extraction)
PRC_RAW_STORE=<raw store root> python -m pytest tests/test_manifest_checksums_match.py
python tools/check_walk_shape.py --run <run_id> --raw-root <raw store root>   # walk-shape check after a run: repeated cursor, page count vs total-results, mid-walk short page, record on two pages (rule 5 reads the raw store; --no-raw for the manifest-only rules); rule 6 checks zero-item Sciety walks against the run's docmaps index snapshot (or --sciety-index <stored index response>); exit 1 on an issue, 2 when inconclusive
python tools/audit_text.py --tokens <path outside the repository> --history
python tools/append_dq_rows.py <rows.csv> [--dry-run]   # insert preset rows into data/processed/data_quality_log.csv after the last preset row, written by the same CSV writer as the analysis stage (minimal quoting, LF); rows arrive as a CSV with the log's header or as the + lines of a unified diff
```

Stage order, fixed in `src/run_pipeline.py`:

1. `extract_crossref_works` — one cursor walk per `works__<prefix>__<type>` or `works__issn_<issn>__<type>` scope (journal-article, posted-content) → `data/raw/crossref/<scope>/…`, split per row by DOI regex into `data/interim/crossref_works__<row_id>.csv`
2. `extract_crossref_peer_reviews` — one walk per `works__<prefix>__peer-review` scope over every declared review prefix (10.21956, 10.5256, 10.68336, 10.3310, …) plus the declared evaluation-record scopes (PCI: `works__10.24072__journal-article`) → `data/interim/crossref_peer_reviews__<row_id>.csv` (one line per review DOI, `is-review-of` target and `asserted_by`) and `crossref_peer_reviews__unattributed__<prefix>.csv`
3. `extract_sciety_evaluations` — one walk of the unfiltered index per run (`index`, scope `index__all`, the coverage probe of D-058) and one paginated walk per group (`index?publisheraccount=<group page URL>`) → `data/raw/sciety/evaluations__<group_slug>/…`, `data/interim/sciety_evaluations__<group_slug>.csv`; `index_coverage` per group in the run manifest; publisher-account mismatch hard-fails normalisation
4. `normalise` — `src/normalise/clean_and_normalise.py`: record-level layer `data/processed/records_<row_id>.csv` (work, evaluation and relation lines; canonical identifiers; evaluation identity; source-precision dates) plus `normalisation_summary.json`; rows with a blocked scope get no file
5. `analyse` — `src/analyse/build_aggregates.py`: work-level decisions `data/processed/works_included.csv`, `analysis_manifest.json`, run counts in `data_quality_log.csv`, every table in `reports/tables/*.csv|md`
6. `openalex_diagnostics` — `src/extract/openalex_diagnostics.py` (D-041, D-066): resolves the included works of every quantified Crossref row in OpenAlex by DOI (batches of at most 100) and, where a source id is configured, retrieves the source's yearly counts; tests the residual Gates Open Research / VeriXiv works (no Crossref relation from either side) for a shared OpenAlex work id. Output: `openalex_volume_check` and `openalex_pair_signal` rows in `data_quality_log.csv`, raw responses under `data/raw/openalex/…`, a summary under `openalex_diagnostics` in the run manifest. Nothing from OpenAlex enters a record file, `works_included.csv`, a table or a figure; a failed or capped walk yields no row and blocks nothing. Requires `PRC_OPENALEX_API_KEY` (never read from a tracked file, never written to a sidecar); per-run request cap in `config/sources.yaml`. Run it again after any re-run of `analyse` (complete walks are reused without requests)
7. `report` — `src/report/make_reports.py`: Figures 1–8 in `reports/figures/*.png|svg` (matplotlib, Agg backend) and `reports/CHECKSUMS.txt` over processed files, tables and figures. Figures 2, 3, 6 and 8 draw group cells that are lower bounds with a dotted hatch; each such figure is a lower bound and excludes the rows named in the table footnotes and in its own footer (D-061). Figure 8 stacks the all-rows total by the register row of each work's earliest counting event, merging rows below 1,000 works over the whole period into `Other`

Extraction is idempotent: raw HTTP responses are immutable
(`data/raw/<source>/<scope>/<run_id>/<walk_id>/page_<n>/attempt_<k>.*`; the
root can be moved with `PRC_RAW_STORE`), the accepted-page manifests in
`data/manifests/<run_id>/` record the SHA-256 of every accepted response and
the terminal state of every walk, and `logs/extraction_<run_id>.jsonl` is the
per-attempt log. A complete walk is reused by later invocations; an
interrupted or rejected walk is closed and a new `walk_id` starts from the
first page — walks are never resumed in place. An incomplete or failed scope
writes no interim file for any dependent row and the stage exits with an
error naming those rows (D-031). Expected runtime depends on Crossref polite-pool
throughput; the F1000-platform and Copernicus scopes are the largest cursor
walks. Extraction scripts are run only locally by the maintainer; nothing in
this repository contacts an API during tests.

Crossref completion requires an empty items list or an absent `next-cursor`,
and an accepted item total matching first-page `total-results` within the
configured tolerance (D-035). A short non-empty page with a continuation
is followed and logged as a page-level `short_page` anomaly. Missing
`next-cursor` remains an anomaly and cannot override the item-total check.
Every request repeats the original query parameters with the `next-cursor`
from the immediately preceding response. The default tolerance is zero;
scope-specific overrides and their reasons are in `config/sources.yaml`.
A scope whose single cursor walk loses
records between cursor steps is listed in `pagination.windowed_scopes`
and walked per date window at tolerance 0 (D-045 option c, D-057): the
unwindowed `total-results` is probed before and after the pass, and the
scope is complete only when every window walk is complete and the window
totals sum to both probes.
Sciety follows continuation links
until exhaustion, independently of Crossref's total check (D-034).

Stages 4, 5 and 7 read only local files (interim CSVs, run manifest, register).
They derive each row's technical state from the run manifest: a row is
analysed only when every primary scope has a selected complete walk;
cross-check scopes never block a row but are required for
`cross_source_confirmed` evaluation identity. Blank cells in the tables are
never zeros — `observation_status`, `extraction_status` and
`source_observability_status` say why a cell is blank. A class,
configuration or all-rows cell is blank only when a member row in range
carries `unknown_scope`, `pending_run` or `selector_no_match`, or its scope
is not complete; `not_applicable` and `observed_zero` members never block
the sum, and the `blocking_rows` column names the blocking row (D-038,
D-061). Members with partial coverage are counted and named in
`lower_bound_rows`; Sciety rows whose group is absent from the index are
left out and named in `excluded_rows`; such a cell is a lower bound
(`coverage = partial_coverage`, D-061). The only all-row total is the
deduplicated `unique_works_all_rows_year.csv`; its per-row attribution is
`unique_works_all_rows_by_row_year.csv`.

Copernicus attribution uses any of three signals: `is-preprint-of`, a
verified journal title, or an incoming Crossref peer-review `is-review-of`.
The peer-review stage refreshes per-record `attribution_basis` from complete
selected walks. Unattributed preprints stay in interim with `included=false`
and `exclusion_reason=no_journal_attribution`; attributed records still need
final eligibility checks. Affected years carry `partial_known_scope` in
`coverage_matrix`, independently of `partial_year` (D-032).
A first-public-posting row whose eligibility event names `posted-content`
(eLife Reviewed Preprints, Access Microbiology) admits a work only through a
posted-content record; journal-article-only stems are excluded as
`no_posting_record`, and `register_summary.csv` counts the eligible range
only (`n_works_outside_eligible_range`; D-060). ResearchHub is
scheduled for reassessment when the documentation stabilises, before release freeze (D-033).

## Repository layout

```
config/      platforms.yaml|csv, excluded_candidates.yaml|csv, classification_scheme.md,
             sources.yaml, run.yaml, audit_allowlist.yaml
docs/        analysis_plan.md, data_dictionary.md, decisions.md, limitations.md
src/         run_pipeline.py; common/ (config, register, identifiers, log, dates,
             http, raw_store, manifest, walk, interim, eligibility, aggregates,
             correspondence, preprint_pairs),
             extract/ (selectors, crossref_common, crossref_works,
             crossref_peer_reviews, sciety_evaluations, openalex_diagnostics),
             normalise/, analyse/, report/
tools/       audit_text.py (repository text audit), check_register_prefixes.py
             (owner-prefix and member check of the register against Crossref),
             check_walk_shape.py (post-run cursor-walk shape check against the
             walk manifests and the local raw store; Sciety index coverage),
             append_dq_rows.py (inserts preset rows into the data-quality log)
tests/       pytest suite and fixtures
data/        raw/ (outside Git), interim/ (outside Git), processed/, manifests/
             (walk manifests per run; probes/ with one-off probe outputs cited
             in docs/decisions.md)
reports/     tables/, figures/, CHECKSUMS.txt
logs/        extraction_<run_id>.jsonl (outside Git)
```

## Data availability

The repository tracks configuration, documentation, the data-quality log,
the page manifests, the published tables and figures and `reports/CHECKSUMS.txt`
(D-056). Harvested records are not tracked: for each run they are deposited
as a release archive. For `run_20261102_01` the archive
`prc-platform-dataset_run_20261102_01.zip` (99.4 MB) contains
`data/processed/records_*.csv`, `works_included.csv`,
`normalisation_summary.json`, `analysis_manifest.json`, `data/interim/*`, a
copy of `data/manifests/run_20261102_01/` and `SHA256SUMS.txt` with the digest
of each file — 631 files; the same sums and the sum of the archive itself are
in `reports/release_archive_run_20261102_01.sha256`. Archive SHA-256:
`a1783244b25b202ac1f824a7f454ec31f96631569746270f41dfb55a291bf627`.
Zenodo DOI: [10.5281/zenodo.23891928](https://doi.org/10.5281/zenodo.23891928).
The archive of the preceding run, `run_20261027_01`, remains available under
[10.5281/zenodo.23812673](https://doi.org/10.5281/zenodo.23812673) and is
superseded by this one.

## Licensing

- `LICENSE` — MIT License; applies to the code in `src/`, `tools/` and
  `tests/`.
- `LICENSE-DATA` — Creative Commons Attribution 4.0 International (CC BY 4.0);
  applies to `config/`, `data/processed/`, `reports/` and `docs/`.
- Raw HTTP responses under `data/raw/` are not part of the repository; when
  shared, they carry the source terms recorded in `config/sources.yaml`
  (Crossref REST API, Sciety).

## Citation

Citation metadata is in `CITATION.cff`. Source code and documentation:
<https://github.com/essentia2020/prc-platform-dataset>; the release
archive of each run is on Zenodo (see Data availability). The dataset is a supplement to the seminar presentation listed there under
`references` (`isSupplementTo`; seminar page with the recording:
<https://www.universiteitleiden.nl/en/events/2026/09/crossing-the-chasm-the-publish-review-curate-model-and-the-future-of-peer-review>);
the dataset DOI is added at the release freeze.

## Authorship and tooling

The analytical code in src/, tools/ and tests/ was written with the
assistance of Perplexity. All design, classification and data-handling
decisions recorded in docs/decisions.md were taken by the researcher, who
reviewed the code and its outputs and bears final responsibility for the
integrity of the data.

## Related publications

The PRC definition follows Corker, Waltman and Coates (2024). The treatment
of workflow configuration as a separate axis follows Kochetkov (2026),
Learned Publishing, 39(2), e2046, https://doi.org/10.1002/leap.2046, which I
wrote as the conceptual companion to this dataset; the operational
definitions used here are specific to the dataset.

## Limitations

Counts describe the machine-readable part of the PRC landscape as
reconstructed from a recorded retrieval: Crossref sees only deposited DOIs
and `peer-review` records, Sciety only groups that joined it, deposition
practice changes over time, and counting events differ by row. SciPost counts
final articles; Copernicus counts discussion-preprint entry into public
discussion for individually verified journals. Full statement:
[Limitations](docs/limitations.md).

## Future work

1. Validation of the classification scheme and of the platform list with
   the expert community (preprint-review and open-peer-review practitioners;
   for example the ASAPbio, Sciety, PCI, eLife and PREreview teams).
2. Verification of the extracted counts directly with the platforms
   (per-platform data confirmation).
3. OpenAlex as a diagnostic source (D-066). Two of the three permitted
   uses ran in `run_20261102_01` as the `openalex_diagnostics` stage: the
   per-row volume check (32 rows resolved by counting-record DOI) and the
   Gates Open Research–VeriXiv pair signal on the D-041 residual (0 shared
   OpenAlex work ids); both leave rows in the data-quality log only. Still
   open: source-level yearly counts (`openalex.source_ids` is empty for
   1.4.0 — deferred because the OpenAlex source of a merged Copernicus
   record is the final article, D-066 follow-up 2), and the topic, country
   and citation enrichment for the article, which is done outside the
   release pipeline on the CWTS OpenAlex dump and will be recorded by one
   preset data-quality row naming the snapshot. OpenAlex never enters a
   record file, table or figure.
4. Extension of the platform register with additional attributes describing
   outputs and review-transparency features of each platform.
5. Review of the Gates Open Research / VeriXiv pairs after the first
   complete run: the pairing itself is implemented (D-041, `preprint_pair`
   on the VeriXiv row; `is-preprint-of` on the VeriXiv record,
   `has-preprint` on the Gates Open Research version-1 record, either side
   suffices; one line per pair in `cross_platform_overlap.csv` with the
   side(s) observed in `correspondence_basis`); the share of pairs asserted
   from one side only and the OpenAlex residual signal (D-066) are to be
   reported in the limitations.
6. Access Microbiology coverage start: resolved by `run_20261102_01` 
  (D-017, D-060); the start is re-derived from every complete run, and a run 
  without qualifying events would return the row to `unknown_scope`.
7. Generalised preprint–article pairing: extend D-041 to `has-preprint`
   on eLife Reviewed Preprint records (and the matching `is-version-of`
   assertions) so that the 105 cross-row pairs of DQ-019 are counted once
   in the deduplicated tables (D-068).
