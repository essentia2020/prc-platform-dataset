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

from ..common.identifiers import is_doi_like, normalise_doi

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
    # record type -> "prefix" | "issn": which key builds that type's work scope
    # when a row declares both. Peer-review scopes are always prefix-based.
    scope_keys: dict[str, str] = field(default_factory=dict)
    doi_regex: re.Pattern | None = None
    exclude_doi_regex: re.Pattern | None = None
    container_titles: list[str] = field(default_factory=list)
    review_doi_prefix: str | None = None
    review_doi_regex: re.Pattern | None = None
    exclude_title_regex: re.Pattern | None = None
    target_filter: str | None = None          # "external" for qeios_external_works
    journals: list[JournalRule] = field(default_factory=list)
    egusphere_regex: re.Pattern | None = None
    selector_status: str = ""
    register_status: str = ""

    # ------------------------------------------------------------ scopes
    @property
    def pending(self) -> bool:
        return self.selector_status.startswith("pending")

    def work_prefixes(self) -> list[str]:
        return list(self.prefixes)

    def work_keys(self, record_type: str | None = None) -> list[str]:
        """Scope keys for one work record type: owner prefixes or ``issn:<issn>``.

        With only one kind declared, that kind is used. With both, the row's
        ``scope_keys`` names the kind per record type; ``record_type=None``
        returns the union (diagnostics only).
        """
        issn_keys = [f"issn:{i}" for i in self.issns]
        if record_type is None:
            return list(self.prefixes) + issn_keys
        kind = self.scope_keys.get(record_type) or ("issn" if self.issns and not self.prefixes else "prefix")
        return issn_keys if kind == "issn" else list(self.prefixes)

    def review_prefixes(self) -> list[str]:
        out = list(self.prefixes)
        if self.review_doi_prefix and self.review_doi_prefix not in out:
            out.append(self.review_doi_prefix)
        return out

    # ------------------------------------------------------------- works
    def doi_in_scope(self, doi: str) -> bool:
        """DOI-level test used for works and for review targets."""
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
        doi = normalise_doi(item.get("DOI", ""))
        if not self.doi_in_scope(doi):
            return False
        if self.container_titles:
            titles = [t.strip() for t in _as_list(item.get("container-title"))]
            if not any(t in self.container_titles for t in titles):
                return False
        return True

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
        """Is this peer-review record attributable to the row?"""
        if item.get("type") != REVIEW_RECORD_TYPE or REVIEW_RECORD_TYPE not in self.record_types:
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
        return any(t.doi and self.doi_in_scope(t.doi) for t in targets if not t.flag)


@dataclass(frozen=True)
class ReviewTarget:
    raw: str
    id_type: str
    doi: str          # normalised DOI when id_type is doi-like, else ""
    flag: str         # "", "placeholder", "malformed", "self_reference", "missing"


def review_targets(item: Mapping[str, Any]) -> list[ReviewTarget]:
    """Flatten ``relation.is-review-of`` with the three target flags."""
    relation = item.get("relation") or {}
    entries = relation.get("is-review-of") if isinstance(relation, Mapping) else None
    review_doi = normalise_doi(item.get("DOI", "")) if item.get("DOI") else ""
    if not entries:
        return [ReviewTarget("", "", "", "missing")]
    out: list[ReviewTarget] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            out.append(ReviewTarget(str(entry), "", "", "malformed"))
            continue
        raw = str(entry.get("id", "")).strip()
        id_type = str(entry.get("id-type", "")).strip().lower()
        doi = ""
        flag = ""
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
            elif review_doi and doi == review_doi:
                flag = "self_reference"
        elif id_type in ("url", "uri"):
            if not raw.lower().startswith(("http://", "https://")):
                flag = "malformed"
        elif not raw:
            flag = "malformed"
        out.append(ReviewTarget(raw, id_type, doi, flag))
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
    issns = [i.strip().upper() for i in _as_list(block.get("issn")) if i and i.strip()]
    for issn in issns:
        if not ISSN_RE.match(issn):
            raise SelectorError(f"row {row.get('row_id')}: invalid ISSN selector {issn!r}")
    if issns and not (block.get("doi_regex") or block.get("container_titles")):
        raise SelectorError(f"row {row.get('row_id')}: an issn selector requires doi_regex or "
                            "container_titles (an ISSN walk is not restricted to one DOI prefix)")
    prefixes = [p for p in _as_list(block.get("prefix")) if p]
    if not prefixes and not issns and not block.get("journals"):
        raise SelectorError(f"row {row.get('row_id')}: crossref selector needs prefix or issn")
    scope_keys = {str(k): str(v) for k, v in (block.get("scope_keys") or {}).items()}
    for record_type, kind in scope_keys.items():
        if kind not in ("prefix", "issn"):
            raise SelectorError(f"row {row.get('row_id')}: scope_keys[{record_type}] must be prefix or issn")
        if record_type == REVIEW_RECORD_TYPE:
            raise SelectorError(f"row {row.get('row_id')}: peer-review scopes are always prefix-based")
        if (kind == "issn" and not issns) or (kind == "prefix" and not prefixes):
            raise SelectorError(f"row {row.get('row_id')}: scope_keys[{record_type}] = {kind} "
                                f"but the selector declares no {kind}")
    if prefixes and issns:
        uncovered = [t for t in _as_list(block.get("record_types"))
                     if t != REVIEW_RECORD_TYPE and t not in scope_keys]
        if uncovered:
            raise SelectorError(f"row {row.get('row_id')}: prefix and issn both declared; scope_keys "
                                f"must name the key for {uncovered}")
    return CrossrefSelector(
        row_id=str(row["row_id"]),
        prefixes=prefixes,
        record_types=_as_list(block.get("record_types")),
        issns=issns,
        scope_keys=scope_keys,
        doi_regex=_compile(block.get("doi_regex")),
        exclude_doi_regex=_compile(block.get("exclude_doi_regex")),
        container_titles=_as_list(block.get("container_titles")),
        review_doi_prefix=block.get("review_doi_prefix"),
        review_doi_regex=_compile(block.get("review_doi_regex")),
        exclude_title_regex=_compile(block.get("exclude_title_regex")),
        target_filter=target_filter,
        journals=journals,
        egusphere_regex=egusphere,
        selector_status=str(block.get("selector_status") or ""),
        register_status=str(row.get("register_status") or ""),
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
                for key in sel.work_keys(record_type):
                    scopes.add(CrossrefScope(key, record_type))
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
