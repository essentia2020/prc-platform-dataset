# Audit fixture: version strings and lineage words

This file is a test fixture for `tools/audit_text.py`. The paragraph below
intentionally contains patterns that rule R2 reports; the markers make the
span exempt in the repository self-audit.

<!-- audit-fixture: begin -->
The previous release 1.3.0 of this dataset used a different register. See
the changelog and the legacy selectors; migration notes describe the upgrade
from the earlier version 1.2 to this one.
<!-- audit-fixture: end -->

Outside the markers only neutral text appears: Python 3.10, DOI
10.21468/scipost.1.2, a threshold of 2.5 ratings, and the current release
identifier 1.5.0.
