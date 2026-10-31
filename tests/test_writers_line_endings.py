"""Every text writer under ``src/`` fixes its line terminator to LF.

Outputs are then byte-identical across operating systems, and ``CHECKSUMS.txt``
computed on one platform verifies on another.  Two guards: the fixture run
produces no ``\\r`` anywhere, and no text-mode writer in ``src/`` is left
without an explicit ``newline=`` / ``lineterminator=``.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

# text-mode write/append opens and write_text calls; binary modes and reads are exempt
_OPEN = re.compile(r"""\b(?:open|\.open)\(\s*(?:[^,()]+,\s*)?["'](?:[wax]t?\+?)["']""")
_WRITE_TEXT = re.compile(r"\.write_text\(")


def _text_output_files(out) -> list[Path]:
    roots = [out.tables, out.processed, out.figures.parent, out.roots["manifest_root"], out.roots["interim_root"],
             out.roots["raw_root"], out.root / "logs"]
    files = []
    for root in roots:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() and p.suffix in {".csv", ".md", ".json", ".jsonl", ".txt"})
    return files


def test_fixture_run_writes_no_carriage_return(pipeline_outputs):
    files = _text_output_files(pipeline_outputs)
    assert any(p.suffix == ".csv" for p in files) and any(p.suffix == ".md" for p in files)
    assert any(p.name == "CHECKSUMS.txt" for p in files) and any(p.suffix == ".jsonl" for p in files)
    offenders = [p for p in files if b"\r" in p.read_bytes()]
    assert not offenders, offenders


def test_every_text_writer_in_src_pins_its_line_terminator():
    missing = []
    for path in SRC.rglob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if _OPEN.search(line) or _WRITE_TEXT.search(line):
                window = " ".join(lines[i:i + 3])          # arguments may continue on the next lines
                if "newline=" not in window and "lineterminator=" not in window:
                    missing.append(f"{path.relative_to(SRC.parent)}:{i + 1}: {line.strip()}")
    assert not missing, "\n".join(missing)
