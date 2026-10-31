"""Immutable raw store for API responses.

Layout (root is ``data/raw/`` or ``$PRC_RAW_STORE``; never tracked by Git)::

    <root>/<source>/<scope>/<run_id>/<walk_id>/page_<n>/attempt_<k>.response.json.gz
    <root>/<source>/<scope>/<run_id>/<walk_id>/page_<n>/attempt_<k>.request.json

Rules enforced here:

* a file is written at most once; any attempt to overwrite raises
  :class:`RawStoreError` instead of replacing bytes;
* every attempt is kept, including rejected ones;
* ``walk_id`` values are allocated monotonically (``w01``, ``w02``, …) and an
  existing walk directory is never reused for a new walk.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

RAW_STORE_ENV = "PRC_RAW_STORE"
DEFAULT_RAW_ROOT = Path("data") / "raw"
_WALK_ID = re.compile(r"^w(\d{2,})$")
_SAFE = re.compile(r"^[A-Za-z0-9_.\-]+$")


class RawStoreError(RuntimeError):
    """Raised on any violation of the immutability rules."""


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def resolve_raw_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Raw root from the argument, else ``$PRC_RAW_STORE``, else ``data/raw``."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(RAW_STORE_ENV)
    return Path(env) if env else DEFAULT_RAW_ROOT


def _check_component(name: str, value: str) -> str:
    if not _SAFE.match(value):
        raise RawStoreError(f"unsafe {name} component {value!r}")
    return value


@dataclass(frozen=True)
class AttemptPaths:
    response_path: Path
    request_path: Path
    response_rel: str
    request_rel: str


class RawStore:
    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = resolve_raw_root(root)

    # ----------------------------------------------------------- directories
    def scope_dir(self, source: str, scope: str, run_id: str) -> Path:
        return (self.root / _check_component("source", source)
                / _check_component("scope", scope) / _check_component("run_id", run_id))

    def walk_dir(self, source: str, scope: str, run_id: str, walk_id: str) -> Path:
        return self.scope_dir(source, scope, run_id) / _check_component("walk_id", walk_id)

    def existing_walks(self, source: str, scope: str, run_id: str) -> list[str]:
        base = self.scope_dir(source, scope, run_id)
        if not base.is_dir():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir() and _WALK_ID.match(p.name))

    def new_walk_id(self, source: str, scope: str, run_id: str,
                    known: list[str] | None = None) -> str:
        """Next unused walk id, greater than every walk on disk or in ``known``."""
        ids = set(self.existing_walks(source, scope, run_id)) | set(known or [])
        numbers = [int(_WALK_ID.match(w).group(1)) for w in ids if _WALK_ID.match(w)]
        return f"w{(max(numbers) + 1 if numbers else 1):02d}"

    # ---------------------------------------------------------------- writes
    def attempt_paths(self, source: str, scope: str, run_id: str, walk_id: str,
                      page: int, attempt: int) -> AttemptPaths:
        if page < 1 or attempt < 1:
            raise RawStoreError("page and attempt numbers start at 1")
        page_dir = self.walk_dir(source, scope, run_id, walk_id) / f"page_{page}"
        response = page_dir / f"attempt_{attempt}.response.json.gz"
        request = page_dir / f"attempt_{attempt}.request.json"
        rel = lambda p: p.relative_to(self.root).as_posix()  # noqa: E731
        return AttemptPaths(response, request, rel(response), rel(request))

    def write_attempt(self, source: str, scope: str, run_id: str, walk_id: str,
                      page: int, attempt: int, request: dict, body: bytes) -> AttemptPaths:
        """Persist one attempt.  Refuses to touch an existing file."""
        paths = self.attempt_paths(source, scope, run_id, walk_id, page, attempt)
        if paths.response_path.exists() or paths.request_path.exists():
            raise RawStoreError(
                f"refusing to overwrite existing attempt {paths.response_rel}; "
                "raw files are immutable — start a new walk instead")
        paths.response_path.parent.mkdir(parents=True, exist_ok=True)
        # ``x`` mode makes the no-overwrite rule hold even under races.
        with open(paths.request_path, "x", encoding="utf-8", newline="\n") as handle:
            json.dump(request, handle, ensure_ascii=False, sort_keys=True, indent=1)
        with open(paths.response_path, "xb") as handle:
            with gzip.GzipFile(fileobj=handle, mode="wb", mtime=0) as gz:
                gz.write(body)
        return paths

    def next_attempt_number(self, source: str, scope: str, run_id: str,
                            walk_id: str, page: int) -> int:
        page_dir = self.walk_dir(source, scope, run_id, walk_id) / f"page_{page}"
        if not page_dir.is_dir():
            return 1
        numbers = [int(m.group(1)) for p in page_dir.iterdir()
                   if (m := re.match(r"^attempt_(\d+)\.", p.name))]
        return (max(numbers) + 1) if numbers else 1

    # ----------------------------------------------------------------- reads
    def read_response_bytes(self, response_rel: str) -> bytes:
        path = self.root / response_rel
        with gzip.open(path, "rb") as handle:
            return handle.read()

    def read_response_json(self, response_rel: str) -> object:
        return json.loads(self.read_response_bytes(response_rel).decode("utf-8"))

    def file_sha256(self, response_rel: str) -> str:
        return sha256_of_file(self.root / response_rel)
