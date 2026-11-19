"""Popular public Commander decks from Archidekt.

Archidekt's API is public but undocumented, so every response is checked on our
side (format, bracket, colour identity, deck size) instead of trusting filters.
"""
import json
import os
import random
import re
import urllib.parse

from .candidates import Candidate
from .decklist import Deck
from .net import get_json

API = "https://archidekt.com/api/decks/"
COMMANDER_FORMAT = 3
COLOR_LETTERS = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G",
                 "W": "W", "U": "U", "B": "B", "R": "R", "G": "G"}


def deck_id_from_url(s):
    m = re.search(r"archidekt\.com/(?:api/)?decks/(\d+)", s)
    if m:
        return m.group(1)
    return s.strip() if s.strip().isdigit() else None


def _colors_of(result):
    c = result.get("colors")
    if isinstance(c, dict):
        return frozenset(COLOR_LETTERS[k] for k, v in c.items() if k in COLOR_LETTERS and v)
    if isinstance(c, list):
        return frozenset(COLOR_LETTERS[k] for k in c if k in COLOR_LETTERS)
    return None


class Archidekt:
    name = "Archidekt"

    def __init__(self, cache_dir, log=print):
        self.cache_dir = os.path.join(cache_dir, "archidekt")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.log = log

    def _search(self, params, pages):
        out = []
        for page in pages:
            url = API + "v3/?" + urllib.parse.urlencode(dict(params, page=page))
            try:
                data = get_json(url, host_gap=1.0)
            except Exception as e:
                self.log(f"  Archidekt search failed: {e}")
                break
            if not data:
                break
            out.extend(data.get("results", []))
            if not data.get("next"):
                break
        return out

    def search(self, commanders, bracket, pages=5, deepest_page=40):
        """Random public Commander decks as Candidates: random pages from the first ~2,000 decks of
        Archidekt's list (sorted by views, so abandoned or empty decks are rare). Commanders and
        colours play no role, like sitting down at a random table."""
        page_list = sorted(random.sample(range(1, deepest_page + 1), pages))
        base = {"deckFormat": COMMANDER_FORMAT, "orderBy": "-viewCount", "pageSize": 50}
        if bracket:
            base["edhBracket"] = bracket
        found, seen = [], set()
        queries = [(False, base, page_list)]
        for from_cmd, params, n_pages in queries:
            self.log("Searching Archidekt for random decks in your bracket...")
            for r in self._search(params, n_pages):
                rid = r.get("id")
                if rid is None or rid in seen:
                    continue
                if r.get("deckFormat") not in (None, COMMANDER_FORMAT):
                    continue
                seen.add(rid)
                found.append(Candidate("archidekt", str(rid), r.get("name", ""), int(r.get("viewCount") or 0),
                                       _colors_of(r), r.get("edhBracket"), from_cmd))
        return found

    def fetch(self, deck_id, refresh=False):
        path = os.path.join(self.cache_dir, f"{deck_id}.json")
        if os.path.exists(path) and not refresh:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = get_json(f"{API}{deck_id}/", host_gap=1.0)
            if not data:
                return None
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        excluded = {c["name"] for c in data.get("categories", []) if not c.get("includedInDeck", True)}
        excluded |= {"Maybeboard", "Sideboard"}
        commanders, cards = [], {}
        for entry in data.get("cards", []):
            cats = entry.get("categories") or []
            if any(c in excluded for c in cats):
                continue
            card = entry.get("card", {})
            name = (card.get("oracleCard") or {}).get("name") or card.get("displayName") or card.get("name")
            if not name:
                continue
            qty = int(entry.get("quantity", 1))
            if "Commander" in cats:
                commanders.append(name)
            else:
                cards[name] = cards.get(name, 0) + qty
        return Deck(name=data.get("name") or f"Archidekt {deck_id}", commanders=commanders,
                    cards=[(q, n) for n, q in cards.items()],
                    url=f"https://archidekt.com/decks/{deck_id}", bracket=data.get("edhBracket"),
                    source="Archidekt", views=int(data.get("viewCount") or 0))
