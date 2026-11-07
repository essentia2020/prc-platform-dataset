# Zenodo description — draft for the release record

Text for the description field of the Zenodo record that holds the release
archive of a run. The values below are those of the 1.5.0 archive of
`run_20261102_01` (DOI 10.5281/zenodo.24015301, published 2026-11-07) and match `README.md`, Data availability. For a
later archive, update the archive name, the file count, the SHA-256 digest
and the supersession paragraph.
The text is plain prose because the Zenodo description field renders only
simple HTML; links are written in full.

---

PRC Platform Dataset 1.5.0 — release archive of run `run_20261102_01`.

An open, reproducible dataset of research works flowing through
Publish-Review-Curate (PRC) platforms. Platforms are classified on two
independent axes (who initiates the evaluation; workflow configuration) and
described by a register of evidence fields. Counts are derived from the
Crossref REST API and Sciety docmaps and are organised as observation
series per register row and year. Source code, configuration, documentation,
the published tables and figures and the decision log are in the repository
https://github.com/essentia2020/prc-platform-dataset (tag of this release).

Contents of the archive (637 ZIP members, file
`prc-platform-dataset_run_20261102_01_v1.5.0.zip`): the record files `data/processed/records_<row_id>.csv` (one line per work
record, evaluation record and evaluation relation), `works_included.csv`
(one line per work, included or excluded, with the counting event and the
exclusion reason), `normalisation_summary.json`, `analysis_manifest.json`,
the interim files `data/interim/*` (97 CSV files and `.gitkeep`), a copy of
the page manifests `data/manifests/run_20261102_01/` and `SHA256SUMS.txt`
with the digest of each file (636 files). The SHA-256
digest of the archive is
`da814ac04d985971bf1e6e77191cd3e84d60a5659a38a0bed04fac1e9aa01dbe`; the
same sums are in `reports/release_archive_run_20261102_01_v1.5.0.sha256` in
the repository. Raw HTTP responses are not deposited; the manifests record
every accepted page.

This archive is the S13-validated snapshot of `run_20261102_01` (data
baseline 9affb3c) and supersedes the archive of the same run deposited on
2026-11-02 (https://doi.org/10.5281/zenodo.23891928, 631 files), which
remains unchanged. A run id can span documented extensions, so the release
version, the baseline commit and the archive hash identify the snapshot.
Relative to the 2026-11-02 archive, 605 files are identical, 5 are added
(the JMIRx Bio interim, record and manifest files, D-072) and 26 changed
(early F1000Research DOI form recovered, D-067; JMIRx companion flags,
D-050; duplicated evaluation-relation lines removed from nineteen record
files without changing any count, D-074; snapshot provenance fields,
D-066). Three header-only interim files bound to no selected walk of the
run are retained for continuity and documented in the repository README
(Data availability).

Licensing. The interim and record files in this archive are derived from
Crossref metadata (made available without restriction, CC0 waiver, per
`config/sources.yaml` and
https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-metadata-license-information/)
and from Sciety docmap identifiers, dates and URLs (https://sciety.org/about;
evaluation texts are not stored). The Creative Commons Attribution 4.0
International licence (CC BY 4.0) applies to the compilation and to the
derived fields (identifiers, intervals, eligibility decisions, counts),
not to the source metadata as such. The code that produced the archive is
under the MIT License.

Provenance. Analysis cutoff date, selected-walk policy and the `mailto`
address are in `config/run.yaml` of the tagged commit; every data-affecting
rule is a numbered decision in `docs/decisions.md`; known limits are in
`docs/limitations.md` and `data/processed/data_quality_log.csv`. The dataset
is a supplement to the seminar presentation "Crossing the chasm: the
Publish-Review-Curate model and the future of peer review" (Leiden
University, 2026;
https://www.universiteitleiden.nl/en/events/2026/09/crossing-the-chasm-the-publish-review-curate-model-and-the-future-of-peer-review).
