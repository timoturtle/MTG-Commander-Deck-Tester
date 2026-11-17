"""Combos from Commander Spellbook (https://commanderspellbook.com), the community combo database.

Uses the public find-my-combos endpoint of its open-source backend
(https://github.com/SpaceCowMedia/commander-spellbook-backend). Results are cached per decklist.
"""
import hashlib
import json
import os

from .net import post_json

API = "https://backend.commanderspellbook.com/find-my-combos"
SITE = "https://commanderspellbook.com/combo/{}/"

# Commander Spellbook's bracket tags and the Commander bracket each one maps to
BRACKET_TAGS = {"R": ("Ruthless", 4), "S": ("Spicy", 3), "P": ("Powerful", 3), "O": ("Oddball", 2),
                "C": ("Core", 2), "E": ("Exhibition", 1), "B": ("Banned", 5)}
WIN_WORDS = ("win the game", "infinite damage", "infinite lifeloss", "infinite life loss", "infinite mill",
             "infinite combat", "lose the game", "each opponent loses", "infinite poison")


def _g(d, *keys, default=None):
    """Read a key in camelCase or snake_case."""
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return default


def _parse_variant(v):
    pieces, commander_pieces = [], []
    for u in _g(v, "uses", default=[]) or []:
        card = _g(u, "card", default={}) or {}
        name = _g(card, "name")
        if not name:
            continue
        zones = _g(u, "zoneLocations", "zone_locations", default=[]) or []
        pieces.append({"name": name, "zones": list(zones), "quantity": int(_g(u, "quantity", default=1) or 1)})
        if _g(u, "mustBeCommander", "must_be_commander", default=False):
            commander_pieces.append(name)
    templates = [_g(_g(t, "template", default={}) or {}, "name") for t in _g(v, "requires", default=[]) or []]
    produces = [_g(_g(p, "feature", default={}) or {}, "name") for p in _g(v, "produces", default=[]) or []]
    produces = [p for p in produces if p]
    tag = _g(v, "bracketTag", "bracket_tag") or ""
    text = " ".join(produces).lower()
    prereq = " ".join(x for x in (_g(v, "easyPrerequisites", "easy_prerequisites"),
                                  _g(v, "notablePrerequisites", "notable_prerequisites")) if x)
    return {
        "id": str(_g(v, "id", default="")),
        "url": SITE.format(_g(v, "id", default="")),
        "pieces": pieces,
        "commander_pieces": commander_pieces,
        "templates": [t for t in templates if t],
        "produces": produces,
        "wins": any(w in text for w in WIN_WORDS),
        "mana_value_needed": int(_g(v, "manaValueNeeded", "mana_value_needed", default=0) or 0),
        "mana_needed": _g(v, "manaNeeded", "mana_needed", default="") or "",
        "prerequisites": prereq.strip(),
        "bracket_tag": tag,
        "bracket_label": BRACKET_TAGS.get(tag, ("", None))[0],
        "bracket": BRACKET_TAGS.get(tag, ("", None))[1],
        "popularity": int(_g(v, "popularity", default=0) or 0),
        "identity": _g(v, "identity", default=""),
    }


class Spellbook:
    def __init__(self, cache_dir, log=print):
        self.cache_dir = os.path.join(cache_dir, "spellbook")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.log = log

    def find(self, deck):
        """Returns {'included': [...], 'almost': [...]} for a Deck. Raises on network errors."""
        payload = {"commanders": [{"card": c, "quantity": 1} for c in deck.commanders],
                   "main": [{"card": n, "quantity": int(q)} for q, n in deck.cards]}
        key = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        path = os.path.join(self.cache_dir, key + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = post_json(API, payload, host_gap=0.6, timeout=90)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        results = _g(data, "results", default=data) or {}
        included = [_parse_variant(v) for v in _g(results, "included", default=[]) or []]
        almost = [_parse_variant(v) for v in _g(results, "almostIncluded", "almost_included", default=[]) or []]
        return {"included": included, "almost": almost}
