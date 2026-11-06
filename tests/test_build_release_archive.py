"""S1 uses synthetic bytes only; never build a production release in tests."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from tools import build_release_archive as tool


RUN = "run_20261102_01"
# audit-fixture: begin
VERSION = "1.5.0"
# audit-fixture: end
COMMIT = "9affb3c97af4eb2d8612242d392278485cfd148e"
ZIP_NAME = f"prc-platform-dataset_{RUN}_v{VERSION}.zip"
SUM_NAME = f"release_archive_{RUN}_v{VERSION}.sha256"


def put(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: dict) -> None:
    put(path, (json.dumps(value) + "\n").encode())


def capture(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def refresh_evidence(args) -> None:
    data = capture(args.snapshot / "data")
    validated = {f"data/{p}": hash_bytes(b) for p, b in data.items()
                 if p != "interim/.gitkeep"}
    expected = {p: h for p, h in validated.items() if p.startswith("data/processed/")}
    expected.update({f"reports/{p}": hash_bytes(b) for p, b in capture(args.snapshot / "reports").items()})
    put(args.evidence / "validated-input-snapshot.sha256", tool.sums_bytes(validated))
    put(args.evidence / "expected-output.sha256", tool.sums_bytes(expected))
    gate = {"status": "PASS", "comparison_performed": True, "network_attempts": 0,
            "guard_events": [], "counts": {"same": len(expected), "changed": 0, "added": 0, "missing": 0}}
    write_json(args.evidence / "comparison.json", {
        "status": "PASS", "run_id": RUN, "baseline_commit": COMMIT,
        "protected_inputs_unchanged": True, "no_figure_exception": True,
        "gates": {"raw-to-interim": gate, "downstream": gate},
    })


@pytest.fixture
def args(tmp_path):
    snapshot = tmp_path / "snapshot with spaces"
    evidence = tmp_path / "accepted evidence"
    evidence.mkdir()
    for name, body in {
        "data/interim/.gitkeep": b"",
        "data/interim/crossref_works__example.csv": b"doi,value\r\n10.1234/example,1\r\n",
        "data/processed/records_example.csv": b"doi\n10.1234/example\n",
        "data/processed/works_included.csv": b"doi\n10.1234/example\n",
        "data/processed/normalisation_summary.json": b"{}\n",
        "data/processed/analysis_manifest.json": b"{}\n",
        tool.DQ: b"issue_id,issue\nDQ-001,synthetic\n",
        f"data/manifests/{RUN}/{RUN}.json": json.dumps({"run_id": RUN}).encode(),
        f"data/manifests/{RUN}/crossref__example__w01.manifest.jsonl": b'{"page":1}\n',
        "reports/CHECKSUMS.txt": b"synthetic fixture only\n",
        "reports/tables/example.csv": b"a,b\n1,2\n",
        "reports/figures/example.png": b"synthetic image bytes\n",
    }.items():
        put(snapshot / name, body)
    a = tool.parser().parse_args([
        "--snapshot", str(snapshot), "--evidence", str(evidence), "--run-id", RUN,
        "--release-version", VERSION, "--data-commit", COMMIT,
        "--output", str(tmp_path / "release output" / ZIP_NAME),
        "--checksum-file", str(snapshot / "reports" / SUM_NAME),
        "--report", str(tmp_path / "release output" / "verification.json"),
    ])
    refresh_evidence(a)
    return a


def test_build_roundtrip_readonly_and_exclusions(args):
    before_data = capture(args.snapshot / "data")
    before_evidence = capture(args.evidence)
    # Files outside the selected directories must never enter the ZIP.
    put(args.snapshot / "data/raw/secret-response.json", b"not for release")
    put(args.snapshot / "data/manifests/run_19990101_01/old.json", b"{}")
    put(args.snapshot / ".env", b"SECRET=never-archive")
    report = tool.build(args)
    assert report["status"] == "PASS"
    assert report["categories"] == {"interim": 2, "processed": 4, "manifests": 2}
    assert report["payload_count"] == 8 and report["member_count"] == 9
    assert report["excluded"] == [tool.DQ]
    assert report["backslash_members"] == 0
    assert report["data_commit"] == COMMIT
    assert capture(args.evidence) == before_evidence
    for name, body in before_data.items():
        assert (args.snapshot / "data" / name).read_bytes() == body
    with zipfile.ZipFile(args.output) as z:
        assert z.namelist() == sorted(z.namelist())
        assert z.read("data/interim/crossref_works__example.csv").endswith(b"\r\n")
        assert tool.DQ not in z.namelist()
        assert all(n.startswith("data/") or n == "SHA256SUMS.txt" for n in z.namelist())
        assert z.read("SHA256SUMS.txt") == tool.sums_bytes(report["payload"])
    assert json.loads(args.report.read_text()) == report


def test_external_format_matches_published_layout_line_for_line(args):
    published = Path(__file__).resolve().parents[1] / "reports" / f"release_archive_{RUN}.sha256"
    original = published.read_bytes()
    lines = original.decode().splitlines()
    assert lines[0] == f"# archive: prc-platform-dataset_{RUN}.zip"
    assert lines[1] == "# zenodo_doi: 10.5281/zenodo.23891928"
    hashes = {}
    for line in lines[2:-1]:
        value, name = line.split("  ", 1)
        assert tool.HEX.fullmatch(value)
        hashes[name] = value
    zip_hash, zip_name = lines[-1].split("  ", 1)
    # Byte-for-byte reconstruction establishes comments, preserved line order, lowercase
    # digests, exactly two spaces, POSIX names, LF termination and ZIP last.
    assert tool.external_sums(hashes, zip_name, zip_hash, lines[1].split(": ", 1)[1]) == original
    report = tool.build(args)
    expected = (
        f"# archive: {ZIP_NAME}\n# zenodo_doi: pending\n"
        + "".join(f"{value}  {name}\n" for name, value in sorted(report["payload"].items()))
        + f"{tool.digest(args.output)}  {ZIP_NAME}\n"
    ).encode()
    assert args.checksum_file.read_bytes() == expected
    assert b"SHA256SUMS.txt" not in expected  # payload only; no circular checksum
    assert published.read_bytes() == original


def test_deterministic_bytes_ignore_mtime_mode_and_native_paths(args, tmp_path):
    first = tool.build(args)
    original = args.output.read_bytes()
    for p in (args.snapshot / "data").rglob("*"):
        if p.is_file():
            os.utime(p, (1700000000, 1700000000))
            p.chmod(0o600)
    args.output = tmp_path / "second output" / ZIP_NAME
    args.checksum_file = tmp_path / "second output" / "reports" / SUM_NAME
    args.report = tmp_path / "second output" / "report.json"
    second = tool.build(args)
    assert args.output.read_bytes() == original
    assert second["archive_sha256"] == first["archive_sha256"]
    assert second["runtime"]["zlib"]


@pytest.mark.parametrize("name", [
    "", "/absolute", "../escape", "a/../b", "a//b", "./a", "a/", "a\\b",
    "C:/escape", "C:escape", "\\\\server\\share", "a:b", "a\nb", "a\tb",
    "a/CON.txt", "NUL", "a/COM1.csv", "a/LPT9", "a/COM¹.txt", "a/name.", "a/name ",
])
def test_reject_unsafe_windows_and_posix_member_names(name):
    with pytest.raises(tool.ArchiveError):
        tool.safe_member(name)


@pytest.mark.parametrize("name", ["data/interim/.gitkeep", "data/a b.csv", "data/é.csv"])
def test_safe_members(name):
    assert tool.safe_member(name) == name


@pytest.mark.parametrize("names", [["a", "a"], ["data/A.csv", "data/a.csv"]])
def test_duplicate_members(names):
    with pytest.raises(tool.ArchiveError):
        tool.unique_names(names)


@pytest.mark.parametrize("field", ["output", "checksum_file", "report"])
def test_no_write_under_any_data_directory(args, field, tmp_path):
    before = capture(args.snapshot)
    setattr(args, field, tmp_path / "DATA" / getattr(args, field).name)
    with pytest.raises(tool.ArchiveError, match="No writes under data"):
        tool.build(args)
    assert capture(args.snapshot) == before
    assert not (tmp_path / "DATA").exists()


@pytest.mark.parametrize("field", ["output", "checksum_file", "report"])
def test_no_overwrite(args, field):
    path = getattr(args, field)
    put(path, b"keep original")
    with pytest.raises(tool.ArchiveError, match="Refusing to overwrite"):
        tool.build(args)
    assert path.read_bytes() == b"keep original"


@pytest.mark.parametrize("field,name", [
    ("output", f"prc-platform-dataset_{RUN}.zip"),
    ("output", f"prc-platform-dataset_{RUN}_v1.4.0.zip"),
    ("checksum_file", f"release_archive_{RUN}.sha256"),
    ("checksum_file", f"release_archive_{RUN}_v1.4.0.sha256"),
])
def test_require_matching_versioned_filenames(args, field, name):
    setattr(args, field, getattr(args, field).with_name(name))
    with pytest.raises(tool.ArchiveError):
        tool.build(args)
    assert not args.output.exists()


@pytest.mark.parametrize("field,value", [
    ("release_version", "v1.5.0"), ("release_version", "1.05.0"),
    ("run_id", "../bad"), ("data_commit", "9affb3c"), ("zenodo_doi", "old\ninjected"),
])
def test_invalid_cli_metadata(args, field, value):
    setattr(args, field, value)
    with pytest.raises(tool.ArchiveError):
        tool.build(args)


def test_no_output_in_evidence(args):
    args.output = args.evidence / ZIP_NAME
    with pytest.raises(tool.ArchiveError, match="inside S13 evidence"):
        tool.build(args)


@pytest.mark.parametrize("change", ["changed", "missing", "extra", "nonempty-gitkeep", "missing-gitkeep"])
def test_source_drift(args, change):
    target = args.snapshot / "data/interim/crossref_works__example.csv"
    if change == "changed":
        target.write_bytes(b"drift")
    elif change == "missing":
        target.unlink()
    elif change == "extra":
        put(target.with_name("stale.csv"), b"header\n")
    elif change == "nonempty-gitkeep":
        (args.snapshot / tool.KEEP).write_bytes(b"x")
    else:
        (args.snapshot / tool.KEEP).unlink()
    with pytest.raises(tool.ArchiveError):
        tool.build(args)
    assert not args.output.exists() and not args.checksum_file.exists()


@pytest.mark.parametrize("field,value", [
    ("status", "FAIL"), ("run_id", "run_19990101_01"),
    ("baseline_commit", "a" * 40), ("protected_inputs_unchanged", False),
    ("no_figure_exception", False),
])
def test_reject_unaccepted_evidence(args, field, value):
    p = args.evidence / "comparison.json"
    report = json.loads(p.read_text())
    report[field] = value
    write_json(p, report)
    with pytest.raises(tool.ArchiveError, match="S13 PASS"):
        tool.build(args)


@pytest.mark.parametrize("field,value", [
    ("status", "FAIL"), ("network_attempts", 1), ("guard_events", ["event"]),
    ("comparison_performed", False),
    ("counts", {"same": 8, "changed": 1, "added": 0, "missing": 0}),
])
def test_reject_bad_gate(args, field, value):
    p = args.evidence / "comparison.json"
    report = json.loads(p.read_text())
    report["gates"]["downstream"][field] = value
    write_json(p, report)
    with pytest.raises(tool.ArchiveError, match="Unaccepted S13 gate"):
        tool.build(args)


@pytest.mark.parametrize("line", [
    "A" * 64 + "  data/a.csv\n", "f" * 64 + " data/a.csv\n",
    "f" * 64 + "  data\\a.csv\n", "f" * 64 + "  ../a.csv\n",
])
def test_malformed_checksum_inputs(tmp_path, line):
    path = tmp_path / "sums"
    put(path, line.encode())
    with pytest.raises(tool.ArchiveError):
        tool.load_sums(path)


def test_duplicate_checksum_inputs(tmp_path):
    path = tmp_path / "sums"
    put(path, (("f" * 64 + "  data/a.csv\n") * 2).encode())
    with pytest.raises(tool.ArchiveError, match="Duplicate"):
        tool.load_sums(path)


def test_conflicting_input_and_output_evidence(args):
    p = args.evidence / "expected-output.sha256"
    sums = tool.load_sums(p)
    sums["data/processed/works_included.csv"] = "0" * 64
    put(p, tool.sums_bytes(sums))
    with pytest.raises(tool.ArchiveError, match="Conflicting"):
        tool.build(args)


@pytest.mark.parametrize("location", ["payload", "directory", "output-parent"])
def test_symlinks_forbidden(args, tmp_path, location):
    real = tmp_path / "real"
    real.mkdir()
    if location == "payload":
        target = args.snapshot / "data/interim/crossref_works__example.csv"
        put(real / "file.csv", target.read_bytes())
        target.unlink()
        destination = real / "file.csv"
    elif location == "directory":
        target = args.snapshot / "data/interim/alias"
        destination = real
    else:
        target = args.output.parent
        destination = real
    try:
        target.symlink_to(destination, target_is_directory=destination.is_dir())
    except OSError as error:
        pytest.skip(f"OS account cannot create symlinks: {error}")
    with pytest.raises(tool.ArchiveError, match="Symlink/reparse"):
        tool.build(args)


def test_windows_reparse_detection_without_symlink_privilege(tmp_path, monkeypatch):
    path = tmp_path / "junction"
    path.mkdir()
    original = Path.lstat

    def fake(self, *a, **kw):
        if self == path:
            from types import SimpleNamespace
            return SimpleNamespace(st_mode=0o40755, st_file_attributes=0x400)
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "lstat", fake)
    with pytest.raises(tool.ArchiveError, match="reparse"):
        tool.checked_path(path / "child")


@pytest.mark.parametrize("change", ["payload", "evidence", "extra"])
def test_mid_build_changes_leave_no_release_outputs(args, monkeypatch, change):
    original = tool.write_zip

    def changed(*params):
        original(*params)
        if change == "payload":
            put(args.snapshot / "data/processed/works_included.csv", b"changed")
        elif change == "evidence":
            p = args.evidence / "comparison.json"
            p.write_bytes(p.read_bytes() + b" ")
        else:
            put(args.snapshot / "data/interim/new.csv", b"x\n")

    monkeypatch.setattr(tool, "write_zip", changed)
    with pytest.raises(tool.ArchiveError):
        tool.build(args)
    assert not args.output.exists()
    assert not args.checksum_file.exists()
    assert not args.report.exists()
    assert not list(args.output.parent.glob(".s1-stage-*"))


def test_corrupt_zip_detected_before_outputs(args, monkeypatch):
    original = tool.write_zip

    def corrupt(path, *rest):
        original(path, *rest)
        path.write_bytes(b"not a zip")

    monkeypatch.setattr(tool, "write_zip", corrupt)
    with pytest.raises(zipfile.BadZipFile):
        tool.build(args)
    assert not args.output.exists()


@pytest.mark.parametrize("member", ["../escape", "data\\backslash"])
def test_zip_reverification_rejects_unsafe_member(tmp_path, member):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as z:
        info = zipfile.ZipInfo(member, tool.FIXED_TIME)
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        z.writestr(info, b"outside")
    with pytest.raises(tool.ArchiveError):
        tool.verify_zip(path, {}, tmp_path / "extract")
    assert not (tmp_path / "extract").exists()


@pytest.mark.parametrize("alter", ["symlink", "time", "comment", "extra", "duplicate", "bytes"])
def test_zip_metadata_duplicates_and_extracted_digests(tmp_path, alter):
    path = tmp_path / "bad.zip"
    payload = {"data/a": hash_bytes(b"contents")}
    with zipfile.ZipFile(path, "w") as z:
        for name, body in [("SHA256SUMS.txt", tool.sums_bytes(payload)), ("data/a", b"contents")]:
            info = zipfile.ZipInfo(name, tool.FIXED_TIME)
            info.create_system = 3
            info.external_attr = tool.FILE_MODE
            info.compress_type = zipfile.ZIP_DEFLATED
            if name == "data/a":
                if alter == "symlink":
                    info.external_attr = 0o120777 << 16
                elif alter == "time":
                    info.date_time = (2020, 1, 1, 0, 0, 0)
                elif alter == "comment":
                    info.comment = b"extra metadata"
                elif alter == "extra":
                    info.extra = b"\x34\x12\x00\x00"
                elif alter == "bytes":
                    body = b"altered"
            z.writestr(info, body)
            if name == "data/a" and alter == "duplicate":
                with pytest.warns(UserWarning, match="Duplicate"):
                    z.writestr(info, body)
    with pytest.raises(tool.ArchiveError):
        tool.verify_zip(path, payload, tmp_path / "extract")


def test_structural_zip64_only():
    info = zipfile.ZipInfo("large")
    info.header_offset = 0
    assert tool.zip64_extra(info) == b""
    info.file_size = zipfile.ZIP64_LIMIT + 1
    info.compress_size = 7
    assert tool.zip64_extra(info).hex().startswith("01001000")
    info.header_offset = zipfile.ZIP64_LIMIT + 1
    assert tool.zip64_extra(info).hex().startswith("01001800")


def test_reserved_doi_is_metadata_only(args):
    args.zenodo_doi = "10.5281/zenodo.999999999"
    report = tool.build(args)
    assert report["zenodo_doi"] == args.zenodo_doi
    assert args.checksum_file.read_text().splitlines()[1] == f"# zenodo_doi: {args.zenodo_doi}"


def test_out_of_scope_processed_file_even_if_in_evidence(args):
    put(args.snapshot / "data/processed/unagreed.json", b"{}")
    refresh_evidence(args)
    with pytest.raises(tool.ArchiveError, match="outside agreed inventory"):
        tool.build(args)


def test_source_manifest_run_mismatch(args):
    write_json(args.snapshot / f"data/manifests/{RUN}/{RUN}.json", {"run_id": "run_19990101_01"})
    refresh_evidence(args)
    with pytest.raises(tool.ArchiveError, match="Manifest run_id mismatch"):
        tool.build(args)


def test_output_publication_failure_rolls_back_only_created_files(args, monkeypatch):
    original = Path.open

    def fail(self, *a, **kw):
        if self == args.checksum_file and a and a[0] == "xb":
            raise OSError("simulated write failure")
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(OSError, match="simulated"):
        tool.build(args)
    assert not args.output.exists() and not args.checksum_file.exists() and not args.report.exists()


def test_production_shaped_synthetic_inventory(args):
    interim = args.snapshot / "data/interim"
    (interim / "crossref_works__example.csv").rename(interim / "crossref_works__jmirx_bio.csv")
    for n in range(93):
        put(interim / f"run_owned_{n:03}.csv", b"doi\n10.1234/synthetic\n")
    for name in ("crossref_peer_reviews__jmirx_med.csv",
                 "crossref_peer_reviews__unattributed__10.2196.csv",
                 "crossref_works__rapid_reviews_infectious_diseases.csv"):
        put(interim / name, b"doi\n")
    for n in range(41):
        put(args.snapshot / f"data/processed/records_synthetic_{n:03}.csv", b"doi\n")
    for n in range(491):
        put(args.snapshot / f"data/manifests/{RUN}/page_{n:03}.manifest.jsonl", b"{}\n")
    for n in range(38):
        put(args.snapshot / f"reports/tables/synthetic_{n:03}.csv", b"a\n")
    refresh_evidence(args)
    report = tool.build(args)
    assert report["categories"] == {"interim": 98, "processed": 45, "manifests": 493}
    assert report["payload_count"] == 636 and report["member_count"] == 637
    assert report["validated_inventory_entries"] == 636
    assert report["expected_inventory_entries"] == 87
    assert report["unique_source_hashes_verified_before_and_after"] == 677
    assert "data/interim/crossref_works__jmirx_bio.csv" in report["payload"]


def test_standard_library_only_and_cli_help_no_src(tmp_path):
    script = Path(tool.__file__).resolve()
    tree = ast.parse(script.read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert not any(n == "src" or n.startswith("src.") for n in imports if n)
    assert {n.split(".")[0] for n in imports if n} <= sys.stdlib_module_names
    # Isolated mode, foreign CWD and no repository on sys.path.
    result = subprocess.run([sys.executable, "-I", "-B", str(script), "--help"],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0 and "--release-version" in result.stdout


def test_cli_failure_no_traceback(args, capsys):
    assert tool.main([
        "--snapshot", str(args.snapshot), "--evidence", str(args.evidence),
        "--run-id", RUN, "--release-version", VERSION, "--data-commit", "short",
        "--output", str(args.output), "--checksum-file", str(args.checksum_file),
        "--report", str(args.report),
    ]) == 1
    assert "S1 FAIL" in capsys.readouterr().err
