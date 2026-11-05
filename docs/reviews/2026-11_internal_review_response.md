# Response scaffold: internal pre-submission review

Source: internal pre-submission review, 2026-11-05. The comments below are paraphrased in English.

## Acceptance criterion

A comment is accepted when it identifies an error in the data, a contradiction between documents or between code and documents, or verifiable evidence against a recorded decision; proposals to proceed differently without such grounds receive a reasoned decline with a reference to the decision that governs the choice. Assessments, actions and references are intentionally left blank pending verification and researcher rulings.

## Comments

| # | Comment (paraphrased in English) | Assessment | Action / rationale | Reference |
|---|---|---|---|---|
| S1 | The release archive uses Windows path separators, preventing ordinary extraction into the intended directory hierarchy on other systems and causing checksum verification to fail until paths are normalised. Rebuild the archive with portable paths and update its release checksums. | | | |
| S2 | The published register, tables and documentation lack a frozen release identifier, while the harvested-record archive does not adequately identify the corresponding dataset version and repository state. Freeze and cross-reference the releases. | | | |
| S3 | Repeated evaluation-relation lines contradict the documented de-duplication key and the claim that normalisation collapses duplicate assertions. The review reports byte-identical duplicates and warns that reusers counting relation lines could overcount even if aggregate work counts are unaffected. | | | |
| S4 | The test suite does not pass as distributed: audit tests require a private token file, and a release-metadata test rejects the `repository-code` field now present in `CITATION.cff`. Clarify the public test requirements and reconcile the stale assertion. | | | |
| S5 | The README describes the OpenAlex diagnostic output as 32 per-row volume checks, whereas the review reports 31 volume-check entries and one pair-signal entry. Reconcile the wording with the log and manifest. | | | |
| S6 | The archive metadata is less complete than the repository metadata, including version, keywords, source relationships, affiliation and links to associated publications. Review the metadata for consistency and completeness. | | | |
| S7 | Licensing for redistributed third-party metadata in interim and record files is not stated as clearly as licensing for raw responses and the dataset compilation. Clarify the applicable terms without conflating those layers. | | | |
| S8 | The repository checksum test skips harvested files absent from the checkout, so it does not establish that the repository and separately distributed archive remain paired. Consider explicit verification against a supplied archive location. | | | |
| S9 | The work-level file contains fewer observation series than the record-file set because the PeerRef record file is header-only. Document explicitly that rows without work records have no entries in `works_included.csv`. | | | |
| S10 | A tracked Crossref contact address belongs to the maintainer and could be reused inadvertently by others. Review whether a placeholder and clearer configuration guidance are preferable. | | | |
| S11 | Add a concise reuse entry guide mapping common analytical questions to the appropriate data files. The current README is extensive and decision-heavy. | | | |
| S12 | Consider publishing a machine-readable schema alongside the data dictionary to expose column definitions and controlled vocabularies in a reusable format. | | | |
| S13 | Before submission, consider rerunning normalisation, analysis and reporting from the archive and comparing the resulting checksums with the published outputs. This would distinguish reproduced outputs from consistency checks alone. | | | |
