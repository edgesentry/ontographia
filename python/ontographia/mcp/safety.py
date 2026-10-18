"""Defense-in-depth write-query rejection for Ontographia-generated Cypher."""

from __future__ import annotations

import re
from dataclasses import dataclass


class WriteQueryRejected(ValueError):
    """Raised when generated Cypher contains a denied write construct."""


# Clause / keyword deny list. Matching is case-insensitive on word boundaries
# after comment/string stripping so identifiers like ``created_at`` do not trip
# ``CREATE``.
_WRITE_CLAUSE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bCREATE\b",
        r"\bMERGE\b",
        r"\bDELETE\b",
        r"\bDETACH\b",
        r"\bSET\b",
        r"\bREMOVE\b",
        r"\bDROP\b",
        r"\bFOREACH\b",
        r"\bLOAD\s+CSV\b",
        r"\bIN\s+TRANSACTIONS\b",
        # Subquery form used for batch writes: CALL { ... } IN TRANSACTIONS
        # (IN TRANSACTIONS already covered; keep CALL { as extra signal when
        # paired with write keywords inside — still deny bare IN TRANSACTIONS.)
    )
)

# Procedure prefixes that mutate the graph or filesystem.
_WRITE_PROC_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bapoc\.create\b",
        r"\bapoc\.merge\b",
        r"\bapoc\.periodic\b",
        r"\bapoc\.refactor\b",
        r"\bapoc\.nodes\.delete\b",
        r"\bapoc\.cypher\.do",
        r"\bapoc\.load\b",
        r"\bapoc\.export\b",
        r"\bapoc\.import\b",
        r"\bdb\.create",
        r"\bdb\.index\.",
        r"\bdb\.constraints\.",
        r"\bdbms\.security\.",
        r"\bdbms\.set",
        r"\bgds\..*\.write\b",
        r"\bgds\..*\.mutate\b",
    )
)


_STRING_OR_COMMENT = re.compile(
    r"""
    '(?:\\'|[^'])*'   |   # single-quoted string
    "(?:\\"|[^"])*"   |   # double-quoted string
    //[^\n]*          |   # line comment
    /\*.*?\*/             # block comment
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclass(frozen=True)
class DenyMatch:
    pattern: str
    snippet: str


def _strip_strings_and_comments(cypher: str) -> str:
    return _STRING_OR_COMMENT.sub(" ", cypher)


def find_write_constructs(cypher: str) -> list[DenyMatch]:
    """Return deny-list hits in ``cypher`` (empty if none)."""
    scrubbed = _strip_strings_and_comments(cypher)
    hits: list[DenyMatch] = []
    for pattern in _WRITE_CLAUSE_PATTERNS + _WRITE_PROC_PATTERNS:
        match = pattern.search(scrubbed)
        if match:
            start = max(0, match.start() - 20)
            end = min(len(scrubbed), match.end() + 20)
            hits.append(
                DenyMatch(
                    pattern=pattern.pattern,
                    snippet=scrubbed[start:end].strip(),
                )
            )
    return hits


def assert_read_only_cypher(cypher: str) -> None:
    """Raise :class:`WriteQueryRejected` if ``cypher`` matches the deny list."""
    hits = find_write_constructs(cypher)
    if not hits:
        return
    details = "; ".join(f"{h.pattern!r} near {h.snippet!r}" for h in hits[:5])
    raise WriteQueryRejected(
        "Refusing to execute write Cypher (Ontographia MCP is read-only). "
        f"Denied constructs: {details}"
    )
