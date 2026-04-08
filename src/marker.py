"""HTML-comment markers embedded in bot comments — our only state store.

A marker looks like:
    <!-- ga-bot:v1 sha=abc1234 silent_skips=def5678,ghi9012 -->

- `sha`          = the commit the bot has processed up to
- `silent_skips` = optional, short SHAs where the goose chose SILENT (debugging)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MARKER_VERSION = "v1"

# Matches the whole marker and captures sha + the rest (for silent_skips etc).
_MARKER_RE = re.compile(
    r"<!--\s*ga-bot:" + MARKER_VERSION + r"\s+sha=([0-9a-fA-F]+)([^>]*?)-->"
)
_SKIPS_RE = re.compile(r"silent_skips=([0-9a-fA-F,]+)")


@dataclass
class Marker:
    sha: str
    silent_skips: list[str] = field(default_factory=list)
    # The exact substring we matched — used for in-place replacement.
    raw: str = ""


def parse(body: str) -> Marker | None:
    """Return the FIRST marker found in `body`, or None."""
    if not body:
        return None
    m = _MARKER_RE.search(body)
    if not m:
        return None
    sha = m.group(1).lower()
    rest = m.group(2) or ""
    skips: list[str] = []
    sm = _SKIPS_RE.search(rest)
    if sm:
        skips = [s.lower() for s in sm.group(1).split(",") if s]
    return Marker(sha=sha, silent_skips=skips, raw=m.group(0))


def encode(sha: str, silent_skips: list[str] | None = None) -> str:
    """Build a marker string to embed at the end of a comment body."""
    parts = [f"ga-bot:{MARKER_VERSION}", f"sha={sha.lower()}"]
    if silent_skips:
        unique = []
        seen = set()
        for s in silent_skips:
            s_low = s.lower()
            if s_low not in seen:
                seen.add(s_low)
                unique.append(s_low)
        parts.append(f"silent_skips={','.join(unique)}")
    return f"<!-- {' '.join(parts)} -->"


def replace_in_body(body: str, new_marker: str) -> str:
    """Swap the existing marker in `body` with `new_marker`.

    If no marker is present, append `new_marker` at the end.
    """
    if _MARKER_RE.search(body):
        # Use a lambda to avoid backreference interpretation of `\` in new_marker.
        return _MARKER_RE.sub(lambda _m: new_marker, body, count=1)
    return body.rstrip() + "\n\n" + new_marker
