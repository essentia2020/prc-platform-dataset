# Release notes

## 1.5.0 (run `run_20261102_01`, data baseline 9affb3c, docs baseline e9fdcba)

### Scope of the release
- Register: 45 observation series of 27 organisations (`config/platforms.yaml`); 42 `quantified`, 3 `register_only`.
- Published run: all 45 series in `reports/tables/register_summary.csv`; 41 series carry `unique_works_to_cutoff` (PeerRef quantified but blank, `source_not_covering`). No provisional rows; `extraction_status = complete` for every quantified row.
- JMIRx Bio (D-072) is walked by ISSN scope within the run: 14 unique works to the cutoff, 38 excluded, years 2023-2026.
- OpenAlex diagnostics (D-066): 32 `openalex_volume_check` rows (31 before D-072) and one `openalex_pair_signal` row (VeriXiv / Gates Open Research, 0 shared work ids; signal only, D-041 correspondence unchanged).
- Data-quality log: 62 run rows and 69 preset rows, 12 columns.

### Changes against the 2026-11-02 archive (10.5281/zenodo.23891928, 631 files)
605 files identical, 5 added, 26 changed, none removed.
- D-072: JMIRx Bio interim, record and three manifest files added.
- D-067: early F1000Research DOI form recovered (+545 records, +422 canonical works).
- D-050: JMIRx Med companion flags (same line count; note of 2026-11-05).
- D-074: 118,448 duplicated evaluation-relation lines removed from nineteen record files; no count changed.
- D-066: snapshot provenance fields.

### Review items (docs/reviews/2026-11_internal_review_response.md)
S1 POSIX path separators in the archive; S2 frozen release identifier (version + baseline commit + archive hash); S3 relation de-duplication (D-074); S4 test suite runs without private token; S5 volume-check count reconciled at 32; S6 archive metadata aligned with repository metadata (this release); S8 checksum test no longer skips absent harvested files; S9 PeerRef header-only record file documented; S10 contact address policy; S11 reuse entry guide; S12 machine-readable schema; S13 independent re-run from the archive: PASS (report `prc-s13-report-v1.3-PASS.zip`, SHA-256 e5275819b79f67f372c4ffff8f5be43aa5aedde4bbc860f8b8f0fff4ca1cc559).
External pre-review (Denis Kosyakov, comments of 2026-11-03; `docs/reviews/2026-11_external_prereview_response.md`): assessments filled 2026-11-05, rulings recorded in D-067 to D-075.

### Known limits carried into this release
Thirty notice works remain counted as documented in D-076 and DQ-021 through DQ-024; notice identification is approved in principle, implementation deferred to the next minor release pending assessment of Crossref `update-to` / `relation` metadata. Three header-only interim files bound to no selected walk are retained for continuity.

### Archive and identifiers
`prc-platform-dataset_run_20261102_01_v1.5.0.zip`: 636 payload files (+ `SHA256SUMS.txt`), SHA-256 `da814ac04d985971bf1e6e77191cd3e84d60a5659a38a0bed04fac1e9aa01dbe`; per-file sums in the versioned checksum file under `reports/` (SHA-256 `01b94b3cc52200a831a617f247d3819151a2fb95937119af55c98431635dddea`, 636 payload entries). Zenodo DOI 10.5281/zenodo.24015301 (published 2026-11-07), all versions 10.5281/zenodo.23812672. The 2026-11-02 archive and the `run_20261027_01` archive (10.5281/zenodo.23812673) remain unchanged. Audit policy: current release 1.5.0 with a revision-aware history scan (D-056 note 2026-11-06). `CITATION.cff` carries `date-released: 2026-11-07`, the publication date of the Zenodo record; the DOI was reserved on the draft before publication.
