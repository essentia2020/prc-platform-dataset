"""PRC Platform Dataset 1.5.0 — source package.

Sub-packages follow the fixed stage order declared in ``src/run_pipeline.py``:
``extract`` -> ``normalise`` (conditional) -> ``analyse`` -> ``report``.
``common`` holds the configuration loader, the register loader/exporter,
identifier normalisation and the structured logger shared by all stages.
"""

__version__ = "1.5.0"
