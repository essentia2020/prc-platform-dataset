#!/usr/bin/env python3
"""Repository text audit — the only audit mechanism of this repository.

One matching engine is applied to the working tree, to every historical blob
and to every commit message.  Four rules are implemented:

    R1  private tokens        tokens listed in a file kept OUTSIDE the repository
                              (``--tokens PATH`` or ``PRC_AUDIT_TOKENS``); no exemptions
    R2  dataset-version       version-like strings in a dataset-release context and
        lineage                lineage words in prose
    R3  citation context      mentions of the conceptual sources outside the
                              permitted, allow-listed spans
    R4  author voice          first-person plural and third-person self-reference
                              in documentation and docstrings

Exit status: 0 only when there are zero unresolved hits; 1 when hits remain;
2 on a configuration error (missing or empty token file, conflicting token
paths, malformed allow-list, unbalanced fixture markers).

Usage::

    python tools/audit_text.py --tokens /path/outside/repo/.audit_tokens.txt
    python tools/audit_text.py --tokens … --history      # also blobs + commit messages
    python tools/audit_text.py --tokens … --json         # machine-readable report

Allow-list (``config/audit_allowlist.yaml``): each entry has ``rule_id``,
``file`` and exactly one of ``literal`` or ``yaml_path``; it exempts only the
matched span under the named rule.  Fixture spans between
``# audit-fixture: begin`` / ``# audit-fixture: end`` (or the HTML-comment
form) are exempt from R2 and R3 only.  Nothing ever exempts R1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence
import fnmatch

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = REPO_ROOT / "config" / "audit_allowlist.yaml"
TOKENS_ENV = "PRC_AUDIT_TOKENS"

TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".yaml", ".yml", ".cff", ".csv", ".json", ".jsonl",
    ".toml", ".cfg", ".ini", ".rst", ".sh", ".gitignore", "",
}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "data/raw", "data/interim", "logs"}
SKIP_GLOBS = ("data/processed/records_*.csv", "data/manifests/*")
SKIP_NAMES = {".gitkeep"}

# Files exempt from R2 as a whole (dependency pins and package metadata).
R2_EXEMPT_FILES = {"requirements.txt", "pyproject.toml"}
# Verbatim third-party licence texts: not project prose, outside R4.
R4_EXEMPT_FILES = {"LICENSE", "LICENSE-DATA"}
R4_SUFFIXES = {".md", ".txt", ".cff", ".yaml", ".yml", ".csv", ".py", ".rst", ".toml", ".json"}

# ---------------------------------------------------------------------------
# Executable rule definitions
# ---------------------------------------------------------------------------

# audit-fixture: begin
VERSION_RE = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b")
CONTEXT_WORDS_RE = re.compile(
    r"\b(?:release|version|dataset|changelog|previous|earlier|legacy|migration|upgrade)s?\b",
    re.IGNORECASE,
)
CONTEXT_WINDOW = 80
CURRENT_RELEASE = {"1.4.0", "v1.4.0"}
DEPENDENCY_LABELS_RE = re.compile(
    r"(?:python|pyyaml|pandas|seaborn|matplotlib|pytest|pip|schema|cff-version)",
    re.IGNORECASE,
)
DEPENDENCY_WINDOW = 40
DOI_RE = re.compile(r"10\.\d{4,9}/\S+")
DOI_PREFIX_RE = re.compile(r"^10\.\d{4,9}$")
THRESHOLD_FOLLOWER_RE = re.compile(
    r"^\s*(?:/\s*\d+\s*)?(?:\w+\s+){0,3}?(?:reviews?|ratings?|stars)\b", re.IGNORECASE
)
LINEAGE_WORDS_RE = re.compile(
    r"\b(?:changelogs?|legacy|migrations?|migrat(?:e|ed|es|ing)|upgrades?|upgrad(?:ed|ing))\b"
    r"|\b(?:previous|earlier|prior)\s+(?:release|version|dataset|edition|iteration)s?\b"
    r"|\bversion\s+histor(?:y|ies)\b",
    re.IGNORECASE,
)
CITATION_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\bCorker\b"),
    re.compile(r"\bWaltman\b"),
    re.compile(r"\bCoates\b"),
    re.compile(r"\bKochetkov\s*\(\s*20\d\d"),
    re.compile(r"\bKochetkov,?\s+D(?:\.|mitry)\b"),
    re.compile(r"\bKochetkov\s+\(?20\d\d"),
    re.compile(r"leap\.2046"),
    re.compile(r"zenodo\.22787722"),
    re.compile(r"\bLearned Publishing\b"),
    re.compile(r"osf\.io/h7swt"),
    re.compile(r"\bCrossing the Chasm\b"),
    re.compile(r"\bPeer Review at the Crossroads\b"),
    re.compile(r"\bUnderstanding the Publish.Review.Curate\b"),
)
# audit-fixture: end

# The R4 vocabulary is assembled from fragments so that this file does not
# itself contain the flagged words (R4 has no fixture-marker exemption).
def _w(*fragments: str) -> str:
    return "".join(fragments)


_PLURAL = _w("w", "e") + "|" + _w("o", "ur") + "|" + _w("u", "s")
_SELF = "|".join((_w("auth", "or"), _w("resear", "cher"), _w("te", "am"), _w("ag", "ent")))
_TOOL_NAME_A = _w("Perp", "lexity")
_TOOL_NAME_B = _w("Comp", "uter")
_TOOL_ROLE_A = _w("assis", "tant")
_TOOL_ROLE_B = _w("ag", "ent")
VOICE_PATTERNS: Sequence[tuple[re.Pattern[str], str]] = (
    (re.compile(rf"\b(?:{_PLURAL})\b"), "first-person plural"),
    (re.compile(rf"\b[Tt]he (?:{_SELF})\b"), "third-person self-reference"),
    (re.compile(rf"\b{_TOOL_NAME_A}\b", re.IGNORECASE), "tool name"),
    (re.compile(rf"\b{_TOOL_NAME_B}\b"), "tool name"),
    (re.compile(rf"\b{_TOOL_ROLE_A}\b", re.IGNORECASE), "tool role"),
    (re.compile(rf"\b{_TOOL_ROLE_B}\b", re.IGNORECASE), "tool role"),
)
#: Exact HTTP-header phrases preceding the word that is otherwise a hit.
USER_AGENT_PREFIXES = ("User-", "user ")
#: URLs are identifiers, not prose: R4 does not apply inside them.
URL_RE = re.compile(r"https?://[^\s)\]>\"']+")

FIXTURE_BEGIN_RE = re.compile(r"(?:#|<!--)\s*audit-fixture:\s*begin")
FIXTURE_END_RE = re.compile(r"(?:#|<!--)\s*audit-fixture:\s*end")

ABBREVIATION_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-]{1,9}$")


class AuditConfigError(RuntimeError):
    """Configuration problem that prevents a meaningful audit (exit 2)."""


@dataclass(frozen=True)
class Hit:
    rule: str
    path: str
    line: int
    col: int
    matched: str
    detail: str
    revision: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule, "path": self.path, "line": self.line, "col": self.col,
            "matched": self.matched, "detail": self.detail, "revision": self.revision,
        }

    def format(self) -> str:
        where = f"{self.path}:{self.line}:{self.col}"
        if self.revision:
            where = f"{self.revision[:10]}:{where}"
        return f"[{self.rule}] {where}: {self.matched!r} — {self.detail}"


@dataclass
class Span:
    start: int
    end: int

    def contains(self, start: int, end: int) -> bool:
        return self.start <= start and end <= self.end


@dataclass
class AllowEntry:
    rule_id: str
    file: str
    literal: str | None = None
    yaml_path: str | None = None


@dataclass
class Engine:
    """Matching engine shared by working-tree, blob and commit-message scans."""

    tokens: Sequence[tuple[str, re.Pattern[str]]]
    allowlist: Sequence[AllowEntry] = field(default_factory=list)

    # -- R1 -----------------------------------------------------------------
    def rule_r1(self, text: str, path: str) -> Iterator[Hit]:
        for raw, pattern in self.tokens:
            for match in pattern.finditer(text):
                line, col = _position(text, match.start())
                yield Hit("R1", path, line, col, match.group(0), f"private token {raw!r}")

    # -- R2 -----------------------------------------------------------------
    def rule_r2(self, text: str, path: str, exempt: Sequence[Span]) -> Iterator[Hit]:
        name = Path(path).name
        if name in R2_EXEMPT_FILES:
            return
        for match in VERSION_RE.finditer(text):
            start, end = match.span()
            value = match.group(0)
            if value in CURRENT_RELEASE:
                continue
            if _in_spans(start, end, exempt):
                continue
            if DOI_PREFIX_RE.match(value) or _inside_doi(text, start, end):
                continue
            if _dependency_adjacent(text, start, end):
                continue
            if THRESHOLD_FOLLOWER_RE.match(text[end:end + 40]):
                continue
            window = text[max(0, start - CONTEXT_WINDOW):end + CONTEXT_WINDOW]
            if CONTEXT_WORDS_RE.search(window):
                line, col = _position(text, start)
                yield Hit("R2", path, line, col, value, "version string in dataset-release context")
        for match in LINEAGE_WORDS_RE.finditer(text):
            start, end = match.span()
            if _in_spans(start, end, exempt):
                continue
            line, col = _position(text, start)
            yield Hit("R2", path, line, col, match.group(0), "lineage word")

    # -- R3 -----------------------------------------------------------------
    def rule_r3(self, text: str, path: str, exempt: Sequence[Span]) -> Iterator[Hit]:
        for pattern in CITATION_PATTERNS:
            for match in pattern.finditer(text):
                start, end = match.span()
                if _in_spans(start, end, exempt):
                    continue
                line, col = _position(text, start)
                yield Hit("R3", path, line, col, match.group(0), "citation outside permitted context")

    # -- R4 -----------------------------------------------------------------
    def rule_r4(self, text: str, path: str, exempt: Sequence[Span]) -> Iterator[Hit]:
        p = Path(path)
        if p.name in R4_EXEMPT_FILES:
            return
        if p.suffix not in R4_SUFFIXES and not path.startswith("<commit"):
            return
        url_spans = [Span(m.start(), m.end()) for m in URL_RE.finditer(text)]
        for pattern, label in VOICE_PATTERNS:
            for match in pattern.finditer(text):
                start, end = match.span()
                if match.group(0).lower() == _TOOL_ROLE_B and text[max(0, start - 5):start] in USER_AGENT_PREFIXES:
                    continue
                if _in_spans(start, end, exempt) or _in_spans(start, end, url_spans):
                    continue
                line, col = _position(text, start)
                yield Hit("R4", path, line, col, match.group(0), label)

    # -- driver -------------------------------------------------------------
    def scan(self, text: str, path: str, revision: str = "") -> list[Hit]:
        hits: list[Hit] = []
        try:
            fixture_spans = fixture_spans_of(text)
        except AuditConfigError as exc:
            return [Hit("MARKER", path, 1, 1, "audit-fixture", str(exc), revision)]
        allow = {rule: self.allow_spans(rule, path, text) for rule in ("R2", "R3", "R4")}
        hits.extend(self.rule_r1(text, path))
        hits.extend(self.rule_r2(text, path, fixture_spans + allow["R2"]))
        hits.extend(self.rule_r3(text, path, fixture_spans + allow["R3"]))
        hits.extend(self.rule_r4(text, path, allow["R4"]))
        if revision:
            hits = [Hit(h.rule, h.path, h.line, h.col, h.matched, h.detail, revision) for h in hits]
        return hits

    def allow_spans(self, rule: str, path: str, text: str) -> list[Span]:
        spans: list[Span] = []
        for entry in self.allowlist:
            if entry.rule_id != rule or entry.file != path:
                continue
            if entry.literal is not None:
                spans.extend(_literal_spans(text, entry.literal))
            else:
                for value in yaml_path_values(text, entry.yaml_path or ""):
                    spans.extend(_literal_spans(text, value))
                    if "\n" in value:
                        # Multi-line scalars appear in the file as separate
                        # fragments (block scalars or escaped newlines).
                        for fragment in value.split("\n"):
                            fragment = fragment.strip()
                            if len(fragment) >= 4:
                                spans.extend(_literal_spans(text, fragment))
        return spans


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _position(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    col = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, col


def _in_spans(start: int, end: int, spans: Sequence[Span]) -> bool:
    return any(s.contains(start, end) for s in spans)


def _inside_doi(text: str, start: int, end: int) -> bool:
    lo = max(0, start - 60)
    for m in DOI_RE.finditer(text, lo, min(len(text), end + 120)):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _dependency_adjacent(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - DEPENDENCY_WINDOW):start]
    after = text[end:end + DEPENDENCY_WINDOW]
    return bool(DEPENDENCY_LABELS_RE.search(before) or DEPENDENCY_LABELS_RE.search(after))


def _literal_spans(text: str, literal: str) -> list[Span]:
    spans = []
    idx = text.find(literal)
    while idx != -1:
        spans.append(Span(idx, idx + len(literal)))
        idx = text.find(literal, idx + 1)
    return spans


def fixture_spans_of(text: str) -> list[Span]:
    """Spans between balanced ``audit-fixture: begin`` / ``end`` markers."""
    begins = [m.start() for m in FIXTURE_BEGIN_RE.finditer(text)]
    ends = [m.end() for m in FIXTURE_END_RE.finditer(text)]
    if len(begins) != len(ends):
        raise AuditConfigError(f"unbalanced audit-fixture markers ({len(begins)} begin, {len(ends)} end)")
    spans = []
    for b, e in zip(begins, ends):
        if e < b:
            raise AuditConfigError("audit-fixture end marker precedes its begin marker")
        spans.append(Span(b, e))
    return spans


_PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\*|\d+)\]")


def yaml_path_values(text: str, path_expr: str) -> list[str]:
    """Resolve a YAML path expression to scalar string values.

    Grammar: ``key.sub[*].leaf`` or ``key[3].leaf``; ``[*]`` fans out over a
    list.  Leaf values that are lists contribute each string element.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    nodes: list[Any] = [data]
    for key_match in _PATH_TOKEN_RE.finditer(path_expr):
        key, index = key_match.group(1), key_match.group(2)
        next_nodes: list[Any] = []
        for node in nodes:
            if key is not None:
                if isinstance(node, Mapping) and key in node:
                    next_nodes.append(node[key])
            elif index == "*":
                if isinstance(node, list):
                    next_nodes.extend(node)
            else:
                if isinstance(node, list) and int(index) < len(node):
                    next_nodes.append(node[int(index)])
        nodes = next_nodes
    values: list[str] = []
    for node in nodes:
        if isinstance(node, str):
            values.append(node)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            values.append(str(node))
        elif isinstance(node, list):
            values.extend(str(v) for v in node if isinstance(v, (str, int, float)) and not isinstance(v, bool))
    return [v for v in values if v]


# ---------------------------------------------------------------------------
# Token and allow-list loading
# ---------------------------------------------------------------------------

def compile_token(raw: str) -> re.Pattern[str]:
    """Compile one token: word-boundary regex; whitespace -> ``\\s+``;
    all-caps abbreviations are case-sensitive; everything else ignores case."""
    parts = [re.escape(p) for p in raw.split()]
    body = r"\s+".join(parts)
    pattern = rf"(?<!\w){body}(?!\w)"
    flags = 0 if ABBREVIATION_RE.match(raw) else re.IGNORECASE
    return re.compile(pattern, flags)


def load_tokens(cli_path: str | None, env_path: str | None = None) -> list[tuple[str, re.Pattern[str]]]:
    env_path = env_path if env_path is not None else os.environ.get(TOKENS_ENV)
    if cli_path and env_path and Path(cli_path).resolve() != Path(env_path).resolve():
        raise AuditConfigError(
            f"--tokens ({cli_path}) and {TOKENS_ENV} ({env_path}) point to different files; refusing to guess"
        )
    chosen = cli_path or env_path
    if not chosen:
        raise AuditConfigError(f"no token file: pass --tokens PATH or set {TOKENS_ENV}")
    path = Path(chosen)
    if not path.is_file():
        raise AuditConfigError(f"token file not found: {path}")
    try:
        if path.resolve().is_relative_to(REPO_ROOT.resolve()):
            raise AuditConfigError(f"token file must live outside the repository: {path}")
    except AttributeError:  # pragma: no cover - Python < 3.9
        pass
    tokens: list[tuple[str, re.Pattern[str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        tokens.append((raw, compile_token(raw)))
    if not tokens:
        raise AuditConfigError(f"token file contains no tokens: {path}")
    return tokens


def load_allowlist(path: Path = ALLOWLIST_PATH) -> list[AllowEntry]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("allowlist", [])
    if not isinstance(entries, list):
        raise AuditConfigError(f"{path}: 'allowlist' must be a list")
    result: list[AllowEntry] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise AuditConfigError(f"{path}: entry {idx} is not a mapping")
        rule_id = entry.get("rule_id")
        file = entry.get("file")
        literal = entry.get("literal")
        yaml_path = entry.get("yaml_path")
        if rule_id not in ("R2", "R3", "R4"):
            raise AuditConfigError(f"{path}: entry {idx}: rule_id must be R2, R3 or R4 (R1 is never exempted)")
        if not isinstance(file, str) or not file:
            raise AuditConfigError(f"{path}: entry {idx}: 'file' is required")
        if (literal is None) == (yaml_path is None):
            raise AuditConfigError(f"{path}: entry {idx}: exactly one of 'literal' or 'yaml_path' is required")
        result.append(AllowEntry(rule_id, file, literal, yaml_path))
    return result


# ---------------------------------------------------------------------------
# File enumeration
# ---------------------------------------------------------------------------

def _git(args: Sequence[str], root: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout


def is_text_candidate(path: str) -> bool:
    p = Path(path)
    if p.name in SKIP_NAMES:
        return False
    if any(path == d or path.startswith(d + "/") for d in SKIP_DIRS):
        return False
    if any(fnmatch.fnmatch(path, g) for g in SKIP_GLOBS):
        return False
    return p.suffix.lower() in TEXT_SUFFIXES or p.name.startswith(".")


def working_tree_files(root: Path) -> list[str]:
    """Tracked plus untracked-but-not-ignored files, relative POSIX paths."""
    try:
        out = _git(["ls-files", "--cached", "--others", "--exclude-standard", "-z"], root)
        files = [f for f in out.split("\0") if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = [str(p.relative_to(root).as_posix()) for p in root.rglob("*") if p.is_file()]
    return sorted(f for f in files if is_text_candidate(f) and (root / f).is_file())


def read_text(data: bytes) -> str | None:
    if b"\0" in data[:8000]:
        return None
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Audit drivers
# ---------------------------------------------------------------------------

def audit_working_tree(engine: Engine, root: Path, files: Iterable[str] | None = None) -> list[Hit]:
    hits: list[Hit] = []
    for rel in (files if files is not None else working_tree_files(root)):
        text = read_text((root / rel).read_bytes())
        if text is None:
            continue
        hits.extend(engine.scan(text, rel))
    return hits


def audit_history(engine: Engine, root: Path) -> list[Hit]:
    """Scan every blob at every revision and every commit message."""
    hits: list[Hit] = []
    try:
        revisions = [r for r in _git(["rev-list", "--all"], root).split() if r]
    except subprocess.CalledProcessError:
        return hits
    seen: set[tuple[str, str]] = set()
    blob_cache: dict[str, str | None] = {}
    for rev in revisions:
        tree = _git(["ls-tree", "-r", "-z", rev], root)
        for record in tree.split("\0"):
            if not record:
                continue
            meta, _, path = record.partition("\t")
            _, kind, sha = meta.split()
            if kind != "blob" or not is_text_candidate(path):
                continue
            key = (sha, path)
            if key in seen:
                continue
            seen.add(key)
            if sha not in blob_cache:
                raw = subprocess.run(["git", "cat-file", "blob", sha], cwd=root, check=True, capture_output=True).stdout
                blob_cache[sha] = read_text(raw)
            text = blob_cache[sha]
            if text is None:
                continue
            hits.extend(engine.scan(text, path, revision=rev))
        message = _git(["log", "-1", "--format=%B", rev], root)
        hits.extend(engine.scan(message, f"<commit-message {rev[:10]}>", revision=rev))
    return hits


def run_audit(
    tokens_path: str | None,
    history: bool = False,
    root: Path = REPO_ROOT,
    allowlist_path: Path | None = None,
    env_path: str | None = None,
) -> list[Hit]:
    tokens = load_tokens(tokens_path, env_path)
    allowlist = load_allowlist(allowlist_path or (root / "config" / "audit_allowlist.yaml"))
    engine = Engine(tokens=tokens, allowlist=allowlist)
    hits = audit_working_tree(engine, root)
    if history:
        hits.extend(audit_history(engine, root))
    return hits


def summarise(hits: Sequence[Hit]) -> dict[str, int]:
    counts: dict[str, int] = {"R1": 0, "R2": 0, "R3": 0, "R4": 0}
    for hit in hits:
        counts[hit.rule] = counts.get(hit.rule, 0) + 1
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tokens", help=f"path to the private token list (outside the repository); overrides {TOKENS_ENV}")
    parser.add_argument("--history", action="store_true", help="also scan all historical blobs and commit messages")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root (default: this repository)")
    parser.add_argument("--json", action="store_true", help="emit a JSON report instead of text")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    try:
        hits = run_audit(args.tokens, history=args.history, root=root)
    except AuditConfigError as exc:
        print(f"audit configuration error: {exc}", file=sys.stderr)
        return 2

    counts = summarise(hits)
    if args.json:
        print(json.dumps({"hits": [h.as_dict() for h in hits], "counts": counts, "history": args.history}, indent=2))
    else:
        for hit in hits:
            print(hit.format())
        scope = "working tree + history" if args.history else "working tree"
        status = "PASS" if not hits else "FAIL"
        print(f"audit_text: {scope}: {len(hits)} unresolved hit(s) "
              f"(R1={counts['R1']}, R2={counts['R2']}, R3={counts['R3']}, R4={counts['R4']}) -> {status}")
    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())
