"""Popular public Commander decks from Moxfield.

Moxfield's terms of service do not allow automated access without permission.
Moxfield hands out a personal "User-Agent" string on request (support@moxfield.com);
this module only runs when the user has entered one in Settings.
"""
import json
import os
import re
import urllib.parse

from .candidates import Candidate
from .decklist import Deck
from .net import get_json

API = "https://api2.moxfield.com"


def deck_id_from_url(s):
    m = re.search(r"moxfield\.com/decks/([A-Za-z0-9_-]+)", s)
    return m.group(1) if m else None


def _bracket(d):
    for k in ("bracket", "userBracket", "autoBracket"):
        v = d.get(k)
        if isinstance(v, (int, float)) and 1 <= v <= 5:
            return int(v)
    return None


class Moxfield:
    name = "Moxfield"

    def __init__(self, user_agent, cache_dir, log=print):
        self.ua = (user_agent or "").strip()
        self.cache_dir = os.path.join(cache_dir, "moxfield")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.log = log

    @property
    def enabled(self):
        return bool(self.ua)

    def _get(self, url):
        return get_json(url, host_gap=1.1, headers={"User-Agent": self.ua})

    def search(self, commanders, bracket, pages=3):
        if not self.enabled:
            return []
        self.log("Searching Moxfield for popular decks...")
        found = []
        for page in range(1, pages + 1):
            q = {"pageNumber": page, "pageSize": 64, "sortType": "views", "sortDirection": "descending",
                 "fmt": "commander", "board": "mainboard"}
            try:
                data = self._get(f"{API}/v2/decks/search?" + urllib.parse.urlencode(q))
            except Exception as e:
                self.log(f"  Moxfield search failed: {e}")
                break
            rows = (data or {}).get("data") or []
            for r in rows:
                pid = r.get("publicId")
                if not pid or (r.get("format") or "commander").lower() != "commander":
                    continue
                ci = r.get("colorIdentity")
                found.append(Candidate("moxfield", pid, r.get("name", ""), int(r.get("viewCount") or 0),
                                       frozenset(ci) if isinstance(ci, list) else None, _bracket(r)))
            if not rows or page >= int((data or {}).get("totalPages") or 1):
                break
        return found

    def fetch(self, public_id):
        path = os.path.join(self.cache_dir, f"{public_id}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            if not self.enabled:
                raise RuntimeError("Moxfield decks need a Moxfield User-Agent in Settings.")
            data = self._get(f"{API}/v3/decks/all/{public_id}")
            if not data:
                return None
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)

        def board(name):
            b = (data.get("boards") or {}).get(name) or {}
            cards = b.get("cards") if isinstance(b, dict) and "cards" in b else (data.get(name) or {})
            out = {}
            for entry in (cards or {}).values():
                n = (entry.get("card") or {}).get("name")
                if n:
                    out[n] = out.get(n, 0) + int(entry.get("quantity", 1))
            return out

        commanders = list(board("commanders"))
        main = board("mainboard")
        return Deck(name=data.get("name") or f"Moxfield {public_id}", commanders=commanders,
                    cards=[(q, n) for n, q in main.items()],
                    url=f"https://moxfield.com/decks/{public_id}", bracket=_bracket(data),
                    source="Moxfield", views=int(data.get("viewCount") or 0))
