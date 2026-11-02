"""Preprint / article pairs asserted by Crossref relations (D-013, D-041).

A register row may declare, under ``extraction_selector.crossref.preprint_pair``,
that its preprints may have a Version of Record on another register row:

.. code-block:: yaml

    preprint_pair:
      article_row: gates_open_research
      relation_from_preprint: is-preprint-of   # on this row's posted-content records
      relation_from_article: has-preprint      # on the article row's version-1 records
      article_version: 1

A pair is established from either side; the side(s) observed are recorded
in ``correspondence_basis`` (``is_preprint_of``, ``has_preprint`` or
``is_preprint_of+has_preprint``).  Titles never establish a pair; a DOI
that matches neither row's pattern is ignored; a preprint related to two
different articles (or an article to two preprints) is a conflict and is
left unpaired.  The paired work takes the article's canonical identifier
on both rows, so the deduplicated tables count it once and
``cross_platform_overlap.csv`` carries one line; the row series are not
changed by pairing.  Nothing here consults OpenAlex (D-041, D-066).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .identifiers import IdentifierError, canonical_doi, normalise_doi

PAIR_KEY = "preprint_pair"
SIDE_PREPRINT = "is_preprint_of"
SIDE_ARTICLE = "has_preprint"
SIDE_BOTH = f"{SIDE_PREPRINT}+{SIDE_ARTICLE}"
DEFAULT_RELATION_FROM_PREPRINT = "is-preprint-of"
DEFAULT_RELATION_FROM_ARTICLE = "has-preprint"


class PairSpecError(ValueError):
    pass


@dataclass(frozen=True)
class PairSpec:
    preprint_row: str
    article_row: str
    preprint_regex: str
    article_regex: str
    preprint_pattern: str | None
    article_pattern: str | None
    relation_from_preprint: str = DEFAULT_RELATION_FROM_PREPRINT
    relation_from_article: str = DEFAULT_RELATION_FROM_ARTICLE
    article_version: int = 1

    def is_preprint_doi(self, doi: str) -> bool:
        return re.match(self.preprint_regex, doi) is not None

    def is_article_doi(self, doi: str) -> bool:
        return re.match(self.article_regex, doi) is not None

    def is_article_version(self, doi: str) -> bool:
        """True for the configured article version, e.g. ``10.12688/gatesopenres.3003.1`` when it is 1."""
        stem = canonical_doi(doi, self.article_pattern)
        return stem != doi and doi == f"{stem}.{self.article_version}"


def _selector_block(row: Mapping[str, Any]) -> Mapping[str, Any]:
    selector = row.get("extraction_selector") or {}
    return (selector.get("crossref") or {}) if isinstance(selector, Mapping) else {}


def pair_specs(platforms: Iterable[Mapping[str, Any]]) -> list[PairSpec]:
    """Every ``preprint_pair`` declaration of the register, validated against both rows."""
    rows = {str(r["row_id"]): r for r in platforms}
    specs: list[PairSpec] = []
    for row_id, row in rows.items():
        block = _selector_block(row).get(PAIR_KEY)
        if not block:
            continue
        if not isinstance(block, Mapping) or not block.get("article_row"):
            raise PairSpecError(f"{row_id}: preprint_pair needs 'article_row'")
        article_id = str(block["article_row"])
        article = rows.get(article_id)
        if article is None:
            raise PairSpecError(f"{row_id}: preprint_pair.article_row {article_id!r} is not a register row")
        preprint_regex = _selector_block(row).get("doi_regex")
        article_regex = _selector_block(article).get("doi_regex")
        if not preprint_regex or not article_regex:
            raise PairSpecError(f"{row_id}/{article_id}: preprint_pair needs extraction_selector.crossref.doi_regex "
                                "on both rows")
        specs.append(PairSpec(
            preprint_row=row_id, article_row=article_id,
            preprint_regex=str(preprint_regex), article_regex=str(article_regex),
            preprint_pattern=row.get("doi_version_pattern") or None,
            article_pattern=article.get("doi_version_pattern") or None,
            relation_from_preprint=str(block.get("relation_from_preprint") or DEFAULT_RELATION_FROM_PREPRINT),
            relation_from_article=str(block.get("relation_from_article") or DEFAULT_RELATION_FROM_ARTICLE),
            article_version=int(block.get("article_version") or 1)))
    return specs


def _relation_targets(relation_json: str, relation_type: str) -> list[str]:
    """Normalised DOI targets of one relation type in a stored ``relation_json``."""
    if not relation_json:
        return []
    try:
        relation = json.loads(relation_json)
    except json.JSONDecodeError:
        return []
    out: list[str] = []
    for entry in (relation or {}).get(relation_type) or []:
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("id-type") or "").lower() not in ("doi", ""):
            continue
        try:
            out.append(normalise_doi(str(entry.get("id") or "")))
        except IdentifierError:
            continue
    return [d for d in out if d]


@dataclass
class PairIndex:
    """Pairs of one ``PairSpec`` as canonical identifiers (version suffix stripped)."""
    spec: PairSpec
    sides: dict[tuple[str, str], set[str]] = field(default_factory=dict)   # (preprint, article) -> sides seen
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    _by_preprint: dict[str, str] = field(default_factory=dict)
    _by_article: dict[str, str] = field(default_factory=dict)

    def add(self, preprint_doi: str, article_doi: str, side: str) -> None:
        pre = canonical_doi(preprint_doi, self.spec.preprint_pattern)
        art = canonical_doi(article_doi, self.spec.article_pattern)
        self.sides.setdefault((pre, art), set()).add(side)

    def resolve(self) -> "PairIndex":
        by_pre: dict[str, set[str]] = {}
        by_art: dict[str, set[str]] = {}
        for pre, art in self.sides:
            by_pre.setdefault(pre, set()).add(art)
            by_art.setdefault(art, set()).add(pre)
        self._by_preprint, self._by_article, self.conflicts = {}, {}, []
        for (pre, art), seen in sorted(self.sides.items()):
            if len(by_pre[pre]) > 1 or len(by_art[art]) > 1:
                self.conflicts.append({"preprint": pre, "article": art, "sides": sorted(seen),
                                       "reason": "one record related to several counterparts"})
                continue
            self._by_preprint[pre] = art
            self._by_article[art] = pre
        return self

    @staticmethod
    def _basis(seen: set[str]) -> str:
        if seen == {SIDE_PREPRINT, SIDE_ARTICLE}:
            return SIDE_BOTH
        return next(iter(seen))

    def lookup(self, row_id: str, canonical: str) -> tuple[str, str] | None:
        """(canonical identifier, correspondence basis) for a paired work on either row, else None."""
        if row_id == self.spec.preprint_row and canonical in self._by_preprint:
            art = self._by_preprint[canonical]
            return art, self._basis(self.sides[(canonical, art)])
        if row_id == self.spec.article_row and canonical in self._by_article:
            pre = self._by_article[canonical]
            return canonical, self._basis(self.sides[(pre, canonical)])
        return None

    @property
    def pairs(self) -> list[tuple[str, str, str]]:
        return [(pre, art, self._basis(self.sides[(pre, art)])) for pre, art in sorted(self._by_preprint.items())]

    def summary(self) -> dict[str, Any]:
        counts = {SIDE_PREPRINT: 0, SIDE_ARTICLE: 0, SIDE_BOTH: 0}
        for _, _, basis in self.pairs:
            counts[basis] += 1
        return {"preprint_row": self.spec.preprint_row, "article_row": self.spec.article_row,
                "n_pairs": len(self._by_preprint), "by_basis": counts, "n_conflicts": len(self.conflicts),
                "conflicts": self.conflicts}


def build_pair_index(spec: PairSpec, preprint_works: Iterable[Mapping[str, str]],
                     article_works: Iterable[Mapping[str, str]]) -> PairIndex:
    """Collect pair edges from both rows' interim work records (``relation_json``)."""
    index = PairIndex(spec)
    for r in preprint_works:
        if r.get("type") != "posted-content":
            continue
        try:
            doi = normalise_doi(r["doi"])
        except IdentifierError:
            continue
        if not spec.is_preprint_doi(doi):
            continue
        for target in _relation_targets(r.get("relation_json", ""), spec.relation_from_preprint):
            if spec.is_article_doi(target):
                index.add(doi, target, SIDE_PREPRINT)
    for r in article_works:
        if r.get("type") != "journal-article":
            continue
        try:
            doi = normalise_doi(r["doi"])
        except IdentifierError:
            continue
        if not spec.is_article_doi(doi) or not spec.is_article_version(doi):
            continue
        for target in _relation_targets(r.get("relation_json", ""), spec.relation_from_article):
            if spec.is_preprint_doi(target):
                index.add(target, doi, SIDE_ARTICLE)
    return index.resolve()


class PairIndexes:
    """All pair indexes of a run, addressed by row."""

    def __init__(self, indexes: Iterable[PairIndex] = ()) -> None:
        self._by_row: dict[str, list[PairIndex]] = {}
        self.indexes = list(indexes)
        for index in self.indexes:
            for row_id in (index.spec.preprint_row, index.spec.article_row):
                self._by_row.setdefault(row_id, []).append(index)

    def lookup(self, row_id: str, canonical: str) -> tuple[str, str] | None:
        for index in self._by_row.get(row_id, ()):
            hit = index.lookup(row_id, canonical)
            if hit:
                return hit
        return None

    def rows(self) -> set[str]:
        return set(self._by_row)

    def summary(self) -> list[dict[str, Any]]:
        return [index.summary() for index in self.indexes]
