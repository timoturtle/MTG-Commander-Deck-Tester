"""Parse decklists pasted from Archidekt (and most other deckbuilding sites)."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

CARD_LINE = re.compile(r"^(\d+)\s*[xX]?\s+(.+)$")
SKIP_SECTIONS = {"maybeboard", "maybe", "sideboard", "considering", "tokens", "token",
                 "acquireboard", "wishlist", "attractions", "stickers", "contraptions"}
COMMANDER_SECTIONS = {"commander", "commanders", "command zone", "partner"}


@dataclass
class Deck:
    name: str
    commanders: list = field(default_factory=list)   # card names
    cards: list = field(default_factory=list)        # (qty, name) for the 99
    url: str = ""
    bracket: int | None = None
    source: str = "user"
    views: int = 0

    @property
    def size(self):
        return len(self.commanders) + sum(q for q, _ in self.cards)

    def all_names(self):
        return list(self.commanders) + [n for _, n in self.cards]

    def to_dict(self):
        return {"name": self.name, "commanders": self.commanders, "cards": self.cards,
                "url": self.url, "bracket": self.bracket, "source": self.source, "views": self.views}

    @staticmethod
    def from_dict(d):
        return Deck(d["name"], list(d["commanders"]), [tuple(c) for c in d["cards"]],
                    d.get("url", ""), d.get("bracket"), d.get("source", "user"), d.get("views", 0))


def _clean_name(rest):
    """Strip set codes, collector numbers, foil marks, categories and colour tags."""
    name = re.split(r"\s+\(|\s+\[|\s+\*[A-Za-z]+\*|\s+\^|\s+#", rest, maxsplit=1)[0]
    name = name.strip()
    # "Fire / Ice" -> "Fire // Ice"
    name = re.sub(r"\s+/\s+", " // ", name)
    return name


def _categories(rest):
    cats = []
    for block in re.findall(r"\[([^\]]*)\]", rest):
        for part in block.split(","):
            part = part.strip()
            if part:
                cats.append(part)
    return cats


def parse_decklist(text, commander_override="", deck_name=""):
    """Returns (Deck, warnings)."""
    warnings = []
    commanders, main = [], []
    section = "main"
    lines = [l.strip() for l in text.replace("\r", "").split("\n")]
    has_qty = any(CARD_LINE.match(l) for l in lines if l)

    for line in lines:
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        m = CARD_LINE.match(line) if has_qty else re.match(r"^()(.+)$", line)
        if has_qty and not m:
            # a header such as "Commander", "Ramp (10)", "Maybeboard"
            head = re.sub(r"\(\d+\)|:", "", line).strip().lower()
            if head in COMMANDER_SECTIONS:
                section = "commander"
            elif head in SKIP_SECTIONS:
                section = "skip"
            else:
                section = "main"
            continue
        qty = int(m.group(1)) if m.group(1) else 1
        rest = m.group(2)
        cats = _categories(rest)
        cat_low = [c.lower() for c in cats]
        if any("{nodeck}" in c for c in cat_low) or any(
                c.split("{")[0] in SKIP_SECTIONS for c in cat_low):
            continue
        name = _clean_name(rest)
        if not name:
            continue
        is_cmd = any(c.split("{")[0].strip() == "commander" for c in cat_low)
        if section == "skip":
            continue
        if is_cmd or section == "commander":
            commanders.append(name)
        else:
            main.append((qty, name))

    if commander_override.strip():
        wanted = [c.strip() for c in re.split(r"[\n;]|\s\+\s", commander_override) if c.strip()]
        commanders = []
        for w in wanted:
            commanders.append(w)
            main = [(q, n) for q, n in main if n.lower() != w.lower()]

    # merge duplicates
    merged = {}
    for q, n in main:
        merged[n] = merged.get(n, 0) + q
    main = [(q, n) for n, q in merged.items()]

    deck = Deck(name=deck_name.strip() or "Your deck", commanders=commanders[:2], cards=main)
    if not commanders:
        warnings.append("No commander found. Mark it with the [Commander] category in "
                        "Archidekt, or type it into the Commander field.")
    if len(commanders) > 2:
        warnings.append("More than two commanders found; using the first two.")
    if deck.size not in (99, 100, 101):
        warnings.append(f"Deck has {deck.size} cards (a Commander deck has 100).")
    return deck, warnings
