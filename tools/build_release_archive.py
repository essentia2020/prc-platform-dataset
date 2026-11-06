"""Build a portable release ZIP from an independently verified S13 snapshot.

Standard library only. No harvesting, src imports, data writes or overwrites.
The caller supplies the snapshot root and the original PASS evidence directory.
Use --help for required, version-qualified output paths. Running this tool is
a separate approval gate from reviewing/installing it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import struct
import sys
import tempfile
import zipfile
import zlib


FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FILE_MODE = (stat.S_IFREG | 0o644) << 16
COMPRESSION_LEVEL = 9
HEX = re.compile(r"[0-9a-f]{64}")
KEEP = "data/interim/.gitkeep"
DQ = "data/processed/data_quality_log.csv"
REQUIRED_PROCESSED = {
    "data/processed/works_included.csv",
    "data/processed/normalisation_summary.json",
    "data/processed/analysis_manifest.json",
}


class ArchiveError(ValueError):
    """Fail-closed validation failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ArchiveError(message)


def safe_member(name: str) -> str:
    """Validate rather than repair input names, including Windows hazards."""
    require(isinstance(name, str) and bool(name), "Empty archive member")
    parts = name.split("/")
    require(
        "\\" not in name and not PureWindowsPath(name).drive
        and not PurePosixPath(name).is_absolute()
        and all(p not in ("", ".", "..") for p in parts),
        f"Unsafe member: {name!r}",
    )
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved |= {f"{prefix}{n}" for prefix in ("COM", "LPT") for n in "123456789¹²³"}
    for part in parts:
        require(
            not any(ord(c) < 32 or ord(c) == 127 or c in '<>:"|?*' for c in part)
            and not part.endswith((" ", "."))
            and part.split(".", 1)[0].upper() not in reserved,
            f"Non-portable member: {name!r}",
        )
    return name


def unique_names(names: list[str]) -> None:
    seen: set[str] = set()
    for name in names:
        safe_member(name)
        key = name.casefold()
        require(key not in seen, f"Duplicate/case-colliding member: {name}")
        seen.add(key)


def checked_path(path: Path) -> Path:
    """Reject symlinks and Windows reparse points, including parent aliases."""
    path = path.absolute()
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(
            not stat.S_ISLNK(info.st_mode)
            and not (getattr(info, "st_file_attributes", 0) & 0x400),
            f"Symlink/reparse point forbidden: {part}",
        )
    return path.resolve()


def digest(path: Path) -> str:
    path = checked_path(path)
    require(path.is_file(), f"Missing/non-regular file: {path}")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    text = checked_path(path).read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, f"Invalid checksum line in {path}: {line!r}")
        value, name = match.groups()
        safe_member(name)
        require(name not in result, f"Duplicate inventory path: {name}")
        result[name] = value
    require(bool(result), f"Empty inventory: {path}")
    unique_names(list(result))
    return result


def sums_bytes(hashes: dict[str, str]) -> bytes:
    return "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes)).encode("utf-8")


def external_sums(hashes: dict[str, str], archive: str, archive_hash: str, doi: str) -> bytes:
    """Historical layout, preserving the caller's payload order, ZIP last.

    The builder passes POSIX-name-sorted entries. Preserving insertion order here
    also permits exact reconstruction of the older Windows-sorted manifest.
    """
    return (
        f"# archive: {archive}\n# zenodo_doi: {doi}\n".encode("utf-8")
        + "".join(f"{value}  {name}\n" for name, value in hashes.items()).encode("utf-8")
        + f"{archive_hash}  {archive}\n".encode("utf-8")
    )


def load_evidence(evidence: Path, run_id: str, data_commit: str) -> tuple[dict, dict, dict]:
    report = json.loads(checked_path(evidence / "comparison.json").read_text(encoding="utf-8-sig"))
    require(isinstance(report, dict) and isinstance(report.get("gates"), dict), "Invalid S13 report schema")
    require(
        report.get("status") == "PASS"
        and report.get("run_id") == run_id
        and report.get("baseline_commit") == data_commit
        and report.get("protected_inputs_unchanged") is True
        and report.get("no_figure_exception") is True,
        "S13 PASS/run/data-commit/protected-input/figure binding failed",
    )
    for gate in ("raw-to-interim", "downstream"):
        value = report.get("gates", {}).get(gate, {})
        require(isinstance(value, dict) and isinstance(value.get("counts"), dict), "Invalid S13 gate schema")
        counts = value.get("counts", {})
        require(
            value.get("status") == "PASS" and value.get("comparison_performed") is True
            and value.get("network_attempts") == 0 and value.get("guard_events") == []
            and all(counts.get(k) == 0 for k in ("changed", "missing", "added")),
            f"Unaccepted S13 gate: {gate}",
        )
    validated = load_sums(evidence / "validated-input-snapshot.sha256")
    expected = load_sums(evidence / "expected-output.sha256")
    for name in validated.keys() & expected.keys():
        require(validated[name] == expected[name], f"Conflicting evidence hashes: {name}")
    require(
        report["gates"]["downstream"]["counts"].get("same") == len(expected),
        "Downstream inventory/count mismatch",
    )
    return validated, expected, report


def scan_tree(root: Path, relative: str) -> list[str]:
    directory = checked_path(root / relative)
    require(directory.is_dir(), f"Missing directory: {directory}")
    names = []
    # Do not follow links; reject them even when they point outside the inventory.
    for parent, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs + files:
            child = checked_path(Path(parent) / name)
            require(child.is_file() or child.is_dir(), f"Special file forbidden: {child}")
        for name in files:
            names.append(safe_member((Path(parent) / name).relative_to(root).as_posix()))
    unique_names(names)
    return sorted(names)


def inventory(snapshot: Path, validated: dict[str, str], run_id: str) -> list[str]:
    manifest_dir = f"data/manifests/{run_id}"
    required_manifest = f"{manifest_dir}/{run_id}.json"
    actual: list[str] = []
    for directory in ("data/interim", "data/processed", manifest_dir):
        actual.extend(scan_tree(snapshot, directory))
    require(
        set(actual) == set(validated) | {KEEP},
        "Snapshot inventory differs from S13 (extra, missing or wrong-run files)",
    )
    require(digest(snapshot / KEEP) == hashlib.sha256(b"").hexdigest(), ".gitkeep is not empty")
    require(required_manifest in actual, "Missing selected run manifest")
    root_manifest = json.loads((snapshot / required_manifest).read_text(encoding="utf-8-sig"))
    require(root_manifest.get("run_id") == run_id, "Manifest run_id mismatch")
    require(REQUIRED_PROCESSED <= set(actual), "Required processed outputs missing")
    require(any(Path(n).name.startswith("records_") for n in actual if n.startswith("data/processed/")),
            "No processed record files")
    for name in actual:
        path = PurePosixPath(name)
        if name.startswith("data/interim/"):
            require(len(path.parts) == 3 and (name == KEEP or path.suffix == ".csv"),
                    f"Unexpected interim file: {name}")
        elif name.startswith("data/processed/"):
            require(
                len(path.parts) == 3 and (
                    name in REQUIRED_PROCESSED or name == DQ
                    or (path.name.startswith("records_") and path.suffix == ".csv")
                ), f"Processed file outside agreed inventory: {name}",
            )
        else:
            require(path.suffix in (".json", ".jsonl"), f"Unexpected manifest file: {name}")
    unique_names(actual)
    return sorted(n for n in actual if n != DQ)


def verify_snapshot(snapshot: Path, hashes: dict[str, str]) -> None:
    for name, expected in hashes.items():
        require(digest(snapshot / name) == expected, f"Snapshot digest mismatch: {name}")


def write_zip(path: Path, snapshot: Path, hashes: dict[str, str]) -> None:
    """Stream large payloads; do not load harvested CSVs into memory."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=COMPRESSION_LEVEL, allowZip64=True) as archive:
        for name in sorted([*hashes, "SHA256SUMS.txt"]):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.create_system = 3
            info.external_attr = FILE_MODE
            info.compress_type = zipfile.ZIP_DEFLATED
            # ZipInfo objects do not inherit ZipFile's compression level on all
            # supported Python versions; public compress_level arrived later.
            if hasattr(info, "compress_level"):
                info.compress_level = COMPRESSION_LEVEL
            else:
                info._compresslevel = COMPRESSION_LEVEL
            if name == "SHA256SUMS.txt":
                archive.writestr(info, sums_bytes(hashes))
            else:
                source = checked_path(snapshot / name)
                info.file_size = source.stat().st_size
                with source.open("rb") as src, archive.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)


def zip64_extra(info: zipfile.ZipInfo) -> bytes:
    """Only structural ZIP64 size/offset fields may supplement fixed metadata."""
    values = []
    if info.file_size > zipfile.ZIP64_LIMIT or info.compress_size > zipfile.ZIP64_LIMIT:
        values.extend((info.file_size, info.compress_size))
    if info.header_offset > zipfile.ZIP64_LIMIT:
        values.append(info.header_offset)
    if not values:
        return b""
    return struct.pack("<HH", 1, 8 * len(values)) + struct.pack("<" + "Q" * len(values), *values)


def verify_zip(path: Path, hashes: dict[str, str], extracted: Path) -> dict:
    """Validate all names before any extraction, then verify extracted bytes."""
    require(not extracted.exists(), "Verification extraction directory already exists")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        unique_names(names)
        require(names == sorted([*hashes, "SHA256SUMS.txt"]), "ZIP member inventory/order mismatch")
        for info in infos:
            require(
                not info.is_dir() and info.create_system == 3
                and info.external_attr == FILE_MODE
                and info.date_time == FIXED_TIME
                and info.compress_type == zipfile.ZIP_DEFLATED
                and not info.comment and info.extra == zip64_extra(info)
                and not (info.flag_bits & 1),
                f"Unexpected ZIP metadata: {info.filename}",
            )
        require(not archive.comment, "Unexpected ZIP comment")
        require(archive.testzip() is None, "ZIP CRC verification failed")
        require(archive.read("SHA256SUMS.txt") == sums_bytes(hashes), "Internal checksums differ")
        extracted.mkdir()
        for info in infos:
            target = extracted.joinpath(*PurePosixPath(info.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    verify_snapshot(extracted, hashes)
    require(
        {p.relative_to(extracted).as_posix() for p in extracted.rglob("*") if p.is_file()}
        == set(hashes) | {"SHA256SUMS.txt"}, "Extracted inventory differs",
    )
    return {"payload_count": len(hashes), "member_count": len(hashes) + 1,
            "backslash_members": 0, "extracted_hashes_verified": len(hashes)}


def destinations(args: argparse.Namespace, evidence: Path) -> list[Path]:
    names = (
        f"prc-platform-dataset_{args.run_id}_v{args.release_version}.zip",
        f"release_archive_{args.run_id}_v{args.release_version}.sha256",
    )
    result = []
    for raw in (args.output, args.checksum_file, args.report):
        path = checked_path(raw)
        require("data" not in {p.casefold() for p in path.parts}, f"No writes under data/: {raw}")
        require(not path.is_relative_to(evidence), "Do not write inside S13 evidence")
        require(not path.exists(), f"Refusing to overwrite: {path}")
        result.append(path)
    require(result[0].name == names[0], f"Archive filename must be {names[0]}")
    require(result[1].name == names[1] and result[1].parent.name == "reports",
            f"Checksum path must be reports/{names[1]}")
    require(len(set(result)) == 3, "Output paths overlap")
    require(not any(a in b.parents for a in result for b in result if a != b),
            "An output file is another output's parent")
    return result


def build(args: argparse.Namespace) -> dict:
    require(re.fullmatch(r"run_[0-9]{8}_[0-9]{2}", args.run_id) is not None, "Invalid run ID")
    require(re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
                         args.release_version) is not None, "Release version must be X.Y.Z without v")
    require(re.fullmatch(r"[0-9a-f]{40}", args.data_commit) is not None, "Full lowercase data commit required")
    require(args.zenodo_doi == "pending" or re.fullmatch(r"10\.5281/zenodo\.[0-9]+", args.zenodo_doi),
            "Invalid Zenodo DOI")
    snapshot, evidence = checked_path(args.snapshot), checked_path(args.evidence)
    require(snapshot.is_dir() and evidence.is_dir(), "Snapshot/evidence directory missing")
    output, checksums, report_path = destinations(args, evidence)
    evidence_files = ("comparison.json", "validated-input-snapshot.sha256", "expected-output.sha256")
    evidence_hashes = {name: digest(evidence / name) for name in evidence_files}
    validated, expected, s13 = load_evidence(evidence, args.run_id, args.data_commit)
    all_hashes = {**validated, **expected}
    verify_snapshot(snapshot, all_hashes)
    members = inventory(snapshot, validated, args.run_id)
    hashes = {n: all_hashes[n] if n != KEEP else hashlib.sha256(b"").hexdigest() for n in members}
    published: list[Path] = []
    # Stage beside the versioned ZIP, never in data/ or S13 evidence; do not
    # trust TMP/TEMP/TMPDIR, which may point into a protected source directory.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".s1-stage-", dir=output.parent) as temp:
        stage = Path(temp)
        zip_path = stage / output.name
        write_zip(zip_path, snapshot, hashes)
        verified = verify_zip(zip_path, hashes, stage / "extracted")
        require(inventory(snapshot, validated, args.run_id) == members, "Snapshot inventory changed during build")
        verify_snapshot(snapshot, all_hashes)
        require({n: digest(evidence / n) for n in evidence_files} == evidence_hashes,
                "S13 evidence changed during build")
        zip_hash = digest(zip_path)
        report = {
            "status": "PASS", "run_id": args.run_id, "release_version": args.release_version,
            "data_commit": args.data_commit, "s13_baseline_commit": s13["baseline_commit"],
            "archive": output.name, "archive_sha256": zip_hash,
            "checksum_file": checksums.name, "zenodo_doi": args.zenodo_doi,
            "payload": hashes, **verified,
            "categories": {key: sum(n.startswith(f"data/{key}/") for n in hashes)
                           for key in ("interim", "processed", "manifests")},
            "excluded": [DQ] if DQ in validated else [],
            "evidence_sha256": evidence_hashes,
            "validated_inventory_entries": len(validated),
            "expected_inventory_entries": len(expected),
            "unique_source_hashes_verified_before_and_after": len(all_hashes),
            "snapshot_unchanged": True, "evidence_unchanged": True,
            "zip_metadata": {"date_time": list(FIXED_TIME), "unix_mode": "100644",
                             "compression": "DEFLATE", "compression_level": COMPRESSION_LEVEL},
            "runtime": {"python": sys.version, "zlib": zlib.ZLIB_RUNTIME_VERSION},
            "tool_sha256": digest(Path(__file__)),
        }
        sums_path, json_path = stage / checksums.name, stage / "verification.json"
        sums_path.write_bytes(external_sums(hashes, output.name, zip_hash, args.zenodo_doi))
        json_path.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        # Exclusive creation prevents accidentally replacing either old releases
        # or a concurrent run. Roll back only files created by this invocation.
        try:
            for src, dst in ((zip_path, output), (sums_path, checksums), (json_path, report_path)):
                checked_path(dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                with dst.open("xb") as target:
                    published.append(dst)
                    with src.open("rb") as source:
                        shutil.copyfileobj(source, target, 1024 * 1024)
                require(digest(dst) == digest(src), f"Published output digest mismatch: {dst}")
        except BaseException:
            for path in reversed(published):
                path.unlink()
            raise
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--snapshot", type=Path, required=True,
                        help="Current snapshot root (contains data/ and S13-checked reports/)")
    result.add_argument("--evidence", type=Path, required=True, help="Original S13 PASS evidence directory")
    result.add_argument("--run-id", required=True)
    result.add_argument("--release-version", required=True, help="X.Y.Z; required in ZIP and external checksum names")
    result.add_argument("--data-commit", required=True, help="Full S13 baseline SHA, not the later tool/docs commit")
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--checksum-file", type=Path, required=True)
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--zenodo-doi", default="pending", help="Reserved new-version DOI, otherwise pending")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = build(args)
    except (ArchiveError, OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"S1 FAIL: {error}", file=sys.stderr)
        return 1
    print(f"S1 PASS: {report['payload_count']} payload files; "
          f"{report['member_count']} ZIP members; SHA-256 {report['archive_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
