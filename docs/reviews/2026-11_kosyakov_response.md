# Response scaffold: Denis Kosyakov review

Reviewer: Denis Kosyakov. Date of comments: 2026-11.

## Acceptance criterion

A comment is accepted when it identifies an error in the data, a contradiction between documents or between code and documents, or verifiable evidence against a recorded decision; proposals to proceed differently without such grounds receive a reasoned decline with a reference to the decision that governs the choice. Assessments, actions and references are intentionally left blank pending verification and researcher rulings.

## Comments

| # | Comment (paraphrased in English) | Assessment | Action / rationale | Reference |
|---|---|---|---|---|
| K1 | F1000Research works with older DOI stems containing a volume, a hyphenated article number and a `v` version suffix may be missing. Check these records and their review relations, and investigate whether identifiers under `10.3410` and `10.12688` refer to the same works. | | | |
| K2 | MetaROR records linked to technical DOIs may have been lost through exclusion. Resolve those identifiers to the underlying work before deciding whether the records belong in the dataset. | | | |
| K3 | Cross-platform normalisation relies mainly on identical canonical identifiers and selected mappings. The review reports 105 separately counted identifier pairs linked by `has-preprint` or `is-version-of`; preprints and eLife outputs may therefore remain separate works despite relations retained in the metadata. | | | |
| K4 | JMIRx Med is classified as `core_publish_first`, although its documented binary accept/reject decision conflicts with the category definition, and it lacks the public discussion required by `hybrid_public_discussion`. Consider treating the editorial decision and review-disclosure timing as separate observable features. MetaROR also requires scrutiny because its evaluation of externally hosted preprints appears consistent with much of the `review_or_curation_service` definition. | | | |
| K5 | Observation series count different stages, including incoming works, evaluated works, positively recommended works and final journal articles, while the research questions compare volumes across initiation classes and configurations. Consider separate families of public-posting, public-evaluation and curation measures. | | | |
| K6 | Distinguish observation series, organisations and numeric series rather than describing all rows as platforms. The review reports 44 series, 27 organisation identifiers, 41 quantified rows and 40 rows with numeric data. Assess sensitivity to the mixture of longstanding discussion journals and newer evaluation services, and identify an appropriate denominator before making claims about PRC adoption. | | | |
| K7 | A single `model_since` date and notes may not adequately represent workflow changes, particularly for Review Commons. Clarify whether publish-first requires public availability before reviewing begins or only before review results are disclosed and independently of the journal publication decision. | | | |
| K8 | The review identifies eight rows with completed extraction and numeric values that remain provisional and are excluded from summaries. Either resolve each provisional classification or identify the specific outstanding question that justifies retaining it. | | | |
| K9 | Document the sources of the initial candidate list, the procedure for finding additions and the stopping criterion before claiming systematic coverage. Check JMIRx Bio, which appears in the official family description but not in either candidate register, and distinguish failure to meet criteria from inability to verify a historical candidate. | | | |
| K10 | Check the Crossref review-date fallback from missing `issued` to `created` against the stated methodology. Also examine earliest-date selection when a broad year interval overlaps several exact dates, and establish whether either issue affects the current results. | | | |
