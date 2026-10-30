"""Row selectors compiled from ``config/platforms.yaml``.

Every rule that decides whether a source record belongs to a register row
lives here, so the extraction stage (interim CSVs) and the normalisation
stage (record-level files) apply identical logic.

Crossref retrieval is organised in *scopes*: one cursor walk per
(selector key, record type).  The key is a DOI owner prefix
(``works__<prefix>__<type>``) or a journal ISSN
(``works__issn_<issn>__<type>``).  Shared keys (for example 10.12688) are
retrieved once and split per row by DOI regex — never by bare key.

The Crossref ``prefix`` filter selects by the *current owner* prefix, so
records acquired through a title transfer keep their old DOI prefix but are
retrieved under the acquiring member's prefix.  Rows whose records are
owned by a large shared prefix, or whose original DOIs were aliased to new
primaries, declare an ``issn`` selector instead, which is owner-independent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..common.identifiers import collapse_repeated_slashes, identifier_flag, is_doi_like, normalise_doi
from ..common.correspondence import correspondence_index

PLACEHOLDER_TARGET_RE = re.compile(
    r"^(?:10\.\d{4,9}/(?:x+|placeholder|tbd|na|n/a|none|0+|example|test)\b.*|10\.x+/.*|10\.1234/.*)$",
    re.IGNORECASE)

WORK_RECORD_TYPES = ("journal-article", "posted-content")
_FINAL_ARTICLE_RE = re.compile(r"^10\.5194/([a-z]+)-\d+-\d+-\d{4}$")
REVIEW_RECORD_TYPE = "peer-review"


class SelectorError(ValueError):
    pass


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def _compile(pattern: str | None) -> re.Pattern | None:
    if not pattern:
        return None
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise SelectorError(f"invalid regex {pattern!r}: {exc}") from exc


@dataclass(frozen=True)
class JournalRule:
    journal_id: str
    title: str
    regexes: tuple[re.Pattern, ...]
    egusphere_regime: bool


ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dXx]$")


@dataclass
class CrossrefSelector:
    row_id: str
    prefixes: list[str]
    record_types: list[str]
    issns: list[str] = field(default_factory=list)
    doi_regex: re.Pattern | None = None
    exclude_doi_regex: re.Pattern | None = None
    container_titles: list[str] = field(default_factory=list)
    review_doi_prefixes: list[str] = field(default_factory=list)   # owner prefixes of review records
    review_doi_regex: re.Pattern | None = None
    exclude_title_regex: re.Pattern | None = None
    evaluation_record_types: list[str] = field(default_factory=list)  # non-peer-review types that are evaluations
    evaluation_doi_regex: re.Pattern | None = None
    companion_title_regex: re.Pattern | None = None   # journal-article companions (review reports, responses)
    sample_work_doi: str = ""
    sample_review_doi: str = ""
    target_filter: str | None = None          # "external" for qeios_external_works / pci_recommendations
    journals: list[JournalRule] = field(default_factory=list)
    egusphere_regex: re.Pattern | None = None
    selector_status: str = ""
    register_status: str = ""
    work_correspondences: dict[str, tuple[str, str]] = field(default_factory=dict)

    # ------------------------------------------------------------ scopes
    @property
    def pending(self) -> bool:
        return self.selector_status.startswith("pending")

    def work_prefixes(self) -> list[str]:
        return list(self.prefixes)

    def work_keys(self) -> list[str]:
        """Scope keys for work record types: owner prefixes and ``issn:<issn>``."""
        return list(self.prefixes) + [f"issn:{i}" for i in self.issns]

    @property
    def review_doi_prefix(self) -> str | None:
        """First declared review owner prefix (compatibility accessor)."""
        return self.review_doi_prefixes[0] if self.review_doi_prefixes else None

    def review_prefixes(self) -> list[str]:
        """Owner prefixes walked for peer-review records: the work prefixes
        plus every declared ``review_doi_prefix`` (a string or a list — a
        row's reviews may be owned by another member than its works, e.g.
        F1000Research → 10.5256, Open Research Europe → 10.68336)."""
        out = list(self.prefixes)
        for prefix in self.review_doi_prefixes:
            if prefix not in out:
                out.append(prefix)
        return out

    def record_types_include_evaluations(self) -> bool:
        """Does the row expect evaluation records (peer-review or a declared work type)?"""
        return REVIEW_RECORD_TYPE in self.record_types or bool(self.evaluation_record_types)

    def is_evaluation_record(self, item: Mapping[str, Any]) -> bool:
        """Non-peer-review record that the row treats as an evaluation (D-049).

        Peer Community In deposits recommendations, reviews and decisions as
        ``journal-article`` records carrying ``is-review-of``; the DOI regex
        selects the recommendation records.
        """
        if item.get("type") not in self.evaluation_record_types or not self.evaluation_doi_regex:
            return False
        return bool(self.evaluation_doi_regex.match(normalise_doi(item.get("DOI", ""))))

    def is_companion_item(self, item: Mapping[str, Any]) -> bool:
        """Journal-article companion (review report / author response) deposited as an article (D-050)."""
        if not self.companion_title_regex:
            return False
        return any(self.companion_title_regex.match(t.strip()) for t in _as_list(item.get("title")))

    # ------------------------------------------------------------- works
    def doi_in_scope(self, doi: str) -> bool:
        """DOI-level test used for works and for review targets."""
        if doi in self.work_correspondences:
            doi = self.work_correspondences[doi][0]
        if self.journals:
            if any(rx.match(doi) for j in self.journals for rx in j.regexes):
                return True
            return bool(self.egusphere_regex and self.egusphere_regex.match(doi))
        if self.target_filter == "external":
            return False  # the row owns reviews, not works
        if self.doi_regex and not self.doi_regex.match(doi):
            return False
        if self.exclude_doi_regex and self.exclude_doi_regex.match(doi):
            return False
        if not self.doi_regex and not any(doi.startswith(p.lower() + "/") for p in self.prefixes):
            return False
        return True

    def matches_work(self, item: Mapping[str, Any]) -> bool:
        if item.get("type") not in WORK_RECORD_TYPES or item.get("type") not in self.record_types:
            return False
        if self.is_evaluation_record(item):
            return False
        # Canonical form for selection: a repeated slash at source
        # (10.15694//mep.…) must not hide the record from its row.
        doi = collapse_repeated_slashes(normalise_doi(item.get("DOI", "")))
        if self.exclude_doi_regex and self.exclude_doi_regex.match(doi):
            return False
        if not self.container_titles:
            return self.doi_in_scope(doi)
        titles = [t.strip() for t in _as_list(item.get("container-title"))]
        title_match = any(t in self.container_titles for t in titles)
        if self.doi_regex:
            # D-060: ``doi_regex`` and ``container_titles`` are alternative
            # signals, as for review records. A record whose DOI matches the
            # regex is in scope even when its container-title is empty
            # (Access Microbiology posted-content); a record under the walked
            # prefix whose container-title matches is in scope even when the
            # regex does not match.
            in_walk = bool(self.issns) or any(doi.startswith(p.lower() + "/") for p in self.prefixes)
            return self.doi_in_scope(doi) or (title_match and in_walk)
        # Prefix- or ISSN-wide scope: the container-title is the only
        # discriminator and is required.
        return self.doi_in_scope(doi) and title_match

    def journal_for(self, doi: str) -> str | None:
        """Copernicus only: journal_id whose journal-specific regex matches."""
        for journal in self.journals:
            if any(rx.match(doi) for rx in journal.regexes):
                return journal.journal_id
        return None

    def is_egusphere(self, doi: str) -> bool:
        return bool(self.egusphere_regex and self.egusphere_regex.match(doi))

    def attribute_journal(self, item: Mapping[str, Any]) -> tuple[str, str]:
        """``(journal_id, basis)`` for a Copernicus discussion preprint.

        basis: ``journal_specific_doi`` (stem regimes), ``egusphere_is_preprint_of``
        (final-article relation whose stem is a verified journal),
        ``egusphere_container_title`` (journal title in container-title or
        group-title) or ``egusphere_unattributed`` (no attribution; the record
        is reported, never counted).
        """
        doi = normalise_doi(item.get("DOI", ""))
        journal = self.journal_for(doi)
        if journal:
            return journal, "journal_specific_doi"
        if not self.is_egusphere(doi):
            return "", "out_of_scope"
        relation = item.get("relation") or {}
        for entry in (relation.get("is-preprint-of") or []) if isinstance(relation, Mapping) else []:
            if not isinstance(entry, Mapping):
                continue
            try:
                target = normalise_doi(str(entry.get("id", "")))
            except Exception:
                continue
            match = _FINAL_ARTICLE_RE.match(target)
            if match and any(j.journal_id == match.group(1) for j in self.journals):
                return match.group(1), "egusphere_is_preprint_of"
        titles = [t.strip().lower() for t in _as_list(item.get("container-title")) + _as_list(item.get("group-title"))]
        for j in self.journals:
            if j.title and j.title.lower() in titles:
                return j.journal_id, "egusphere_container_title"
        return "", "egusphere_unattributed"

    def attribution_bases(self, item: Mapping[str, Any], reviewed_preprints=frozenset()) -> list[str]:
        """All observed attribution signals, not just the first matching one."""
        doi = normalise_doi(item.get("DOI", ""))
        if self.journal_for(doi):
            return ["doi_pattern"]
        if not self.is_egusphere(doi):
            return []
        bases = []
        relation_only = {**item, "container-title": [], "group-title": []}
        if self.attribute_journal(relation_only)[1] == "egusphere_is_preprint_of":
            bases.append("is_preprint_of")
        title_only = {**item, "relation": {}}
        if self.attribute_journal(title_only)[1] == "egusphere_container_title":
            bases.append("journal_title")
        if doi in reviewed_preprints:
            bases.append("peer_review_is_review_of")
        return bases

    # ----------------------------------------------------------- reviews
    def claims_review(self, item: Mapping[str, Any], targets: list["ReviewTarget"]) -> bool:
        """Is this evaluation record attributable to the row?"""
        if item.get("type") == REVIEW_RECORD_TYPE:
            if REVIEW_RECORD_TYPE not in self.record_types:
                return False
        elif not self.is_evaluation_record(item):
            return False
        doi = normalise_doi(item.get("DOI", ""))
        if self.review_doi_regex and self.review_doi_regex.match(doi):
            return True
        if self.target_filter == "external":
            under_prefix = any(doi.startswith(p.lower() + "/") for p in self.prefixes)
            if not under_prefix:
                return False
            valid = [t for t in targets if not t.flag and (t.doi or t.raw)]
            # A URL target identifies a work outside the row's prefix by construction.
            return bool(valid) and all(
                not t.doi or not any(t.doi.startswith(p.lower() + "/") for p in self.prefixes) for t in valid)
        if self.container_titles and not self.journals:
            titles = [t.strip() for t in _as_list(item.get("container-title"))]
            if any(t in self.container_titles for t in titles):
                return True
            if not self.doi_regex:
                # A container-title selector cannot be tested on a bare target DOI: the shared
                # publisher prefix would claim every review of every journal under it (D-054).
                return False
        return any(t.doi and self.doi_in_scope(t.doi) for t in targets if not t.flag)


@dataclass(frozen=True)
class ReviewTarget:
    raw: str
    id_type: str
    doi: str          # normalised DOI when id_type is doi-like, else "" (repeated slashes collapsed)
    flag: str         # "", "placeholder", "malformed", "self_reference", "missing"
    relation_type: str = "is-review-of"
    asserted_by: str = ""   # Crossref ``asserted-by``: subject / object / ""
    doi_flag: str = ""      # "repeated_slash" when the raw target DOI had a run of slashes


def review_targets(item: Mapping[str, Any]) -> list[ReviewTarget]:
    """Flatten ``relation.is-review-of`` with the target flags.

    One ``ReviewTarget`` per relation line as asserted by Crossref; the same
    (review, target) pair may appear twice with different ``asserted_by``
    values — the normalise key absorbs the duplicate, the interim keeps both.
    """
    relation = item.get("relation") or {}
    entries = relation.get("is-review-of") if isinstance(relation, Mapping) else None
    review_doi = collapse_repeated_slashes(normalise_doi(item.get("DOI", ""))) if item.get("DOI") else ""
    if not entries:
        return [ReviewTarget("", "", "", "missing")]
    out: list[ReviewTarget] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            out.append(ReviewTarget(str(entry), "", "", "malformed"))
            continue
        raw = str(entry.get("id", "")).strip()
        id_type = str(entry.get("id-type", "")).strip().lower()
        asserted = str(entry.get("asserted-by", "") or "").strip().lower()
        doi = ""
        flag = ""
        doi_flag = ""
        if id_type == "doi" or (not id_type and raw.lower().startswith("10.")):
            try:
                doi = normalise_doi(raw)
            except Exception:
                doi = raw.lower()
            if PLACEHOLDER_TARGET_RE.match(doi):
                flag = "placeholder"
            elif not doi or not is_doi_like(doi):
                flag = "malformed"
                doi = ""
            else:
                doi_flag = identifier_flag(doi)
                doi = collapse_repeated_slashes(doi)
                if review_doi and doi == review_doi:
                    flag = "self_reference"
        elif id_type in ("url", "uri"):
            if not raw.lower().startswith(("http://", "https://")):
                flag = "malformed"
        elif not raw:
            flag = "malformed"
        out.append(ReviewTarget(raw, id_type, doi, flag, asserted_by=asserted, doi_flag=doi_flag))
    return out


# ----------------------------------------------------------------- loading
def compile_crossref_selector(row: Mapping[str, Any]) -> CrossrefSelector | None:
    block = (row.get("extraction_selector") or {}).get("crossref")
    if not isinstance(block, Mapping):
        return None
    journals: list[JournalRule] = []
    egusphere = None
    for entry in block.get("journals") or []:
        sel = entry.get("discussion_selector") or {}
        regexes = tuple(_compile(r) for r in sel.get("journal_specific_doi_regex") or [])
        journals.append(JournalRule(str(entry["journal_id"]), str(entry.get("title", "")),
                                    tuple(r for r in regexes if r), bool(sel.get("egusphere_regime"))))
    regime = block.get("egusphere_regime")
    if isinstance(regime, Mapping) and regime.get("doi_regex"):
        egusphere = _compile(regime["doi_regex"])
    target_filter = None
    if "target_filter" in block:
        target_filter = "external"
    evaluation_types = _as_list(block.get("evaluation_record_types"))
    for t in evaluation_types:
        if t == REVIEW_RECORD_TYPE or t not in WORK_RECORD_TYPES:
            raise SelectorError(f"row {row.get('row_id')}: evaluation_record_types may only name work record "
                                f"types deposited as evaluations, got {t!r}")
    if evaluation_types and not block.get("evaluation_doi_regex"):
        raise SelectorError(f"row {row.get('row_id')}: evaluation_record_types requires evaluation_doi_regex")
    review_prefixes = [p for p in _as_list(block.get("review_doi_prefix")) if p]
    issns = [i.strip().upper() for i in _as_list(block.get("issn")) if i and i.strip()]
    for issn in issns:
        if not ISSN_RE.match(issn):
            raise SelectorError(f"row {row.get('row_id')}: invalid ISSN selector {issn!r}")
    if issns and not block.get("doi_regex"):
        raise SelectorError(f"row {row.get('row_id')}: an issn selector requires doi_regex "
                            "(an ISSN walk is not restricted to one DOI prefix)")
    prefixes = [p for p in _as_list(block.get("prefix")) if p]
    if not prefixes and not issns and not block.get("journals"):
        raise SelectorError(f"row {row.get('row_id')}: crossref selector needs prefix or issn")
    return CrossrefSelector(
        row_id=str(row["row_id"]),
        prefixes=prefixes,
        record_types=_as_list(block.get("record_types")),
        issns=issns,
        doi_regex=_compile(block.get("doi_regex")),
        exclude_doi_regex=_compile(block.get("exclude_doi_regex")),
        container_titles=_as_list(block.get("container_titles")),
        review_doi_prefixes=review_prefixes,
        review_doi_regex=_compile(block.get("review_doi_regex")),
        exclude_title_regex=_compile(block.get("exclude_title_regex")),
        evaluation_record_types=evaluation_types,
        evaluation_doi_regex=_compile(block.get("evaluation_doi_regex")),
        companion_title_regex=_compile(block.get("companion_title_regex")),
        sample_work_doi=str(block.get("sample_work_doi") or ""),
        sample_review_doi=str(block.get("sample_review_doi") or ""),
        target_filter=target_filter,
        journals=journals,
        egusphere_regex=egusphere,
        selector_status=str(block.get("selector_status") or ""),
        register_status=str(row.get("register_status") or ""),
        work_correspondences=correspondence_index(row),
    )


def crossref_selectors(rows: Iterable[Mapping[str, Any]], include_pending: bool = False
                       ) -> list[CrossrefSelector]:
    out = []
    for row in rows:
        if row.get("data_source") not in ("crossref", "both"):
            continue
        sel = compile_crossref_selector(row)
        if sel is None:
            raise SelectorError(f"row {row.get('row_id')} declares a Crossref source without a selector")
        if sel.pending and not include_pending:
            continue
        out.append(sel)
    return out


@dataclass(frozen=True)
class CrossrefScope:
    """One retrieval unit: ``key`` is an owner prefix (``10.12688``) or ``issn:<issn>``."""
    key: str
    record_type: str

    @property
    def kind(self) -> str:
        return "issn" if self.key.startswith("issn:") else "prefix"

    @property
    def prefix(self) -> str:
        """Owner prefix for prefix scopes; empty for ISSN scopes."""
        return "" if self.kind == "issn" else self.key

    @property
    def issn(self) -> str:
        return self.key.split(":", 1)[1] if self.kind == "issn" else ""

    @property
    def scope_id(self) -> str:
        if self.kind == "issn":
            return f"works__issn_{self.issn}__{self.record_type}"
        return f"works__{self.key}__{self.record_type}"


def crossref_scopes(selectors: Iterable[CrossrefSelector], kinds: str = "all") -> list[CrossrefScope]:
    """Distinct (key, type) pairs; ``kinds`` = all / works / reviews.

    Peer-review scopes are prefix-based only: review records are retrieved
    under the row's prefixes and ``review_doi_prefix``, never by ISSN.
    """
    scopes: set[CrossrefScope] = set()
    for sel in selectors:
        for record_type in sel.record_types:
            if record_type == REVIEW_RECORD_TYPE:
                if kinds in ("all", "reviews"):
                    for prefix in sel.review_prefixes():
                        scopes.add(CrossrefScope(prefix, record_type))
            elif kinds in ("all", "works"):
                for key in sel.work_keys():
                    scopes.add(CrossrefScope(key, record_type))
        if kinds in ("all", "reviews"):
            # Evaluation records deposited under a work type (PCI): the same
            # prefix walk feeds the review stage; the walk is shared, not repeated.
            for record_type in sel.evaluation_record_types:
                for prefix in sel.prefixes:
                    scopes.add(CrossrefScope(prefix, record_type))
    return sorted(scopes, key=lambda s: (s.key, s.record_type))


@dataclass(frozen=True)
class ScietyScope:
    row_id: str
    group_slug: str
    group_id: str | None
    role: str

    @property
    def scope_id(self) -> str:
        return f"evaluations__{self.group_slug}"

    @property
    def publisher_account_url(self) -> str:
        return f"https://sciety.org/groups/{self.group_slug}"

    def account_matches(self, account_id: str) -> bool:
        account_id = account_id.rstrip("/").lower()
        candidates = {self.publisher_account_url.lower()}
        if self.group_id:
            candidates.add(f"https://sciety.org/groups/{self.group_id}".lower())
        return account_id in candidates


def sciety_scopes(rows: Iterable[Mapping[str, Any]]) -> list[ScietyScope]:
    out: list[ScietyScope] = []
    for row in rows:
        block = (row.get("extraction_selector") or {}).get("sciety")
        if not isinstance(block, Mapping):
            continue
        role = str(block.get("role") or "primary")
        slugs = _as_list(block.get("group_slugs")) or _as_list(block.get("group_slug"))
        if not slugs:
            raise SelectorError(f"row {row.get('row_id')} declares a Sciety selector without a group slug")
        for slug in slugs:
            group_id = block.get("group_id") if len(slugs) == 1 else None
            out.append(ScietyScope(str(row["row_id"]), slug, group_id, role))
    return out
