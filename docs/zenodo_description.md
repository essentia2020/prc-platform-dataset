# Zenodo description — draft for the release record

Draft text for the description field of the Zenodo record that holds the
release archive of a run. Replace `<run_id>`, the archive name, the file
count and the SHA-256 digest with the values of the archive being deposited
(the values for `run_20261102_01` are in `README.md`, Data availability).
The text is plain prose because the Zenodo description field renders only
simple HTML; links are written in full.

---

PRC Platform Dataset 1.4.0 — release archive of run `<run_id>`.

An open, reproducible dataset of research works flowing through
Publish-Review-Curate (PRC) platforms. Platforms are classified on two
independent axes (who initiates the evaluation; workflow configuration) and
described by a register of evidence fields. Counts are derived from the
Crossref REST API and Sciety docmaps and are organised as observation
series per register row and year. Source code, configuration, documentation,
the published tables and figures and the decision log are in the repository
https://github.com/essentia2020/prc-platform-dataset (tag of this release).

Contents of the archive `prc-platform-dataset_<run_id>.zip`: the record files
`data/processed/records_<row_id>.csv` (one line per work record, evaluation
record and evaluation relation), `works_included.csv` (one line per work,
included or excluded, with the counting event and the exclusion reason),
`normalisation_summary.json`, `analysis_manifest.json`, the interim files
`data/interim/*`, a copy of the page manifests `data/manifests/<run_id>/`
and `SHA256SUMS.txt` with the digest of each file (`<n>` files). The SHA-256
digest of the archive is `<digest>`; the same sums are in
`reports/release_archive_<run_id>.sha256` in the repository. Raw HTTP
responses are not deposited; the manifests record every accepted page.

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
`docs/limitations.md` and `reports/tables/data_quality_log.csv`. The dataset
is a supplement to the seminar presentation "Crossing the chasm: the
Publish-Review-Curate model and the future of peer review" (Leiden
University, 2026;
https://www.universiteitleiden.nl/en/events/2026/09/crossing-the-chasm-the-publish-review-curate-model-and-the-future-of-peer-review).
