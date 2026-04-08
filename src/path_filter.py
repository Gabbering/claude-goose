"""Path-based filters for deciding which PRs to actually feed to Claude.

Pure functions, no external dependencies — kept in its own module so tests can
import it without dragging in httpx / anthropic.
"""

from __future__ import annotations

import re
from typing import Any

# File patterns considered "docs only" — if every file in a delta matches one
# of these, we skip the Claude review entirely. The goose explicitly does not
# review prose, so spending Opus tokens on it is pure waste.
_DOC_PATH_RES = (
    re.compile(r"^docs/", re.IGNORECASE),
    re.compile(r"\.md$", re.IGNORECASE),
    re.compile(r"\.rst$", re.IGNORECASE),
    re.compile(r"\.txt$", re.IGNORECASE),
    re.compile(r"(^|/)README(\.|$)", re.IGNORECASE),
    re.compile(r"(^|/)LICENSE(\.|$)", re.IGNORECASE),
    re.compile(r"(^|/)COPYING(\.|$)", re.IGNORECASE),
    re.compile(r"(^|/)CHANGELOG(\.|$)", re.IGNORECASE),
    re.compile(r"(^|/)AUTHORS(\.|$)", re.IGNORECASE),
    re.compile(r"(^|/)CONTRIBUTING(\.|$)", re.IGNORECASE),
)


def is_docs_only(files: list[dict[str, Any]]) -> bool:
    """True iff every changed file matches a doc-only pattern.

    Empty list returns False (no files = nothing to do, handled separately by
    the caller, not by this filter).
    """
    if not files:
        return False
    for f in files:
        path = f.get("filename") or ""
        if not any(p.search(path) for p in _DOC_PATH_RES):
            return False
    return True
