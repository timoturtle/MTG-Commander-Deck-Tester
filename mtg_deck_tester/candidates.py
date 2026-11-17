"""A deck found by a site search, before it is downloaded."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Candidate:
    source: str              # "archidekt" | "moxfield"
    ref: str                 # site deck id
    name: str
    views: int = 0
    colors: frozenset | None = None   # colour identity as reported by the site (may be missing)
    bracket: int | None = None
    from_commander_search: bool = False
    rank: int = 0            # popularity rank within its source

    @property
    def key(self):
        return f"{self.source}:{self.ref}"
